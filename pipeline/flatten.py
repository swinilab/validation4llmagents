"""Stage 1 - PUML Diagram Flattening (metric preparation).

Extracts structural and behavioral elements from PlantUML diagrams into
canonical element inventories (CSV format).

- Class diagrams: element_id, element_type, canonical_name, owner_class, detail, tier
- Activity diagrams: element_id, element_type, verb, object, swimlane, detail, tier

Integrates with parse_check's ``inventory_allowed``: diagrams that failed
syntax or structural checks are skipped unless explicitly overridden with --force.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .config import (
    ARTIFACT_DIR,
    ConfigError,
    PipelineConfig,
    REPO_ROOT,
    Stage1Config,
    Stage1ConfigError,
    load_config,
    resolve_output_path,
    sha256_of,
)
from .normalize import PIPELINE_VERSION, STAGE1_VERSION
from .parse_check import detect_kind, inventory_allowed

__all__ = [
    "FLATTEN_VERSION",
    "CLASS_COLS",
    "ACT_COLS",
    "FlattenError",
    "InventoryNotAllowedError",
    "parse_class_elements",
    "parse_activity_elements",
    "tier_key",
    "apply_tier_map",
    "flatten_diagram",
    "run_flatten",
    "main",
]

FLATTEN_VERSION = "1.0.0"

# Exit codes matching Stage 1 conventions
EXIT_OK = 0
EXIT_USAGE = 2

CLASS_COLS = ["element_id", "element_type", "canonical_name", "owner_class", "detail", "tier"]
ACT_COLS = ["element_id", "element_type", "verb", "object", "swimlane", "detail", "tier"]

REL_KINDS = [  # (arrow, kind, reversed) reversed=True means whole/parent is on the right
    ("<|--", "generalization", False), ("--|>", "generalization", True),
    ("*--", "composition", False), ("--*", "composition", True),
    ("o--", "aggregation", False), ("--o", "aggregation", True),
    ("..>", "dependency", False), ("<..", "dependency", True),
    ("-->", "association", False), ("<--", "association", True),
    ("--", "association", False),
]

REL_RE = re.compile(
    r'^(?P<a>\w+)\s*(?:"(?P<ma>[^"]*)")?\s*(?P<arrow><\|--|--\|>|\*--|--\*|o--|--o|\.\.>|<\.\.|-->|<--|--)'
    r'\s*(?:"(?P<mb>[^"]*)")?\s*(?P<b>\w+)\s*(?::\s*(?P<label>.*))?$'
)
BLOCK_RE = re.compile(r'^(?:(abstract)\s+)?(class|enum|interface)\s+"?(\w+)"?.*?(\{)?\s*$')
ATTR_RE = re.compile(r'^[+\-#~]?\s*(\w+)\s*:\s*(.+)$')


class FlattenError(RuntimeError):
    """Raised on diagram flattening errors."""


class InventoryNotAllowedError(FlattenError):
    """Raised when extraction from a diagram is disallowed by parse_check."""


def _strip_puml(lines: Sequence[str]) -> list[str]:
    """Strip comments, styling directives, and empty lines."""
    out: list[str] = []
    for raw in lines:
        line = raw.strip()
        if (
            not line
            or line.startswith("'")
            or line.startswith("skinparam")
            or line.startswith("hide")
            or line.startswith("@startuml")
            or line.startswith("@enduml")
            or line.startswith("title")
        ):
            continue
        out.append(line)
    return out


def parse_class_elements(text: str) -> list[dict[str, str]]:
    """Flatten a PlantUML class diagram into element dictionary rows."""
    rows: list[dict[str, str]] = []
    owner: str | None = None
    is_enum = False
    n = {"class": 0, "attribute": 0, "relationship": 0}
    pre = {"class": "CL", "attribute": "AT", "relationship": "RL"}

    def add(t: str, name: str, own: str, detail: str) -> None:
        n[t] += 1
        rows.append({
            "element_id": f"{pre[t]}-{n[t]:02d}",
            "element_type": t,
            "canonical_name": name,
            "owner_class": own,
            "detail": detail,
            "tier": "",
        })

    for line in _strip_puml(text.splitlines()):
        if owner is not None:
            if line.startswith("}"):
                owner = None
                continue
            m = ATTR_RE.match(line)
            if m:
                add("attribute", m.group(1), owner, f"type={m.group(2).strip()}")
            elif is_enum and re.match(r"^\w+$", line):
                add("attribute", line, owner, "literal")
            continue

        m = BLOCK_RE.match(line)
        if m:
            kind, name = m.group(2), m.group(3)
            stereotype = "stereotype=enum" if kind == "enum" else (
                "stereotype=interface" if kind == "interface" else ""
            )
            add("class", name, "", stereotype)
            if m.group(4):
                owner, is_enum = name, kind == "enum"
            continue

        m = REL_RE.match(line)
        if m:
            a, b = m.group("a"), m.group("b")
            ma, mb = m.group("ma") or "", m.group("mb") or ""
            kind, rev = next((k, r) for arrow, k, r in REL_KINDS if arrow == m.group("arrow"))
            if rev:
                a, b, ma, mb = b, a, mb, ma
            add("relationship", f"{a}-{b}", "", f"{a}|{kind}|{b}|{ma}:{mb}")

    return rows


def parse_activity_elements(text: str) -> list[dict[str, str]]:
    """Flatten a PlantUML activity diagram into element dictionary rows."""
    rows: list[dict[str, str]] = []
    lane = ""
    seen_lanes: set[str] = set()
    n = {"action": 0, "branch": 0, "swimlane": 0, "start": 0, "end": 0}
    pre = {"action": "AC", "branch": "BR", "swimlane": "SL", "start": "ST", "end": "EN"}
    stack: list[dict[str, Any]] = []

    def add(t: str, verb: str = "", obj: str = "", detail: str = "") -> dict[str, Any]:
        n[t] += 1
        r = {
            "element_id": f"{pre[t]}-{n[t]:02d}",
            "element_type": t,
            "verb": verb,
            "object": obj,
            "swimlane": lane,
            "detail": detail,
            "tier": "",
        }
        rows.append(r)
        return r

    buf: str | None = None
    for line in _strip_puml(text.splitlines()):
        if buf is not None:
            buf += " " + line
            if buf.endswith(";"):
                line, buf = buf, None
            else:
                continue

        m = re.match(r"^\|(?:[^|]*\|)?([^|]+)\|$", line)
        if m:
            lane = m.group(1).strip()
            if lane not in seen_lanes:
                seen_lanes.add(lane)
                add("swimlane")
            continue

        if line == "start":
            add("start")
            continue
        if line in ("stop", "end", "kill", "detach"):
            add("end")
            continue

        if line.startswith(":"):
            if not line.endswith(";") and not line.endswith("]") and not line.endswith(">"):
                buf = line
                continue
            label = re.sub(r"[;\]<>|/}]+$", "", line[1:]).strip().lower()
            label = re.sub(r"\s+", " ", label)
            verb, _, obj = label.partition(" ")
            obj, sep, target = obj.rpartition(" to ") if " to " in obj else (obj, "", "")
            add("action", verb, obj, f"to={target}" if sep else "")
            continue

        m = re.match(r"^if\s*\((.*)\)\s*then\s*(?:\((.*?)\))?\s*$", line)
        if m:
            r = add("branch", detail=m.group(1).strip())
            r["_then"], r["_else"] = (m.group(2) or "").strip(), ""
            stack.append(r)
            continue

        m = re.match(r"^elseif\s*\((.*)\)\s*then\s*(?:\((.*?)\))?\s*$", line)
        if m and stack:
            stack[-1]["_else"] = f"elseif {m.group(1).strip()}"
            continue

        m = re.match(r"^else\s*(?:\((.*?)\))?\s*$", line)
        if m and stack:
            stack[-1]["_else"] = (m.group(1) or "").strip()
            continue

        if line.startswith("endif") and stack:
            r = stack.pop()
            then_lbl = r.pop("_then", "")
            else_lbl = r.pop("_else", "")
            r["detail"] = f"{r['detail']} [{then_lbl} | {else_lbl}]"
            continue

    for r in stack:
        then_lbl = r.pop("_then", "")
        else_lbl = r.pop("_else", "")
        r["detail"] = f"{r['detail']} [{then_lbl} | {else_lbl}]"

    return rows


def tier_key(kind: str, r: Mapping[str, str]) -> str:
    """Generate the lookup key for tier mapping."""
    t = r["element_type"]
    if kind == "class":
        if t == "attribute":
            return f"attribute:{r['owner_class']}.{r['canonical_name']}"
        if t == "relationship":
            return f"relationship:{r['detail']}"
        return f"class:{r['canonical_name']}"
    if t == "action":
        detail_part = f" {r['detail']}" if r.get("detail") else ""
        return f"action:{r['swimlane']}:{r['verb']} {r['object']}{detail_part}"
    if t == "branch":
        return f"branch:{r['detail']}"
    if t == "swimlane":
        return f"swimlane:{r['swimlane']}"
    return t


def apply_tier_map(rows: list[dict[str, str]], kind: str, tier_map_path: Path | str) -> None:
    """Apply tier mappings from a CSV file. Fails if any gold element is untiered."""
    tmap: dict[str, str] = {}
    with open(tier_map_path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            tmap[r["key"]] = r["tier"]

    missing = [tier_key(kind, r) for r in rows if tier_key(kind, r) not in tmap]
    if missing:
        raise FlattenError("Untiered gold elements:\n  " + "\n  ".join(missing))

    for r in rows:
        r["tier"] = tmap[tier_key(kind, r)]


def _display_path(path: Path) -> str:
    """Repo-relative POSIX path."""
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def flatten_diagram(
    path: Path | str,
    kind: str | None = None,
    out_path: Path | str | None = None,
    parse_check: Path | str | dict[str, Any] | None = None,
    tier_map: Path | str | None = None,
    force: bool = False,
    cfg: PipelineConfig | None = None,
) -> tuple[Path, list[dict[str, str]]]:
    """Flatten one diagram file into a CSV element inventory.

    Args:
        path: Path to the .puml diagram.
        kind: 'class' or 'activity'. If None, detected from the diagram body.
        out_path: Target CSV output path.
        parse_check: Path or dict of parse_check result.
        tier_map: Optional tier mapping CSV.
        force: If True, bypass parse_check's inventory_allowed gate.
        cfg: Optional PipelineConfig.

    Returns:
        (resolved_output_path, rows)
    """
    p = Path(path)
    if not p.is_file():
        raise FlattenError(f"Diagram file not found: {p}")

    text = p.read_text(encoding="utf-8")
    actual_kind = kind or detect_kind(text)
    if actual_kind not in ("class", "activity"):
        raise FlattenError(f"Unsupported diagram kind '{actual_kind}' for {p}")

    # Guard via inventory_allowed unless forced
    if parse_check is not None and not force:
        if not inventory_allowed(parse_check, str(p)):
            raise InventoryNotAllowedError(
                f"Extraction not allowed for {p}: diagram is invalid according to parse_check. "
                f"Pass --force to override."
            )

    rows = parse_class_elements(text) if actual_kind == "class" else parse_activity_elements(text)
    if tier_map is not None:
        apply_tier_map(rows, actual_kind, tier_map)

    cols = CLASS_COLS if actual_kind == "class" else ACT_COLS

    if out_path is None:
        default_name = f"{p.stem}-elements.csv"
        out_file = resolve_output_path(ARTIFACT_DIR / default_name, None)
    else:
        out_file = resolve_output_path(out_path, None)

    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    # Write .meta.json sidecar
    _write_flatten_meta(out_file, p, actual_kind, rows, cfg)
    return out_file, rows


def _write_flatten_meta(
    out_path: Path,
    diagram_path: Path,
    kind: str,
    rows: Sequence[Mapping[str, str]],
    cfg: PipelineConfig | None,
) -> Path:
    """Write provenance sidecar beside the output CSV."""
    meta_path = out_path.with_name(out_path.name + ".meta.json")
    counts: dict[str, int] = {}
    for r in rows:
        t = r.get("element_type", "unknown")
        counts[t] = counts.get(t, 0) + 1

    meta = {
        "pipeline_version": PIPELINE_VERSION,
        "stage1_version": STAGE1_VERSION,
        "flatten_version": FLATTEN_VERSION,
        "kind": kind,
        "input_diagram": _display_path(diagram_path),
        "input_sha256": sha256_of(diagram_path),
        "total_elements": len(rows),
        "counts": counts,
    }
    meta_path.write_text(
        json.dumps(meta, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return meta_path


def run_flatten(
    run_id: str,
    class_puml: Path | str | None = None,
    activity_puml: Path | str | None = None,
    out_dir: Path | str | None = None,
    parse_check: Path | str | dict[str, Any] | None = None,
    tier_map: Path | str | None = None,
    force: bool = False,
    cfg: PipelineConfig | None = None,
) -> dict[str, Any]:
    """Batch flatten diagrams for a given run_id."""
    if not run_id or not str(run_id).strip():
        raise FlattenError("run_id must be a non-empty string.")
    if class_puml is None and activity_puml is None:
        raise FlattenError("Pass at least one of --class-puml or --activity-puml.")

    target_dir = resolve_output_path(out_dir or ARTIFACT_DIR, None)
    target_dir.mkdir(parents=True, exist_ok=True)

    outputs: dict[str, str] = {}
    total_elements = 0

    if class_puml is not None:
        class_out = target_dir / f"{run_id}__class-elements.csv"
        out, rows = flatten_diagram(
            class_puml,
            kind="class",
            out_path=class_out,
            parse_check=parse_check,
            tier_map=tier_map,
            force=force,
            cfg=cfg,
        )
        outputs["class_csv"] = _display_path(out)
        total_elements += len(rows)

    if activity_puml is not None:
        act_out = target_dir / f"{run_id}__activity-elements.csv"
        out, rows = flatten_diagram(
            activity_puml,
            kind="activity",
            out_path=act_out,
            parse_check=parse_check,
            tier_map=tier_map,
            force=force,
            cfg=cfg,
        )
        outputs["activity_csv"] = _display_path(out)
        total_elements += len(rows)

    payload = {
        "run_id": str(run_id),
        "outputs": outputs,
        "total_elements": total_elements,
    }
    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m pipeline.flatten",
        description="Stage 1: Flatten PlantUML diagrams into element CSV inventories.",
    )
    # Mode 1: single diagram
    parser.add_argument("--kind", choices=["class", "activity"], help="Diagram kind.")
    parser.add_argument("--in", dest="in_path", help="Single .puml input file.")
    parser.add_argument("--out", dest="out_path", help="Output .csv file path.")

    # Mode 2: batch / pipeline run
    parser.add_argument("--run-id", help="Opaque label for this run.")
    parser.add_argument("--class-puml", help="Class diagram .puml file.")
    parser.add_argument("--activity-puml", help="Activity diagram .puml file.")
    parser.add_argument("--out-dir", help="Directory for output CSV files.")

    # Shared options
    parser.add_argument("--parse-check", help="Path to __parse_check.json report.")
    parser.add_argument("--tier-map", help="Path to tier-map CSV for gold validation.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Bypass inventory_allowed validation gate from parse_check.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.in_path:
            out, rows = flatten_diagram(
                path=args.in_path,
                kind=args.kind,
                out_path=args.out_path,
                parse_check=args.parse_check,
                tier_map=args.tier_map,
                force=args.force,
            )
            print(f"flatten {FLATTEN_VERSION}: {len(rows)} elements -> {_display_path(out)}")
            return EXIT_OK

        if args.run_id:
            payload = run_flatten(
                run_id=args.run_id,
                class_puml=args.class_puml,
                activity_puml=args.activity_puml,
                out_dir=args.out_dir,
                parse_check=args.parse_check,
                tier_map=args.tier_map,
                force=args.force,
            )
            print(
                f"flatten {FLATTEN_VERSION} [run={payload['run_id']}]: "
                f"{payload['total_elements']} total elements extracted."
            )
            for k, p in payload["outputs"].items():
                print(f"  {k} -> {p}")
            return EXIT_OK

        parser.print_help(sys.stderr)
        return EXIT_USAGE

    except (FlattenError, ConfigError) as exc:
        print(f"flatten error: {exc}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
