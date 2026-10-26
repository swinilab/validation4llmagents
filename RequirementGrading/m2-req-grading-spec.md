# M2 — Requirements Grading: Implementation Spec

**Version:** 1.0
**Date:** 2026-10-24
**Scope:** Implementation of Requirement Recall and Requirement Precision only.
Models Grading (structural / behavioral) and the two VMX metrics are out of scope.

This document specifies a resumable Python pipeline. It is the authoritative
reference for the implementation; where it disagrees with prose in
`M2-grading.md`, this document wins on mechanics and `M2-grading.md` wins on
rationale.

---

## 1. Overview

The pipeline compares a submission's `requirements.json` against the frozen gold
`G1-requirements.json` and produces two metrics plus diagnostics.

Two stages require human judgement: adjudicating polarity cases the rule layer
cannot decide, and the rubric for generated items that match no gold item. The
pipeline **never blocks on input**. A stage that needs human input writes a
review file, returns `NEEDS_REVIEW`, and the runner exits. A human fills the
file; the next run picks the answers up and continues.

### Core invariants

1. **Submissions are immutable.** Each generation run is frozen under its own
   `run_id` directory and never edited. Human answers are keyed by `run_id` plus
   unit ids; no content hashing is used.
2. **`GradingRequirements/run/` is a disposable cache.** Deleting it and re-running must reproduce
   identical results, given the same `GradingRequirements/review/` answers.
3. **`GradingRequirements/review/` is human-authored and version-controlled.** The pipeline reads it
   and appends new empty question rows. It must never overwrite a filled cell.
4. **Human adjudication happens once, at the lowest threshold in the sweep.**
   Candidate sets are nested, so higher thresholds reuse the same answers.

---

## 2. Inputs

| Input | Path | Notes |
|---|---|---|
| Gold listing | `gold/G1-requirements.json` | Frozen. Yields exactly 70 units. |
| Submission | `submissions/<run_id>/requirements.json` | Frozen once written. |
| Run parameters | `config.yaml` | Project-level. Thresholds and run policy. See §8.2. |
| Rule-layer vocabularies | `GradingRequirements/rules.yaml` | Local to this section. See §8.3. |

`<run_id>` is a free-form slug naming one generation run, e.g. `gpt5-run01`. The
same model generated twice produces two run ids.

---

## 3. Directory layout

Project-level, shared with the other grading sections:

```
config.yaml                       # thresholds and run policy (§8.2)

gold/
  G1-requirements.json

submissions/
  <run_id>/
    requirements.json
```

Everything belonging to this section lives under one folder:

```
GradingRequirements/
  rules.yaml                      # rule-layer vocabularies (§8.3)
  run.py                          # runner (§10)
  stages/                         # S0..S6 implementations

  run/                            # disposable cache
    <run_id>/
      00_units.json
      01_sim.npy
      01_sim_index.json
      02_candidates.json          # built at review_threshold (lowest in sweep)
      03_axis.json
      04_dedup.json
      05_metrics.json             # all thresholds, one row each
      manifest.json

  review/                         # human-authored, version-controlled
    <run_id>/
      polarity_ledger.csv
      rubric_llm.csv
      rubric_human.csv
      kappa_rounds.json
```

`GradingRequirements/run/` may be deleted at any time.
`GradingRequirements/review/` must not.

---

## 4. Unit extraction (Stage S0)

### 4.1 Algorithm

For each element of the `requirements` array, in file order:

- If `type == "functional"`: emit one unit per element of `acceptance_criteria`,
  in array order.
- Otherwise: emit exactly one unit from `statement`.

### 4.2 Unit record

```json
{
  "unit_id": "US-03-AC02",
  "parent_id": "US-03",
  "kind": "ac",
  "text_raw": "Each order item records a quantity, a unit price and exactly one product, and belongs to exactly one order.",
  "text_norm": "Each order item records a quantity, a unit price and exactly one product, and belongs to exactly one order"
}
```

