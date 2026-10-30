# Validation pipeline — how the SRS packages are scored

This document describes the pipeline as it is implemented now: one entry point that
(optionally) generates an SRS package, scores it with three independent grading
modules against gold standards the generator never saw, writes one report per run,
and collects the ten metrics of M2 for all runs in one table. It is written as source
material for the method, metrics and threats-to-validity sections of the paper. The
generation side is in [generation_setup.md](generation_setup.md); the metric
definitions are in `materials/M2-metrics.md`; each module has its own README or guide
in `evaluators/<Module>/`.

Status: 2026-10-29. This file replaces `PIPELINE.md`. Statements I could not check in
code or data are marked *not verified*.

---

## 1. Overview

```
                         config.yaml
                              │
   main.py ──► workflow_factory.build() ──► PipelineComponents
      │                                      (agent, graders, report writer)
      ▼
 workflow_pipeline.run_pipeline(phase, run_id, grade, on_pending)
      │
      ├─ phase gen ──► ChatDevGenerationAgent ──► generated/<RUN>/sdk_*/code_workspace/
      ├─ phase grade ─► for each selected module, in order:
      │                   reqs ─► RequirementsGrading ─► generated/<RUN>/grading/reqs/
      │                   models ► ModelsGrading ──────► generated/<RUN>/grading/models/
      │                   vmx ──► VMXGrading ──────────► generated/<RUN>/grading/vmx/
      ├─ report ──► generated/<RUN>/report_<RUN>.json   (raw, merged across invocations)
      │             generated/<RUN>/report_<RUN>.txt    (rendered by report_to_txt.py)
      └─ phase summary ► report_summary.py ──► generated/final_metrics.csv
                          (reads every run's report; no generation, no grading)
```

Principles that hold across the pipeline:

- **The generated workspace is read-only.** Graders copy what they need into
  `grading/<module>/submission/` and read only that copy.
- **Everything about a run lives in one run directory** (`generated/<RUN>/`).
- **Grading modules are independent.** They share configuration and the gold standards
  but no state; one crashing does not cost the others' results.
- **Nothing blocks on input.** A step that needs a human writes a review file and
  stops (or, in provisional mode, continues with a marked default); a rerun picks the
  answers up (§7).
- **Rules and vocabularies that affect a number live in YAML**, never in source code;
  a lint test enforces it for ModelsGrading.

---

## 2. Running it

```bash
uv run main.py --phase all   --run-id RUN_x            # generate, then grade
uv run main.py --phase gen   --run-id RUN_x            # generate only (ChatDev system)
uv run main.py --phase grade --grade reqs models vmx   # grade the run in evaluation.generated
uv run main.py --phase summary [--out file.csv]        # table + CSV of all runs
```

| Flag | Meaning |
|---|---|
| `--phase gen\|grade\|all\|summary` | generation, grading, both (default `all`), or the cross-run summary |
| `--grade reqs models vmx` | grading modules to run; default all three; they always run in this order |
| `--on-pending provisional\|halt` | `provisional` (default): unreviewed items take the configured default and the result is marked `provisional`. `halt`: stop and write the review file |
| `--run-id` | names the run directory in generation; in grading it only labels manifests |
| `--out` | summary phase: CSV path (default `generated/final_metrics.csv`) |
| `--prompt`, `--config` | generation prompt file; configuration file |

`--phase grade` reads the run named by `evaluation.generated` in `config.yaml`: a run
directory (using its newest `sdk_*/code_workspace`) or a directory that holds the five
files directly (the Claude Code and Antigravity runs). Each module can also be run
alone: `python -m evaluators.<Module>.run --submission <dir> --out generated/RUN_x`.

The `summary` phase finds the runs itself: every directory under `generated/` that
contains a `report_*.json` is a run.

---

## 3. Components

