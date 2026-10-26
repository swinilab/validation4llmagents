"""Line-by-line log of the syntax gate (spec §4), one file per diagram.

`00_syntax.json` carries the ratio; these files carry the evidence behind it: for
every source line, whether the parser took it as a declaration, and why not when
it did not. They are rewritten whenever S0 runs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

LOG_NAMES = {
    "structural": "structural_model_syntax_correctness.txt",
    "behavioral": "behavioral_model_syntax_correctness.txt",
}
_SOURCE_FILES = {"structural": "structural.puml", "behavioral": "behavioral.puml"}


def write(run_dir: Path, submission_dir: Path, syntax: dict[str, Any],
          parsed: dict[str, Any]) -> dict[str, Path]:
    """Write one log per diagram in `syntax`; returns `{diagram: path}`."""
    run_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for diagram, block in syntax.items():
        path = run_dir / LOG_NAMES[diagram]
        source = submission_dir / _SOURCE_FILES[diagram]
        text = source.read_text(encoding="utf-8", errors="replace") \
            if source.is_file() else None
        path.write_text(_render(diagram, source.name, block, parsed.get(diagram),
                                text), encoding="utf-8")
        paths[diagram] = path
    return paths


def _render(diagram: str, filename: str, block: dict[str, Any], result: Any,
            text: str | None) -> str:
    title = f"{diagram.upper()} MODEL SYNTAX CORRECTNESS ({filename})"
    if result is None or text is None:
        rule = "=" * len(title)
        return "\n".join([rule, title, rule, f"Gate: {block.get('gate')}",
                          f"{filename} was not found: nothing to check.",
                          rule]) + "\n"

    accepted, total = block["accepted"], block["total"]
    # Column widths follow the content, so no source line is ever cut short.
    text_width = max((len(raw.strip()) for raw in text.splitlines()),
                     default=0)
    text_width = max(text_width, len("Source"))
    header = (f"{'Line':>4}  {'Status':<6}  {'Kind':<12}  "
              f"{'Source':<{text_width}}  Message")
    rule = "=" * max(len(header), len(title))
    lines = [rule, title, rule]
    lines += [f"Gate: {block['gate']}  |  Syntax validity: {block['validity']} "
              f"({accepted}/{total} declarations accepted)"]
    if block.get("parse_error"):
        lines.append(f"Parse error: {block['parse_error']}")
    lines.append("")

    declared = {d.line: d for d in result.declarations}
    reasons: dict[int, list[str]] = {}
    for rejection in result.rejections:
        reasons.setdefault(rejection.line, []).append(rejection.code)
    notes: dict[int, list[str]] = {}
    for violation in result.violations:
        if violation.line is not None:
            notes.setdefault(violation.line, []).append(
                f"{violation.code}: {violation.detail}")

    lines.append(header)
    lines.append("-" * len(header))
    for number, raw in enumerate(text.splitlines(), start=1):
        declaration = declared.get(number)
        if declaration is None:
            status, kind = "-", ""
        else:
            status = "PASS" if declaration.accepted else "FAIL"
            kind = declaration.kind
        message = "; ".join(reasons.get(number, []) + notes.get(number, [])) or "-"
        lines.append(f"{number:>4}  {status:<6}  {kind:<12}  "
                     f"{raw.strip():<{text_width}}  {message}")
    lines.append("-" * len(header))

    lines.append("")
    lines.append(f"Rejected declarations ({len(result.rejections)}):")
    for rejection in result.rejections:
        lines.append(f"  line {rejection.line}: {rejection.code}: {rejection.source}")
    if not result.rejections:
        lines.append("  none")

    lines.append("")
    lines.append(f"Format violations ({len(result.violations)}):")
    for violation in result.violations:
        where = f"line {violation.line}" if violation.line is not None else "-"
        lines.append(f"  {where}: {violation.code}: {violation.detail}")
    if not result.violations:
        lines.append("  none")

    lines.append(rule)
    return "\n".join(lines) + "\n"