- `unit_id` — the AC `id` for `kind == "ac"`, the requirement `id` for
  `kind == "nfr"`.
- `kind` — `"ac"` when the parent `type` is `functional`, otherwise `"nfr"`.
- `text_raw` — verbatim from the JSON. **Used by the rule layer.** Case is
  preserved; role names are case-sensitive.
- `text_norm` — used for embedding only. Derived from `text_raw` by, in order:
  1. remove Markdown emphasis characters `*`, `_`, `` ` ``;
  2. replace all runs of whitespace with a single space;
  3. trim leading and trailing whitespace;
  4. remove a single trailing `.` if present.

Never lowercase either field.

### 4.3 Format violations

Recorded, not fatal. Extraction continues best-effort. Each violation is
`{"unit_id" | "req_id", "code", "detail"}`:

| Code | Condition |
|---|---|
| `json_parse_error` | file is not valid JSON (fatal — abort with `FAILED`) |
| `id_pattern` | id does not match `^US-\d{2}$`, `^NFR-\d{2}$` or `^US-\d{2}-AC\d{2}$` |
| `id_duplicate` | id appears more than once |
| `ac_below_minimum` | `type == "functional"` and fewer than 3 criteria |
| `ac_on_nfr` | `type != "functional"` and `acceptance_criteria` is non-empty |
| `empty_text` | `text` or `statement` is empty after normalization |
| `newline_in_field` | a field contains a newline |
| `ac_prefix_mismatch` | AC id prefix differs from its parent requirement id |
| `missing_member` | a required member is absent |
| `unknown_member` | a member not in the schema is present |

Gold must produce zero violations; if it does not, abort with `FAILED`.

### 4.4 Output

`GradingRequirements/run/<run_id>/00_units.json`:

```json
{
  "run_id": "gpt5-run01",
  "gold": [ /* 70 unit records */ ],
  "gen":  [ /* M unit records */ ],
  "violations": [ /* as above */ ]
}
```

Assert `len(gold) == 70`; abort with `FAILED` otherwise.

---

## 5. Similarity matrix (Stage S1)

```python
from sentence_transformers import SentenceTransformer, util

model = SentenceTransformer("all-mpnet-base-v2")
emb_gold = model.encode([u["text_norm"] for u in gold], normalize_embeddings=True)
emb_gen  = model.encode([u["text_norm"] for u in gen],  normalize_embeddings=True)
sim = util.cos_sim(emb_gold, emb_gen).numpy()          # shape (70, M)
```

Also compute the intra-generation matrix for dedup:

```python
sim_gg = util.cos_sim(emb_gen, emb_gen).numpy()        # shape (M, M)
```

**Output:** `01_sim.npy` holding both arrays, and `01_sim_index.json` mapping row
and column positions to `unit_id` so the matrix can be read without recomputing
embeddings.

Encoding happens exactly once per `run_id`, never per threshold.

---

## 6. Candidate generation (Stage S2)

Let `review_threshold = min(config.sweep)` — `0.70` by default.

```
candidates = [ (g, s, sim[g][s])
               for g in gold, s in gen
               if sim[g][s] >= review_threshold
               and (config.allow_cross_kind or g.kind == s.kind) ]