| File | Role |
|---|---|
| `main.py` | argument parsing, then `build()` and `run_pipeline()` (or the summary) |
| `workflow_factory.py` | builds the agent, the three graders (`GRADER_NAMES = reqs, models, vmx`) and the report writer |
| `workflow_pipeline.py` | prompt injection, generation, standalone-run discovery, grading loop, report export |
| `agents/gen.py` | `ChatDevGenerationAgent` |
| `interfaces/base.py` | `GenerationResult`, `ValidationResult`, protocols |
| `evaluators/*Evaluator.py` | adapters: stage the submission, call the module's `grade()`, wrap metrics in a `ValidationResult` |
| `evaluators/staging.py` | copies a workspace's files into `grading/<module>/submission/` under the names the module expects |
| `evaluators/<Module>/` | the grading modules |
| `report_writer.py`, `report_to_txt.py` | raw JSON report and its text rendering (§9) |
| `report_summary.py` | the ten-metric table and CSV across runs (§9.2) |
| `pipeline/` | an earlier standalone analysis package (text normalization, diagram validity). Not used by generation or grading |

Orchestration details:

1. **Prompt.** `_read_prompt` replaces `{{FR_INPUT}}` / `{{NFR_INPUT}}` with the lines
   of `agent.prompt_inputs` (`materials/M1a.json`).
2. **Grading loop.** For each selected module the pipeline calls
   `validate(generation, run_id, on_pending)`. An exception is caught and recorded
   as a failed result, so the other modules still run.
3. **Staging.** Files come from `code_workspace/artifacts/` if it exists, otherwise
   from the workspace root. A file the generator did not produce is absent in the
   staged copy and the module grades it as missing instead of failing. Diagram files
   are found by name (`*structural*.puml` or `*class*.puml`; `*behavioral*.puml` or
   `*activity*.puml`).

---

## 4. The ten metrics (M2 §1.1) and where each comes from

| # | Group | Metric | Module | Report field | CSV column |
|---|---|---|---|---|---|
| 1 | Completeness | Requirement Recall | reqs | `metrics.sweep[primary].recall` | `requirement_recall` |
| 2 | | Structural Semantic Recall | models | `metrics.structural.recall` | `structural_semantic_recall` |
| 3 | | Behavioral Semantic Recall | models | `metrics.behavioral.recall` | `behavioral_semantic_recall` |
| 4 | | VMX Requirement Coverage | vmx | `metrics.coverage.score` | `vmx_requirement_coverage` |
| 5 | Correctness | Requirement Precision | reqs | `metrics.sweep[primary].precision` | `requirement_precision` |
| 6 | | Structural Semantic Precision | models | `metrics.structural.precision` | `structural_semantic_precision` |
| 7 | | Behavioral Semantic Precision | models | `metrics.behavioral.precision` | `behavioral_semantic_precision` |
| 8 | | Structural Syntax Validity | models | `metrics.structural.syntax_validity` | `structural_syntax_validity` |
| 9 | | Behavioral Syntax Validity | models | `metrics.behavioral.syntax_validity` | `behavioral_syntax_validity` |
| 10 | | VMX Referential Integrity | vmx | `metrics.integrity.score` | `vmx_referential_integrity` |

No F1 is reported; recall and precision are separate columns. (The modules still
compute an F1 in their own result files; it is not one of the ten.)

Definitions in short (full text in M2):

- **Requirement Recall** = covered gold units / **70** (62 acceptance criteria + 8
  NFRs); several generated units may cover one gold unit.
- **Requirement Precision** = (generated units that matched gold + unmatched units
  that pass the rubric) / generated units after deduplication. The rubric term is
  added at the primary threshold only, so precision is comparable across the
  threshold sweep only there.
- **Structural / Behavioral Recall** = matched gold elements / **50** and **39**.
  **Precision** = (matched generated elements + unmatched ones passing the rubric) /
  generated elements (`s8_metrics.py`: `(matched_gen + rubric_pass) / n_gen`).
- **Syntax Validity** = declarations accepted by the project's own parser / all
  declarations (§5.2 explains why this can differ from what PlantUML says).
- **VMX Coverage** and **Integrity** are look-ups, no semantics (§6.3).

Thresholds: cosine 0.75 is primary for requirements and for models, with a
sensitivity sweep 0.70 / 0.75 / 0.80 / 0.85; requirement dedup at 0.90. The models
threshold is inherited from requirements and has not had its own sensitivity
analysis (see §11).

