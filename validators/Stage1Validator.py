"""Stage 1 Validator for SRS and PlantUML diagrams."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from interfaces.base import GenerationResult, IValidator, Status, ValidationResult
from pipeline.stage1.config import load_config
from pipeline.stage1.flatten import run_flatten
from pipeline.stage1.parse_check import run_parse_check


class Stage1Validator(IValidator):
    """Validates generated requirements and UML diagrams using Stage 1 analysis suite."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}
        self.stage1_cfg = load_config()

    def validate(self, generation: GenerationResult, run_id: str = "RUN01") -> ValidationResult:
        workspace = Path(generation.code)
        if not workspace.is_dir():
            return ValidationResult(
                stage=1,
                name="Stage 1 (Diagram & SRS Validity)",
                passed=False,
                message=f"Workspace directory not found: {workspace}",
            )

        # 1. Discover diagram files
        class_diagrams = list(workspace.glob("*class*.puml"))
        activity_diagrams = list(workspace.glob("*activity*.puml"))
        all_diagrams = list(workspace.glob("*.puml"))

        if not all_diagrams:
            return ValidationResult(
                stage=1,
                name="Stage 1 (Diagram & SRS Validity)",
                passed=False,
                message=f"No PlantUML diagrams found in {workspace}",
                details={"workspace": str(workspace)},
            )

        details: dict[str, Any] = {"workspace": str(workspace), "diagrams_found": [p.name for p in all_diagrams]}

        # 2. Metric 7: Diagram Validity & PNG rendering
        try:
            parse_result = run_parse_check(
                run_id=run_id,
                diagrams=all_diagrams,
                cfg=self.stage1_cfg,
                export_png=True,
            )
            details["parse_check"] = parse_result
            diagram_validity = parse_result.get("diagram_validity", 0.0)
            valid_diagrams = parse_result.get("valid_diagrams", 0)
            total_diagrams = parse_result.get("total_diagrams", len(all_diagrams))
        except Exception as exc:
            return ValidationResult(
                stage=1,
                name="Stage 1 (Diagram & SRS Validity)",
                passed=False,
                message=f"Diagram parse_check error: {exc}",
                details=details,
            )

        # 3. Flatten valid diagrams to CSV
        class_puml = class_diagrams[0] if class_diagrams else (all_diagrams[0] if len(all_diagrams) > 0 else None)
        act_puml = activity_diagrams[0] if activity_diagrams else (all_diagrams[1] if len(all_diagrams) > 1 else None)

        parse_check_json = Path(parse_result.get("out_path", ""))
        try:
            flatten_result = run_flatten(
                run_id=run_id,
                class_puml=class_puml,
                activity_puml=act_puml,
                parse_check=parse_check_json if parse_check_json.is_file() else None,
                cfg=self.stage1_cfg,
            )
            details["flatten"] = flatten_result
        except Exception as exc:
            details["flatten_error"] = str(exc)

        # 4. Check overall pass status
        passed = diagram_validity == 1.0 and valid_diagrams == total_diagrams
        msg = f"{valid_diagrams}/{total_diagrams} diagrams valid (score={diagram_validity:.3f})" if total_diagrams else "No diagrams"

        return ValidationResult(
            stage=1,
            name="Stage 1 (Diagram & SRS Validity)",
            passed=passed,
            message=msg,
            details=details,
        )
