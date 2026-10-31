# RequirementsGrading

Scores a generated `requirements.json` against the gold acceptance criteria
(`materials/G1-requirements.json`). Produces two primary metrics:

| Metric | Formula |
|---|---|
| **Requirement Recall** | matched gold units / total gold units |
| **Requirement Precision** | matched generated units / total generated units |

Matching is semantic: sentence embeddings → cosine similarity → threshold →
optional LLM rubric judge for borderline pairs → blind inter-rater κ sample.

---

## Running

```bash
# From the pipeline
uv run main.py --phase grade --grade reqs

# Standalone (from repo root)
python -m evaluators.RequirementsGrading.run \
    --submission <dir> --out generated/<RUN> \
    [--run-id ID] [--on-pending halt|provisional] \
    [--stage all|S0..S6] [--force]
```

`--submission` must contain `requirements.json`.  
`--out` is the run directory (e.g. `generated/RUN_x`).  
All output goes to `<out>/grading/reqs/{run,review}/`.

Exit codes:

| Code | Meaning |
|---|---|
| `0` DONE | All stages complete; metrics are final |
| `1` FAILED | Unrecoverable error (gold invalid, submission unreadable) |
| `2` NEEDS_REVIEW | A review file awaits human input; path printed to stdout |

---

## Pipeline Stages

| Stage | File | Description |
|---|---|---|
| S0 | `s0_units.py` | Parse `requirements.json`; extract text units |
| S1 | `s1_sim.py` | Compute sentence-embedding cosine matrix (cached) |
| S2 | `s2_candidates.py` | Select candidate pairs at `min(sweep)` threshold |
| S3 | `s3_axis.py` | Accept pairs at the primary `threshold` |
| S4 | `s4_dedup.py` | Intra-generation deduplication at `dedup_threshold` |
| S5 | `s5_rubric.py` | LLM rubric judge for unmatched items; blind κ sample |
| S6 | `s6_metrics.py` | Compute recall, precision, sweep, diagnostics; write manifest |

---

## Inputs

| Input | Source |
|---|---|
| Gold requirements | `config.yaml` → `gold.requirements` |
| Generated requirements | `--submission requirements.json` |
| Embedding model | `config.yaml` → `embedding_model` |
| LLM rubric judge | `config.yaml` → `judge_model` (null = disabled) |
| Thresholds & policy | `config.yaml` → `requirement_grading.*` |

---

## Layout

```
RequirementsGrading/
  config.py      Config loading and validation
  models.py      Data structures (Unit, Pair, MatchResult)
  run.py         Runner, exit codes, manifest
  rules.yaml     Module-level rules (kind vocabulary, cross-kind policy)
  stages/
    s0_units.py
    s1_sim.py
    s2_candidates.py
    s3_axis.py
    s4_dedup.py
    s5_rubric.py
    s6_metrics.py
  tests/         Acceptance tests
```

Written at run time into the caller's run directory (not in this folder):

```
<out>/grading/reqs/
  run/      Disposable cache (00–06, manifest.json, 06_judge_log.jsonl)
  review/   Human-authored rubric ledgers — keep with the run, do not delete
```

---

## Human Review

When a stage needs a human reviewer it writes a file under `review/`, returns
`NEEDS_REVIEW`, and the runner exits 2. Fill the file; the next run picks the
answers up and continues. The pipeline never blocks indefinitely.

With `--on-pending provisional`, unreviewed pairs are resolved with
`manual_default` from `config.yaml` and the result is marked *provisional*.

---

## LLM Judge

`s5_rubric.py` calls the judge model (pinned snapshot, must differ from the
generation model) for every unmatched gold or generated unit. With
`config.judge_model: null` there is no judge; unmatched items stay pending.

A blind κ sample is drawn from the judged pairs for inter-rater agreement.
`kappa_accept` in `config.yaml` sets the minimum accepted κ.