**`n/a` versus `0`.** A semantic metric behind a failed syntax gate is recorded as the
string `n/a` ("not measured"), never `0` ("measured, nothing matched"). Keep this
distinction in tables and in aggregates; averaging `n/a` as zero would be wrong.

---

## 5. Syntax gate (ModelsGrading, stage S0)

### 5.1 What it does

Before a generated diagram is compared with the gold, it must pass a **syntax gate**.
A diagram that fails is still parsed and logged (validity, rejected declarations),
but its recall, precision and control items are `n/a`. A missing file gives gate
`missing`. The gold diagrams themselves must parse at validity 1.0, otherwise the run
fails before touching the submission.

### 5.2 Two modes (`syntax_gate` in `config.yaml`)

| Mode | A diagram passes when | Use |
|---|---|---|
| `strict` | the project's own parser accepts **every** declaration (validity = 1.0) | the original rule |
| `plantuml` | **PlantUML itself** accepts the file (`java -jar tools/plantuml.jar -syntax`; PlantUML prints the diagram type, or `ERROR` with a line and a message) | **current setting** |

The own parser is used in both modes to extract the elements that are compared with
the gold; PlantUML only decides the gate. `plantuml` was chosen because `strict`
rejected diagrams that PlantUML accepts, for reasons internal to the own parser.
Examples seen: the arrow `-->` is valid PlantUML but is not in the parser's
relationship table (`unknown_rel_arrow`), which cost three Claude Code runs their
whole structural score for one line each; other rejected constructs in `gptoss-3`
were `unsupported_construct` (46) and `duplicate_declaration` (10), which I did not
examine one by one.

Effects of the change on the nine runs:

- Structural diagrams of `claude-code-1/2/3`, `gptoss-1` and `gptoss-3` now pass the
  gate and have semantic metrics.
- Two diagrams still fail because PlantUML also rejects them: `gptoss-2` structural
  (error at line 80) and `antigravity-3` behavioral (`repeat while` with no `repeat`,
  line 39). Their semantic metrics are `n/a` and that is a genuine syntax failure.
- A cached run made under another gate mode is recomputed automatically (each
  syntax block records its `gate_mode`).

### 5.3 What the gate does not cover

- `-syntax` is lenient: PlantUML can accept, for example, a diagram with an unclosed
  `if`. The repository has structural rules PV-01..PV-04 (`pipeline/parse_check.py`)
  for this, but they are **not** connected to the gate.
- **Syntax Validity (metrics 8–9) still comes from the own parser.** It can be low
  for a diagram PlantUML accepts: `gptoss-3` structural has validity 0.521 (62 of 119
  declarations) and passes the gate. Report both numbers, or state which one the
  paper uses. The gate verdict for each diagram is in the CSV
  (`structural_syntax_gate`, `behavioral_syntax_gate`).
- "PlantUML accepts it" says nothing about whether the model is *right*; that is the
  job of the semantic metrics.

---

## 6. The grading modules

| | **reqs** — RequirementsGrading | **models** — ModelsGrading | **vmx** — VMXGrading |
|---|---|---|---|
| Submission files | `requirements.json` | `structural.puml`, `behavioral.puml` | `VMX.csv`, `requirements.json`, both `.puml` |
| Gold / reference | `G1-requirements.json` (70 units); `M1a.json` for the rubric | `G2-structural-model.puml`, `G3-behavioral-model.puml`; `M1a.json` for the rubric | `M1a.json` (domain ids) and the submission itself |
| Embedding | `all-mpnet-base-v2` | `all-mpnet-base-v2` | none |
| Rule layer | 3 axes: polarity, identifiers/direction, numbers | per-kind checks: types, guards, statuses, relationships | none |
| LLM judge + human κ sample | yes (unmatched generated units) | yes (unmatched elements) | no |
| Needs a human | polarity cases the rules cannot decide; κ sample | type and guard cases; κ sample | never |
| Result file | `run/05_metrics.json` | `run/07_metrics.json` | `run/03_metrics.json` |

