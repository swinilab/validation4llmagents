"""ModelGradingEvaluator.py — pipeline adapter around the GradingModels module.

Grades the generated structural / behavioral PlantUML against the gold models
named in the `gold:` section of config.yaml. The generated workspace is only
read; everything the module writes lands in `<run dir>/grading_models/`, next to
the generator's output.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

from interfaces.base import GenerationResult, IValidator, ValidationResult

# GradingModels is a sibling package of this file, imported as a top-level one.
_EVALUATORS_DIR = str(Path(__file__).resolve().parent)

# Name patterns the generator may use for each diagram, first match wins.
_DIAGRAM_PATTERNS = {
    "structural": ("*structural*.puml", "*class*.puml"),
    "behavioral": ("*behavioral*.puml", "*activity*.puml"),
}

# A pipeline run cannot stop to wait for a human reviewer, so unreviewed pairs
# are resolved with `manual_default` and the run is marked provisional.
_ON_PENDING = "provisional"


class ModelGradingEvaluator(IValidator):
    """Runs `GradingModels.run.grade` on the generated diagrams."""

    def __init__(self, config_path: str | Path = "config.yaml") -> None:
        self._config_path = Path(config_path)

    def validate(self, generation: GenerationResult,
                 run_id: str = "RUN01") -> ValidationResult:
        name = "Model Grading (GradingModels)"
        workspace = Path(generation.code)
        if not workspace.is_dir():
            return ValidationResult(
                stage=2, name=name, passed=False,
                message=f"Workspace directory not found: {workspace}",
                details={"grading_kind": "models"})

        if _EVALUATORS_DIR not in sys.path:
            sys.path.insert(0, _EVALUATORS_DIR)
        from GradingModels.run import EXIT, GRADING_DIR, grade

        out_dir = Path(generation.output_dir or workspace)
        grading_dir = out_dir / GRADING_DIR
        submission = self._stage_submission(workspace, grading_dir / "submission")

        exit_code = grade(submission, out_dir, run_id=run_id,
                          config_path=self._config_path, on_pending=_ON_PENDING)

        metrics = self._read_metrics(grading_dir / "run" / "07_metrics.json")
        details: dict[str, Any] = {
            "grading_kind": "models", "exit_code": exit_code,
            "grading_dir": str(grading_dir), "metrics": metrics,
        }
        if exit_code != EXIT["DONE"]:
            return ValidationResult(
                stage=2, name=name, passed=False,
                message=f"GradingModels exited with code {exit_code}",
                details=details)
        return ValidationResult(
            stage=2, name=name, passed=True,
            message=f"status={metrics.get('status') if metrics else 'n/a'}",
            details=details)

    @staticmethod
    def _stage_submission(workspace: Path, target: Path) -> Path:
        """Copy the diagrams under the names the module expects.

        The generated workspace is left untouched; a diagram the generator did
        not produce is simply absent, which the module grades as `n/a`.
        """
        source = workspace / "artifacts"
        if not source.is_dir():
            source = workspace
        shutil.rmtree(target, ignore_errors=True)
        target.mkdir(parents=True, exist_ok=True)
        for diagram, patterns in _DIAGRAM_PATTERNS.items():
            for pattern in patterns:
                found = sorted(source.glob(pattern))
                if found:
                    shutil.copy2(found[0], target / f"{diagram}.puml")
                    break
        return target

    @staticmethod
    def _read_metrics(path: Path) -> dict[str, Any] | None:
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
