# Stage 1

Stage 1 holds three modules:

| Module | Purpose | Metric |
| --- | --- | --- |
| [`normalize`](normalize.py) | text normalization for the matching cascade | — |
| [`parse_check`](parse_check.py) | diagram validity | 7 |
| [`consistency`](consistency.py) | cross-artifact consistency, CM-01..CM-05 | 8 |

All three are deterministic, read their inputs read-only, never modify the
ontology, and write a `.meta.json` provenance sidecar beside every output.
None of them knows whether its input is gold or agent output: `run_id` is an
opaque label.

For copy-pasteable commands, see [COMMAND.md](COMMAND.md).

---

# normalize — text normalization

normalize is stage 1 of the matching cascade (Stage 1 normalize → Stage 2
ontology → Stage 3 embedding → Stage 4 human). It turns a raw string into one
canonical form so that Stage 2 and Stage 3 compare like with like.

**normalize never decides whether two items match.** It does no Stage 2/Stage 3
work: no actor stripping, no alias lookup, no frame extraction, no synonym
mapping, no embeddings. It is deterministic and offline — one spaCy pipeline,
no network, no randomness — and it never modifies an input file or the
ontology.

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
| `X__state_mentions` | ontology state terms used **as states**, `; `-separated |

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
7. state protection (ontology states used *as states* keep their surface form)
8. negation **scope resolution**, on the dependency parse

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

## State mentions

A token is a state mention only if it is in the ontology's state vocabulary
**and** its context says it is being used as a state. Merely appearing in the
vocabulary is not enough — that was defect 3 of v1.0.0, which reported `new`,
`declined`, `retrieved`, `boxed`, `handed over`, `ordered`, `reserved` and
`returned items` as states.

The vocabulary is read from the ontology at runtime; nothing is hard-coded.
The ontology **does** distinguish canonical names from aliases: the nine
canonical states are `order_lifecycle.canonical_sequence` plus
`order_exceptions.canonical` (equivalently, the keys of `state_aliases`), and
the aliases are that mapping's values. `legal_transitions` and `source_reqs`
are skipped — they hold transition pairs and requirement ids, not state names.

### The rules

**Rule 1 — explicit.** The term is immediately followed by `state` / `status`:
*to the shipped **state***, *payment failed **state***, *declined **state***.
**Aliases are allowed here**, because the author has said the word is a state.

**Rule 2 — structural.** The term is a **canonical** name (never an alias) and
is one of:

- **2a** a participial modifier (`amod`) of `order` / `orders`:
  *a **placed** order*, ***shipped** orders*;
- **2b** the predicate of `order` / `it` as subject: *when an order is
  **placed***, *if it is **shipped***. A relative pronoun is resolved to the
  noun its clause modifies, so *an order that … has already been **picked***
  counts;
- **2c** the complement after `as`: *mark … order as **picked***;
- **2d** the object of `to` / `in` / `into` after `order` or a state verb
  (`transition`, `move`, `set`, `reach`, …): *transition the order to
  **placed***.

**Rule 3 — phrases.** Multi-word canonical states (`payment failed`) are
matched as a phrase, longest first, so `payment failed` wins over `failed`.

Anything else is **not** a state mention and is normalized like any other word
— lemmatized if it is a verb. This is what makes the two sides of a comparison
agree: gold's *"once its items have been **retrieved**"* and an agent's *"the
Warehouse **retrieves** items"* both reduce to `retrieve`, where v1.0.0 kept
the gold side as the state `retrieved` and the two could never match.

### Known failure modes — states

- **Aliases are invisible outside rule 1.** *"mark the order as **boxed**"*
  reports no state mention, although a human would call that the `packed`
  state. Stage 1 does not map aliases to canonical names — that is Stage 2's job — so
  admitting aliases structurally would produce more false positives than it
  fixes.
- **Rule 2 is anchored on the word `order`.** A state predicated of a synonym
  (*"when the purchase is placed"*) or of a pronoun other than `it`/`they` is
  missed.
- **The parse drives 2a–2d.** A misparsed `amod` or a subject spaCy attaches to
  the wrong verb changes the answer. The gold set is fully covered; other
  phrasings may not be.
- **A state word as the main verb is left alone**, by design: *"the carrier
  **shipped** the goods"* is an action, not a state.

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

# consistency — metric 8 (Consistency)

Scores cross-artifact agreement **per instance**:

```
consistency = 1 - failed / total
```

With no instances the metric is `null` with a `no_instances` flag — never
`1.0`, because "nothing was checked" is not "everything was right".

### Inputs

Already-flattened CSVs only. This module never parses `.puml`, markdown or
prose.

