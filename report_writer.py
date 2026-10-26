"""report_writer.py — Dual-file report writer for pipeline evaluation.

Generates two synchronized output reports:
  1. report_<run_id>.txt          — High-level summary report (verdict, metrics, pass/fail)
  2. report_<run_id>_details.txt  — Comprehensive line-by-line and row-by-row audit log
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from interfaces.base import (
    GenerationResult,
    IReportWriter,
    Status,
    ValidationResult,
)


class TextReportWriter(IReportWriter):

    def __init__(self, report_dir: str = "generated/reports/") -> None:
        self._report_dir = report_dir
        self._path: str | None = None
        self._details_path: str | None = None

    def write(
        self,
        generation: GenerationResult | None,
        validation_results: list[ValidationResult],
        all_passed: bool,
        run_id: str | None = None,
    ) -> str:
        # Determine target directory: prefer generation output_dir, then validation run_dir, fallback to report_dir
        run_dir = None
        if generation and generation.output_dir and Path(generation.output_dir).is_dir():
            run_dir = str(generation.output_dir)
        elif validation_results:
            run_dir = next(
                (
                    vr.details.get("run_dir")
                    for vr in validation_results
                    if vr.details and vr.details.get("run_dir")
                ),
                None,
            )

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        if run_dir:
            base_dir = run_dir
            report_name = f"report_{run_id}.txt" if run_id else "report.txt"
            details_name = f"report_{run_id}_details.txt" if run_id else "report_details.txt"
        else:
            base_dir = self._report_dir
            report_name = f"report_{run_id}.txt" if run_id else f"report_{ts}.txt"
            details_name = f"report_{run_id}_details.txt" if run_id else f"report_{ts}_details.txt"

        self._path = os.path.join(base_dir, report_name)
        self._details_path = os.path.join(base_dir, details_name)
        os.makedirs(base_dir, exist_ok=True)

        target_display = str(Path(run_dir if run_dir else base_dir)).replace("\\", "/")

        # 1. Build summary report
        summary_text = self._build_summary(
            generation=generation,
            validation_results=validation_results,
            all_passed=all_passed,
            run_id=run_id or "RUN01",
            target_dir=target_display,
            details_filename=details_name,
        )
        with open(self._path, "w", encoding="utf-8") as f:
            f.write(summary_text)

        # 2. Build detailed line-by-line audit report
        details_text = self._build_details(
            generation=generation,
            validation_results=validation_results,
            all_passed=all_passed,
            run_id=run_id or "RUN01",
            target_dir=target_display,
        )
        with open(self._details_path, "w", encoding="utf-8") as f:
            f.write(details_text)

        return self._path

    def _build_summary(
        self,
        generation: GenerationResult | None,
        validation_results: list[ValidationResult],
        all_passed: bool,
        run_id: str,
        target_dir: str,
        details_filename: str,
    ) -> str:
        lines: list[str] = [
            "=" * 80,
            f"PIPELINE EVALUATION REPORT — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Run ID: {run_id} | Target: {target_dir}",
            "=" * 80,
            "",
        ]

        # Phase 1: Generation
        lines.append("PHASE 1: GENERATION")
        lines.append("-" * 80)
        if generation is None:
            lines.append("skipped (phase not run)")
        elif generation.status is Status.PASS:
            agent_name = (generation.metadata.get("agent") if generation.metadata else None) or "ChatDev"
            reasoning = (generation.metadata.get("reasoning") if generation.metadata else None) or "standard"
            srs_package = str(Path(generation.code)).replace("\\", "/")
            lines.append(f"LLM         : {generation.model}")
            lines.append(f"Reasoning   : {reasoning}".rstrip())
            lines.append(f"Agent       : {agent_name}")
            lines.append(f"SRS Package : {srs_package}")
        else:
            agent_name = (generation.metadata.get("agent") if generation.metadata else None) or "ChatDev"
            reasoning = (generation.metadata.get("reasoning") if generation.metadata else None) or "standard"
            srs_package = str(Path(generation.code)).replace("\\", "/")
            lines.append("❌ Generation failed.")
            lines.append(f"LLM         : {generation.model}")
            lines.append(f"Reasoning   : {reasoning}".rstrip())
            lines.append(f"Agent       : {agent_name}")
            lines.append(f"SRS Package : {srs_package}")
        lines.append("")

        # Phase 2: Evaluation Summary
        lines.append("PHASE 2: EVALUATION SUMMARY")
        lines.append("-" * 80)

        for vr in validation_results:
            d = vr.details or {}
            if d.get("grading_kind"):
                continue
            syntax_audits = d.get("syntax_audits", [])
            struct_audit = next((a for a in syntax_audits if a.get("is_structural")), None)
            behave_audit = next((a for a in syntax_audits if a.get("is_behavioral")), None)

            # Structural diagram
            cl_corr = d.get("class_correct", 0)
            cl_tot = d.get("class_total", 0)
            cl_score = d.get("class_score")
            if cl_score is None:
                cl_score = round(cl_corr / cl_tot, 2) if cl_tot else 0.0
            cl_is_valid = struct_audit.get("valid", False) if struct_audit else (cl_score == 1.0 and cl_tot > 0)
            cl_status = "✅ PASS" if cl_is_valid else "❌ FAIL"
            struct_name = struct_audit.get("file_name", "structural.puml") if struct_audit else "structural.puml"
            lines.append(
                f"[STRUCTURAL DIAGRAM] {struct_name} (Parse: {cl_status} | Score: {cl_score:.2f} | Number of Elements: {cl_corr}/{cl_tot})"
            )

            # Behavioral diagram
            ac_corr = d.get("act_correct", 0)
            ac_tot = d.get("act_total", 0)
            ac_score = d.get("act_score")
            if ac_score is None:
                ac_score = round(ac_corr / ac_tot, 2) if ac_tot else 0.0
            ac_is_valid = behave_audit.get("valid", False) if behave_audit else (ac_score == 1.0 and ac_tot > 0)
            ac_status = "✅ PASS" if ac_is_valid else "❌ FAIL"
            behave_name = behave_audit.get("file_name", "behavioral.puml") if behave_audit else "behavioral.puml"
            lines.append(
                f"[BEHAVIORAL DIAGRAM] {behave_name} (Parse: {ac_status} | Score: {ac_score:.2f} | Number of Elements: {ac_corr}/{ac_tot})"
            )

            # VMX checks
            vmx_d = d.get("vmx")
            if vmx_d and not vmx_d.get("missing"):
                cov_rate = vmx_d.get("coverage_rate", 0.0) * 100
                cov_comp = vmx_d.get("coverage_complete", 0)
                cov_rows = vmx_d.get("rows", 0)
                cov_pass = "✅ PASS" if cov_comp == cov_rows and cov_rows > 0 else "❌ FAIL"
                lines.append(
                    f"[VMX REQUIREMENT COVERAGE] VMX.csv (Coverage: {cov_pass} | Rate: {cov_rate:.1f}% | Complete Rows: {cov_comp}/{cov_rows})"
                )

                int_rate = vmx_d.get("integrity_rate", 0.0) * 100
                int_fnd = vmx_d.get("integrity_found", 0)
                int_tot = vmx_d.get("integrity_total", 0)
                int_pass = "✅ PASS" if int_fnd == int_tot and int_tot > 0 else "❌ FAIL"
                lines.append(
                    f"[VMX REFERENTIAL INTEGRITY] VMX.csv (Integrity: {int_pass} | Rate: {int_rate:.1f}% | Valid References: {int_fnd}/{int_tot})"
                )
            else:
                lines.append("[VMX REQUIREMENT COVERAGE] VMX.csv (Coverage: ❌ FAIL | Rate: 0.0% | VMX.csv missing)")
                lines.append("[VMX REFERENTIAL INTEGRITY] VMX.csv (Integrity: ❌ FAIL | Rate: 0.0% | VMX.csv missing)")

        lines.extend(self._grading_section(validation_results))

        lines.append("")
        lines.append("FINAL VERDICT")
        lines.append("-" * 80)
        if all_passed:
            lines.append("✅ RESULT: PASS — All syntax, coverage, and referential integrity checks satisfied")
        else:
            lines.append("❌ RESULT: FAIL — Pipeline validation completed with issues")
            for vr in validation_results:
                if not vr.passed:
                    lines.append(f"  • {vr.name}: {vr.message}")

        lines.append("")
        lines.append(f"Detailed line-by-line audit: {details_filename}")
        lines.append("=" * 80)
        return "\n".join(lines) + "\n"

    @staticmethod
    def _grading_section(validation_results: list[ValidationResult]) -> list[str]:
        """Summary of the grading modules (`--grade`); their full output sits in
        the run directory, next to this report."""
        graded = [vr for vr in validation_results
                  if (vr.details or {}).get("grading_kind")]
        if not graded:
            return []
        lines = ["", "PHASE 3: GRADING", "-" * 80]
        for vr in graded:
            d = vr.details or {}
            icon = "✅" if vr.passed else "❌"
            lines.append(f"{icon} {vr.name}: {vr.message}")
            metrics = d.get("metrics") or {}
            for diagram in ("structural", "behavioral"):
                block = metrics.get(diagram)
                if not isinstance(block, dict):
                    continue
                parts = [f"gate={block.get('gate')}"]
                for key in ("recall", "precision", "f1"):
                    value = block.get(key)
                    parts.append(f"{key}={value:.3f}" if isinstance(value, (int, float))
                                 else f"{key}={value}")
                lines.append(f"  [{diagram.upper()}] " + " | ".join(parts))
            if d.get("grading_dir"):
                lines.append(f"  Results: {str(d['grading_dir']).replace(chr(92), '/')}")
        return lines

    def _build_details(
        self,
        generation: GenerationResult | None,
        validation_results: list[ValidationResult],
        all_passed: bool,
        run_id: str,
        target_dir: str,
    ) -> str:
        lines: list[str] = [
            "=" * 80,
            f"PIPELINE DETAILED AUDIT REPORT — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Run ID: {run_id} | Target: {target_dir}",
            "=" * 80,
            "",
        ]

        for vr in validation_results:
            d = vr.details or {}
            if d.get("grading_kind"):
                continue
            syntax_audits = d.get("syntax_audits", [])
            struct_audit = next((a for a in syntax_audits if a.get("is_structural")), None)
            behave_audit = next((a for a in syntax_audits if a.get("is_behavioral")), None)

            # 1. Structural Diagram Syntax Audit
            lines.append("=" * 80)
            struct_name = struct_audit.get("file_name", "structural.puml") if struct_audit else "structural.puml"
            lines.append(f"1. STRUCTURAL DIAGRAM SYNTAX AUDIT ({struct_name})")
            lines.append("=" * 80)
            if struct_audit:
                v_icon = "✅ PASS" if struct_audit.get("valid") else "❌ FAIL"
                score = struct_audit.get("score", 0.0)
                corr = struct_audit.get("correct_elements", 0)
                tot = struct_audit.get("total_elements", 0)
                lines.append(f"Verdict: {v_icon} | Score: {score:.2f} ({corr}/{tot} elements)")
                if struct_audit.get("syntax_error"):
                    lines.append(f"Syntax Error: {struct_audit.get('syntax_error')}")
                lines.append("")
                lines.append(f"{'Line':>4}  {'Status':<6}  {'Content / Element':<45}  {'Message / Rule'}")
                lines.append("-" * 80)
                for row in struct_audit.get("lines", []):
                    l_num = row.get("line", 0)
                    st = row.get("status", "PASS")
                    txt = row.get("text", "")
                    if len(txt) > 43:
                        txt = txt[:40] + "..."
                    msg = row.get("message", "-")
                    lines.append(f"{l_num:>4}  {st:<6}  {txt:<45}  {msg}")
                lines.append("-" * 80)
                rules = struct_audit.get("rules", [])
                if rules:
                    lines.append("Structural Rules:")
                    for r in rules:
                        r_icon = "✅ PASS" if r.get("passed") else "❌ FAIL"
                        lines.append(f"  - {r.get('rule_id')}: {r_icon} ({r.get('message', '')})")
            else:
                lines.append("❌ Diagram file not found or not evaluated.")
            lines.append("")

            # 2. Behavioral Diagram Syntax Audit
            lines.append("=" * 80)
            behave_name = behave_audit.get("file_name", "behavioral.puml") if behave_audit else "behavioral.puml"
            lines.append(f"2. BEHAVIORAL DIAGRAM SYNTAX AUDIT ({behave_name})")
            lines.append("=" * 80)
            if behave_audit:
                v_icon = "✅ PASS" if behave_audit.get("valid") else "❌ FAIL"
                score = behave_audit.get("score", 0.0)
                corr = behave_audit.get("correct_elements", 0)
                tot = behave_audit.get("total_elements", 0)
                lines.append(f"Verdict: {v_icon} | Score: {score:.2f} ({corr}/{tot} elements)")
                if behave_audit.get("syntax_error"):
                    lines.append(f"Syntax Error: {behave_audit.get('syntax_error')}")
                lines.append("")
                lines.append(f"{'Line':>4}  {'Status':<6}  {'Content / Element':<45}  {'Message / Rule'}")
                lines.append("-" * 80)
                for row in behave_audit.get("lines", []):
                    l_num = row.get("line", 0)
                    st = row.get("status", "PASS")
                    txt = row.get("text", "")
                    if len(txt) > 43:
                        txt = txt[:40] + "..."
                    msg = row.get("message", "-")
                    lines.append(f"{l_num:>4}  {st:<6}  {txt:<45}  {msg}")
                lines.append("-" * 80)
                rules = behave_audit.get("rules", [])
                if rules:
                    lines.append("Structural Rules:")
                    for r in rules:
                        r_icon = "✅ PASS" if r.get("passed") else "❌ FAIL"
                        lines.append(f"  - {r.get('rule_id')}: {r_icon} ({r.get('message', '')})")
            else:
                lines.append("❌ Diagram file not found or not evaluated.")
            lines.append("")

            # 3. VMX Traceability & Referential Integrity Audit
            lines.append("=" * 80)
            lines.append("3. VMX TRACEABILITY & REFERENTIAL INTEGRITY AUDIT (VMX.csv)")
            lines.append("=" * 80)
            vmx = d.get("vmx")
            if vmx and not vmx.get("missing"):
                cov_comp = vmx.get("coverage_complete", 0)
                cov_rows = vmx.get("rows", 0)
                cov_rate = vmx.get("coverage_rate", 0.0) * 100
                int_fnd = vmx.get("integrity_found", 0)
                int_tot = vmx.get("integrity_total", 0)
                int_rate = vmx.get("integrity_rate", 0.0) * 100
                v_pass = "✅ PASS" if cov_comp == cov_rows and int_fnd == int_tot else "❌ FAIL"
                lines.append(f"Verdict: {v_pass}")
                lines.append(
                    f"Completeness: {cov_comp}/{cov_rows} rows ({cov_rate:.1f}%) | Integrity: {int_fnd}/{int_tot} references ({int_rate:.1f}%)"
                )
                lines.append("")
                incomplete = vmx.get("incomplete", [])
                broken = vmx.get("broken", [])
                lines.append("VMX Issues & Findings:")
                if not incomplete and not broken:
                    lines.append("  • Incomplete Rows (0): None")
                    lines.append("  • Broken References (0): None")
                else:
                    lines.append(f"  • Incomplete Rows ({len(incomplete)}):")
                    for inc in incomplete:
                        lines.append(f"    - {inc}")
                    lines.append(f"  • Broken References ({len(broken)}):")
                    for brk in broken:
                        lines.append(f"    - {brk}")
            else:
                lines.append("❌ VMX.csv not found in workspace or artifacts directory.")

        lines.append("=" * 80)
        return "\n".join(lines) + "\n"