```

**No truncation.** Every pair above the threshold is a candidate. Ranking and
cutting to a fixed number of nearest candidates would introduce an arbitrary
constant that suppresses legitimate evidence: Recall is a coverage question, and
any pair above the declared threshold is admissible evidence of coverage. The
cost is bounded — at most `70 × M` pairs, and the rule layer is regex matching —
so there is no performance argument for a cutoff either.

Candidate pairs are emitted in a deterministic order: `gold_id` ascending, then
cosine descending, then `gen_id` ascending.

**Cross-kind pairs.** By default (`allow_cross_kind: false`) a gold `ac` may only
be covered by a generated `ac`, and a gold `nfr` only by a generated `nfr`. Pairs
excluded by this rule are still recorded in `02_candidates.json` with
`"excluded": "cross_kind"` so the diagnostic in §11 can report how many gold
units would have been covered had the rule been relaxed. They take no part in
grading.

Building candidates at the lowest threshold once is what makes human
adjudication reusable: the candidate set at any higher threshold is a subset.

**Output:** `02_candidates.json`:

```json
[
  {"gold_id": "US-06-AC01", "gen_id": "US-05-AC02", "cosine": 0.8431, "excluded": null}
]
```

---

## 7. Rule layer — three axes (Stage S3)

Runs once, over every non-excluded candidate pair, using `text_raw`.

### 7.1 Applicability

An axis is evaluated for a pair **only if the gold unit yields a non-empty
feature set for that axis**. Otherwise the axis is vacuously satisfied. Applying
axes unconditionally would fail nearly every pair.

Axis 3 additionally applies only when `gold.kind == "nfr"`.

### 7.2 Axis 1 — Polarity

Classify each text into `reject`, `accept`, or `none`.

**Reject patterns are tested first**, because accept patterns are substrings of
some reject phrases (`registers no order` contains `registers`).

Reject (case-insensitive, regex):

```
\brejects?\b
\bleaves\b[^.]*\bunchanged\b
\bremains? unchanged\b
\bregisters no\b
\bdoes not\b
\bcannot\b
\bis not (allowed|permitted|accepted)\b
```

Accept (case-insensitive, regex):

```
\bsets\b[^.]*\bto\b
\brecords?\b
\bstores?\b
\baccepts?\b
\bregisters\b
\bis set to\b
```

Classification: if any reject pattern matches → `reject`; else if any accept
pattern matches → `accept`; else `none`.

Comparison:

| gold | gen | outcome |
|---|---|---|
| `reject` or `accept` | same class | pass |
| `reject` or `accept` | opposite class | `FAIL(polarity)` |
| `reject` or `accept` | `none` | `MANUAL` |
| `none` | anything | axis not applicable |

`MANUAL` is the only route to human adjudication. It arises when the agent used
wording outside the keyword sets, e.g. "no state change occurs".

### 7.3 Axis 2 — Identifiers and direction

Pure rule-based, deterministic. Three independent sub-checks; any mismatch yields
`FAIL(identifier)` with the sub-check named.

**2a. Transition direction.** Extract ordered pairs with

```
from\s+(STATUS)\s+to\s+(STATUS)
```

where `STATUS` is the union of the status whitelists below, case-insensitive.
Collect as an ordered-pair set. Gold `US-06-AC04` yields five pairs:
`(submitted, pending)`, `(pending, filled)`, `(pending, closed)`,
`(filled, shipped)`, `(shipped, closed)`.

The gen set must equal the gold set. `(pending, filled)` and `(filled, pending)`
are different elements.

**2b. Identifier tokens.** Scan `text_raw` with word boundaries and collect every
hit into **one flat set**, without categorising:

| Source | Members | Case |
|---|---|---|
| Statuses | `submitted`, `pending`, `filled`, `shipped`, `closed`, `issued`, `paid`, `completed`, `failed` | insensitive |
| Payment methods | `bank`, `card`, `cash` | insensitive |
| Entity nouns | `order`, `invoice`, `payment` | insensitive |
| Roles | `Customer`, `OrderStaff`, `Accountant` | **sensitive** |

The gen set must equal the gold set.

Including the entity nouns in the same set is what makes categorisation
unnecessary. `pending` belongs to both order status and payment status, but a
criterion about a pending order and one about a pending payment differ in their
entity noun, so a flat comparison already separates them.

Note the deliberate trap in the domain: an invoice becomes `paid`, a payment
becomes `completed`. A generated criterion saying a payment becomes `paid`
produces a different token set and fails.

**2c. Cardinality direction.** Extract occurrences of, case-insensitive:

```
at most one | at least one | exactly one | any number of | no more than one | zero or one
```

Normalize `no more than one` → `at most one`, `zero or one` → `at most one`. The
gen multiset must equal the gold multiset.

### 7.4 Axis 3 — Numeric values and thresholds

Applies only when `gold.kind == "nfr"`.

Extract every `(value, unit)` pair and every inequality direction marker.

Number regex: `(\d+(?:\.\d+)?)\s*(%|seconds?|s\b|minutes?|months?|users?|submissions?|items?)`
plus the special literal `TLS 1.2`.

Direction markers: `at least`, `at most`, `within`, `up to`, `no more than`,
`no fewer than`, `exceeds`.

Gen must reproduce every gold `(value, unit)` pair exactly and the same direction
marker for each. Expected values:

| NFR | Required values |
|---|---|
| NFR-01 | 50 items, 2 seconds, 95% |
| NFR-02 | 200 users, 20 submissions, (per second) |
| NFR-03 | 100% |
| NFR-05 | TLS 1.2 |
| NFR-06 | 12 months |
| NFR-07 | 99.5%, 24 hours |
| NFR-08 | 15 minutes |

NFR-04 carries no numeric threshold; axis 3 is not applicable to it.

### 7.5 Verdict and ledger

Per pair, the verdict is:

- `PASS` — every applicable axis matched.
- `FAIL` — at least one applicable axis mismatched. Record `failed_axis` and a
  human-readable `detail`.
- `MANUAL` — no axis failed, but axis 1 returned `MANUAL`.

For every `MANUAL` pair, look up `GradingRequirements/review/<run_id>/polarity_ledger.csv` by
`(gold_id, gen_id)`. If a non-empty `verdict` exists there, substitute it.
Otherwise append a question row with an empty `verdict` and count the pair as
pending.

**Ledger schema** (`polarity_ledger.csv`):

```
gold_id,gen_id,cosine,gold_text,gen_text,verdict,reviewer,timestamp,note
```

The reviewer fills `verdict` with `PASS` or `FAIL`, plus `reviewer` and
`timestamp`. The pipeline writes every other column and must never modify a row
whose `verdict` is non-empty.

**Output:** `03_axis.json`:

```json
[
  {"gold_id":"US-06-AC01","gen_id":"US-06-AC02","verdict":"FAIL",
   "failed_axis":"polarity","detail":"gold=accept gen=reject","source":"rule"},
  {"gold_id":"US-09-AC03","gen_id":"US-08-AC04","verdict":"PASS",
   "failed_axis":null,"detail":null,"source":"ledger"}
]
```

`source` is one of `rule`, `ledger`, `default`.

**Stage result:** `NEEDS_REVIEW` if any pending rows were appended, unless
`--on-pending provisional`, in which case pending pairs take
`config.manual_default` (`not_covered`, i.e. treated as `FAIL`) with
`"source": "default"` and the stage returns `DONE`.

---

## 8. Configuration

### 8.1 Two files, one dividing line

**No magic numbers.** Every threshold, cutoff and vocabulary that can affect a
reported number is read from a file. No numeric literal and no domain term list
that influences a result may appear in source code. The paper has to declare
these values, the sensitivity analysis has to vary them without editing code, and
a reviewer has to be able to see the whole tuning surface without reading the
implementation.

They are split across two files by a single rule:

| File | Holds | Scope |
|---|---|---|
| `config.yaml` | numeric parameters and run policy — thresholds, sweep, sample sizes, seeds, model pins, agreement cutoffs | Project-level, shared with the other grading sections |
| `GradingRequirements/rules.yaml` | the rule layer's closed vocabularies and patterns — status sets, roles, cardinality phrases, polarity regexes, numeric units, text normalization | Local to this section only |

The dividing line: `config.yaml` holds what a sensitivity analysis varies;
`rules.yaml` holds the operational definition of the rule layer, which is
specific to this domain and to the acceptance-criteria grammar, and means nothing
to the other sections.

Permitted literals in code: structural constants with no effect on results, such
as the expected gold unit count `70` used in an assertion, array indices and
formatting widths.

Both loaders must fail loudly on a missing key and on an unknown key. No silent
defaults inside the code — defaults live in the YAML and nowhere else.

### 8.2 `config.yaml` (project root)

```yaml
# --- embedding ---
embedding_model: sentence-transformers/all-mpnet-base-v2
embedding_revision: null          # pin before the real run; copied into manifest
pooling: mean
normalize_embeddings: true