```bash
python -m pipeline.stage1.consistency --run-id RUN01 \
  --class-csv        pipeline/stage1/artifact/gold-class-elements__stage1.csv \
  --activity-csv     pipeline/stage1/artifact/gold-activity-elements__stage1.csv \
  --requirements-csv pipeline/stage1/artifact/gold-requirements__stage1.csv
```

All three are Stage 1 `normalize` outputs. `--out-dir` defaults to
`pipeline/stage1/artifact/`.

### Outputs

| File | Contents |
| --- | --- |
| `<run_id>__consistency_instances.csv` | `run_id, rule_id, instance, status, detail, ontology_sha256, tool_version` |
| `<run_id>__consistency.json` | per-rule `{total, failed}`, totals, and `consistency` |
| `<run_id>__ontology_gaps.csv` | `term, source_file, rule_id, count` |
| `<run_id>__consistency.json.meta.json` | provenance sidecar |

Unknown terms are **never** added to the ontology. M2's HARD RULE 2 requires
human adjudication, so they are logged to the gaps CSV instead.

### Rules

| Rule | One instance per | Passes when |
| --- | --- | --- |
| CM-01 | swimlane element | The swimlane resolves to an ontology class or actor. |
| CM-02 | action with an object | The object resolves to a class or attribute. |
| CM-03 | class | Its canonical name or an alias occurs in ≥1 requirement. |
| CM-04 | detected transition | The transition is in `states.legal_transitions`. |
| CM-05 | concept in >1 source | One canonical name is used across sources. |

Matching is ontology lookup only: longest alias first, case-insensitive, and
insensitive to identifier style (`PaymentGateway` = `payment_gateway`).

**There is deliberately no CM-06.** No multiplicity rule is implemented.

### Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Ran to completion, including when instances fail. |
| `2` | Missing prerequisite column, unreadable input, bad arguments. |

### Known limitations

- **CM-01 needs artifacts built by normalize 1.2.0 or later.** It reads
  `swimlane__normalized` and `owner_class__normalized`, which the
  `activity-inv` and `class-inv` presets emit from 1.2.0 on. Against an
  artifact produced by an older version the module stops with an error naming
  both columns rather than silently skipping the rule; regenerate the input,
  or deselect CM-01 via `stage1.consistency.rules` to run the other four.
  Enabled by default now that the gold artifacts are regenerated with 1.2.0;
  on the gold set it passes 4/4.
- **CM-04 is pattern-based and conservative.** An instance is created only
  when one of three ordered patterns matches: `mark <from> … as <to>`,
  `<from> … marked as <to>`, and `from <from> … to <to>` (plus the ontology's
  `action_verbs.transition` surface forms). A requirement that merely mentions
  two states states no transition — "cancel only while *placed* and not yet
  *picked*" is a guard, not a move, and yields no instance. The cost is
  recall: a transition phrased outside these patterns is missed rather than
  guessed at.
- **CM-05 covers structured fields only** — class `canonical_name`, activity
  `swimlane` and `object`, requirement `actor` and `object`. Requirement prose
  is not mined for names. It also ignores pure formatting differences: two
  spellings that resolve to the same ontology concept are one name, not an
  inconsistency.
- **CM-03 matching tolerates a regular plural** on the final word (`order
  lines` matches `OrderLine`) because `normalize` keeps surface nouns by
  default. It does no general stemming.
- Ontology lookups use the **raw** identifier column, not the normalized one:
  `normalize_label` lemmatizes short labels (`ShoppingCart` → `shop cart`),
  which is right for embeddings but destroys the identifier a lookup needs.

## Changelog

The versions below are `normalize`'s. `parse_check` and `consistency` are
versioned separately (`PARSE_CHECK_VERSION`, `CONSISTENCY_VERSION`, both
1.0.0) because their contracts change for different reasons.

### parse_check 1.0.0 / consistency 1.0.0

Initial release of the two analysis modules: metric 7 (syntax via
`plantuml -checkonly` plus structural rules PV-01..PV-04) and metric 8 (rules
CM-01..CM-05, per-instance scoring, ontology-gap logging). Both are registered
in [registry.py](registry.py). `normalize` is unchanged by this work.

### 1.2.0

Additive. No existing column changed name, position or value.

**Added**

- `activity-inv` now normalizes `swimlane`, and `class-inv` now normalizes
  `owner_class`, each emitting the usual six `X__*` columns. Both are treated
  as label columns (the same path as `canonical_name` and `verb`/`object`), so
  identifier splitting applies: `PaymentGateway` and `Payment_Gateway` both
  normalize to `payment gateway`. Both are optional: `owner_class` is empty on
  every non-attribute row and `swimlane` may be empty on rows that belong to no
  lane, and an empty cell emits empty fields rather than raising.

Requested by CM-01 in [consistency.py](consistency.py), which needs canonical
lane and owner-class names. The gold artifacts have since been regenerated
with this version, so CM-01 is included in the default rule set and passes
4/4 on the gold set.

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
