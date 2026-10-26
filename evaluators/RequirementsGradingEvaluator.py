"""RequirementsGradingEvaluator.py -- pipeline adapter around the RequirementsGrading module.

Grades the generated `requirements.json` against the gold requirements named in
the `gold:` section of config.yaml. The generated workspace is only read;
everything the module writes lands in `<run dir>/grading/reqs/`, next to the
generator's output.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evaluators.staging import stage
from interfaces.base import GenerationResult, IValidator, ValidationResult

# By default a pipeline run does not stop for a human reviewer: unreviewed pairs
# are resolved with `manual_default` and the run is marked provisional.
# `--on-pending halt` makes the module stop and write the review files instead.
DEFAULT_ON_PENDING = "provisional"


class RequirementsGradingEvaluator(IValidator):
    """Runs `RequirementsGrading.run.grade` on the generated requirements."""

    def __init__(self, config_path: str | Path = "config.yaml") -> None:
        self._config_path = Path(config_path)

    def validate(self, generation: GenerationResult, run_id: str = "RUN01",
                 on_pending: str = DEFAULT_ON_PENDING) -> ValidationResult:
        name = "Requirements Grading (RequirementsGrading)"
        workspace = Path(generation.code)
        if not workspace.is_dir():
            return ValidationResult(
                stage=2, name=name, passed=False,
                message=f"Workspace directory not found: {workspace}",
                details={"grading_kind": "reqs"})

        # Imported here so the pipeline starts without the grading dependencies
        # (numpy, sentence-transformers) unless `--grade reqs` is used.
        from evaluators.RequirementsGrading.run import (
            EXIT, METRICS_FILE, SUBMISSION_FILE, WORKSPACE, grade)

        out_dir = Path(generation.output_dir or workspace)
        grading_dir = out_dir / WORKSPACE
        submission = stage(workspace, grading_dir / "submission",
                           {SUBMISSION_FILE: (SUBMISSION_FILE,)})

        exit_code = grade(submission, out_dir, run_id=run_id,
                          config_path=self._config_path, on_pending=on_pending)

        metrics = self._read_json(grading_dir / "run" / METRICS_FILE)
        details: dict[str, Any] = {
            "grading_kind": "reqs", "exit_code": exit_code,
            "grading_dir": str(grading_dir), "metrics": metrics,
            "format_violations": (metrics or {}).get("diagnostics", {})
                                                 .get("format_violations", {}),
        }
        if exit_code == EXIT["NEEDS_REVIEW"]:
            return ValidationResult(
                stage=2, name=name, passed=False,
                message=("awaiting human review: fill "
                         f"{grading_dir / 'review'} then rerun with the same run id"),
                details=details)
        if exit_code != EXIT["DONE"]:
            return ValidationResult(
                stage=2, name=name, passed=False,
                message=f"RequirementsGrading exited with code {exit_code}",
                details=details)
        return ValidationResult(
            stage=2, name=name, passed=True,
            message=f"status={metrics.get('status') if metrics else 'n/a'}",
            details=details)

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any] | None:
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
