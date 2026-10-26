# GradingModels — M2 Models Grading

Implementation of `materials/m2-req-grading-spec.md`'s sibling: Structural /
Behavioral Semantic Recall and Precision, the two Syntax Validity gates, and the
six-item control checklist. Requirements Grading and the two VMX metrics are out
of scope.

The spec is authoritative. Section references in the code (`§5.3`, `§7.4.6`, …)
point at it.

## Running

```bash
.venv/bin/python evaluators/GradingModels/run.py \
    --submission <dir> --out <run dir> [--run-id <id>] \
    [--diagram structural|behavioral|both] \
    [--on-pending halt|provisional] \
    [--stage all|S0..S7] [--force]
```

Or from the pipeline, on the generated diagrams of a run:

```bash
uv run main.py --phase val --grade models
```

The module keeps no workspace of its own. It reads `--submission` and writes
only to `<out>/grading_models/{run,review}/` (the run directory, for example
`generated/RUN_x`). From Python: `GradingModels.run.grade(submission, out, ...)`.

Exit codes (§11):

| Result | Exit | Meaning |
|---|---|---|
| `DONE` | 0 | all stages complete, metrics final |
| `NEEDS_REVIEW` | 2 | a review file awaits human input; path printed to stdout |
| `FAILED` | 1 | unrecoverable error (gold invalid, submission unreadable) |

A failed syntax gate is **not** `FAILED`. It is a graded outcome: the run
completes with `n/a` semantics for that diagram and exits 0.

## Inputs

| Input | Path |
|---|---|
| Gold structural (50 elements) | `config.yaml` → `gold.structural` |
| Gold behavioral (39 elements) | `config.yaml` → `gold.behavioral` |
| Domain input (rubric traceability) | `config.yaml` → `gold.domain` |
| Submission | `--submission <dir>` with `{structural,behavioral}.puml` |
| Numeric parameters, run policy | `config.yaml` (project root) |
| Rule-layer vocabularies | `GradingModels/rules.yaml` |

The gold paths live in one shared `gold:` section of `config.yaml` (currently
under `materials/`), so a new grading module reads them from there instead of
carrying its own. Relative paths are taken from the config file's directory.
`materials/domain-requirements.md` holds the 40 `REQ-F-*` / `REQ-N-*`
statements used for rubric traceability.

## Layout

```
GradingModels/
  rules.yaml        rule-layer vocabularies (§9.3)
  configload.py     both loaders; fail loudly on missing/unknown keys (§9.1)
  ledgers.py        review-file I/O; never overwrites a filled cell (§7.4.7)
  run.py            runner, exit codes, manifest (§11)
  parser/           PlantUML -> Graph IR
    ir.py           Declaration / Element / ParseResult; parser version
    normalize.py    label normalization (§5.4)
    structural.py   classes, attributes, enums, literals, relationships (§5.1)
    behavioral.py   activities, object nodes, swimlanes, transition walk (§5.2, §5.5)
    collapse.py     identity by distinct label (§5.3)
  stages/
    s0_syntax.py    syntax gate (§4)
    s1_elements.py  extraction + gold inventory assertion (§5)
    s2_similarity.py per-(diagram, kind) cosine blocks (§6)
    s3_candidates.py candidates at the review threshold (§7.2)
    s4_match.py     staged Hungarian assignment (§7.1, §7.3)
    s5_rules.py     the rule layer's checks (§7.4)
    s5_axis.py      verdicts + ledger routing (§7.4.7)
    s6_control.py   the six-item control checklist (§8)
    s7_rubric.py    rubric for unmatched elements, blind κ sample (§7.6)
    s8_metrics.py   metrics and diagnostics (§10, §12)
  tests/            the acceptance tests of §14
```

Written at run time, inside the caller's run directory (not in this folder):

```
<out>/grading_models/
  run/      disposable cache (00..07, manifest.json, 08_judge_log.jsonl)
  review/   human-authored ledgers — keep with the run, do not delete
```

Module file names carry the stage number from the spec. `s6_control.py` implements
the checklist and `s8_metrics.py` the metrics, both of which the spec labels S7;
`s7_rubric.py` is the rubric, which the spec labels S6. The CLI `--stage` values
follow the spec, not the file names.