### 6.1 Requirements (reqs)

Stages S0–S6: extract units (acceptance criteria and NFRs) → cosine similarity
(cached) → candidate pairs at the lowest sweep threshold (0.70) → rule layer →
single-linkage dedup of the generated units (cosine ≥ 0.90) → rubric for generated
units with no passing pair at the primary threshold (0.75) → metrics. Scoring is at
acceptance-criterion level, not per story (M2 §2.2 gives the reasons: merging
criteria dilutes cosine and loses the numerator/denominator meaning of recall).

### 6.2 Models (models)

Stages S0–S7: syntax gate (§5) → element extraction and gold-inventory check →
per-kind similarity → candidates → staged Hungarian assignment → rule layer with
type and guard ledgers → control checklist (six items) → rubric → metrics. Gold
inventory: structural 6 classes, 22 attributes, 4 enums, 13 literals, 5
relationships (50); behavioral 9 actions, 10 object nodes, 9 swimlanes, 11
transitions (39).

### 6.3 VMX (vmx)

**Coverage**: a requirement counts when its VMX row exists and the required columns
are non-empty (`US-` needs `Domain-Req-ID` and `Structural-Elements`; `NFR-` needs
`Domain-Req-ID`), over the requirements in the submission's `requirements.json`.
**Integrity**: the share of VMX references that match, character for character, a name
declared in the submission itself (domain ids from `M1a.json`; classes, enums and
`Class.attribute` from `structural.puml`; actions from `behavioral.puml`). Existence is
judged against the submission, never against the gold, so it measures internal
consistency, not similarity. The column name `Behavorial-Elements` is spelled that way
in the schema.

---

## 7. LLM judge and human validation

### 7.1 The judge

For every unmatched generated item (requirement unit or model element) an LLM judge
decides two conditions independently (M2 §1.3):

1. **traceable** — attributable to a real domain requirement, not an invented
   capability;
2. **consistent** — does not contradict any gold item.

Atomicity is deliberately *not* a condition. An item counts as correct when it is
traceable **and** consistent.

| Setting | Value |
|---|---|
| Judge model | `deepseek-v4.1-flash:cloud` (a tag, not a snapshot id) |
| Endpoint | Ollama Cloud, `https://ollama.com/v1` |
| Temperature | 0 |
| Retries | up to 3 calls per item while the reply does not parse |
| Prompt | fixed, in `RequirementsGrading/stages/s5_rubric.py` and `ModelsGrading/stages/s7_rubric.py`; every call (prompt and raw reply) is appended to `run/*judge_log.jsonl` |
| Reuse | an item already labelled on both conditions is not asked again |

The judge differs in family from all three generator systems (M2 requires this to avoid
self-preference). An unreadable reply is stored blank and the item stays unscored
instead of being recorded as a "no".

### 7.2 The human sample and κ

A blind sample of at most `kappa_sample_size` = **30** items is drawn per run and per
module (`random_seed` fixed) and labelled by a human in a file with no column for the
judge's labels. Cohen's κ is computed on the combined label `traceable AND consistent`;
`κ ≥ kappa_accept` = **0.60** lets the judge's labels stand.
(`kappa_sample_fraction` appears in `config.yaml` but no code reads it.)

One reviewer labelled each run; five reviewer ids appear in the files:

| Run(s) | Reviewer id |
|---|---|
| antigravity-1/2/3, gptoss-1 | Le Anh Duc |
| claude-code-1, claude-code-2 | vuhuy |
| claude-code-3 | tmh |
| gptoss-2 | Nguyen Duc Manh |
| gptoss-3 | Nguyen Nhat Lam |

No item was labelled by two humans, so there is no human–human agreement figure.
That the labels were entered by the person named in the file is *not verified*.

### 7.3 κ in this data, and how to report it

Per run (n = items labelled by both judge and human):

