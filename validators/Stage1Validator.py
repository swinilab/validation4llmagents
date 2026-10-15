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

        artifact_dir = workspace / "artifact"
        artifact_dir.mkdir(parents=True, exist_ok=True)

        details: dict[str, Any] = {
            "workspace": str(workspace),
            "run_dir": str(workspace),
            "diagrams_found": [p.name for p in all_diagrams],
        }

        # 2. Metric 7: Diagram Validity & PNG rendering
        try:
            parse_result = run_parse_check(
                run_id=run_id,
                diagrams=all_diagrams,
                cfg=self.stage1_cfg,
                export_png=True,
                out_path=artifact_dir / f"{run_id}__parse_check.json",
                png_dir=artifact_dir / f"{run_id}__png",
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
                out_dir=artifact_dir,
            )
            details["flatten"] = flatten_result
        except Exception as exc:
            details["flatten_error"] = str(exc)

        # 4. Check overall pass status & component metrics
        components = parse_result.get("components", {})
        cl_info = components.get("class", {})
        ac_info = components.get("activity", {})

        cl_correct = cl_info.get("correct", 0)
        cl_total = cl_info.get("total", 0)
        cl_score = cl_info.get("score")
        if cl_score is None or isinstance(cl_score, str):
            try:
                cl_score = float(cl_score)
            except (ValueError, TypeError):
                cl_score = round(cl_correct / cl_total, 2) if cl_total > 0 else 0.0

        ac_correct = ac_info.get("correct", 0)
        ac_total = ac_info.get("total", 0)
        ac_score = ac_info.get("score")
        if ac_score is None or isinstance(ac_score, str):
            try:
                ac_score = float(ac_score)
            except (ValueError, TypeError):
                ac_score = round(ac_correct / ac_total, 2) if ac_total > 0 else 0.0

        details["valid_diagrams"] = valid_diagrams
        details["total_diagrams"] = total_diagrams
        details["class_score"] = cl_score
        details["class_correct"] = cl_correct
        details["class_total"] = cl_total
        details["act_score"] = ac_score
        details["act_correct"] = ac_correct
        details["act_total"] = ac_total

        passed = diagram_validity == 1.0 and valid_diagrams == total_diagrams
        msg = (
            f"1. SYNTAX CORRECTNESS: {valid_diagrams}/{total_diagrams} diagrams parsed: "
            f"structural score={cl_score} ({cl_correct}/{cl_total}), "
            f"behavioral score={ac_score} ({ac_correct}/{ac_total})"
        )

        return ValidationResult(
            stage=1,
            name="Stage 1 (Diagram & SRS Validity)",
            passed=passed,
            message=msg,
            details=details,
        )
