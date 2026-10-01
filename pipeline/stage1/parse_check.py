"""Stage 1 - metric 7 (Diagram Validity).

Checks each PlantUML diagram in a run two ways:

1. **Syntax**, by running PlantUML's own ``-checkonly``. This is the official
   parser's verdict, not a reimplementation of it.
2. **Structural rules PV-01..PV-04**, a deliberately small v0 set. These exist
   because ``-checkonly`` is lenient: it accepts an activity diagram with an
   unclosed ``if`` or a missing ``@enduml`` and exits 0. Syntax alone would
   therefore call a malformed diagram valid.

A diagram is ``valid`` iff syntax passes *and* every structural rule passes.
``diagram_validity`` is ``valid_diagrams / total_diagrams`` for the run.

**A failing diagram is recorded, not fatal.** The run continues to the other
diagrams, writes its JSON and exits 0. Non-zero exits are reserved for
tool/IO/argument errors, so a caller can tell "the diagram is bad" (exit 0,
read the JSON) from "I could not check it" (exit 2 or 3).

This module is gold-agnostic: ``run_id`` is an opaque label and no input is
treated specially.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from .config import (
    REPO_ROOT,
    Stage1Config,
    Stage1ConfigError,
    load_config,
    resolve_output_path,
    sha256_of,
)
from .normalize import STAGE1_VERSION

__all__ = [
    "PARSE_CHECK_VERSION",
    "STRUCTURAL_RULES",
    "DiagramResult",
    "ParseCheckError",
    "PlantUmlNotAvailable",
    "RuleResult",
    "Violation",
    "inventory_allowed",
    "check_diagram",
    "run_parse_check",
    "main",
]

# Versioned separately from STAGE1_VERSION: the normalization contract and the
# diagram-validity contract change for different reasons.
PARSE_CHECK_VERSION = "1.0.0"

# Exit codes. 0 covers "ran to completion", including diagrams that failed.
EXIT_OK = 0
EXIT_USAGE = 2
EXIT_TOOL = 3


class ParseCheckError(RuntimeError):
    """Raised on an input/argument problem that prevents a run."""


class PlantUmlNotAvailable(ParseCheckError):
    """Raised when PlantUML itself cannot be run.

    Kept distinct from a diagram being invalid: this means the verdict is
    *unknown*, not negative.
    """


# --- diagram kinds -------------------------------------------------------

KIND_CLASS = "class"
KIND_ACTIVITY = "activity"
KIND_UNKNOWN = "unknown"

_RE_CLASS_DECL = re.compile(r"^\s*(?:abstract\s+|final\s+)?class\s+[\w\"']", re.MULTILINE)
_RE_OTHER_CLASS_TYPE = re.compile(r"^\s*(?:interface|enum|entity|abstract)\s+[\w\"']", re.MULTILINE)
_RE_ACTIVITY_MARKER = re.compile(
    r"^\s*(?::.*;|start\b|stop\b|end\b|if\s*\(|\|[^|]*\|)", re.MULTILINE
)


@dataclass(frozen=True)
class RuleResult:
    """One structural rule's verdict on one diagram."""

    rule_id: str
    message: str
    passed: bool


@dataclass(frozen=True)
class Violation:
    """One concrete failure, with a line number when we can attribute one.

    ``line`` is None for syntax failures: PlantUML's ``-checkonly`` reports
    only that a diagram contains errors, without a position. The structural
    rules, which read the file themselves, do supply line numbers.
    """

    rule_id: str
    message: str
    line: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"rule_id": self.rule_id, "message": self.message, "line": self.line}


@dataclass
class DiagramResult:
    """The full verdict for one diagram file."""

    path: str
    kind: str
    parse_ok: bool
    rules: list[RuleResult] = field(default_factory=list)
    violations: list[Violation] = field(default_factory=list)
    syntax_error: str | None = None

    @property
    def valid(self) -> bool:
        """Valid iff syntax passed and no structural rule failed."""
        return self.parse_ok and all(rule.passed for rule in self.rules)

    @property
    def inventory_allowed(self) -> bool:
        """Whether a downstream inventory extractor may trust this diagram.

        Mirrors :attr:`valid`. ``puml_to_inventory`` reads this to skip a
        failed block rather than extracting nonsense from it.
        """
        return self.valid

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "kind": self.kind,
            "parse_ok": self.parse_ok,
            "valid": self.valid,
            "inventory_allowed": self.inventory_allowed,
            "syntax_error": self.syntax_error,
            "rules": [
                {"rule_id": r.rule_id, "message": r.message, "passed": r.passed}
                for r in self.rules
            ],
            "violations": [v.as_dict() for v in self.violations],
        }


