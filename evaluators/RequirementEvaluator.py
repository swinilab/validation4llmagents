"""RequirementEvaluator.py — Evaluator wrapper around RequirementGrading module."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from interfaces.base import GenerationResult, IValidator, Status, ValidationResult
from RequirementGrading.run import run_pipeline


class RequirementEvaluator(IValidator):
    """Evaluates generated requirements against gold standards using RequirementGrading."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}

    def validate(self, generation: GenerationResult, run_id: str = "RUN01") -> ValidationResult:
        workspace = Path(generation.code)
        sub_path = workspace / "artifacts" / "requirements.json"
        if not sub_path.is_file():
            sub_path = workspace / "requirements.json"

        if not sub_path.is_file():
            return ValidationResult(
                stage=1,
                name="Requirement Grading (Recall & Precision)",
                passed=False,
                message=f"requirements.json not found in {workspace}",
                details={"missing": True},
            )

        # Run pipeline in provisional mode so it never blocks
        exit_code = run_pipeline(
            run_id=run_id,
            submission_path=sub_path,
            on_pending="provisional",
            stage="all",
            force=False,
        )

        metrics_file = Path("RequirementGrading/run") / run_id / "05_metrics.json"
        if metrics_file.is_file():
            metrics = json.loads(metrics_file.read_text(encoding="utf-8"))
            primary = metrics.get("primary_threshold", 0.75)
            primary_row = next(
                (r for r in metrics.get("sweep", []) if abs(r["threshold"] - primary) < 1e-4),
                None,
            )
            rec = primary_row["recall"] if primary_row else 0.0
            prec = primary_row["precision"] if primary_row else 0.0
            f1 = primary_row["f1"] if primary_row else 0.0

            msg = f"Requirement Recall={rec:.2%}, Precision={prec:.2%}, F1={f1:.4f} (threshold={primary})"
            passed = (rec > 0.5 and prec > 0.5)

            return ValidationResult(
                stage=1,
                name="Requirement Grading (Recall & Precision)",
                passed=passed,
                message=msg,
                details=metrics,
            )

        return ValidationResult(
            stage=1,
            name="Requirement Grading (Recall & Precision)",
            passed=(exit_code == 0),
            message=f"Pipeline exited with code {exit_code}",
            details={"exit_code": exit_code},
        )
