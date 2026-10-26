"""Stage S0 -- syntax gate (spec §4).

Runs before extraction, separately per diagram.

The gate is the one place where `n/a` and `0` must stay distinguishable end to
end: a failed gate means *not measured*, a `0` means *measured and nothing
matched* (§4.2). `NA` below is the sentinel; serializers must not coerce it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..configload import DIAGRAMS
from ..parser import parse_behavioral, parse_structural

# The JSON string recorded for a metric that was not measured (§4.2).
NA = "n/a"

GATE_PASS = "pass"
GATE_FAIL = "fail"
GATE_MISSING = "missing"

_PARSERS = {"structural": parse_structural, "behavioral": parse_behavioral}


def parse_diagram(path: Path, diagram: str, rules: dict):
    """Parse one diagram file. A missing file is not an error here (§13)."""
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    return _PARSERS[diagram](text, rules)


def gate_for(result, syntax_gate: str) -> str:
    """Decide the gate for one diagram (§4.2).

    `syntax_gate: strict` requires validity == 1.0. The loader admits no other
    value, so an unknown mode is a programming error rather than a config one.
    """
    if result is None:
        return GATE_MISSING
    if syntax_gate != "strict":
        raise ValueError(f"unknown syntax_gate: {syntax_gate!r}")
    return GATE_PASS if result.validity() == 1.0 else GATE_FAIL


def run(submission_dir: Path, rules: dict, config: dict,
        diagrams=DIAGRAMS) -> tuple[dict[str, Any], dict]:
    """Parse and gate each requested diagram.

    Returns `(00_syntax.json payload, {diagram: ParseResult | None})`.
    """
    syntax: dict[str, Any] = {}
    parsed: dict[str, Any] = {}

    for diagram in diagrams:
        filename = "structural.puml" if diagram == "structural" else "behavioral.puml"
        result = parse_diagram(submission_dir / filename, diagram, rules)
        parsed[diagram] = result
        if result is None:
            syntax[diagram] = {
                "validity": NA, "accepted": 0, "total": 0,
                "parse_error": f"{filename} not found",
                "rejections": [], "gate": GATE_MISSING,
            }
            continue
        block = result.syntax_json()
        block["gate"] = gate_for(result, config["syntax_gate"])
        syntax[diagram] = block

    return syntax, parsed
