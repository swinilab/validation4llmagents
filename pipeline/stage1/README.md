# Stage 1

Stage 1 holds two modules:

| Module | Purpose | Metric |
| --- | --- | --- |
| [`normalize`](normalize.py) | text normalization for the matching cascade | — |
| [`parse_check`](parse_check.py) | diagram validity | 7 |

Both are deterministic, read their inputs read-only, and write a `.meta.json`
provenance sidecar beside every output. Neither depends on an ontology or
knows whether its input is gold or agent output: `run_id` is an opaque label.

For copy-pasteable commands, see [COMMAND.md](COMMAND.md).

---

# normalize — text normalization

normalize prepares a raw string as one canonical form for downstream matching.

**normalize never decides whether two items match.** It does no Stage 2/Stage 3
work: no actor stripping, no alias lookup, no frame extraction, no synonym
mapping, no embeddings. It is deterministic and offline — one spaCy pipeline,
no network, no randomness — and never modifies an input file.

---

## Output columns

For each normalized column `X`, Stage 1 adds:

| Column | Meaning |
|---|---|
| `X__normalized` | the canonical token sequence, single-space separated |
| `X__has_negation_cue` | a negation cue appears **anywhere** in the string |
| `X__main_predicate_negated` | the negation applies to the **main predicate** |
| `X__negation_scope` | `main`, `subordinate` or `none` — what the parser decided |
| `X__negation_cues` | the surface cues that matched, in sentence order |

Plus one `stage1_version` column per row.

> **Breaking change in 1.1.0:** the single `X__negated` column is gone. It
> conflated "a negation is present" with "the requirement is negative". Use
> `X__has_negation_cue` for the former (it has exactly the old semantics) and
> `X__main_predicate_negated` for the latter.

---

## Pipeline order

The order is part of the contract:

1. negation **cue detection**, on the raw sentence, before any token is removed
2. lowercase
3. identifier splitting (camelCase / PascalCase / snake_case)
4. modal removal, possessive-marker removal
5. article / determiner removal, auxiliary removal
6. verb lemmatization (participial modifiers keep their surface form)
7. negation **scope resolution**, on the dependency parse

---

## Negation

### Cues are never removed

Since 1.1.0 a negation cue always survives into `normalized`. Stage 1 never deletes
`not`, `n't` (written out as `not`), determiner `no`, `never`, `cannot`, `nor`,
`none` or `without`.

v1.0.0 deleted the pure particles, on the theory that a negated sentence and
its affirmative twin should share one token sequence and differ only in a flag.
That was wrong for two reasons. It made `shall not store X` and `shall store X`
*identical* strings, so Stage 3's cosine similarity could not tell them apart at
all; and it was inconsistent, because `without` and `no more than` were kept
while `not` and `no` were not.

### Numeric bounds are not negations

`no more than`, `not more than`, `no less than`, `no later than`, `at least`,
`at most` and the rest of `non_negating_phrases` (in `config.yaml`) state a
bound. Their words stay in `normalized`, and they do **not** count as a
negation cue: `error rate of no more than 0.1%` yields
`has_negation_cue = false`.

The phrases are masked twice — once on the raw surface before cue detection,
once in token space before scope resolution — so a bound can never reach either
decision.

### Scope: `main_predicate_negated`

`main_predicate_negated` is `true` only when, in the dependency parse, **one**
of these holds:

1. a `neg` dependent — `not`, `n't`, `never`, or the `not` half of `cannot` —
   attaches to the **root verb**, or to an auxiliary/modal of the root verb:
   *shall **not** store*, *must **never** expose*; or
2. the determiner `no` modifies a **direct object of the root verb**:
   *shall store **no** unencrypted primary account numbers*.

It is `false` when the cue sits in a subordinate, relative, conditional,
participial or prepositional structure. On the gold set that is five of the six
cue-bearing rows:

| Row | Cue sits in | Scope |
|---|---|---|
| GR-30 | `shall **not** store …` — root verb | `main` |
| GR-15 | `only while it … has **not** been marked` — condition | `subordinate` |
| GR-31 | `modifiable by **no** role` — prepositional adjunct | `subordinate` |
| GR-36 | `leaving **no** order in …` — participial adjunct | `subordinate` |
| GR-37 | `**without** modification to …` — prepositional adjunct | `subordinate` |
| GR-39 | `an order that is **not** in the placed state` — relative clause | `subordinate` |

A coordinated main verb is still the main clause (*shall reject X **and
inform** Y*), but a `conj` link is trusted only when the conjunct carries the
root's own verb form. See the failure modes below for why.

`negation_scope` reports `main`, `subordinate` or `none` so a reviewer can see
what the parser decided without re-running it.

### Known failure modes — negation

- **The rule is heuristic and only as good as `en_core_web_sm`'s parse.** In
  GR-15, "…in the placed state **and has not been marked** as picked", spaCy
  attaches `marked` as a conjunct of the *root* (`allow`) rather than of the
  `while` clause's `is`. Read literally, rule 1 would then call this `main`.
  Stage 1 rejects the link because `marked` (VBN, with its own auxiliaries) does not
  share the root's verb form (VB). This works here and on the rest of the gold
  set, but it is a syntactic proxy for a semantic question: a genuinely
  coordinated main verb in a *different* form would be missed.
