# Pipeline — how a run works

This document describes the pipeline as it is implemented now: one entry point
that generates an SRS package with an LLM agent, grades it with three independent
modules, and writes one report per run. For the generation settings and the
reference run see [GENERATION_RUN.md](GENERATION_RUN.md); each grading module has
its own README in `evaluators/<Module>/`.

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
      │                 (prompt = M1-prompt.md + M1a.json)       srs.md structural.puml
      │                                                          behavioral.puml
      │                                                          requirements.json VMX.csv
      ├─ phase grade ─► for each selected module, in order:
      │                   reqs ─► RequirementsGrading ─► generated/<RUN>/grading/reqs/
      │                   models ► ModelsGrading ──────► generated/<RUN>/grading/models/
      │                   vmx ──► VMXGrading ──────────► generated/<RUN>/grading/vmx/
      │
      └─ report ──► generated/<RUN>/report_<RUN>.json  (raw, merged across invocations)
                    generated/<RUN>/report_<RUN>.txt   (rendered by report_to_txt.py)
```

Principles that hold across the pipeline:

- **The generated workspace is read-only.** Graders copy the files they need into
  `grading/<module>/submission/` and read only that copy.
- **Everything about a run lives in one run directory** (`generated/<RUN>/`). A
  grading module writes only under `grading/<module>/`.
- **Grading modules are independent.** They share configuration and the gold
  standards but not state, and one crashing does not cost the others' results.
- **Nothing blocks on input.** A step that needs a human writes a review file and
  stops; a rerun picks the answers up (§5).

---

## 2. Running it

```bash
uv run main.py --phase all   --run-id RUN_x            # generate, then grade
uv run main.py --phase gen   --run-id RUN_x            # generate only
uv run main.py --phase grade --grade reqs models vmx   # grade the run in evaluation.generated
```

| Flag | Meaning |
|---|---|
| `--phase gen\|grade\|all` | generation only, grading only, or both (default `all`) |
| `--grade reqs models vmx` | grading modules to run; default all three. They always run in this order |
| `--on-pending provisional\|halt` | `provisional` (default): unreviewed items take the configured default and the result is marked provisional. `halt`: stop and write the review file |
| `--run-id` | names the run directory in generation; default `RUN_<timestamp>`. In grading it only labels manifests |
| `--prompt` | generation prompt file (default `agent.prompt_template`) |
| `--config` | configuration file (default `config.yaml`) |

`--phase grade` reads the run named by `evaluation.generated` in `config.yaml`: a
run directory (`generated/RUN_x`, using its newest `sdk_*/code_workspace`) or a
workspace itself. Each grading module can also be run alone, from the repository
root: `python -m evaluators.<Module>.run --submission <dir> --out generated/RUN_x`.

---

## 3. Components

| File | Role |
|---|---|
| `main.py` | argument parsing, then `build()` and `run_pipeline()` |
| `workflow_factory.py` | reads `config.yaml`; builds the agent, the three graders (`GRADER_NAMES = reqs, models, vmx`) and the report writer |
| `workflow_pipeline.py` | the orchestration: prompt injection, generation, standalone-run discovery, grading loop, report export |
| `agents/gen.py` | `ChatDevGenerationAgent`: runs the ChatDev workflow |
| `interfaces/base.py` | `GenerationResult`, `ValidationResult`, and the `IGenerationAgent`, `IValidator`, `IReportWriter` protocols |
| `evaluators/*Evaluator.py` | pipeline adapters: stage the submission, call the module's `grade()`, wrap metrics in a `ValidationResult` |
| `evaluators/staging.py` | copies a workspace's files into `grading/<module>/submission/` under the names the module expects |
| `evaluators/<Module>/` | the grading modules themselves |
| `report_writer.py`, `report_to_txt.py` | raw JSON report and its text rendering (§6) |
| `pipeline/` | an earlier, standalone analysis package (text normalization, diagram validity). Not used by generation or grading |

### Orchestration details

1. **Prompt.** `_read_prompt` reads the template and replaces `{{FR_INPUT}}` /
   `{{NFR_INPUT}}` with the lines of `agent.prompt_inputs` (`materials/M1a.json`).
2. **Generation.** The agent writes into `generated/<run-id>/` and returns a
   `GenerationResult`. If the status is not `PASS`, grading is skipped and reported
   as failed.
3. **Standalone grading.** Without a generation in the same invocation, the run is
   rebuilt from `evaluation.generated`, and its generation record is marked
   `standalone`.
4. **Grading loop.** For each selected module the pipeline calls
   `validate(generation, run_id, on_pending)`. An exception is caught and recorded
   as a failed result with `grading_kind` set, so the other modules still run.
5. **Staging.** The adapter takes files from `code_workspace/artifacts/` if that
   folder exists, otherwise from the workspace root. A file the agent did not
   produce is simply absent in the staged copy; the module grades it as missing
   instead of failing. Diagram files are found by name pattern
   (`*structural*.puml` or `*class*.puml`; `*behavioral*.puml` or `*activity*.puml`).

---

## 4. The grading modules

All three score the same package against materials the generator never saw. Gold
paths come from the shared `gold:` section of `config.yaml`.

| | **reqs** — RequirementsGrading | **models** — ModelsGrading | **vmx** — VMXGrading |
|---|---|---|---|
| Submission files | `requirements.json` | `structural.puml`, `behavioral.puml` | `VMX.csv`, `requirements.json`, both `.puml` |
| Gold / reference | `G1-requirements.json` (70 units); `M1a.json` for the rubric | `G2-structural-model.puml`, `G3-behavioral-model.puml`; `M1a.json` for the rubric | `M1a.json` (domain requirement ids) and the submission itself |
| Embedding | `all-mpnet-base-v2` | `all-mpnet-base-v2` | none |
| Rule layer | 3 axes: polarity, identifiers/direction, numeric | per-kind checks: types, guards, statuses, relationships | none |
| LLM judge + human κ sample | yes (unmatched generated units) | yes (unmatched elements) | no |
| Needs a human | polarity cases the rules cannot decide; κ sample | type and guard cases; κ sample | never |
| Metrics | Recall, Precision, F1 over a threshold sweep | structural and behavioral Recall / Precision / F1 behind a syntax gate; control checklist | Requirement Coverage, Referential Integrity |
| Result file | `run/05_metrics.json` | `run/07_metrics.json` | `run/03_metrics.json` |

### Requirements (reqs)

Stages S0–S6: extract units (acceptance criteria and NFRs) → cosine similarity
(cached) → candidate pairs at the lowest sweep threshold (0.70) → rule layer →
single-linkage dedup of the generated units (cosine ≥ 0.90) → rubric for generated
units with no passing pair at the primary threshold (0.75) → metrics.
Coverage semantics: several generated units may cover one gold unit; Recall =
covered gold / 70; Precision = (matched generated + rubric-passed) / deduplicated
generated units. `rubric_pass` is added to Precision at the primary threshold only,
so Precision is comparable across the sweep only at that threshold.

### Models (models)

Stages S0–S7: syntax gate (a diagram must parse at validity 1.0 to be graded) →
element extraction and gold-inventory check → per-kind similarity → candidates →
staged Hungarian assignment → rule layer with type/guard ledgers → control checklist
(six items) → rubric → metrics. The gold files must themselves parse at validity
1.0, otherwise the run fails before touching the submission. A failed syntax gate
is a graded outcome (`n/a` semantics, exit 0), not a failure.

### VMX (vmx)

Two look-ups, no semantics. **Coverage**: a requirement counts when its VMX row
exists and its required columns are non-empty (`US-` needs `Domain-Req-ID` and
`Structural-Elements`; `NFR-` needs `Domain-Req-ID`), over the requirements in
`requirements.json`. **Integrity**: the share of VMX references that match, character
for character, a name declared in the submission (domain ids from `M1a.json`; classes,
enums and `Class.attribute` from `structural.puml`; actions from `behavioral.puml`).
Missing inputs give a defined outcome (`0` or `n/a`), never a failure.

---

## 5. Human review and resumability

Each module with a human step follows the same contract.

- **`run/` is a disposable cache.** Deleting it and rerunning gives identical
  results for the same `review/` answers.
- **`review/` is human-authored and never overwritten.** The module appends new
  empty question rows; a filled cell is never touched.
- **Exit codes** (module level): `0` DONE, `2` NEEDS_REVIEW (the path of the file to
  fill and the number of empty rows are printed), `1` FAILED (unreadable config or
  gold, unreachable judge). Through the pipeline, NEEDS_REVIEW and FAILED both show
  as a failed grading result with an explanatory message.
- **`--on-pending provisional`** (the pipeline default) never stops: unreviewed
  pairs take `manual_default` (`not_covered`), unscored rubric items count as
  failing, and the result is marked `provisional`. A result is `final` only when
  nothing is left open, whichever mode was asked for.

Review files:

| Module | File | Filled by the reviewer |
|---|---|---|
| reqs | `polarity_ledger.csv` | `verdict` PASS/FAIL |
| reqs, models | `rubric_human.csv` | `traceable`, `consistent` (yes/no) on a blind sample |
| models | `type_ledger.csv`, `guard_ledger.csv` | `verdict` PASS/FAIL |
| reqs, models | `rubric_llm.csv` | written by the judge; not a human input |

**Rubric and κ.** The LLM judge labels every unmatched item as *traceable* and
*consistent*, with a fixed prompt, `temperature` from the config, and every call
(prompt and raw reply) logged to `run/*judge_log.jsonl`. A human labels a
`kappa_sample_size` sample in a file with no column for the judge's labels. Cohen's
κ is computed on `traceable AND consistent`; `κ ≥ kappa_accept` (0.60) lets the
judge's labels stand. The judge model should come from a different family than the
generator.

---

## 6. Run directory and report

```
generated/<RUN>/
├── sdk_ChatDev_v1_<ts>_<ts>/          generator output, never edited
│   ├── code_workspace/                the five deliverables
│   └── execution_logs.json, node_outputs.yaml, token_usage_*.json, workflow_summary.yaml
├── grading/
│   ├── reqs/    submission/  run/ (00_units … 05_metrics, 06_judge_log.jsonl, manifest.json)  review/
│   ├── models/  submission/  run/ (00_syntax … 07_metrics, 08_judge_log.jsonl, syntax logs, manifest.json)  review/
│   └── vmx/     submission/  run/ (00_inputs … 03_metrics, manifest.json)
├── report_<RUN>.json                  raw report
└── report_<RUN>.txt                   rendered from the JSON
```

Every module's `manifest.json` records the rules used and the run's start and end
times; the Requirements and Models manifests also record the embedding model and
revision, the config (secrets removed) and the commit of the code, so a result can
be reconstructed from the run directory.

**Report.** `report_writer.py` keeps the run's report as JSON and merges each
invocation into it: running `--grade reqs` and later `--grade models` leaves both
in the report, running a module again replaces only its entry, and a grade-only
invocation does not overwrite the generation record. The text version is produced
only by `report_to_txt.py`, which can be run alone on any report file:

```bash
python report_to_txt.py generated/RUN_x/report_RUN_x.json [-o report.txt]
```

The text report has the generation record, an overview (embedding and judge model
used), one block per module with its headline metrics, and a verdict over all
modules in the report.

---

## 7. Configuration

`config.yaml` (git-ignored; copy `config.example.yaml`) is organized in six
sections. Shared keys sit at the top level so that one change applies to every
module.

| Section | Keys | Used by |
|---|---|---|
| 1. Run | `workdir`, `evaluation.generated`, `output.report_dir` | pipeline |
| 2. Generation | `agent.model`, `api_base`, `api_key`, `prompt_template`, `prompt_inputs`, `generated_dir` (others have no effect, see GENERATION_RUN.md) | generation |
| 3. Grading, shared | `embedding_model`, `embedding_revision`, `pooling`, `normalize_embeddings`; `judge_model`, `judge_api_base`, `judge_api_key`, `judge_temperature`, `judge_max_attempts`; `manual_default`, `kappa_sample_size`, `kappa_accept`, `random_seed` | reqs, models |
| 4. Per module | reqs: `requirement_grading.{threshold, sweep, dedup_threshold, allow_cross_kind, expected_gold_units}`; models: `threshold_models`, `sweep_models`, `syntax_gate`, `kappa_pool`; vmx: none (schema in `VMXGrading/rules.yaml`) | one module each |
| 5. Gold | `gold.{requirements, structural, behavioral, domain}` | all graders |
| 6. Pipeline analysis | `pipeline.*` | the `pipeline/` package only |

Rules and vocabularies that affect a number live in each module's `rules.yaml`,
never in source code. The judge key may be left empty and read from
`OPENROUTER_API_KEY` or `OPENAI_API_KEY` (by endpoint host). It is never written to
a manifest.

---

## 8. Tests

```bash
.venv/bin/python -m pytest tests                      # report writer and parser script
.venv/bin/python -m pytest evaluators/RequirementsGrading
.venv/bin/python -m pytest evaluators/ModelsGrading
.venv/bin/python -m pytest evaluators/VMXGrading
```

The Requirements and Models suites load the sentence-transformer model, so they
take minutes; the VMX suite is fast. No
test calls a live LLM: the judge is injected.

---

## 9. Known limits (state them when reporting results)

- **One generation run, nothing pinned.** The generator model tag is not a
  snapshot, no seed is set, and the temperature is ChatDev's 0.7. There is no tool
  yet that aggregates several runs.
- **Embedding revision is unpinned** (`embedding_revision: null`); the manifest
  records `null`. Pin it before a scored run.
- **Judge tag, not snapshot.** `judge_model` is a tag; for the paper, record a
  snapshot id if the provider offers one.
- **Review labels in the reference run.** The `rubric_human.csv` and ledger
  answers in `RUN_20261026_GPTOSS120B` were filled by an AI assistant at the
  authors' request, and in part after the judge's labels were visible, so the
  reported κ is not a blind agreement figure. Replace them with human labels, on a
  sample drawn afresh, before publishing κ.
- **ModelsGrading open items** (see its README): the type table is a draft,
  threshold 0.75 is inherited from Requirements and needs its own sensitivity
  analysis, `kappa_pool: pooled` is not supported yet, and the guard alias
  `approved` collides across two groups.
- **Rule-layer strictness.** The identifier axis in Requirements compares token sets
  for equality, so a paraphrase with one extra or missing noun can be rejected;
  `diagnostics.axis_rejections` counts these, and the rejected pairs are in
  `run/03_axis.json`.
- **Stage caching differs between modules.** Models keeps a stage's output file once
  written (`--force` rewrites it); Requirements caches only the embedding step (keyed by a digest of the
  texts and model) and recomputes the rest so that new review answers are always
  read.