# --- thresholds ---
threshold: 0.75                   # primary, reported in the paper body
sweep: [0.70, 0.75, 0.80, 0.85]   # sensitivity analysis; min() is review_threshold
dedup_threshold: 0.90             # intra-generation clustering

# --- matching policy ---
allow_cross_kind: false           # may a gold `ac` be covered by a generated `nfr`
manual_default: not_covered       # substitution used in provisional mode

# --- rubric and agreement ---
judge_model: null                 # pinned snapshot, e.g. gpt-4o-2024-08-06
judge_temperature: 0
kappa_sample_size: 30
kappa_accept: 0.60
random_seed: 20261024
```

### 8.3 `GradingRequirements/rules.yaml`

Consumed only by Stage S3 (§7) and by the normalization step of S0 (§4.2).

```yaml
# --- closed vocabularies (§7.3) ---
status_sets:
  order:   [submitted, pending, filled, shipped, closed]
  invoice: [issued, paid]
  payment: [pending, completed, failed]
payment_methods: [bank, card, cash]
roles: [Customer, OrderStaff, Accountant]
roles_case_sensitive: true

cardinality_phrases:
  canonical: [at most one, at least one, exactly one, any number of]
  aliases:
    no more than one: at most one
    zero or one: at most one
    no fewer than one: at least one