- **Lexical negation is not detected.** `prevent`, `deny`, `reject`, `refuse`,
  `fail to`, `exclude` and similar verbs negate their complement without any
  cue word. GR-39 and GR-41 ("shall **reject** a cancellation request") are
  affirmative requirements to reject something, and Stage 1 reports them as such —
  which is correct for Stage 1's purpose, but a consumer must not read
  `main_predicate_negated = false` as "this requirement is positive in
  meaning".
- **`nor`, `none` and `without` never set `main`.** They introduce a
  coordination, a noun or an adjunct rather than negating a predicate directly.
  A sentence whose main predicate is genuinely negated by one of them would be
  reported `subordinate`.
- **Double negation is not resolved.** Two cues in one sentence produce two
  entries in `negation_cues`; Stage 1 does not cancel them out.

---

## Ontology-independent normalization

Normalization does not identify states or resolve terms against an ontology.
Words such as `placed` and `shipped` are processed like any other word; they
may be lemmatized according to the normal verb rules.

---

## Other normalization rules

### Possessives

The possessive marker is dropped and the noun kept: *a Customer's delivery
address* → `customer delivery address`. Both the straight `'s` and the curly
`’s` are handled. v1.0.0 left a stray `s` token behind.

A genuine contraction (*it's*) is not affected — spaCy tags that `AUX`, while
the possessive is tagged `POS`.

### Participial adjectives keep their surface form

A token is lemmatized only when its POS is `VERB`/`AUX` **and** its dependency
is not `amod`. A participial modifier is an adjective in everything but
spaCy's coarse tag, and lemmatizing it destroys the phrase:

| v1.0.0 | 1.1.0 |
|---|---|
| `act role` | `acting role` |
| `result state` | `resulting state` |
| `process revenue` | `processed revenue` |
| `schedule maintenance` | `scheduled maintenance` |
| `desire quantity` | `desired quantity` |

A main verb is still lemmatized: *retrieves* → `retrieve`.

### Auxiliaries are dropped

Tokens whose dependency is `aux` or `auxpass` are removed, so *have been
marked* → `marked`/`mark` (by the lemma rule for the main verb). A **root
copula** is kept, because it carries the predication: *is out of stock* keeps
`be`.

### Modals, articles, identifiers

Modals (`shall`, `must`, `should`, `will`, `can`, `may`) and articles (`a`,
`an`, `the`) are removed, so the same requirement normalizes identically
whether the author wrote *shall* or *can*. `normalize_label` never drops the
first meaningful token, so a class named `Can` survives.

Identifiers are split on camelCase / PascalCase / snake_case boundaries:
`OrderLine` → `order line`. Numbers and units stay whole: `aes-256`, `30-day`,
`0.1%`, `2,000`.

---

---

# parse_check — metric 7 (Diagram Validity)

Checks each PlantUML diagram in a run and scores the run as
`diagram_validity = valid_diagrams / total_diagrams`.

A diagram is **valid** iff PlantUML's own parser accepts it **and** every
structural rule passes.

### Inputs

One or more `.puml` files plus a `run_id`:

```bash
python -m pipeline.stage1.parse_check --run-id RUN01 \
  --diagram materials/M4-gold-v0.2/gold/gold-class.puml \
  --diagram materials/M4-gold-v0.2/gold/gold-activity.puml
```

| Flag | Meaning |
| --- | --- |
| `--run-id` | Opaque label. Not interpreted. |
| `--diagram` | A `.puml` file. Repeat for several. |
| `--out` | Output JSON. Default `pipeline/stage1/artifact/<run-id>__parse_check.json`. |
| `--config` | A `config.yaml` holding the `stage1:` section. |

### Outputs

`<run_id>__parse_check.json` plus its `.meta.json` sidecar. The JSON holds
`run_id`, run-level `diagram_validity`, and per diagram: `path`, `kind`,
`parse_ok`, `valid`, `inventory_allowed`, every rule's verdict, and
`violations[]` with a line number where one can be attributed.

`inventory_allowed` mirrors `valid`. A downstream extractor reads it through
the helper rather than re-deriving the rules:

```python
from pipeline.stage1.parse_check import inventory_allowed
if inventory_allowed("pipeline/stage1/artifact/RUN01__parse_check.json", "gold-class.puml"):
    ...  # safe to extract an inventory from this diagram
```

A diagram that was never checked returns `False`: never extract from something
that was not judged.

### Rules

**Syntax** — `plantuml -checkonly`. This is the official parser's verdict.

| Rule | Applies to | Check |
| --- | --- | --- |
| PV-01 | class | At least one class is defined. |
| PV-02 | activity | Has a start node and an end/stop node. |
| PV-03 | activity | Every `if` has a matching `endif`. |
| PV-04 | any | Every `partition`/swimlane block is closed. |

The structural layer is not redundant with the syntax check. `-checkonly`
**accepts** an activity diagram with an unclosed `if` and one with a missing
`@enduml`, exiting 0 in both cases. Only PV-02..PV-04 catch those.

### Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Ran to completion — **including when diagrams are invalid**. Read the JSON. |
| `2` | Bad arguments, unreadable file, or output outside the repository. |
| `3` | PlantUML could not be run (missing jar/binary, timeout). The diagrams were **not** judged. |

The 0-vs-3 split is the point: "this diagram is bad" and "I could not check it"
are different answers and must not be confused.

### Known limitations

- **The v0 rule set is the four rules above.** Broader UML well-formedness
  (unreachable nodes, orphan classes, relationship cardinality, type
  correctness) is not covered.
- **Syntax violations carry no line number.** `-checkonly` reports only that a
  diagram contains errors, so `line` is `null` for `SYNTAX`; the structural
  rules do supply line numbers.
- **PlantUML is not vendored.** The jar is downloaded to `tools/` and
  gitignored, so a fresh checkout gets exit code 3 until it is fetched.
- Diagram kind is inferred from the body, not the `@startuml` label. A file
  that is neither class-like nor activity-like gets only PV-04.

---

## Removed ontology-dependent analysis

Ontology-backed state recognition and the metric 8 consistency analyzer have
been removed. Stage 1 now consists of normalization and diagram validation.
The `X__state_mentions` output column and ontology provenance fields are no
longer produced.

## Changelog

`parse_check` is versioned separately (`PARSE_CHECK_VERSION`) because its
contract changes independently of normalization.

### 1.3.0

Breaking. Removed ontology-backed state recognition and metric 8 consistency
analysis. Normalization and parse-check metadata no longer record ontology
paths or hashes.

### 1.2.0

Additive. No existing column changed name, position or value.

**Added**

- `activity-inv` now normalizes `swimlane`, and `class-inv` now normalizes
  `owner_class`, each emitting the normalization `X__*` columns. Both are treated
  as label columns (the same path as `canonical_name` and `verb`/`object`), so
  identifier splitting applies: `PaymentGateway` and `Payment_Gateway` both
  normalize to `payment gateway`. Both are optional: `owner_class` is empty on
  every non-attribute row and `swimlane` may be empty on rows that belong to no
  lane, and an empty cell emits empty fields rather than raising.

### 1.1.0

Four defects found reviewing the v1.0.0 output on the 49-row gold set, plus two
quality improvements. 187 cells changed on the gold file; the full cell-level
diff is in [reports/gold_v1.0_vs_v1.1.csv](reports/gold_v1.0_vs_v1.1.csv).

**Breaking**

- **Removed `X__negated`.** Replaced by `X__has_negation_cue` (same semantics
  as the old flag) and `X__main_predicate_negated` (the negation reaches the
  main predicate). `X__negation_scope` was added alongside them, reporting
  `main` / `subordinate` / `none`. The `Normalized.negated` attribute is gone
  too; `Normalized` now carries `has_negation_cue`, `main_predicate_negated`
  and `negation_scope`.
- `config.yaml`'s `Stage1.keep_negation_cue_tokens` is no longer read. Cues are now
  always kept. The key is accepted and ignored.

**Fixed**

- **Negation words are no longer deleted from `normalized`** (defect 1).
  v1.0.0 made GR-30 identical to its affirmative twin and inverted GR-31 and
  GR-36. `n't` is written out as `not`.
- **Sentence-level negation split into cue and scope** (defect 2). Of the six
  gold rows carrying a cue, only GR-30 negates the main requirement; the other
  five would have been wrongly blocked from matching downstream.
- **State mentions now require a state *use*, not just a vocabulary hit**
  (defect 3). Removed 14 rows' worth of false positives — `new` (GR-06, 07),
  `declined` (GR-10, 11), `retrieved` (GR-12, 23, 24), `boxed` (GR-13),
  `handed over` (GR-14), `ordered` (GR-44), `reserved` (GR-45) and `returned`
  in "returned items" (GR-19, 20, 21) — without losing a single true positive.
- **The possessive marker is dropped** (defect 4). `customer s delivery
  address` → `customer delivery address`; the curly apostrophe is handled too.
- **`source_reqs` no longer leaks into the state vocabulary.** The ontology
  reader was collecting requirement ids (`FR06`, `FR08`, …) as state terms.
  Found while separating canonical names from aliases; harmless in v1.0.0 only
  because no sentence contains those tokens.

**Improved**

- Participial adjectives (`amod`) keep their surface form instead of being
  lemmatized (I1).
- `aux` / `auxpass` tokens are dropped; a root copula is kept (I2).
- `not more than`, `not less than`, `at least` and `at most` added to the
  default `non_negating_phrases`.

### 1.0.0

Initial release: identifier splitting, modal and article removal, verb
lemmatization, sentence-level negation flag, ontology state protection, four
source presets, `.meta.json` provenance sidecar.