# Rule catalogue, documented in README.md. v0 is intentionally this short.
STRUCTURAL_RULES: dict[str, str] = {
    "PV-01": "A class diagram defines at least one class.",
    "PV-02": "An activity diagram has a start node and an end/stop node.",
    "PV-03": "Every 'if' in an activity diagram has a matching 'endif'.",
    "PV-04": "Every partition/swimlane block is closed.",
}


def detect_kind(text: str) -> str:
    """Classify a diagram as class, activity, or unknown, from its body.

    The declared ``@startuml <name>`` is only a label, so the body decides.
    Class declarations win over activity markers because a class diagram may
    legitimately contain a line that looks like an activity marker inside a
    note, while the reverse is not true of ``class X {``.
    """
    if _RE_CLASS_DECL.search(text):
        return KIND_CLASS
    if _RE_ACTIVITY_MARKER.search(text):
        return KIND_ACTIVITY
    if _RE_OTHER_CLASS_TYPE.search(text):
        return KIND_CLASS
    return KIND_UNKNOWN


def _strip_noise(text: str) -> list[tuple[int, str]]:
    """Return (line_number, code) pairs with comments and notes removed.

    Single-quote comments, ``/' ... '/`` blocks and ``note ... end note``
    bodies are dropped so a rule never fires on prose. Line numbers are
    1-based and refer to the original file.
    """
    out: list[tuple[int, str]] = []
    in_block_comment = False
    in_note = False
    for index, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if in_block_comment:
            if "'/" in line:
                in_block_comment = False
            continue
        if line.startswith("/'"):
            if "'/" not in line[2:]:
                in_block_comment = True
            continue
        if in_note:
            if re.match(r"^end\s*note\b", line, re.IGNORECASE):
                in_note = False
            continue
        if re.match(r"^note\b", line, re.IGNORECASE) and not re.search(
            r"\bnote\b.*:", line, re.IGNORECASE
        ):
            # A multi-line note opens a body; a one-liner "note left: x" does not.
            if not re.search(r"^note\s+(left|right|top|bottom)\s*:", line, re.IGNORECASE):
                in_note = True
            continue
        if line.startswith("'"):
            continue
        if not line:
            continue
        out.append((index, line))
    return out


def _check_class_rules(lines: Sequence[tuple[int, str]]) -> tuple[list[RuleResult], list[Violation]]:
    """PV-01 for a class diagram."""
    rules: list[RuleResult] = []
    violations: list[Violation] = []
    body = "\n".join(code for _, code in lines)
    has_class = bool(_RE_CLASS_DECL.search(body) or _RE_OTHER_CLASS_TYPE.search(body))
    rules.append(RuleResult("PV-01", STRUCTURAL_RULES["PV-01"], has_class))
    if not has_class:
        violations.append(
            Violation("PV-01", "No class is defined in this class diagram.", None)
        )
    return rules, violations


def _check_activity_rules(
    lines: Sequence[tuple[int, str]],
) -> tuple[list[RuleResult], list[Violation]]:
    """PV-02 and PV-03 for an activity diagram."""
    rules: list[RuleResult] = []
    violations: list[Violation] = []

    has_start = False
    has_end = False
    if_stack: list[int] = []
    unmatched_endif: list[int] = []

    for number, code in lines:
        if re.match(r"^start\b", code, re.IGNORECASE):
            has_start = True
        if re.match(r"^(stop|end)\b", code, re.IGNORECASE):
            # "end note"/"end group" are structural keywords, not end nodes;
            # notes are already stripped, so guard the remaining compounds.
            if not re.match(r"^end\s+(note|group|box|title|legend|while|fork)\b", code, re.IGNORECASE):
                has_end = True
        if re.match(r"^(else)?if\s*\(", code, re.IGNORECASE) and not re.match(
            r"^elseif\s*\(", code, re.IGNORECASE
        ):
            if re.match(r"^if\s*\(", code, re.IGNORECASE):
                if_stack.append(number)
        if re.match(r"^endif\b", code, re.IGNORECASE):
            if if_stack:
                if_stack.pop()
            else:
                unmatched_endif.append(number)

    rules.append(RuleResult("PV-02", STRUCTURAL_RULES["PV-02"], has_start and has_end))
    if not has_start:
        violations.append(Violation("PV-02", "Activity diagram has no 'start' node.", None))
    if not has_end:
        violations.append(
            Violation("PV-02", "Activity diagram has no 'stop'/'end' node.", None)
        )

    balanced = not if_stack and not unmatched_endif
    rules.append(RuleResult("PV-03", STRUCTURAL_RULES["PV-03"], balanced))
    for line_number in if_stack:
        violations.append(
            Violation("PV-03", "'if' opened here is never closed by 'endif'.", line_number)
        )
    for line_number in unmatched_endif:
        violations.append(
            Violation("PV-03", "'endif' here closes no open 'if'.", line_number)
        )
    return rules, violations