# --- polarity (§7.2); reject is tested first ---
polarity:
  reject:
    - '\brejects?\b'
    - '\bleaves\b[^.]*\bunchanged\b'
    - '\bremains? unchanged\b'
    - '\bregisters no\b'
    - '\bdoes not\b'
    - '\bcannot\b'
    - '\bis not (allowed|permitted|accepted)\b'
  accept:
    - '\bsets\b[^.]*\bto\b'
    - '\brecords?\b'
    - '\bstores?\b'
    - '\baccepts?\b'
    - '\bregisters\b'
    - '\bis set to\b'

# --- numeric extraction (§7.4) ---
numeric:
  units: ['%', seconds, s, minutes, months, users, submissions, items]
  direction_markers: [at least, at most, within, up to, no more than, no fewer than, exceeds]
  literals: ['TLS 1.2']

# --- transition extraction (§7.3, sub-check 2a) ---
transition_pattern: 'from\s+(STATUS)\s+to\s+(STATUS)'
entity_nouns: [order, invoice, payment]

# --- text normalization (§4.2) ---
normalization:
  strip_markdown_chars: ['*', '_', '`']
  collapse_whitespace: true
  strip_trailing_period: true
  lowercase: false                # must stay false; roles are case-sensitive
```

`lowercase` is listed so the choice is explicit and auditable, but setting it to
`true` breaks the role sub-check in §7.3. The loader must reject `true`.

### 8.4 Reporting

Values from **both** files used in a run are copied verbatim into
`manifest.json`, under separate keys `config` and `rules`, so a run is
reconstructible from the manifest alone.

The paper body declares, at minimum: `embedding_model` with
`embedding_revision`, `pooling`, `normalize_embeddings`, `threshold` with the
full `sweep` and its result table, `dedup_threshold`, `allow_cross_kind`,
`judge_model` with `judge_temperature`, `kappa_sample_size` and the resulting κ,
and `random_seed`.

`rules.yaml` goes in the appendix in full. It is the operational definition of
the rule layer, and the layer is not reproducible without it.

---

## 9. Coverage, dedup and metrics (Stages S4–S6)

### 9.1 S4 — Dedup of generated units (once per run)

Cluster generated units using `sim_gg >= config.dedup_threshold` (single-linkage
over the thresholded graph).

Representative selection within a cluster:

1. the highest cosine to any gold unit;
2. ties broken by `unit_id` ascending.

Non-representatives are marked `redundant` and excluded from `S`.

This stage does not depend on the matching threshold. Clustering uses `sim_gg`
alone, so the number of clusters — and therefore `|S|` — is the same at every
threshold in the sweep. Run it once.

**Output** `04_dedup.json`: `{"kept": [gen_id...], "redundant": [{"gen_id","cluster_rep"}]}`.

### 9.2 Per-threshold evaluation

Only coverage and the metrics depend on the threshold. For each `t` in
`config.sweep`, filter `03_axis.json` to pairs with `cosine >= t` and evaluate.
No re-encoding, no re-clustering, no further human questions.

For each gold unit `g`, over its pairs with `cosine >= t`:

- any `PASS` → `covered`
- else → `not_covered`

Many-to-one is legal: several generated units covering one gold unit count once.

### 9.3 S5 — Rubric for unmatched generated units

Unmatched set: units in `S` with no `PASS` pair at the primary threshold
(`config.threshold`). The rubric is judged once, at that threshold.

Each is judged on the two correctness conditions:

1. **Traceable** — attributable to a real domain requirement or a real part of the
   domain description, not an invented capability.
2. **Consistent** — not contradicting any gold acceptance criterion.

Atomicity is **not** a condition and must not be tested.

**LLM judge.** Fixed prompt, `temperature = 0`, pinned snapshot in
`config.judge_model`, full output logged to `GradingRequirements/review/<run_id>/rubric_llm.csv`:

```
gen_id,gen_text,traceable,consistent,rationale,judge_model,timestamp
```

**Human sample for κ.** Draw `config.kappa_sample_size` units from the unmatched
set with `config.random_seed`, excluding every `gen_id` listed in previous rounds
of `GradingRequirements/review/<run_id>/kappa_rounds.json`. Write `GradingRequirements/review/<run_id>/rubric_human.csv`
with **only** these columns:

```
gen_id,gen_text,traceable,consistent,reviewer,timestamp
```

The LLM's labels must not appear in this file. Blindness is enforced by the
schema, not by instruction.

A separate step joins the two files on `gen_id` and computes Cohen's κ over the
combined binary label (`traceable AND consistent`):

```
κ = (p_o − p_e) / (1 − p_e)
```

Append the round to `kappa_rounds.json` as
`{"round", "seed", "gen_ids", "kappa", "n"}`.

**Stage result:** `NEEDS_REVIEW` while `rubric_human.csv` has empty rows, unless
in provisional mode, where unmatched units are all treated as failing the rubric.

### 9.4 S6 — Metrics

Computed for every `t` in `config.sweep`:

```
matched_gold  = |{g : covered at t}|
matched_gen   = |{s in S : s has >= 1 PASS pair at t}|
rubric_pass   = |{s in S : unmatched and passes both conditions}|

