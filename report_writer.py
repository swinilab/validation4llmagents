"""
report_writer.py
─────────────────
Concrete IReportWriter — writes a human-readable report.txt.

The report covers:
  • generation summary
  • validation results (waterfall: shows where it stopped)
  • final verdict
"""

from __future__ import annotations

import os
from datetime import datetime

from interfaces.base import (
    GenerationResult,
    IReportWriter,
    Status,
    ValidationResult,
)


class TextReportWriter(IReportWriter):

    def __init__(self, report_dir: str = "generated/reports/") -> None:
        self._report_dir = report_dir

    def write(
        self,
        generation:         GenerationResult | None,
        validation_results: list[ValidationResult],
        all_passed:         bool,
        run_id:             str | None = None,
    ) -> str:
        # Determine the report file path using run_id
        if run_id:
            report_name = f"report_{run_id}.txt"
        else:
            # Fallback to run_dir or timestamp if run_id not provided
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_name = f"report_{timestamp}.txt"

        self._path = os.path.join(self._report_dir, report_name)

        # When a stage produced a per-app run folder, put the summary next to
        # that stage's own artefacts instead of leaving a bare report file.
        run_dir = next(
            (vr.details.get("run_dir") for vr in validation_results
             if vr.details and vr.details.get("run_dir")),
            None,
        )
        if run_dir:
            self._path = os.path.join(run_dir, f"{run_id or 'report'}.txt")

        os.makedirs(os.path.dirname(self._path), exist_ok=True)

        lines: list[str] = []

        lines.append(f"PIPELINE REPORT — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")

        lines.append("GENERATION")
        if generation is None:
            lines.append("skipped (phase not run)")
            lines.append("")
        elif generation.status is Status.PASS:
            lines.append(f"model: {generation.model}")
            lines.append(f"code: {generation.code}")
            lines.append("")
        else:
            lines.append("❌ Generation failed.")
            lines.append(f"model: {generation.model}")
            lines.append("")

        if validation_results:
            lines.append("VALIDATION:")
            for vr in validation_results:
                if vr.stage == 1:
                    valid_d = vr.details.get("valid_diagrams", 0)
                    total_d = vr.details.get("total_diagrams", 0)
                    cl_corr = vr.details.get("class_correct", 0)
                    cl_tot = vr.details.get("class_total", 0)
                    ac_corr = vr.details.get("act_correct", 0)
                    ac_tot = vr.details.get("act_total", 0)

                    lines.append(f"\t1. SYNTAX CORRECTNESS: {valid_d}/{total_d} diagrams parsed: ")
                    lines.append(f"\t\t- structural model (class diagram): score = {cl_corr}, {cl_corr}/{cl_tot}")
                    lines.append(f"\t\t- behavioral model (activity diagram): score = {ac_corr}, {ac_corr}/{ac_tot}")
                else:
                    icon = "✅" if vr.passed else "❌"
                    lines.append(f"  {icon} {vr.stage} : {vr.message}")

                if vr.details.get("stderr"):
                    lines.append(f"    error detail : {vr.details.get('stderr')}")

                summary = vr.details.get("summary")
                if summary:
                    total     = vr.details.get("total")
                    passed    = vr.details.get("passed")
                    failed    = vr.details.get("failed")
                    pass_rate = vr.details.get("pass_rate")
                    lines.append(f"    {failed}/{total} failed ({passed} passed, {pass_rate} pass rate)")
                    # Stage 2 groups by entity ("group"), stage 6 by check
                    # kind ("category"); both render the same way.
                    for row in summary:
                        label = row.get("group") or row.get("category") or "?"
                        lines.append(
                            f"    - {label} : {row['failed']}/{row['total']} failed"
                            f" ({row.get('pass_rate')} pass rate)"
                        )
                    for step, route in (vr.details.get("transitions_used") or {}).items():
                        lines.append(
                            f"    transition {step} : {route.get('method')} "
                            f"{route.get('pathTemplate')} [{route.get('source')}]"
                        )
                    report_path = vr.details.get("report_path")
                    if report_path:
                        lines.append(f"    full report : {report_path}")
                    seed_log_path = vr.details.get("seed_log_path")
                    if seed_log_path:
                        lines.append(f"    seed context log : {seed_log_path}")
                elif vr.details.get("tally"):
                    lines.append(f"    tally : {vr.details.get('tally')}")
                    report_path = vr.details.get("report_path")
                    if report_path:
                        lines.append(f"    full report : {report_path}")
            lines.append("")

        lines.append("RESULT")
        if all_passed:
            lines.append("  ✅ all checks passed — check QA manually")
        else:
            lines.append("  ❌ pipeline failed")
            blocking = next((vr for vr in validation_results if not vr.passed), None)
            if blocking:
                lines.append(f"  blocking stage : {blocking.stage}")
                lines.append(f"  error          : {blocking.message}")

        report_text = "\n".join(lines)
        with open(self._path, "w", encoding="utf-8") as f:
            f.write(report_text)

        return self._path