## Review workflow

A stage that needs a human writes a file, returns `NEEDS_REVIEW`, and the runner
exits. Fill the file; the next run picks the answers up and continues. The
pipeline never blocks on input.

| File | Filled by the reviewer |
|---|---|
| `type_ledger.csv` | `verdict` (`PASS`/`FAIL`), `reviewer`, `timestamp` |
| `guard_ledger.csv` | `verdict` (`PASS`/`FAIL`), `reviewer`, `timestamp` |
| `rubric_human.csv` | `traceable`, `consistent`, `reviewer`, `timestamp` |

`rubric_human.csv` deliberately carries no column for the LLM's labels:
blindness for the κ computation is enforced by the schema, not by instruction
(§7.6). `kappa_rounds.json` records each round so a later round draws a genuinely
held-out sample.

A verdict outside `{PASS, FAIL}` aborts the run, naming the row.

## The LLM judge

`s7_rubric.py` takes the judge as an injected callable, so the pipeline is
runnable and testable without a live model. With `config.judge_model` unset
there is no judge to call and every unmatched element stays pending — which is
the honest state, not a zero. Wire a pinned snapshot in before the first scored
run and pass it to `s7_rubric.run(..., judge=...)`.

## Tests

```bash
.venv/bin/python -m pytest GradingModels/tests -q
```

The suite is the §14 list, including the one that matters most — acceptance
test 4's last row, branch inversion: swapping `accepted` / `declined` on
transitions 2 and 3 leaves every node and edge in place and inverts the business
meaning, so a pipeline that passes everything else and fails that test cannot
detect it.

## Open issues from the spec

- **§16.1 (parser cannot read gold) — resolved.** The parser supports `detach`
  and the `split` / `split again` / `end split` family, and both gold files
  parse at validity 1.0 with the exact per-kind inventory. Acceptance test 1
  asserts it.
- **§16.2 (type table is a draft) — open.** `rules.yaml` carries the spec's
  draft rows. Freeze them before the first scored run; they move attributes
  between `matched` and `MANUAL` and therefore move Precision.
- **§16.3 (threshold inherited, not justified) — open.** `threshold_models`
  starts at 0.75, shared with Requirements. The sweep runs and is reported, but
  it still needs its own sensitivity analysis before the number is published.
- **§16.4 (κ sample size) — open.** `kappa_pool: per_section` is the current
  setting; `pooled` is the intended resolution. Decide before the first scored
  run, since switching afterwards changes a published number.
- **§16.5 (guard alias collision) — partly addressed.** `approved` appears under
  both `accepted` and `authorized` in `rules.yaml`. `normalize_guard` resolves
  by first match, and an unrecognised guard is routed to `guard_ledger.csv`
  rather than guessed. The positional resolution the spec describes still needs
  confirming on a real submission before the `guard` rejection counter is
  trusted.

## Implementation notes where the spec left a choice

These are decisions the spec did not fix, recorded here because they affect
numbers:

- **Enum-typed attributes.** `status : OrderStatus` names a declared enum, not a
  primitive, so it is compared by the enum the two sides matched in M2 rather
  than against the primitive type table. Without this, every enum-typed gold
  attribute would route to the ledger as an unlisted type and the identity run
  could not pass. The enum's own literal set is still graded by its `enum`
  element (§7.4.2).
- **Object-node status gates candidacy.** §7.4.4 makes the exact status a graded
  check; it is also applied as a candidacy constraint in S3, because entity-only
  embedding makes `Order [filled]` and `Order [shipped]` nearly identical and
  the solver would otherwise pair them arbitrarily and fail a correct
  submission. Excluded pairs are recorded as `status_mismatch`.
- **Control item 5 looks through control nodes.** Gold attaches
  `Payment [completed]`, `Invoice [paid]` and `Order [closed]` to their actions
  through a `split`, so a successor test that stopped at the first node would
  fail an item gold satisfies. The walk skips control nodes and stops at the
  next action, as the transition walk does.
- **`cross_kind_near_miss`** is computed from exact normalized-label collisions.
  A cross-kind cosine matrix is never built (§6), so this is the unambiguous
  signal available without re-encoding.