Recall    = matched_gold / 70
Precision = (matched_gen + rubric_pass) / |S|
F1        = 2 * Precision * Recall / (Precision + Recall)      # 0 if P+R == 0
```

**The two numerators are different quantities.** `matched_gold` counts gold units;
`matched_gen` counts generated units. They diverge whenever many-to-one or
one-to-many matching occurs. Using one in place of the other is the most likely
implementation error; assert that both are computed from their own side.

**Output** `05_metrics.json` — one file per run, one row per threshold:

```json
{
  "run_id": "gpt5-run01",
  "primary_threshold": 0.75,
  "status": "final",
  "s_size": 47,
  "gold_total": 70,
  "rubric_pass": 0,
  "pending_polarity": 0,
  "pending_rubric": 0,
  "manual_default": null,
  "sweep": [
    {"threshold": 0.70, "recall": 0.7571, "precision": 0.7872, "f1": 0.7719,
     "matched_gold": 53, "matched_gen": 37},
    {"threshold": 0.75, "recall": 0.7143, "precision": 0.8085, "f1": 0.7584,
     "matched_gold": 50, "matched_gen": 38}
  ]
}
```

`s_size` sits outside `sweep` because dedup is threshold-independent (§9.1).

`status` is `"final"` when nothing is pending, `"provisional"` otherwise. In
provisional mode `manual_default` names the substitution used. Provisional
numbers are a lower bound on Recall, because the default is `not_covered`.

---

## 10. Runner, exit codes, CLI

```
python run.py --run-id gpt5-run01 [--on-pending halt|provisional] [--stage all|S0..S6] [--force]
```

Stage results and process exit codes:

| Result | Exit | Meaning |
|---|---|---|
| `DONE` | 0 | all stages complete, metrics final |
| `NEEDS_REVIEW` | 2 | a review file awaits human input; path printed to stdout |
| `FAILED` | 1 | unrecoverable error (gold invalid, submission unparseable) |

Each stage skips itself when its output file already exists, unless `--force`.
On `NEEDS_REVIEW` the runner prints the absolute path of the file to fill and the
number of empty rows, then stops without running later stages.

`manifest.json`, written on every run:

```json
{
  "run_id": "gpt5-run01",
  "submission_path": "submissions/gpt5-run01/requirements.json",
  "gold_path": "gold/G1-requirements.json",
  "embedding_model": "sentence-transformers/all-mpnet-base-v2",
  "embedding_revision": "...",
  "sentence_transformers_version": "...",
  "pooling": "mean",
  "normalized": true,
  "config": { /* verbatim copy of config.yaml */ },
  "rules": { /* verbatim copy of GradingRequirements/rules.yaml */ },
  "review_commit": "git rev-parse HEAD of GradingRequirements/review/",
  "started_at": "...",
  "finished_at": "..."
}
```

---

## 11. Diagnostics

Written to `GradingRequirements/run/<run_id>/05_metrics.json` under `"diagnostics"`, at the primary threshold:

| Field | Meaning |
|---|---|
| `cross_us_matches` | PASS pairs whose `gen.parent_id` differs from `gold.parent_id` — right content, wrong organisation |
| `cross_kind_would_cover` | gold units that would become covered if `allow_cross_kind` were true |
| `axis_rejections` | count of pairs above threshold rejected by the rule layer, split by `polarity` / `identifier` / `numeric` |
| `dedup_removed` | number of generated units marked redundant |
| `manual_resolved` | MANUAL pairs resolved from the ledger, and how many of each verdict |
| `ac_per_story` | distribution of criteria per generated story; gold reference is 15 stories, 62 criteria, mean 4.1 |
| `ac_length` | token-length distribution of generated criteria vs gold |
| `format_violations` | counts by code from S0 |

`axis_rejections` is a reported result in its own right: it is the empirical
justification for having a rule layer at all.

---

## 12. Edge cases

| Case | Required behaviour |
|---|---|
| `M == 0` (no generated units) | Recall 0, Precision 0, F1 0, `status: final`; no review files |
| Gold yields ≠ 70 units | abort `FAILED` |
| Submission is not valid JSON | abort `FAILED`, record `json_parse_error` |
| Duplicate `unit_id` in submission | keep first occurrence, record `id_duplicate`, continue |
| Generated unit with empty text | excluded from `gen`, recorded as `empty_text` |
| Gold unit with no candidate at all | `not_covered`, no review row |
| All candidates of a gold unit are `MANUAL` | pending in halt mode; `not_covered` in provisional mode |
| Ledger row whose `(gold_id, gen_id)` is no longer a candidate | ignored, kept in file, reported as `stale_ledger_rows` |
| Ledger `verdict` outside `{PASS, FAIL}` | abort `FAILED` naming the row |
| `Precision + Recall == 0` | F1 defined as 0 |
| Cluster in S4 where no member matches any gold unit | representative is the highest cosine to any gold unit, ties by `unit_id` |

---

## 13. Acceptance tests

The implementation must pass all of these before any real run.

1. **Identity.** Grading gold against itself gives `Recall == 1.0`,
   `Precision == 1.0`, `matched_gold == 70`, zero pending, zero axis rejections.
2. **Axis sensitivity.** One table-driven test. Start from gold, apply each
   mutation below in isolation, and assert the named unit becomes `not_covered`
   with the named rejection counter incremented:

   | Mutation | Unit | Counter |
   |---|---|---|
   | swap `rejects` → `sets ... to` in `US-06-AC02` | US-06-AC02 | `polarity` |
   | reverse `pending → filled` in `US-06-AC04` | US-06-AC04 | `identifier` |
   | change a payment's `completed` to `paid` | affected unit | `identifier` |
   | change NFR-01 to 3 seconds | NFR-01 | `numeric` |

3. **Duplication.** Append a verbatim copy of three criteria under new ids.
   `dedup_removed == 3`, and Recall must be unchanged from the identity run.
4. **Splitting.** Replace `US-01-AC01` with three single-attribute criteria.
   `US-01-AC01` must remain `covered` (many-to-one), and `|S|` must grow by 2.
5. **Nesting.** Candidate set at 0.70 must be a superset of the set at 0.85, and
   running the full sweep must append zero new rows to `polarity_ledger.csv`
   after the first pass at 0.70.
6. **Dedup is threshold-independent.** `|S|` and the kept set must be identical
   at every threshold in the sweep.
7. **Resumability.** Delete `GradingRequirements/run/` entirely, re-run with the
   same `GradingRequirements/review/`; every metric must be bit-identical.
8. **Ledger immutability.** Re-running must not alter any row with a non-empty
   `verdict`; assert by comparing the file before and after.

Config completeness is a CI lint, not an acceptance test: grep the source for
numeric literals and for members of the closed vocabularies, permitting only the
structural constants named in §8.1, and assert that loading a YAML with a key
removed aborts rather than falling back to a default.

---

## 14. Settled policy decisions

These three choices affect the published numbers. They are fixed here with their
justification, remain configurable for sensitivity analysis, and must be declared
in the paper.

### `allow_cross_kind: false`

A gold acceptance criterion may only be covered by a generated acceptance
criterion, and a gold NFR statement only by a generated NFR statement.

Justification: §4 defines the two unit kinds differently and for a reason — an
acceptance criterion is a checkable assertion subordinate to a user story, an NFR
statement is a standalone quantified requirement placed in a specific clause.
Letting one cover the other would make the denominator of 70 a mixture of units
whose identity conditions differ, and would credit a submission that put a
quality attribute in the wrong clause as though it had placed it correctly —
while the specification being graded explicitly requires the separation.

Nothing is hidden by this: `cross_kind_would_cover` reports exactly how many gold
units would become covered under the permissive rule, so the sensitivity of the
result to this choice is visible without changing the headline number.

### No candidate truncation

Earlier drafts capped each gold unit at its five nearest candidates. That cap is
removed. An arbitrary constant that discards admissible evidence is difficult to
justify to a reviewer and has no principled value: "why five" has no answer that
is not post hoc. Recall is a coverage problem, so every pair above the declared
threshold participates.

Human workload is not expected to be a problem: a `MANUAL` verdict requires the
generated text to match none of the thirteen polarity patterns, which well-formed
criteria rarely do. Measure the actual `MANUAL` count on a real submission before
adding any pruning mechanism.

### `manual_default: not_covered`

In provisional mode, a polarity case not yet adjudicated is treated as a failure.

Justification: this makes provisional Recall a **lower bound** on final Recall, so
a number seen mid-development can never overstate the result. The alternative —
defaulting to covered — would produce optimistic figures that drift downward as
review proceeds, which is the wrong direction for a number that may be quoted
before the review finishes. The gap between provisional and final is itself
reported, and is the measure of how much the human adjudication mattered.