def _check_partition_rule(
    lines: Sequence[tuple[int, str]],
) -> tuple[RuleResult, list[Violation]]:
    """PV-04: every ``partition``/swimlane block is closed.

    Two syntaxes exist and are checked differently:

    * ``partition Name { ... }`` - brace-delimited, must balance;
    * ``|Lane|`` - a switch, not a block. It needs no closing token, so it can
      only fail by being malformed (an odd number of pipes on the line).
    """
    violations: list[Violation] = []
    depth = 0
    opened_at: list[int] = []

    for number, code in lines:
        if re.match(r"^partition\b", code, re.IGNORECASE):
            if "{" in code:
                depth += 1
                opened_at.append(number)
            else:
                # "partition Name" with the brace on a following line.
                opened_at.append(number)
                depth += 1
            continue
        if code == "}" or code.endswith("}"):
            if depth > 0:
                depth -= 1
                if opened_at:
                    opened_at.pop()
        # A swimlane switch must have a balanced pair of pipes.
        if code.startswith("|") and code.count("|") % 2 != 0:
            violations.append(
                Violation("PV-04", f"Malformed swimlane marker: {code!r}.", number)
            )

    for line_number in opened_at:
        violations.append(
            Violation("PV-04", "'partition' opened here is never closed.", line_number)
        )
    passed = not violations
    return RuleResult("PV-04", STRUCTURAL_RULES["PV-04"], passed), violations


def _structural_check(text: str, kind: str) -> tuple[list[RuleResult], list[Violation]]:
    """Run the rules that apply to this diagram kind."""
    lines = _strip_noise(text)
    rules: list[RuleResult] = []
    violations: list[Violation] = []

    if kind == KIND_CLASS:
        class_rules, class_violations = _check_class_rules(lines)
        rules.extend(class_rules)
        violations.extend(class_violations)
    elif kind == KIND_ACTIVITY:
        activity_rules, activity_violations = _check_activity_rules(lines)
        rules.extend(activity_rules)
        violations.extend(activity_violations)

    # PV-04 applies to any diagram that uses partitions or swimlanes.
    partition_rule, partition_violations = _check_partition_rule(lines)
    rules.append(partition_rule)
    violations.extend(partition_violations)
    return rules, violations


# --- PlantUML invocation -------------------------------------------------


def _plantuml_command(cfg: Stage1Config) -> list[str]:
    """Build the PlantUML command from config.

    Supports either a ``plantuml`` executable on PATH or a jar run through
    ``java -jar``, so the module works whether the tool was installed by a
    package manager or downloaded as the official jar.
    """
    settings = cfg.parse_check
    if settings.plantuml_jar:
        jar = Path(settings.plantuml_jar)
        if not jar.is_absolute():
            jar = REPO_ROOT / jar
        if not jar.is_file():
            raise PlantUmlNotAvailable(
                f"PlantUML jar not found: {jar}. Set stage1.parse_check.plantuml_jar "
                f"in config.yaml, or install a 'plantuml' executable and set "
                f"stage1.parse_check.plantuml_cmd."
            )
        return [settings.java_cmd, "-jar", str(jar)]
    return [settings.plantuml_cmd]


