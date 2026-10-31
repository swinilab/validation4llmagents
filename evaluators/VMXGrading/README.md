# VMXGrading

Scores the generated `VMX.csv` (Verification / Traceability Matrix) on two
metrics defined in the M2 spec §1:

| Metric | Formula |
|---|---|
| **VMX Requirement Coverage** | requirements with a qualifying VMX row / total requirements in `requirements.json` |
| **VMX Referential Integrity** | VMX references that resolve to a declared requirement / total VMX references |

All checks are plain lookups — no embedding, no LLM judge, no human review.
Results are always deterministic and always marked `final`.

---

## Running

```bash
# From the pipeline
uv run main.py --phase grade --grade vmx

# Standalone (from repo root)
python -m evaluators.VMXGrading.run \
    --submission <dir> --out generated/<RUN> \
    [--run-id ID] [--config PATH]
```

`--submission` must contain `requirements.json`, `VMX.csv`,
`structural.puml`, and `behavioral.puml`.  
`--out` is the run directory (e.g. `generated/RUN_x`).  
All output goes to `<out>/grading/vmx/run/`.

Exit codes:

| Code | Meaning |
|---|---|
| `0` DONE | Metrics written |
| `1` FAILED | Unrecoverable error (config or domain input unreadable) |

A missing or malformed submission file is **not** `FAILED`: it is a graded
outcome. Coverage of a missing VMX is 0; integrity with no references is `n/a`.

---

## Coverage Rules

A requirement is counted as *covered* when it has at least one VMX row whose
`SRS-Req-ID` matches and the row satisfies the completeness rules from
`rules.yaml`:

- `US-*` rows must have a non-empty `Domain-Req-ID` and non-empty
  `Structural-Elements`.
- `NFR-*` rows must have a non-empty `Domain-Req-ID`.

---

## Inputs

| Input | Source |
|---|---|
| Domain requirement vocabulary | `config.yaml` → `gold.domain` |
| VMX schema rules | `evaluators/VMXGrading/rules.yaml` |
| Submission files | `--submission {requirements.json, VMX.csv, *.puml}` |

---

## Layout

```
VMXGrading/
  configload.py   Config and domain-input loading
  metrics.py      Coverage and integrity calculations
  table.py        VMX.csv parsing and validation
  vocab.py        Domain requirement ID vocabulary
  rules.yaml      Completeness rules per requirement kind
  run.py          Runner, exit codes, manifest
  tests/          Unit tests
```

Written at run time into the caller's run directory:

```
<out>/grading/vmx/
  run/    metrics.json, manifest.json, inputs.json
```
