"""ModelsGradingEvaluator.py — pipeline adapter around the ModelsGrading module.

Grades the generated structural / behavioral PlantUML against the gold models
named in the `gold:` section of config.yaml. The generated workspace is only
read; everything the module writes lands in `<run dir>/grading/models/`, next to
the generator's output.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evaluators.staging import DIAGRAM_PATTERNS, stage
from interfaces.base import GenerationResult, IValidator, ValidationResult

# By default a pipeline run does not stop for a human reviewer: unreviewed pairs
# are resolved with `manual_default` and the run is marked provisional.
# `--on-pending halt` makes the module stop and write the review files instead.
DEFAULT_ON_PENDING = "provisional"


class ModelsGradingEvaluator(IValidator):
    """Runs `ModelsGrading.run.grade` on the generated diagrams."""

    def __init__(self, config_path: str | Path = "config.yaml") -> None:
        self._config_path = Path(config_path)

    def validate(self, generation: GenerationResult, run_id: str = "RUN01",
                 on_pending: str = DEFAULT_ON_PENDING) -> ValidationResult:
        name = "Model Grading (ModelsGrading)"
        workspace = Path(generation.code)
        if not workspace.is_dir():
            return ValidationResult(
                stage=2, name=name, passed=False,
                message=f"Workspace directory not found: {workspace}",
                details={"grading_kind": "models"})

        # Imported here so the pipeline starts without the grading dependencies
        # (numpy, scipy, sentence-transformers) unless `--grade models` is used.
        from evaluators.ModelsGrading.run import EXIT, WORKSPACE, grade
        from evaluators.ModelsGrading.stages.s0_log import LOG_NAMES

        out_dir = Path(generation.output_dir or workspace)
        grading_dir = out_dir / WORKSPACE
        submission = stage(workspace, grading_dir / "submission", DIAGRAM_PATTERNS)

        exit_code = grade(submission, out_dir, run_id=run_id,
                          config_path=self._config_path, on_pending=on_pending)

        run_dir = grading_dir / "run"
        metrics = self._read_metrics(run_dir / "07_metrics.json")
        details: dict[str, Any] = {
            "grading_kind": "models", "exit_code": exit_code,
            "grading_dir": str(grading_dir), "metrics": metrics,
            "syntax": self._read_metrics(run_dir / "00_syntax.json"),
            "syntax_logs": {diagram: str(run_dir / name)
                            for diagram, name in LOG_NAMES.items()
                            if (run_dir / name).is_file()},
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
                message=f"ModelsGrading exited with code {exit_code}",
                details=details)
        return ValidationResult(
            stage=2, name=name, passed=True,
            message=f"status={metrics.get('status') if metrics else 'n/a'}",
            details=details)

    @staticmethod
    def _read_metrics(path: Path) -> dict[str, Any] | None:
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