def _run_plantuml(cfg: Stage1Config, path: Path) -> tuple[bool, str | None]:
    """Run ``-checkonly`` on one file.

    Returns:
        ``(parse_ok, error_text)``. ``error_text`` is None when syntax passed.

    Raises:
        PlantUmlNotAvailable: If the tool could not be executed at all.
    """
    settings = cfg.parse_check
    command = [*_plantuml_command(cfg), "-checkonly"]
    if settings.layout_smetana:
        command.append("-Playout=smetana")
    command.extend(settings.extra_args)
    command.append(str(path))

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=settings.timeout_seconds,
            check=False,
        )
    except FileNotFoundError as exc:
        raise PlantUmlNotAvailable(
            f"Cannot run PlantUML ({command[0]!r} not found): {exc}. "
            f"Install PlantUML or set stage1.parse_check.plantuml_jar in config.yaml."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise PlantUmlNotAvailable(
            f"PlantUML timed out after {settings.timeout_seconds}s on {path}."
        ) from exc
    except OSError as exc:  # pragma: no cover - platform dependent
        raise PlantUmlNotAvailable(f"Cannot run PlantUML: {exc}") from exc

    output = f"{completed.stdout}\n{completed.stderr}".strip()

    # A JVM that cannot start at all (bad jar, missing class) is a tool
    # problem, not a diagram problem. PlantUML reports diagram errors with
    # exit 200 and the message below; anything else non-zero is suspect.
    if completed.returncode not in (0, 200):
        if "Error: Unable to access jarfile" in output or "ClassNotFoundException" in output:
            raise PlantUmlNotAvailable(f"Cannot run PlantUML: {output}")
    if completed.returncode == 0:
        return True, None
    return False, output or f"PlantUML exited {completed.returncode}."


# --- public API ----------------------------------------------------------


def check_diagram(path: Path, cfg: Stage1Config) -> DiagramResult:
    """Check one ``.puml`` file: syntax plus the structural rules.

    Args:
        path: The diagram. Opened read-only.
        cfg: Effective Stage 1 config.

    Returns:
        A :class:`DiagramResult`; a failing diagram is reported, not raised.

    Raises:
        ParseCheckError: If the file cannot be read.
        PlantUmlNotAvailable: If PlantUML could not be run.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ParseCheckError(f"Cannot read diagram {path}: {exc}") from exc

    kind = detect_kind(text)
    parse_ok, syntax_error = _run_plantuml(cfg, path)
    rules, violations = _structural_check(text, kind)

    if not parse_ok:
        violations.insert(
            0,
            Violation("SYNTAX", syntax_error or "PlantUML reported a syntax error.", None),
        )

    return DiagramResult(
        path=_display_path(path),
        kind=kind,
        parse_ok=parse_ok,
        rules=rules,
        violations=violations,
        syntax_error=syntax_error,
    )


def _display_path(path: Path) -> str:
    """Repo-relative POSIX path, matching the normalize module's convention."""
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def inventory_allowed(result_json: Path | str | dict[str, Any], diagram: str) -> bool:
    """Whether ``puml_to_inventory`` may extract from ``diagram``.

    The helper a downstream caller uses to skip a failed block. It reads the
    ``__parse_check.json`` this module writes, so the inventory extractor needs
    no knowledge of the rules themselves.

    Args:
        result_json: The written result file, or its already-parsed dict.
        diagram: Path of the diagram to ask about; compared by repo-relative
            path and, failing that, by file name.

    Returns:
        True if that diagram was found and is valid. An unknown diagram is
        False: never extract from something that was not checked.
    """
    if isinstance(result_json, dict):
        payload = result_json
    else:
        path = Path(result_json)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False

    wanted = Path(diagram)
    for entry in payload.get("diagrams", ()):
        entry_path = Path(str(entry.get("path", "")))
        if entry_path == wanted or entry_path.name == wanted.name:
            return bool(entry.get("inventory_allowed", False))
    return False


def run_parse_check(
    run_id: str,
    diagrams: Sequence[str | Path],
    out_path: str | Path | None = None,
    cfg: Stage1Config | None = None,
) -> dict[str, Any]:
    """Check every diagram in a run and write ``<run_id>__parse_check.json``.

    Args:
        run_id: Opaque label for the run. Not interpreted; gold and agent
            output are treated identically.
        diagrams: The ``.puml`` files to check.
        out_path: Output JSON. Defaults to
            ``pipeline/stage1/artifact/<run_id>__parse_check.json``. Must
            resolve inside the repository.
        cfg: Effective config; loaded from ``config.yaml`` when None.

    Returns:
        The payload that was written.

    Raises:
        ParseCheckError: On bad arguments or an unreadable diagram.
        PlantUmlNotAvailable: If PlantUML could not be run.
        Stage1ConfigError: If ``out_path`` resolves outside the repository.
    """
    if not run_id or not str(run_id).strip():
        raise ParseCheckError("run_id must be a non-empty label.")
    if not diagrams:
        raise ParseCheckError("No diagrams given: pass at least one .puml file.")

    effective = cfg or load_config()

    results: list[DiagramResult] = []
    for item in diagrams:
        path = Path(item)
        if not path.is_file():
            raise ParseCheckError(f"Diagram file not found: {path}")
        results.append(check_diagram(path, effective))

    # Stable row order: sort by the displayed path so the JSON does not depend
    # on the order the shell happened to glob the arguments in.
    results.sort(key=lambda r: r.path)

    total = len(results)
    valid = sum(1 for r in results if r.valid)
    payload: dict[str, Any] = {
        "run_id": str(run_id),
        "diagram_validity": (valid / total) if total else None,
        "total_diagrams": total,
        "valid_diagrams": valid,
        "diagrams": [r.as_dict() for r in results],
    }

    output_file = _resolve_json_output(out_path, run_id)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    _write_meta(output_file, effective, run_id, results)
    payload["out_path"] = _display_path(output_file)
    return payload


def _resolve_json_output(out_path: str | Path | None, run_id: str) -> Path:
    """Default to ``<run_id>__parse_check.json`` in the artifact directory."""
    if out_path is not None:
        return resolve_output_path(out_path, None)
    # resolve_output_path names the default from the input stem; parse_check is
    # named from the run instead, so build the default name here and let
    # resolve_output_path enforce the repository boundary.
    from .config import ARTIFACT_DIR

    return resolve_output_path(ARTIFACT_DIR / f"{run_id}__parse_check.json", None)


def _write_meta(
    out_path: Path, cfg: Stage1Config, run_id: str, results: Sequence[DiagramResult]
) -> Path:
    """Write the ``.meta.json`` sidecar, following the normalize convention."""
    meta_path = out_path.with_name(out_path.name + ".meta.json")
    meta = {
        "stage1_version": STAGE1_VERSION,
        "parse_check_version": PARSE_CHECK_VERSION,
        "ontology_sha256": sha256_of(Path(cfg.ontology_path)),
        "ontology_path": cfg.as_dict()["ontology_path"],
        "config": cfg.parse_check.as_dict(),
        "run_id": run_id,
        "inputs": [r.path for r in results],
        "diagram_count": len(results),
        "structural_rules": dict(sorted(STRUCTURAL_RULES.items())),
    }
    meta_path.write_text(
        json.dumps(meta, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return meta_path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m pipeline.stage1.parse_check",
        description=(
            "Stage 1 - metric 7 (Diagram Validity). Checks PlantUML diagrams "
            "for syntax (plantuml -checkonly) and structural rules PV-01..PV-04. "
            "An invalid diagram is recorded and exits 0; non-zero means the "
            "check could not be performed."
        ),
    )
    parser.add_argument("--run-id", required=True, help="Opaque label for this run.")
    parser.add_argument(
        "--diagram",
        dest="diagrams",
        action="append",
        required=True,
        metavar="PUML",
        help="A .puml file to check. Repeat for several diagrams.",
    )
    parser.add_argument(
        "--out",
        dest="out_path",
        help=(
            "Output .json file. Defaults to "
            "pipeline/stage1/artifact/<run-id>__parse_check.json. Must be "
            "inside the repository."
        ),
    )
    parser.add_argument("--config", help="Path to a config.yaml holding the stage1 section.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point. Returns the process exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        cfg = load_config(args.config)
    except Stage1ConfigError as exc:
        print(f"parse_check config error: {exc}", file=sys.stderr)
        return EXIT_USAGE

    try:
        payload = run_parse_check(args.run_id, args.diagrams, args.out_path, cfg)
    except PlantUmlNotAvailable as exc:
        # Distinct exit code: the tool is missing, the diagrams are not judged.
        print(f"parse_check tool error: {exc}", file=sys.stderr)
        return EXIT_TOOL
    except (ParseCheckError, Stage1ConfigError) as exc:
        print(f"parse_check error: {exc}", file=sys.stderr)
        return EXIT_USAGE

    validity = payload["diagram_validity"]
    shown = "n/a" if validity is None else f"{validity:.3f}"
    print(
        f"parse_check {PARSE_CHECK_VERSION}: "
        f"{payload['valid_diagrams']}/{payload['total_diagrams']} diagrams valid "
        f"(diagram_validity={shown}) -> {payload['out_path']}"
    )
    for diagram in payload["diagrams"]:
        if not diagram["valid"]:
            for violation in diagram["violations"]:
                where = f":{violation['line']}" if violation["line"] else ""
                print(
                    f"  {diagram['path']}{where} [{violation['rule_id']}] "
                    f"{violation['message']}",
                    file=sys.stderr,
                )
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
