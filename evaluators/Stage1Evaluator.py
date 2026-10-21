"""Stage 1 Evaluator for SRS and PlantUML diagrams."""

from __future__ import annotations

import csv
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from interfaces.base import GenerationResult, IValidator, Status, ValidationResult
from pipeline.stage1.config import load_config
from pipeline.stage1.flatten import run_flatten
from pipeline.stage1.parse_check import run_parse_check


class Stage1Evaluator(IValidator):
    """Evaluates generated requirements and UML diagrams using Stage 1 analysis suite."""

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

        # 1. Discover artifacts directory (prefer artifacts/, fallback to workspace)
        artifacts_dir = workspace / "artifacts"
        if not artifacts_dir.is_dir():
            artifacts_dir = workspace

        # 2. Discover diagram files (new names first, fall back to legacy names)
        structural_diagrams = list(artifacts_dir.glob("*structural*.puml")) or list(artifacts_dir.glob("*class*.puml"))
        behavioral_diagrams = list(artifacts_dir.glob("*behavioral*.puml")) or list(artifacts_dir.glob("*activity*.puml"))
        all_diagrams = list(artifacts_dir.glob("*.puml"))

        if not structural_diagrams and all_diagrams:
            from pipeline.stage1.parse_check import detect_kind, KIND_CLASS
            structural_diagrams = [p for p in all_diagrams if detect_kind(p.read_text(encoding="utf-8", errors="replace")) == KIND_CLASS]
        if not behavioral_diagrams and all_diagrams:
            from pipeline.stage1.parse_check import detect_kind, KIND_ACTIVITY
            behavioral_diagrams = [p for p in all_diagrams if detect_kind(p.read_text(encoding="utf-8", errors="replace")) == KIND_ACTIVITY]

        if not all_diagrams:
            return ValidationResult(
                stage=1,
                name="Stage 1 (Diagram & SRS Validity)",
                passed=False,
                message=f"No PlantUML diagrams found in {artifacts_dir}",
                details={"workspace": str(workspace)},
            )

        # 3. Prepare target evaluation directories matching the research methodology diagram
        gradebook_dir = workspace / "gradebook"
        completeness_dir = workspace / "completeness"
        correctness_dir = workspace / "correctness"
        struct_syntax_dir = correctness_dir / "struct_syntax"
        behave_syntax_dir = correctness_dir / "behave_syntax"
        vmx_integrity_dir = correctness_dir / "vmx_referential_integrity"

        for d in (gradebook_dir, completeness_dir, struct_syntax_dir, behave_syntax_dir, vmx_integrity_dir):
            d.mkdir(parents=True, exist_ok=True)

        details: dict[str, Any] = {
            "workspace": str(workspace),
            "run_dir": str(workspace),
            "diagrams_found": [p.name for p in all_diagrams],
        }

        # 4. Metric 7: Diagram Validity & PNG rendering (into correctness/struct_syntax and behave_syntax)
        try:
            parse_check_json_path = correctness_dir / f"{run_id}__parse_check.json"
            parse_result = run_parse_check(
                run_id=run_id,
                diagrams=all_diagrams,
                cfg=self.stage1_cfg,
                export_png=True,
                out_path=parse_check_json_path,
                png_dir=correctness_dir / "_temp_png",
            )
            details["parse_check"] = parse_result
            diagram_validity = parse_result.get("diagram_validity", 0.0)
            valid_diagrams = parse_result.get("valid_diagrams", 0)
            total_diagrams = parse_result.get("total_diagrams", len(all_diagrams))

            # Distribute rendered PNGs into struct_syntax and behave_syntax directories
            temp_png_dir = correctness_dir / "_temp_png"
            if temp_png_dir.is_dir():
                for png_file in temp_png_dir.glob("*.png"):
                    lower_name = png_file.name.lower()
                    if "activity" in lower_name or "behavioral" in lower_name:
                        shutil.copy2(png_file, behave_syntax_dir / "behavioral.png")
                    elif "class" in lower_name or "structural" in lower_name:
                        shutil.copy2(png_file, struct_syntax_dir / "structural.png")
                shutil.rmtree(temp_png_dir, ignore_errors=True)

        except Exception as exc:
            return ValidationResult(
                stage=1,
                name="Stage 1 (Diagram & SRS Validity)",
                passed=False,
                message=f"Diagram parse_check error: {exc}",
                details=details,
            )

        # 5. Flatten valid diagrams to CSV
        class_puml = structural_diagrams[0] if structural_diagrams else (all_diagrams[0] if len(all_diagrams) > 0 else None)
        act_puml = behavioral_diagrams[0] if behavioral_diagrams else (all_diagrams[1] if len(all_diagrams) > 1 else None)

        try:
            flatten_temp_dir = correctness_dir / "_temp_flatten"
            flatten_temp_dir.mkdir(parents=True, exist_ok=True)
            flatten_result = run_flatten(
                run_id=run_id,
                class_puml=class_puml,
                activity_puml=act_puml,
                parse_check=parse_check_json_path if parse_check_json_path.is_file() else None,
                cfg=self.stage1_cfg,
                out_dir=flatten_temp_dir,
            )
            details["flatten"] = flatten_result

            # Move class elements to struct_syntax/ and activity elements to behave_syntax/
            for csv_file in flatten_temp_dir.glob("*.csv"):
                if "class-elements" in csv_file.name:
                    shutil.copy2(csv_file, struct_syntax_dir / "class-elements.csv")
                elif "activity-elements" in csv_file.name:
                    shutil.copy2(csv_file, behave_syntax_dir / "activity-elements.csv")
            shutil.rmtree(flatten_temp_dir, ignore_errors=True)

        except Exception as exc:
            details["flatten_error"] = str(exc)

        # 6. Check component metrics for syntax
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

        # Save syntax metrics summaries into struct_syntax and behave_syntax
        (struct_syntax_dir / "syntax_summary.json").write_text(
            json.dumps({"valid": cl_score == 1.0, "score": cl_score, "correct_elements": cl_correct, "total_elements": cl_total}, indent=2),
            encoding="utf-8",
        )
        (behave_syntax_dir / "syntax_summary.json").write_text(
            json.dumps({"valid": ac_score == 1.0, "score": ac_score, "correct_elements": ac_correct, "total_elements": ac_total}, indent=2),
            encoding="utf-8",
        )

        # 7. VMX Traceability Check (Completeness & Correctness)
        vmx_path = artifacts_dir / "VMX.csv"
        if not vmx_path.is_file():
            vmx_path = workspace / "VMX.csv"

        dom_inputs_path = Path(self.config.get("agent", {}).get("prompt_inputs", "prompts/prompt_inputs.json"))
        if not dom_inputs_path.is_file():
            dom_inputs_path = Path("materials/G1a-prompt-inputs.json")

        vmx_completeness: dict[str, Any] = {}
        vmx_correctness: dict[str, Any] = {}

        if vmx_path.is_file() and dom_inputs_path.is_file():
            try:
                vmx_scripts_dir = str(Path("materials/vmx_grading_scripts").resolve())
                if vmx_scripts_dir not in sys.path:
                    sys.path.insert(0, vmx_scripts_dir)
                from grade_vmx import behavioral_vocab, cells, structural_vocab

                dom = json.loads(dom_inputs_path.read_text(encoding="utf-8"))
                source_vocab = set(dom.get("FR_INPUT", {})) | set(dom.get("NFR_INPUT", {}))
                st_vocab = structural_vocab(class_puml) if class_puml and Path(class_puml).is_file() else set()
                bh_vocab = behavioral_vocab(act_puml) if act_puml and Path(act_puml).is_file() else set()

                rows = list(csv.reader(vmx_path.open(encoding="utf-8")))
                body = [r for r in rows[1:] if any(v.strip() for v in r)]
                complete, incomplete = 0, []
                found, total, broken = 0, 0, []
                for row in body:
                    rid, src, st, bh = cells(row)[:4]
                    if rid.startswith("NFR-"):
                        ok = bool(src)
                        need = "Source"
                    else:
                        ok = bool(src) and bool(st)
                        need = "Source + Structural"
                    complete += ok
                    if not ok:
                        incomplete.append(f"{rid} (needs {need})")
                    for cell, vocab, label in (
                        (src, source_vocab, "source"),
                        (st, st_vocab, "structural"),
                        (bh, bh_vocab, "behavioral"),
                    ):
                        for ref in filter(None, (v.strip() for v in cell.split(";"))):
                            total += 1
                            if ref in vocab:
                                found += 1
                            else:
                                broken.append(f"{rid} [{label}] {ref!r}")

                # Output into completeness/vmx_reqs_coverage.json
                coverage_score = round(complete / len(body), 4) if body else 0.0
                vmx_completeness = {
                    "metric": "VMX Requirement Coverage",
                    "score": coverage_score,
                    "coverage_rate": coverage_score,
                    "complete_rows": complete,
                    "total_rows": len(body),
                    "incomplete": incomplete,
                }
                (completeness_dir / "vmx_reqs_coverage.json").write_text(
                    json.dumps(vmx_completeness, indent=2), encoding="utf-8"
                )

                # Output into correctness/vmx_referential_integrity/vmx_integrity.json
                integrity_score = round(found / total, 4) if total else 0.0
                vmx_correctness = {
                    "metric": "VMX Referential Integrity",
                    "score": integrity_score,
                    "integrity_rate": integrity_score,
                    "found_references": found,
                    "total_references": total,
                    "broken": broken,
                }
                (vmx_integrity_dir / "vmx_integrity.json").write_text(
                    json.dumps(vmx_correctness, indent=2), encoding="utf-8"
                )

                details["vmx"] = {
                    "rows": len(body),
                    "coverage_complete": complete,
                    "coverage_rate": coverage_score,
                    "integrity_found": found,
                    "integrity_total": total,
                    "integrity_rate": integrity_score,
                    "incomplete": incomplete,
                    "broken": broken,
                }

            except Exception as vmx_err:
                details["vmx_error"] = str(vmx_err)

        # 8. Load into Gradebook (gradebook/gradebook_<RUN_ID>.json)
        gradebook_payload = {
            "run_id": run_id,
            "timestamp": datetime.now().isoformat(),
            "completeness": {
                "vmx_reqs_coverage": vmx_completeness,
            },
            "correctness": {
                "struct_syntax": {
                    "valid": cl_score == 1.0,
                    "score": cl_score,
                    "correct_elements": cl_correct,
                    "total_elements": cl_total,
                },
                "behave_syntax": {
                    "valid": ac_score == 1.0,
                    "score": ac_score,
                    "correct_elements": ac_correct,
                    "total_elements": ac_total,
                },
                "vmx_referential_integrity": vmx_correctness,
            },
        }
        (gradebook_dir / f"gradebook_{run_id}.json").write_text(
            json.dumps(gradebook_payload, indent=2), encoding="utf-8"
        )
        details["gradebook"] = str(gradebook_dir / f"gradebook_{run_id}.json")

        passed = diagram_validity == 1.0 and valid_diagrams == total_diagrams
        msg = (
            f"1. SYNTAX CORRECTNESS: {valid_diagrams}/{total_diagrams} diagrams parsed: "
            f"structural score={cl_score} ({cl_correct}/{cl_total}), "
            f"behavioral score={ac_score} ({ac_correct}/{ac_total})"
        )
        if "vmx" in details:
            vmx_d = details["vmx"]
            msg += (
                f"; 2. TRACEABILITY: coverage={int(vmx_d['coverage_rate']*100)}% "
                f"({vmx_d['coverage_complete']}/{vmx_d['rows']}), "
                f"integrity={int(vmx_d['integrity_rate']*100)}% "
                f"({vmx_d['integrity_found']}/{vmx_d['integrity_total']})"
            )

        return ValidationResult(
            stage=1,
            name="Stage 1 (Diagram & SRS Validity)",
            passed=passed,
            message=msg,
            details=details,
        )