| Run | κ reqs (n) | κ models (n) |
|---|---|---|
| antigravity-1 | 1.000 (34) | 0.778 (24) |
| antigravity-2 | 1.000 (27) | 1.000 (18) |
| antigravity-3 | 1.000 (31) | 1.000 (7) |
| claude-code-1 | 1.000 (38) | 0.419 (25) |
| claude-code-2 | 1.000 (39) | 0.348 (30) |
| claude-code-3 | **0.000** (30) | 0.884 (25) |
| gptoss-1 | 0.898 (26) | 0.527 (33) |
| gptoss-2 | 0.768 (35) | 0.612 (46) |
| gptoss-3 | 0.836 (27) | 0.820 (45) |

Three things to know before interpreting this table:

- **κ is unstable when labels are almost all "pass".** In `claude-code-3` (reqs) the
  human passed all 30 items and the judge passed 29: raw agreement 96.7%, yet κ = 0,
  because with one rater constant the chance agreement equals the observed one (the
  kappa paradox). Where both raters passed everything, the code returns κ = 1.0
  (`expected == 1.0` branch), so most of the 1.0 values come from samples with no
  "fail" label at all (`antigravity-2/3`, `claude-code-1/2` on `reqs`;
  `antigravity-1` has a single one). Only the three gptoss runs have more than one
  "fail" label on `reqs`, so only there does κ carry much information.
- **A sample of about 30 is far below the 150–200 customary for κ** (M2 §2.3 says so
  and asks to state it). M2 recommends pooling the unmatched items of all models when
  several are evaluated.
- Pooled over the nine runs (computed by a one-off script from the review files, not
  by the pipeline, which only supports `kappa_pool: per_section`):

| | n | Raw agreement | κ | PABAK | Gwet AC1 | "fail" labels (judge / human) |
|---|---:|---:|---:|---:|---:|---|
| reqs | 287 | 0.983 | 0.839 | 0.965 | 0.980 | 18 / 15 |
| models | 253 | 0.881 | 0.707 | 0.763 | 0.801 | 67 / 75 |

Suggested reporting: pooled κ as the headline with n and the "fail" counts, per-run κ
as supplementary, plus raw agreement and one prevalence-robust statistic (PABAK or AC1).
If a run falls below 0.60 for real (for example `models` of `claude-code-1`/`-2`), M2
prescribes: revise the prompt, draw a new held-out sample, repeat; never recompute on
the sample used to tune the prompt. If that is not done, say so as a limitation.

---

## 8. Human review and resumability

Each module with a human step follows one contract.

- **`run/` is a disposable cache; `review/` is human-authored.** The module adds new
  empty question rows; a filled cell is not changed.
- **Exit codes** (module level): `0` DONE, `2` NEEDS_REVIEW, `1` FAILED. Through the
  pipeline NEEDS_REVIEW shows as a failed grading result with an explanatory message.
- **`provisional`** never stops: unreviewed pairs take `manual_default`
  (`not_covered`), unscored rubric items count as failing, and the result is marked
  `provisional`. A result is `final` only when nothing is open, whichever mode was
  asked for. The CSV carries `reqs_status`, `models_status`, `vmx_status`.

| Module | File | Filled by the reviewer |
|---|---|---|
| reqs | `polarity_ledger.csv` | `verdict` PASS/FAIL |
| reqs, models | `rubric_human.csv` | `traceable`, `consistent` (yes/no) on the blind sample |
| models | `type_ledger.csv`, `guard_ledger.csv` | `verdict` PASS/FAIL |
| reqs, models | `rubric_llm.csv` | written by the judge; not a human input |

Behaviours observed while running the nine runs (state them if the labelling
procedure is described in the paper):

- **The blind sample is redrawn when the pool of unmatched items changes.** The
  sample is `random.Random(seed).sample(pool, 30)`; one item more or less in the pool
  gives a different draw, and the new items are appended as empty rows (old labelled
  rows stay in the file and still count toward κ when the item is still judged). The
  pool depends on the ledgers (a human PASS makes a pair matched), so the order that
  avoids rework is: **ledgers first, rerun, then `rubric_human.csv`**.
- **Free-text columns are lost on rerun.** The reviewer of `claude-code-3` added a note
  column after the sixth column; the module rewrites the file with six columns only.
  The notes were restored from a copy after each rerun.
