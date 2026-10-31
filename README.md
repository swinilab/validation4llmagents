# validation4llmagents

An empirical benchmarking pipeline that measures how well LLM agents produce
Software Requirements Specification (SRS) packages. One agent generates a full
SRS package from a prompt; three independent grading modules then score it
against a curated gold standard and write a consolidated report.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Repository Layout](#2-repository-layout)
3. [Evaluation Metrics](#3-evaluation-metrics)
4. [Prerequisites](#4-prerequisites)
5. [Configuration](#5-configuration)
6. [Running the Pipeline](#6-running-the-pipeline)
7. [Output Structure](#7-output-structure)
8. [Grading Modules](#8-grading-modules)
9. [Reporting](#9-reporting)
10. [Running Tests](#10-running-tests)

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
      ├─ phase gen ──► ChatDevGenerationAgent ──► generated/<RUN>/
      │                (prompt = M1-prompt.md + M1a.json)
      │                srs.md  structural.puml  behavioral.puml
      │                requirements.json  VMX.csv
      │
      ├─ phase grade ─► for each selected module, in order:
      │                   reqs   ─► RequirementsGrading ─► generated/<RUN>/grading/reqs/
      │                   models ─► ModelsGrading ──────► generated/<RUN>/grading/models/
      │                   vmx    ─► VMXGrading ──────────► generated/<RUN>/grading/vmx/
      │
      └─ report ──► generated/<RUN>/report_<RUN>.json
                    generated/<RUN>/report_<RUN>.txt
```

**Design principles:**

- The generated workspace is **read-only**. Graders copy files they need into
  `grading/<module>/submission/` and read only that copy.
- Everything about a run lives in one directory (`generated/<RUN>/`).
- Grading modules are **independent**: one crashing does not affect the others.
- Nothing blocks on input. A step that needs a human writes a review file and
  stops; re-running picks up the answers automatically.

---

## 2. Repository Layout

```
validation4llmagents/
│
├── main.py                   # CLI entry point
├── workflow_pipeline.py      # Orchestration: generate → grade → report
├── workflow_factory.py       # Build agent + graders + report writer from config
├── config.yaml               # Active configuration (git-ignored)
├── config.example.yaml       # Annotated template — copy to config.yaml
├── report_writer.py          # Writes report_<RUN>.json and .txt
├── report_to_txt.py          # Text renderer for the raw JSON report
├── report_summary.py         # Aggregates all runs into final_metrics.csv
│
├── agents/
│   └── gen.py                # ChatDevGenerationAgent (ChatDev SDK + direct API)
│
├── interfaces/
│   └── base.py               # Protocols and dataclasses: GenerationResult,
│                             #   ValidationResult, IGenerationAgent, IReportWriter
│
├── evaluators/
│   ├── staging.py            # Copies workspace files into grading/<module>/submission/
│   ├── RequirementsGradingEvaluator.py   # Pipeline adapter for RequirementsGrading
│   ├── ModelsGradingEvaluator.py         # Pipeline adapter for ModelsGrading
│   ├── VMXGradingEvaluator.py            # Pipeline adapter for VMXGrading
│   ├── RequirementsGrading/  # Requirements recall & precision (embedding + judge)
│   ├── ModelsGrading/        # Structural & behavioral recall, precision, syntax gate
│   └── VMXGrading/           # Traceability matrix coverage & referential integrity
│
├── materials/
│   ├── M1-prompt.md          # Generation prompt template
│   ├── M1a.json              # FR / NFR inputs injected into the prompt
│   ├── G1-requirements.json  # Gold standard — acceptance criteria
│   ├── G2-structural-model.puml  # Gold standard — class / structural diagram
│   ├── G3-behavioral-model.puml  # Gold standard — activity / behavioral diagram
│   └── G4-vmx.csv            # Gold standard — verification/traceability matrix
│
├── generated/                # All run outputs (git-ignored)
│   ├── <RUN>/
│   │   ├── srs.md
│   │   ├── requirements.json
│   │   ├── structural.puml
│   │   ├── behavioral.puml
│   │   ├── VMX.csv
│   │   ├── grading/{reqs,models,vmx}/
│   │   ├── report_<RUN>.json
│   │   └── report_<RUN>.txt
│   └── final_metrics.csv     # Aggregated metrics across all runs
│
├── tests/                    # Unit tests for report_writer and report_summary
├── tools/
│   └── plantuml.jar          # Used by the syntax gate in ModelsGrading
└── pyproject.toml
```

---

## 3. Evaluation Metrics

The pipeline measures ten metrics defined in the M2 spec, grouped into
**Completeness** and **Correctness**.

| Group | Metric | Description |
|---|---|---|
| Completeness | `requirement_recall` | Fraction of gold acceptance criteria matched by the agent |
| Completeness | `structural_semantic_recall` | Fraction of gold structural elements matched |
| Completeness | `behavioral_semantic_recall` | Fraction of gold behavioral elements matched |
| Completeness | `vmx_requirement_coverage` | Fraction of domain requirements linked in the VMX |
| Correctness | `requirement_precision` | Fraction of generated requirements matched to gold (penalises hallucination) |
| Correctness | `structural_semantic_precision` | Fraction of generated structural elements matched to gold |
| Correctness | `behavioral_semantic_precision` | Fraction of generated behavioral elements matched to gold |
| Correctness | `structural_syntax_validity` | PlantUML structural diagram compiles without error (0 or 1) |
| Correctness | `behavioral_syntax_validity` | PlantUML behavioral diagram compiles without error (0 or 1) |
| Correctness | `vmx_referential_integrity` | Fraction of VMX references that resolve to declared requirements |

Semantic recall and precision use cosine similarity of sentence embeddings
(`sentence-transformers/all-mpnet-base-v2`), an optional LLM rubric judge for
borderline pairs, and a blind inter-rater κ sample for quality control.

---

## 4. Prerequisites

- **Python ≥ 3.12**
- **Java** (for PlantUML syntax gate — `tools/plantuml.jar`)
- **uv** (recommended) or pip

Install dependencies:

```bash
# with uv (recommended)
uv sync

# or with pip
pip install -e .
```

Copy and edit the configuration:

```bash
cp config.example.yaml config.yaml
# then edit config.yaml — see §5 below
```

---

## 5. Configuration

All tuneable values live in `config.yaml`. No grading-relevant number may
appear in source code (spec §9.1).

Key sections:

| Section | Purpose |
|---|---|
| `agent` | Generation model endpoint, temperature, prompt paths |
| `embedding_model` | Sentence-transformer model for semantic similarity |
| `judge_model` | LLM judge for borderline pairs (must differ from `agent.model`; `null` disables) |
| `requirement_grading` | Cosine threshold, sensitivity sweep, dedup threshold |
| `threshold_models` / `sweep_models` | Primary threshold and sweep for ModelsGrading |
| `gold` | Paths to all four gold standard files |
| `evaluation.generated` | Run directory used by `--phase grade` |

Set API keys either in `config.yaml` or in a `.env` file:

```
OPENAI_API_KEY=...
OPENROUTER_API_KEY=...
```

---

## 6. Running the Pipeline

```bash
# Generate SRS package, then grade it
uv run main.py --phase all --run-id my-run-01

# Generation only
uv run main.py --phase gen --run-id my-run-01

# Grade an existing run (set evaluation.generated in config.yaml first)
uv run main.py --phase grade --grade reqs models vmx

# Print a summary table and write generated/final_metrics.csv
uv run main.py --phase summary
```

### CLI flags

| Flag | Default | Description |
|---|---|---|
| `--phase gen\|grade\|all\|summary` | `all` | Pipeline phase to execute |
| `--grade reqs models vmx` | all three | Grading modules to run (always in this order) |
| `--on-pending provisional\|halt` | `provisional` | `provisional`: unreviewed items use `manual_default`; result is marked provisional. `halt`: stop and write review files for a human |
| `--run-id ID` | `RUN_<timestamp>` | Name for the run directory and reports |
| `--prompt PATH` | `agent.prompt_template` | Override the generation prompt file |
| `--config PATH` | `config.yaml` | Path to the configuration YAML |
| `--out PATH` | `generated/final_metrics.csv` | CSV output path for `--phase summary` |

### Running a single grading module

Each module can be run standalone from the repository root:

```bash
python -m evaluators.RequirementsGrading.run \
    --submission <dir> --out generated/<RUN>

python -m evaluators.ModelsGrading.run \
    --submission <dir> --out generated/<RUN>

python -m evaluators.VMXGrading.run \
    --submission <dir> --out generated/<RUN>
```

---

## 7. Output Structure

After a complete run the directory looks like:

```
generated/<RUN>/
  srs.md
  requirements.json
  structural.puml
  behavioral.puml
  VMX.csv
  grading/
    reqs/
      submission/         staged copy of requirements.json
      run/                disposable cache (stages 0–6, manifest.json)
      review/             human-authored rubric ledgers (keep these)
    models/
      submission/         staged .puml files
      run/                disposable cache
      review/             human-authored type & guard ledgers, rubric_human.csv
    vmx/
      run/                metrics output (no review needed)
  report_<RUN>.json       raw merged report
  report_<RUN>.txt        rendered text report
```

---

## 8. Grading Modules

### RequirementsGrading (`--grade reqs`)

Scores `requirements.json` against the gold acceptance criteria
(`materials/G1-requirements.json`).

**Pipeline:** unit extraction (S0) → sentence-embedding similarity matrix (S1)
→ candidate pairs at the review threshold (S2) → cosine-axis acceptance at the
primary threshold (S3) → deduplication clustering (S4) → LLM rubric judge for
unmatched items (S5) → precision / recall metrics (S6).

Exit codes: `0` DONE · `1` FAILED · `2` NEEDS_REVIEW

### ModelsGrading (`--grade models`)

Scores `structural.puml` and `behavioral.puml` against the gold diagrams
(`materials/G2-*.puml`, `materials/G3-*.puml`).

**Pipeline:** PlantUML syntax gate (S0) → element extraction (S1) → per-kind
cosine similarity blocks (S2) → candidate pairs (S3) → staged Hungarian
assignment (S4) → rule-layer checks (S5) → control checklist (S6) → LLM
rubric for unmatched elements + blind κ sample (S7) → metrics (S8).

A failed syntax gate is a graded outcome (not an error): semantic metrics for
that diagram are reported as `n/a` and the run exits 0.

Exit codes: `0` DONE · `1` FAILED · `2` NEEDS_REVIEW

### VMXGrading (`--grade vmx`)

Scores `VMX.csv` on two metrics: requirement coverage and referential
integrity. All checks are plain lookups — no embedding, no judge, no human
review. Results are always deterministic and marked `final`.

Exit codes: `0` DONE · `1` FAILED

---

## 9. Reporting

### Per-run report

`report_writer.py` writes `report_<RUN>.json` (raw) and `report_<RUN>.txt`
(human-readable) into the run directory after every grading phase.

### Cross-run summary

```bash
uv run main.py --phase summary [--out generated/final_metrics.csv]
# or directly:
python report_summary.py generated [-o final_metrics.csv]
```

Produces one row per run with the ten metrics plus gate results, module
statuses, and κ statistics.

---

## 10. Running Tests

```bash
# Unit tests (report_writer, report_summary)
python -m pytest tests -q

# ModelsGrading acceptance tests
python -m pytest evaluators/ModelsGrading/tests -q

# RequirementsGrading acceptance tests
python -m pytest evaluators/RequirementsGrading/tests -q

# VMXGrading tests
python -m pytest evaluators/VMXGrading/tests -q
```
