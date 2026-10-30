"""Stage S0 -- syntax gate (spec §4).

Runs before extraction, separately per diagram.

The gate is the one place where `n/a` and `0` must stay distinguishable end to
end: a failed gate means *not measured*, a `0` means *measured and nothing
matched* (§4.2). `NA` below is the sentinel; serializers must not coerce it.
"""

from __future__ import annotations

import subprocess
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


class PlantUmlUnavailable(RuntimeError):
    """PlantUML could not be run, so `syntax_gate: plantuml` cannot decide."""


def plantuml_check(path: Path, settings: dict) -> tuple[bool, str | None]:
    """Ask PlantUML itself whether `path` is a valid diagram.

    Runs `java -jar plantuml.jar -syntax` with the file on stdin. PlantUML prints
    the diagram type when it parses (`CLASS (10 entities)`) and `ERROR`, the line
    and a message when it does not. Returns `(ok, error message or None)`.
    """
    jar = Path(settings["jar"])
    if not jar.is_file():
        raise PlantUmlUnavailable(f"PlantUML jar not found: {jar}")
    command = [settings["java_cmd"], "-Djava.awt.headless=true", "-jar", str(jar),
               "-syntax"]
    try:
        done = subprocess.run(command, input=path.read_bytes(), capture_output=True,
                              timeout=settings["timeout_seconds"], check=False)
    except FileNotFoundError as error:
        raise PlantUmlUnavailable(f"cannot run {settings['java_cmd']!r}: {error}") \
            from error
    except subprocess.TimeoutExpired as error:
        raise PlantUmlUnavailable(
            f"PlantUML timed out after {settings['timeout_seconds']}s on {path.name}"
        ) from error
    lines = done.stdout.decode("utf-8", errors="replace").strip().splitlines()
    if lines and lines[0].strip().upper() == "ERROR":
        return False, " ".join(line.strip() for line in lines[1:]) or "syntax error"
    if not lines:
        raise PlantUmlUnavailable(
            f"PlantUML printed nothing for {path.name}: "
            f"{done.stderr.decode('utf-8', errors='replace').strip()}")
    return True, None


def gate_for(result, syntax_gate: str, plantuml_ok: bool | None = None) -> str:
    """Decide the gate for one diagram (§4.2).

    `syntax_gate: strict` requires validity == 1.0 from the project's own parser.
    `syntax_gate: plantuml` passes a diagram when PlantUML accepts it
    (`plantuml_ok`); the own parser still extracts the elements, but a
    declaration it cannot read no longer costs the whole diagram its metrics.
    The loader admits no other value, so an unknown mode is a programming error.
    """
    if result is None:
        return GATE_MISSING
    if syntax_gate == "plantuml":
        if plantuml_ok is None:
            raise ValueError("syntax_gate 'plantuml' needs PlantUML's verdict")
        return GATE_PASS if plantuml_ok else GATE_FAIL
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
                "gate_mode": config["syntax_gate"],
            }
            continue
        block = result.syntax_json()
        mode = config["syntax_gate"]
        plantuml_ok = None
        if mode == "plantuml":
            plantuml_ok, error = plantuml_check(submission_dir / filename,
                                                config["plantuml"])
            block["plantuml"] = {"accepted": plantuml_ok, "error": error}
        block["gate"] = gate_for(result, mode, plantuml_ok)
        # Lets a rerun notice that the cached verdict was made under another mode.
        block["gate_mode"] = mode
        syntax[diagram] = block

    return syntax, parsed