- **Dates.** Timestamps in review files were unified to `dd/mm/yyyy`; some files had
  carried times or ISO dates. The pipeline does not parse them.

---

## 9. Run directory, reports, and the cross-run table

### 9.1 Per run

```
generated/<RUN>/
├── sdk_ChatDev_v1_<ts>_<ts>/ (ChatDev runs) or the five files directly
├── grading/
│   ├── reqs/    submission/  run/ (00_units … 05_metrics, 06_judge_log.jsonl, manifest.json)  review/
│   ├── models/  submission/  run/ (00_syntax … 07_metrics, 08_judge_log.jsonl, syntax logs, manifest.json)  review/
│   └── vmx/     submission/  run/ (00_inputs … 03_metrics, manifest.json)
├── report_<RUN>.json     raw report
└── report_<RUN>.txt      rendered from the JSON
```

Each manifest records the rules used and start and end times; the reqs and models
manifests also record the embedding model and revision, the config (secrets removed)
and the code commit, so a result can be reconstructed from the run directory.

`report_writer.py` keeps the run's report as JSON and merges each invocation into it:
running `--grade reqs` and later `--grade models` leaves both in the report, running
a module again replaces only its entry, and a grade-only invocation does not overwrite
the generation record. The text version comes only from `report_to_txt.py`
(`python report_to_txt.py generated/RUN_x/report_RUN_x.json`).

### 9.2 Across runs: `final_metrics.csv`

```bash
python main.py --phase summary          # prints the table, writes generated/final_metrics.csv
python report_summary.py [generated] [-o file.csv]
```

Columns: `run`; the ten metrics in the order of §4; `structural_syntax_gate`,
`behavioral_syntax_gate`; `reqs_status`, `models_status`, `vmx_status`;
`requirements_kappa`, `requirements_kappa_n`, `models_kappa`, `models_kappa_n`.
`n/a` is kept as `n/a`; a module that has not run leaves its cells blank.

---

## 10. Configuration

`config.yaml` (git-ignored; copy `config.example.yaml`):

| Section | Keys | Used by |
|---|---|---|
| 1. Run | `workdir`, `evaluation.generated`, `output.report_dir` | pipeline |
| 2. Generation | `agent.model`, `api_base`, `api_key`, `prompt_template`, `prompt_inputs`, `generated_dir` | generation |
| 3. Grading, shared | `embedding_model` (`all-mpnet-base-v2`), `embedding_revision` (null), `pooling`, `normalize_embeddings`; `judge_model`, `judge_api_base`, `judge_api_key`, `judge_temperature`, `judge_max_attempts`; `manual_default`, `kappa_sample_size`, `kappa_accept`, `random_seed` | reqs, models |
| 4. Per module | reqs: `requirement_grading.{threshold, sweep, dedup_threshold, allow_cross_kind, expected_gold_units}`; models: `threshold_models`, `sweep_models`, `syntax_gate` (`strict` \| `plantuml`), `kappa_pool` (`per_section`) | one module each |
| 5. Gold | `gold.{requirements, structural, behavioral, domain}` | all graders |
| 6. Pipeline analysis | `pipeline.*`; `pipeline.parse_check.{plantuml_jar, java_cmd, timeout_seconds}` are also read by `syntax_gate: plantuml` | `pipeline/`, models |

`syntax_gate: plantuml` needs Java and `tools/plantuml.jar` (downloaded, not committed);
a missing jar or Java is an error, not a silent pass. The judge key may be left empty
and read from `OPENROUTER_API_KEY` or `OPENAI_API_KEY` by endpoint host; it is never
written to a manifest.

---

## 11. Results snapshot and known limits

### 11.1 Snapshot (2026-10-29; `generated/final_metrics.csv` is authoritative)

