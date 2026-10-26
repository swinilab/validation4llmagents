"""report_to_txt.py — Render a run's raw report (`report_<run>.json`) as text.

The pipeline stores what a run produced as JSON (`report_writer.py`) and nothing
else; this script is the only place that turns that JSON into the text report. It
can be run on its own, at any time, on any report file:

    python report_to_txt.py generated/RUN_x/report_RUN_x.json [-o report.txt]

The JSON layout (`schema` 1):

    {"schema": 1, "run_id": ..., "target": ..., "created_at": ..., "updated_at": ...,
     "generation": {"status", "model", "agent", "reasoning", "code", "output_dir"},
     "grading": {"reqs": {...}, "models": {...}, "vmx": {...}}}

Each grading entry is `{"name", "passed", "message", "details", "ran_at",
"models_used"}`: the module's result as the pipeline returned it, so a run graded
in several invocations (`--grade reqs`, later `--grade models`) keeps every module.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RULE = "-" * 80

# Order the grading modules are listed in; anything else follows alphabetically.
GRADING_ORDER = ("reqs", "models", "vmx")


def _fmt(value: object) -> str:
    """Numbers to three decimals; anything else (`n/a`, None) as it is."""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return f"{value:.3f}"
    return str(value)


def _posix(path: object) -> str:
    return str(path).replace("\\", "/")


def render(report: dict) -> str:
    """The text report for one raw report."""
    generation = report.get("generation")
    grading = report.get("grading") or {}
    lines: list[str] = [
        "=" * 80,
        f"PIPELINE EVALUATION REPORT — {report.get('updated_at', 'n/a')}",
        f"Run ID: {report.get('run_id', 'n/a')} | Target: {report.get('target', 'n/a')}",
        "=" * 80,
        "",
        *_generation_section(generation),
        "",
        *_overview(grading),
        *_grading_section(grading),
        "",
        *_verdict(generation, grading),
    ]
    return "\n".join(lines) + "\n"


def _generation_section(generation: dict | None) -> list[str]:
    lines = ["PHASE 1: GENERATION", RULE]
    if not generation:
        lines.append("skipped (phase not run)")
        return lines
    if generation.get("status") != "PASS":
        lines.append("❌ Generation failed.")
    lines.append(f"LLM         : {generation.get('model')}")
    lines.append(f"Reasoning   : {generation.get('reasoning') or 'standard'}".rstrip())
    lines.append(f"Agent       : {generation.get('agent') or 'ChatDev'}")
    lines.append(f"SRS Package : {_posix(generation.get('code', ''))}")
    return lines


def _overview(grading: dict[str, dict]) -> list[str]:
    """The models the grading used: the embedding model and the rubric judge.

    Listed only for the modules that ran: reqs and models both embed and call the
    judge, vmx uses neither. Each module recorded its own settings, so if two
    modules were run with different ones, both are shown.
    """
    used = {kind: entry.get("models_used") or {}
            for kind, entry in grading.items() if kind in ("reqs", "models")}
    if not used:
        return []

    def per_module(label: str, values: dict[str, str]) -> str:
        distinct = set(values.values())
        if len(distinct) == 1:
            return f"{label}: {distinct.pop()}"
        return f"{label}: " + "; ".join(f"{k}={v}" for k, v in values.items())

    def embedding(models: dict) -> str:
        revision = models.get("embedding_revision") or "unpinned"
        return f"{models.get('embedding_model', 'n/a')} (revision: {revision})"

    lines = [
        per_module("Embedding model ", {k: embedding(m) for k, m in used.items()}),
        per_module("Judge model     ", {k: m.get("judge_model") or "not set"
                                         for k, m in used.items()}),
    ]
    return ["OVERVIEW", RULE, *lines, ""]


def _ordered(grading: dict[str, dict]) -> list[str]:
    known = [k for k in GRADING_ORDER if k in grading]
    return known + sorted(k for k in grading if k not in GRADING_ORDER)


def _grading_section(grading: dict[str, dict]) -> list[str]:
    """One block per grading module, in canonical order."""
    if not grading:
        return []
    blocks = {"reqs": _reqs_block, "models": _models_block, "vmx": _vmx_block}
    lines = ["PHASE 2: GRADING", RULE]
    for kind in _ordered(grading):
        entry = grading[kind]
        d = entry.get("details") or {}
        icon = "✅" if entry.get("passed") else "❌"
        stamp = f" [{entry['ran_at']}]" if entry.get("ran_at") else ""
        lines.append(f"{icon} {entry.get('name', kind)}: {entry.get('message', '')}{stamp}")
        block = blocks.get(d.get("grading_kind"))
        if block:
            lines.extend(block(d))
        if d.get("grading_dir"):
            lines.append(f"  Results: {_posix(d['grading_dir'])}")
        lines.append("")
    return lines[:-1]


def _verdict(generation: dict | None, grading: dict[str, dict]) -> list[str]:
    lines = ["FINAL VERDICT", RULE]
    failed = [e for e in grading.values() if not e.get("passed")]
    if not grading:
        if generation and generation.get("status") == "PASS":
            lines.append("✅ RESULT: PASS — Generation completed (grading not run)")
        else:
            lines.append("❌ RESULT: FAIL — Generation failed")
    elif not failed:
        lines.append("✅ RESULT: PASS — Every selected grading module completed")
    else:
        lines.append("❌ RESULT: FAIL — Grading completed with issues")
        for entry in failed:
            lines.append(f"  • {entry.get('name')}: {entry.get('message')}")
    lines.append("=" * 80)
    return lines


def _reqs_block(d: dict) -> list[str]:
    metrics = d.get("metrics") or {}
    if not metrics:
        return []
    lines: list[str] = []
    primary = metrics.get("primary_threshold")
    total = metrics.get("gold_total")
    for row in metrics.get("sweep", []):
        mark = " *" if row.get("threshold") == primary else "  "
        lines.append(
            f"  [REQUIREMENTS t={row['threshold']:.2f}]{mark}"
            f" recall={_fmt(row['recall'])} | precision={_fmt(row['precision'])}"
            f" | f1={_fmt(row['f1'])} | matched_gold={row['matched_gold']}/{total}")
    lines.append("  (* = primary threshold)")
    lines.append(
        f"  [UNITS] generated after dedup={metrics.get('s_size')} | "
        f"rubric_pass={metrics.get('rubric_pass')} | "
        f"pending polarity={metrics.get('pending_polarity')} "
        f"rubric={metrics.get('pending_rubric')} | "
        f"manual_default={metrics.get('manual_default')}")
    if metrics.get("kappa") is not None:
        verdict = {True: "accepted", False: "below kappa_accept"}.get(
            metrics.get("kappa_accepted"), "n/a")
        lines.append(
            f"  [JUDGE] kappa={metrics['kappa']} (n={metrics.get('kappa_n')}) | "
            f"accept>={metrics.get('kappa_accept')}: {verdict}")
    diag = metrics.get("diagnostics") or {}
    if diag:
        lines.append(
            f"  [DIAGNOSTICS] axis_rejections={diag.get('axis_rejections')} | "
            f"cross_us_matches={diag.get('cross_us_matches')} | "
            f"cross_kind_would_cover={diag.get('cross_kind_would_cover')} | "
            f"dedup_removed={diag.get('dedup_removed')}")
        if diag.get("format_violations"):
            lines.append(f"  [FORMAT VIOLATIONS] {diag['format_violations']}")
    return lines


def _models_block(d: dict) -> list[str]:
    lines: list[str] = []
    syntax = d.get("syntax") or {}
    logs = d.get("syntax_logs") or {}
    for diagram in ("structural", "behavioral"):
        block = syntax.get(diagram)
        if not isinstance(block, dict):
            continue
        lines.append(
            f"  [{diagram.upper()} SYNTAX] validity={block.get('validity')} "
            f"({block.get('accepted')}/{block.get('total')} declarations) | "
            f"gate={block.get('gate')}")
        if logs.get(diagram):
            lines.append(f"    Log: {_posix(logs[diagram])}")
    metrics = d.get("metrics") or {}
    for diagram in ("structural", "behavioral"):
        block = metrics.get(diagram)
        if not isinstance(block, dict):
            continue
        parts = [f"gate={block.get('gate')}"]
        for key in ("recall", "precision", "f1"):
            parts.append(f"{key}={_fmt(block.get(key))}")
        lines.append(f"  [{diagram.upper()}] " + " | ".join(parts))
    if metrics.get("kappa") is not None:
        verdict = {True: "accepted", False: "below kappa_accept"}.get(
            metrics.get("kappa_accepted"), "n/a")
        lines.append(
            f"  [JUDGE] kappa={metrics['kappa']} (n={metrics.get('kappa_n')}) | "
            f"accept>={metrics.get('kappa_accept')}: {verdict} | "
            f"role={metrics.get('kappa_role')}")
    return lines


def _vmx_block(d: dict) -> list[str]:
    metrics = d.get("metrics") or {}
    if not metrics:
        return []
    cov = metrics.get("coverage") or {}
    integ = metrics.get("integrity") or {}
    lines = [
        f"  [VMX REQUIREMENT COVERAGE] score={_fmt(cov.get('score'))} "
        f"({cov.get('covered')}/{cov.get('total')} requirements)",
    ]
    uncovered = (metrics.get("diagnostics") or {}).get("uncovered") or []
    if uncovered:
        lines.append("    Not covered: " + ", ".join(
            f"{u['id']} ({u['outcome']}"
            + (f": empty {'+'.join(u['empty'])}" if u.get("empty") else "")
            + ")" for u in uncovered))
    by_column = " | ".join(
        f"{role} {block['resolved']}/{block['total']}"
        for role, block in (integ.get("by_column") or {}).items())
    lines.append(
        f"  [VMX REFERENTIAL INTEGRITY] score={_fmt(integ.get('score'))} "
        f"({integ.get('resolved')}/{integ.get('total')} references)"
        + (f" | {by_column}" if by_column else ""))
    inputs = metrics.get("inputs") or {}
    for name in ("requirements", "vmx", "structural", "behavioral"):
        block = inputs.get(name)
        if isinstance(block, dict) and block.get("status") not in ("read", "parsed"):
            lines.append(f"    Input {name}: {block.get('status')}"
                         + (f" ({block['error']})" if block.get("error") else ""))
    schema = (inputs.get("vmx") or {}).get("schema") or {}
    if schema.get("missing_columns"):
        lines.append(f"    VMX header lacks column(s): {schema['missing_columns']}")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render a raw report (report_<run>.json) as the text report")
    parser.add_argument("report", help="path of the raw report JSON")
    parser.add_argument("-o", "--output", default=None,
                        help="text file to write (default: the JSON's path with .txt); "
                             "'-' prints to stdout")
    args = parser.parse_args(argv)

    source = Path(args.report)
    try:
        report = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"cannot read {source}: {error}", file=sys.stderr)
        return 1
    text = render(report)
    if args.output == "-":
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdout.write(text)
        return 0
    target = Path(args.output) if args.output else source.with_suffix(".txt")
    target.write_text(text, encoding="utf-8")
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
