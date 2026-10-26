"""VMXGradingEvaluator.py -- pipeline adapter around the VMXGrading module.

Checks the generated `VMX.csv` against the generated `requirements.json`, the two
diagrams and the domain input. The generated workspace is only read; everything
the module writes lands in `<run dir>/grading/vmx/`, next to the generator's
output.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evaluators.staging import DIAGRAM_PATTERNS, stage
from interfaces.base import GenerationResult, IValidator, ValidationResult

# File names the generator may use for the two non-diagram inputs.
_FILE_PATTERNS = {
    "requirements.json": ("requirements.json",),
    "VMX.csv": ("VMX.csv", "vmx.csv"),
}


class VMXGradingEvaluator(IValidator):
    """Runs `VMXGrading.run.grade` on the generated traceability matrix."""

    def __init__(self, config_path: str | Path = "config.yaml") -> None:
        self._config_path = Path(config_path)

    def validate(self, generation: GenerationResult, run_id: str = "RUN01",
                 on_pending: str | None = None) -> ValidationResult:
        # `on_pending` is accepted for a uniform grader interface: VMX grading is
        # fully automatic and never waits for a human.
        name = "VMX Grading (VMXGrading)"
        workspace = Path(generation.code)
        if not workspace.is_dir():
            return ValidationResult(
                stage=2, name=name, passed=False,
                message=f"Workspace directory not found: {workspace}",
                details={"grading_kind": "vmx"})

        from evaluators.VMXGrading.run import EXIT, WORKSPACE, grade

        out_dir = Path(generation.output_dir or workspace)
        grading_dir = out_dir / WORKSPACE
        submission = stage(workspace, grading_dir / "submission",
                           {**_FILE_PATTERNS, **DIAGRAM_PATTERNS})

        exit_code = grade(submission, out_dir, run_id=run_id,
                          config_path=self._config_path)

        metrics = self._read_json(grading_dir / "run" / "03_metrics.json")
        details: dict[str, Any] = {
            "grading_kind": "vmx", "exit_code": exit_code,
            "grading_dir": str(grading_dir), "metrics": metrics,
        }
        if exit_code != EXIT["DONE"]:
            return ValidationResult(
                stage=2, name=name, passed=False,
                message=f"VMXGrading exited with code {exit_code}",
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