| Run | ReqRec | StrRec | BehRec | VMXCov | ReqPrec | StrPrec | BehPrec | StrSyn | BehSyn | VMXInt |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| antigravity-1 | 0.314 | 0.860 | 0.667 | 1.000 | 0.983 | 1.000 | 0.954 | 1.000 | 1.000 | 1.000 |
| antigravity-2 | 0.243 | 0.940 | 0.718 | 1.000 | 1.000 | 1.000 | 0.954 | 1.000 | 1.000 | 1.000 |
| antigravity-3 | 0.186 | 0.860 | n/a | 1.000 | 1.000 | 1.000 | n/a | 1.000 | 0.875 | 0.995 |
| claude-code-1 | 0.443 | 0.920 | 0.692 | 1.000 | 1.000 | 1.000 | 0.878 | 0.980 | 1.000 | 1.000 |
| claude-code-2 | 0.400 | 0.900 | 0.641 | 1.000 | 0.988 | 1.000 | 0.898 | 0.981 | 1.000 | 1.000 |
| claude-code-3 | 0.443 | 0.920 | 0.692 | 1.000 | 0.987 | 1.000 | 0.898 | 0.980 | 1.000 | 1.000 |
| gptoss-1 | 0.243 | 0.840 | 0.487 | 1.000 | 0.861 | 1.000 | 0.872 | 0.942 | 1.000 | 0.967 |
| gptoss-2 | 0.271 | n/a | 0.103 | 0.893 | 0.892 | n/a | 0.570 | 0.924 | 1.000 | 0.858 |
| gptoss-3 | 0.243 | 0.840 | 0.410 | 1.000 | 0.907 | 0.897 | 0.600 | 0.521 | 1.000 | 0.919 |

All nine runs are `final` in all three modules. Requirement recall is low for every
run (0.19–0.44) mostly because the generators write fewer, coarser requirements than
the 70-unit gold (generation_setup.md §7.1); that is a finding about granularity, not
only about coverage.

### 11.2 Known limits (state them when reporting)

- **Three runs per generator system, nothing pinned.** Model tags are not snapshots;
  no seeds; Claude Code and Antigravity sampling parameters unknown.
- **One reviewer per run, no double labelling**; per-run κ rests on about 30 items and
  often on samples with no "fail" label (§7.3).
- **Embedding revision is unpinned** (`embedding_revision: null`); pin it before a
  scored run you want to reproduce.
- **Judge tag, not snapshot.**
- **Syntax gate.** `plantuml` is lenient (§5.3); Syntax Validity still comes from the
  own parser; two diagrams fail the gate for a genuine syntax reason and have `n/a`
  semantic metrics.
- **ModelsGrading open items** (its README): the type table is a draft, threshold 0.75
  is inherited from requirements without its own sensitivity analysis, `kappa_pool:
  pooled` is not supported, the guard alias `approved` collides across two groups.
- **Rule-layer strictness.** The identifier axis in reqs compares token sets for
  equality, so a paraphrase with one extra or missing noun can be rejected;
  `diagnostics.axis_rejections` counts these and the pairs are in `run/03_axis.json`.
- **Stage caching differs between modules.** Models keeps a stage's output once
  written (a changed `syntax_gate` triggers a full recompute; `--force` rewrites it);
  reqs caches only the embedding step.
- **Sample redraw and lost free-text columns** (§8).
- **Earlier reference run.** `RUN_20261026_GPTOSS120B` is no longer in the working tree
  (git history, commit `507cab9`). Its review labels, per the earlier documentation,
  were filled by an AI assistant after the judge's labels were visible, so it must not
  be used for κ.

---

## 12. Tests

```bash
.venv/bin/python -m pytest tests                              # report writer, summary table
.venv/bin/python -m pytest evaluators/ModelsGrading/tests     # 30 acceptance tests + lint, gate, κ, judge
.venv/bin/python -m pytest evaluators/RequirementsGrading
.venv/bin/python -m pytest evaluators/VMXGrading
```

The ModelsGrading suite (including the new tests for the PlantUML gate) and `tests/`
passed when last run; the RequirementsGrading and VMXGrading suites were *not* run in
this session. The reqs and models suites load the sentence-transformer model and take
minutes (the 30 acceptance tests took about 11 minutes). No test calls a live LLM: the
judge is injected. The PlantUML test is skipped when Java or the jar is missing.
