"""Runner for the VMX grading module (M2-metrics §1).

    python -m evaluators.VMXGrading.run --submission <dir> --out <dir>
                  [--run-id ID] [--config PATH]

Run it from the repository root.

`--submission` holds `requirements.json`, `VMX.csv`, `structural.puml` and
`behavioral.puml`; `--out` is the run directory (e.g. `generated/RUN_x`). This
module keeps no workspace of its own: everything it writes goes to
`<out>/grading/vmx/run/`. The domain requirement ids come from `gold.domain` in
`config.yaml`.

The checks are plain look-ups: no embedding, no judge, no human review, so the
run is deterministic, always final, and never returns NEEDS_REVIEW.

Exit codes:

    DONE          0   metrics written
    FAILED        1   unrecoverable error (configuration or domain input unreadable)

A missing or malformed submission file is **not** FAILED: it is a graded
outcome, reported in `inputs`. Coverage of a missing VMX is 0 (measured, nothing
linked); integrity with no references is `n/a` (nothing to measure).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..ModelsGrading.configload import ConfigError as ModelsConfigError
from ..ModelsGrading.configload import load_rules as load_model_rules
from . import metrics, table, vocab
from .configload import ConfigError, load_domain_path, load_rules

DONE, FAILED = "DONE", "FAILED"
EXIT = {DONE: 0, FAILED: 1}

SECTION = Path(__file__).resolve().parent
ROOT = SECTION.parent.parent
MODEL_RULES = SECTION.parent / "ModelsGrading" / "rules.yaml"

# Folder created inside the caller's run directory; the only place this module
# writes to. Every grading module gets its own folder under `grading/`.
WORKSPACE = Path("grading") / "vmx"

OUTPUTS = {
    "inputs": "00_inputs.json",
    "coverage": "01_coverage.json",
    "integrity": "02_integrity.json",
    "metrics": "03_metrics.json",
}


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def grade(submission_dir: str | Path, out_dir: str | Path, *,
          run_id: str | None = None,
          config_path: str | Path | None = None) -> int:
    """Grade one submission's VMX and write `<out_dir>/grading/vmx/run/`."""
    started = _now()
    submission_dir = Path(submission_dir)
    run_dir = Path(out_dir) / WORKSPACE / "run"
    config_path = Path(config_path) if config_path else ROOT / "config.yaml"
    run_id = run_id or Path(out_dir).resolve().name

    try:
        rules = load_rules(SECTION / "rules.yaml")
        model_rules = load_model_rules(MODEL_RULES)
        domain_path = load_domain_path(config_path)
        domain_ids = vocab.domain_vocab(domain_path, rules["domain_sections"])
    except (ConfigError, ModelsConfigError, OSError, ValueError) as error:
        print(f"FAILED: {error}", file=sys.stderr)
        return EXIT[FAILED]

    if not submission_dir.is_dir():
        print(f"FAILED: submission directory not found: {submission_dir}",
              file=sys.stderr)
        return EXIT[FAILED]
    if not domain_ids:
        print(f"FAILED: {domain_path} holds no requirement ids under "
              f"{rules['domain_sections']}", file=sys.stderr)
        return EXIT[FAILED]

    files = {name: submission_dir / filename
             for name, filename in rules["submission_files"].items()}

    # --- S0 inputs and vocabularies ----------------------------------------
    inputs: dict[str, Any] = {"domain_path": str(domain_path),
                              "domain_ids": len(domain_ids)}

    requirement_ids: list[str] | None = None
    if files["requirements"].is_file():
        try:
            requirement_ids = table.read_requirement_ids(files["requirements"])
            inputs["requirements"] = {"status": "read",
                                      "count": len(requirement_ids)}
        except (OSError, ValueError) as error:
            inputs["requirements"] = {"status": "unreadable", "error": str(error)}
    else:
        inputs["requirements"] = {"status": "missing"}

    rows: list[table.Row] | None = None
    if files["vmx"].is_file():
        try:
            rows, schema = table.read_vmx(files["vmx"], rules)
            inputs["vmx"] = {"status": "read", "rows": len(rows), "schema": schema}
        except (OSError, ValueError) as error:
            inputs["vmx"] = {"status": "unreadable", "error": str(error)}
    else:
        inputs["vmx"] = {"status": "missing"}

    structural, inputs["structural"] = vocab.parse_vocab(
        files["structural"], "structural", model_rules)
    behavioral, inputs["behavioral"] = vocab.parse_vocab(
        files["behavioral"], "behavioral", model_rules)
    lookup = {"source": domain_ids, "structural": structural,
              "behavioral": behavioral}
    _write_json(run_dir / OUTPUTS["inputs"], inputs)

    # --- S1 coverage ---------------------------------------------------------
    cov = metrics.coverage(requirement_ids, rows, rules)
    _write_json(run_dir / OUTPUTS["coverage"], cov)

    # --- S2 integrity --------------------------------------------------------
    integ = metrics.integrity(rows, lookup)
    _write_json(run_dir / OUTPUTS["integrity"], integ)

    # --- S3 metrics ----------------------------------------------------------
    payload = {
        "run_id": run_id,
        "status": "final",
        "coverage": {k: cov[k] for k in ("score", "covered", "total")},
        "integrity": {k: integ[k] for k in ("score", "resolved", "total",
                                            "by_column")},
        "diagnostics": {
            "uncovered": [r for r in cov["requirements"]
                          if r["outcome"] != "covered"],
            "broken_references": len(integ["broken"]),
            "duplicate_rows": [r["id"] for r in cov["requirements"]
                               if r.get("duplicate_rows")],
            "rows_outside_requirements": sorted(
                {r.req_id for r in rows or []} - set(requirement_ids or [])),
        },
        "inputs": inputs,
    }
    _write_json(run_dir / OUTPUTS["metrics"], payload)
    _write_json(run_dir / "manifest.json", {
        "run_id": run_id, "submission_dir": str(submission_dir),
        "domain_path": str(domain_path), "rules": rules,
        "started_at": started, "finished_at": _now(),
    })

    print(f"VMX Requirement Coverage : {cov['score']} "
          f"({cov['covered']}/{cov['total']})")
    print(f"VMX Referential Integrity: {integ['score']} "
          f"({integ['resolved']}/{integ['total']})")
    print(DONE)
    return EXIT[DONE]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m evaluators.VMXGrading.run",
        description="M2 VMX grading (coverage and referential integrity)")
    parser.add_argument("--submission", required=True,
                        help="directory holding requirements.json, VMX.csv and "
                             "the two .puml files")
    parser.add_argument("--out", required=True,
                        help="run directory; results go to <out>/grading/vmx/")
    parser.add_argument("--run-id", default=None,
                        help="label for the manifest (default: name of --out)")
    parser.add_argument("--config", default=None,
                        help="config.yaml (default: the project's)")
    args = parser.parse_args(argv)
    return grade(args.submission, args.out, run_id=args.run_id,
                 config_path=args.config)


if __name__ == "__main__":
    raise SystemExit(main())
