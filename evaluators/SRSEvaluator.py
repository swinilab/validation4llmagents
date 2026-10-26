"""SRS Evaluator for requirements and PlantUML diagrams."""

from __future__ import annotations

import csv
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from interfaces.base import GenerationResult, IValidator, Status, ValidationResult
from pipeline.config import load_config
from pipeline.flatten import run_flatten
from pipeline.parse_check import run_parse_check


class SRSEvaluator(IValidator):
    """Evaluates generated requirements and UML diagrams using pipeline analysis suite."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}
        self.pipeline_cfg = load_config()

    @property
    def stage1_cfg(self):
        return self.pipeline_cfg

    def validate(self, generation: GenerationResult, run_id: str = "RUN01") -> ValidationResult:
        workspace = Path(generation.code)
        if not workspace.is_dir():
            return ValidationResult(
                stage=1,
                name="Diagram & SRS Validity",
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
            from pipeline.parse_check import detect_kind, KIND_CLASS
            structural_diagrams = [p for p in all_diagrams if detect_kind(p.read_text(encoding="utf-8", errors="replace")) == KIND_CLASS]
        if not behavioral_diagrams and all_diagrams:
            from pipeline.parse_check import detect_kind, KIND_ACTIVITY
            behavioral_diagrams = [p for p in all_diagrams if detect_kind(p.read_text(encoding="utf-8", errors="replace")) == KIND_ACTIVITY]

        if not all_diagrams:
            return ValidationResult(
                stage=1,
                name="Diagram & SRS Validity",
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
                cfg=self.pipeline_cfg,
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

            # Generate line-by-line syntax audit for each diagram
            syntax_audits = []
            for diag_info in parse_result.get("diagrams", []):
                d_path_str = diag_info.get("path", "")
                d_file = Path(d_path_str)
                if not d_file.is_file():
                    for cand in all_diagrams:
                        if cand.name == d_file.name or str(cand).endswith(d_file.name):
                            d_file = cand
                            break

                lines = d_file.read_text(encoding="utf-8", errors="replace").splitlines() if d_file.is_file() else []
                violations = diag_info.get("violations", [])
                viol_by_line: dict[int, list[str]] = {}
                for v in violations:
                    l_num = v.get("line")
                    msg = f"[{v.get('rule_id', 'ERROR')}] {v.get('message', '')}"
                    if l_num is not None:
                        viol_by_line.setdefault(l_num, []).append(msg)
                    else:
                        viol_by_line.setdefault(0, []).append(msg)

                line_records = []
                for line_no, raw_line in enumerate(lines, start=1):
                    clean_line = raw_line.rstrip()
                    if line_no in viol_by_line:
                        line_status = "FAIL"
                        line_msg = "; ".join(viol_by_line[line_no])
                    else:
                        line_status = "PASS"
                        line_msg = "-"
                    line_records.append({
                        "line": line_no,
                        "text": clean_line,
                        "status": line_status,
                        "message": line_msg,
                    })

                d_kind = diag_info.get("kind", "unknown")
                fname = d_file.name
                is_struct = (d_kind == "class") or ("struct" in fname.lower()) or ("class" in fname.lower())
                is_behave = (d_kind == "activity") or ("behave" in fname.lower()) or ("activity" in fname.lower())

                audit_item = {
                    "file_name": fname,
                    "path": str(d_file),
                    "kind": d_kind,
                    "is_structural": is_struct,
                    "is_behavioral": is_behave,
                    "valid": diag_info.get("valid", False),
                    "parse_ok": diag_info.get("parse_ok", False),
                    "score": diag_info.get("component_score", 0.0),
                    "correct_elements": diag_info.get("correct_elements", 0),
                    "total_elements": diag_info.get("total_elements", 0),
                    "syntax_components": diag_info.get("syntax_components", "0/0"),
                    "syntax_error": diag_info.get("syntax_error"),
                    "rules": diag_info.get("rules", []),
                    "violations": violations,
                    "general_errors": viol_by_line.get(0, []),
                    "lines": line_records,
                }
                syntax_audits.append(audit_item)

                if is_struct:
                    (struct_syntax_dir / "syntax_audit.json").write_text(
                        json.dumps(audit_item, indent=2), encoding="utf-8"
                    )
                if is_behave:
                    (behave_syntax_dir / "syntax_audit.json").write_text(
                        json.dumps(audit_item, indent=2), encoding="utf-8"
                    )

            details["syntax_audits"] = syntax_audits

        except Exception as exc:
            return ValidationResult(
                stage=1,
                name="Diagram & SRS Validity",
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
                cfg=self.pipeline_cfg,
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

        dom_inputs_path = Path(self.config.get("agent", {}).get("prompt_inputs", "materials/G1a-prompt-inputs.json"))
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
                row_audits = []

                for row_idx, row in enumerate(body, start=1):
                    rid, src, st, bh = cells(row)[:4]
                    is_nfr = rid.startswith("NFR-")
                    if is_nfr:
                        ok = bool(src)
                        need = "Source"
                    else:
                        ok = bool(src) and bool(st)
                        need = "Source + Structural"
                    complete += ok
                    if not ok:
                        incomplete.append(f"{rid} (needs {need})")

                    src_refs = [v.strip() for v in src.split(";") if v.strip()]
                    st_refs = [v.strip() for v in st.split(";") if v.strip()]
                    bh_refs = [v.strip() for v in bh.split(";") if v.strip()]

                    src_checks = []
                    for ref in src_refs:
                        total += 1
                        valid = ref in source_vocab
                        if valid:
                            found += 1
                        else:
                            broken.append(f"{rid} [source] {ref!r}")
                        src_checks.append({"ref": ref, "valid": valid})

                    st_checks = []
                    for ref in st_refs:
                        total += 1
                        valid = ref in st_vocab
                        if valid:
                            found += 1
                        else:
                            broken.append(f"{rid} [structural] {ref!r}")
                        st_checks.append({"ref": ref, "valid": valid})

                    bh_checks = []
                    for ref in bh_refs:
                        total += 1
                        valid = ref in bh_vocab
                        if valid:
                            found += 1
                        else:
                            broken.append(f"{rid} [behavioral] {ref!r}")
                        bh_checks.append({"ref": ref, "valid": valid})

                    src_ok = all(c["valid"] for c in src_checks) if src_checks else (not is_nfr or bool(src))
                    st_ok = all(c["valid"] for c in st_checks) if st_checks else True
                    bh_ok = all(c["valid"] for c in bh_checks) if bh_checks else True

                    row_pass = ok and all(c["valid"] for c in (src_checks + st_checks + bh_checks))

                    reasons = []
                    if not ok:
                        reasons.append(f"Missing mapping (needs {need})")
                    for c in src_checks:
                        if not c["valid"]:
                            reasons.append(f"[SRC] '{c['ref']}' not in domain inputs")
                    for c in st_checks:
                        if not c["valid"]:
                            reasons.append(f"[STR] '{c['ref']}' not in structural model")
                    for c in bh_checks:
                        if not c["valid"]:
                            reasons.append(f"[BEH] '{c['ref']}' not in behavioral model")

                    row_audits.append({
                        "row": row_idx,
                        "req_id": rid,
                        "passed": row_pass,
                        "completeness_pass": ok,
                        "completeness_need": need,
                        "src_pass": src_ok,
                        "st_pass": st_ok,
                        "bh_pass": bh_ok,
                        "has_src": bool(src_refs),
                        "has_st": bool(st_refs),
                        "has_bh": bool(bh_refs),
                        "src_refs": src_checks,
                        "st_refs": st_checks,
                        "bh_refs": bh_checks,
                        "detail": "; ".join(reasons) if reasons else "All references resolved",
                    })

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
                (vmx_integrity_dir / "vmx_row_audits.json").write_text(
                    json.dumps(row_audits, indent=2), encoding="utf-8"
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
                    "missing": False,
                    "row_audits": row_audits,
                }

            except Exception as vmx_err:
                details["vmx_error"] = str(vmx_err)
        else:
            # VMX.csv is missing
            vmx_completeness = {
                "metric": "VMX Requirement Coverage",
                "score": 0.0,
                "coverage_rate": 0.0,
                "complete_rows": 0,
                "total_rows": 0,
                "incomplete": ["VMX.csv not found"],
                "missing": True,
            }
            (completeness_dir / "vmx_reqs_coverage.json").write_text(
                json.dumps(vmx_completeness, indent=2), encoding="utf-8"
            )

            vmx_correctness = {
                "metric": "VMX Referential Integrity",
                "score": 0.0,
                "integrity_rate": 0.0,
                "found_references": 0,
                "total_references": 0,
                "broken": ["VMX.csv not found"],
                "missing": True,
            }
            (vmx_integrity_dir / "vmx_integrity.json").write_text(
                json.dumps(vmx_correctness, indent=2), encoding="utf-8"
            )

            details["vmx"] = {
                "rows": 0,
                "coverage_complete": 0,
                "coverage_rate": 0.0,
                "integrity_found": 0,
                "integrity_total": 0,
                "integrity_rate": 0.0,
                "incomplete": ["VMX.csv not found"],
                "broken": ["VMX.csv not found"],
                "missing": True,
                "row_audits": [],
            }

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

        passed = (
            diagram_validity == 1.0
            and valid_diagrams == total_diagrams
            and not details.get("vmx", {}).get("missing", False)
        )
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
            name="Diagram & SRS Validity",
            passed=passed,
            message=msg,
            details=details,
        )


Stage1Evaluator = SRSEvaluator  # Backward compatibility alias
