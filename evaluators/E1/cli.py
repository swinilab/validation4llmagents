"""CLI and batch runner for E1.

``run_e1`` is the importable entry point, so E2 can call E1 without shelling
out. The command-line interface is a thin wrapper around it.

Input files are opened read-only and never modified. Every run writes a
``<output>.meta.json`` sidecar recording ``e1_version``, the ontology SHA-256,
library versions and the effective config, so an output can be traced back to
the exact inputs that produced it.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from .config import (
    ARTIFACT_DIR,
    E1Config,
    E1ConfigError,
    REPO_ROOT,
    load_config,
    resolve_output_path,
    sha256_of,
)
from .normalize import (
    E1_VERSION,
    SCOPE_NONE,
    Normalized,
    library_versions,
    model_version,
    normalize,
    normalize_label,
)

__all__ = ["SOURCES", "SourcePreset", "run_e1", "main"]


class E1InputError(RuntimeError):
    """Raised when an input file is missing a required column or is malformed."""


@dataclass(frozen=True)
class SourcePreset:
    """One ``--source`` preset.

    Attributes:
        name: The value passed to ``--source``.
        fmt: ``csv`` or ``json``.
        columns: Columns normalized, in output order.
        optional_columns: Columns normalized only when non-empty.
        label_columns: Columns normalized with :func:`normalize_label` rather
            than :func:`normalize`, because they are short diagram labels.
    """

    name: str
    fmt: str
    columns: tuple[str, ...]
    optional_columns: frozenset[str] = frozenset()
    label_columns: frozenset[str] = frozenset()


SOURCES: dict[str, SourcePreset] = {
    "reqs-json": SourcePreset("reqs-json", "json", ("statement",)),
    "gold-reqs": SourcePreset("gold-reqs", "csv", ("statement",)),
    "class-inv": SourcePreset(
        "class-inv",
        "csv",
        ("canonical_name", "detail"),
        optional_columns=frozenset({"detail"}),
        label_columns=frozenset({"canonical_name"}),
    ),
    "activity-inv": SourcePreset(
        "activity-inv",
        "csv",
        ("verb", "object", "detail"),
        optional_columns=frozenset({"detail"}),
        label_columns=frozenset({"verb", "object"}),
    ),
}

# Suffixes appended per normalized column, in output order. ``__negated`` was
# removed in 1.1.0 and replaced by the two scope-aware flags below; see the
# README changelog.
SUFFIXES: tuple[str, ...] = (
    "__normalized",
    "__has_negation_cue",
    "__main_predicate_negated",
    "__negation_scope",
    "__negation_cues",
    "__state_mentions",
)

# Value written for a boolean suffix when a column is present but empty.
BOOL_SUFFIXES: frozenset[str] = frozenset(
    {"__has_negation_cue", "__main_predicate_negated"}
)

# Separator used inside the list-valued output columns.
LIST_SEPARATOR = "; "


def _display_path(path: Path) -> str:
    """A repo-relative path for messages and metadata, absolute as a fallback."""
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:  # pragma: no cover - guarded by resolve_output_path
        return path.resolve().as_posix()


def _result_fields(result: Normalized) -> dict[str, Any]:
    """The per-column output values for one normalization result."""
    return {
        "__normalized": result.normalized,
        "__has_negation_cue": str(result.has_negation_cue).lower(),
        "__main_predicate_negated": str(result.main_predicate_negated).lower(),
        "__negation_scope": result.negation_scope,
        "__negation_cues": LIST_SEPARATOR.join(result.negation_cues),
        "__state_mentions": LIST_SEPARATOR.join(result.state_mentions),
    }


def _read_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """Read a CSV read-only, returning its field order and rows."""
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise E1InputError(f"{path} is empty: no CSV header row found.")
        fieldnames = list(reader.fieldnames)
        rows = [{k: ("" if v is None else v) for k, v in row.items() if k is not None}
                for row in reader]
    return fieldnames, rows


def _read_json_rows(path: Path) -> tuple[list[str], list[dict[str, Any]]]:
    """Read a JSON array of objects read-only, returning key order and rows."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise E1InputError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(data, list):
        raise E1InputError(f"{path} must contain a JSON array of objects.")
    fieldnames: list[str] = []
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            raise E1InputError(f"{path} element {index} is not a JSON object.")
        for key in item:
            if key not in fieldnames:
                fieldnames.append(key)
        rows.append(dict(item))
    return fieldnames, rows


def _validate_columns(preset: SourcePreset, fieldnames: Sequence[str], path: Path) -> list[str]:
    """Check the required columns are present; return the ones to normalize.

    An optional column (``detail``) may be absent from the file entirely; a
    required one may not.

    Raises:
        E1InputError: naming the missing column and the columns that are there.
    """
    present = list(fieldnames)
    missing = [
        column
        for column in preset.columns
        if column not in present and column not in preset.optional_columns
    ]
    if missing:
        raise E1InputError(
            f"{path}: --source {preset.name} requires column(s) "
            f"{', '.join(missing)}, which are not present. "
            f"Columns found: {', '.join(present) or '(none)'}."
        )
    return [c for c in preset.columns if c in present]


def _normalize_row(
    row: dict[str, Any],
    columns: Iterable[str],
    preset: SourcePreset,
    cfg: E1Config,
) -> dict[str, Any]:
    """Return the added output fields for one row."""
    added: dict[str, Any] = {}
    for column in columns:
        value = row.get(column)
        text = "" if value is None else str(value)
        if column in preset.optional_columns and not text.strip():
            # Optional column present but empty: emit empty fields, do not run.
            for suffix in SUFFIXES:
                if suffix in BOOL_SUFFIXES:
                    added[f"{column}{suffix}"] = "false"
                elif suffix == "__negation_scope":
                    added[f"{column}{suffix}"] = SCOPE_NONE
                else:
                    added[f"{column}{suffix}"] = ""
            continue
        fn = normalize_label if column in preset.label_columns else normalize
        result = fn(text, cfg)
        for suffix, field_value in _result_fields(result).items():
            added[f"{column}{suffix}"] = field_value
    return added


def _write_csv(path: Path, fieldnames: Sequence[str], rows: Sequence[dict[str, Any]]) -> None:
    """Write rows as CSV with ``\\n`` line endings so output is byte-stable."""
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def _write_jsonl(path: Path, fieldnames: Sequence[str], rows: Sequence[dict[str, Any]]) -> None:
    """Write rows as JSON Lines, keys in the same order as the CSV columns."""
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            ordered = {k: row.get(k, "") for k in fieldnames}
            handle.write(json.dumps(ordered, ensure_ascii=False, sort_keys=False))
            handle.write("\n")


def _write_meta(out_path: Path, cfg: E1Config, source: str, in_path: Path, row_count: int) -> Path:
    """Write the ``.meta.json`` sidecar next to the output."""
    meta_path = out_path.with_name(out_path.name + ".meta.json")
    meta = {
        "e1_version": E1_VERSION,
        "ontology_sha256": sha256_of(Path(cfg.ontology_path)),
        "ontology_path": cfg.as_dict()["ontology_path"],
        "library_versions": {**library_versions(), "spacy_model": model_version(cfg)},
        "config": cfg.as_dict(),
        "source": source,
        "input": _display_path(in_path),
        "row_count": row_count,
    }
    meta_path.write_text(
        json.dumps(meta, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return meta_path


def run_e1(
    source: str,
    in_path: str | Path,
    out_path: str | Path | None = None,
    cfg: E1Config | None = None,
) -> dict[str, Any]:
    """Normalize one input file and write the output plus its metadata sidecar.

    Args:
        source: A key of :data:`SOURCES` (``reqs-json``, ``gold-reqs``,
            ``class-inv``, ``activity-inv``).
        in_path: Input file. Opened read-only; never modified.
        out_path: Output file. ``.jsonl`` writes JSON Lines, anything else CSV.
            When None, the output goes to ``evaluators/E1/artifact/`` under a
            name derived from the input. Must resolve inside the repository.
        cfg: Effective config; loaded from ``config.yaml`` when None.

    Returns:
        A summary dict with ``rows``, ``columns_normalized``, ``out_path``,
        ``meta_path`` and ``e1_version``.

    Raises:
        E1InputError: On an unknown source, a missing file, or a missing column.
        E1ConfigError: If ``out_path`` resolves outside the repository.
    """
    if source not in SOURCES:
        raise E1InputError(
            f"Unknown --source '{source}'. Choose one of: "
            f"{', '.join(sorted(SOURCES))}, text."
        )
    preset = SOURCES[source]
    input_file = Path(in_path)
    if not input_file.is_file():
        raise E1InputError(f"Input file not found: {input_file}")

    effective = cfg or load_config()

    if preset.fmt == "csv":
        fieldnames, rows = _read_csv_rows(input_file)
    else:
        fieldnames, rows = _read_json_rows(input_file)

    columns = _validate_columns(preset, fieldnames, input_file)

    out_fields = list(fieldnames)
    for column in columns:
        for suffix in SUFFIXES:
            name = f"{column}{suffix}"
            if name not in out_fields:
                out_fields.append(name)
    if "e1_version" not in out_fields:
        out_fields.append("e1_version")

    out_rows: list[dict[str, Any]] = []
    for row in rows:
        merged: dict[str, Any] = {k: ("" if v is None else v) for k, v in row.items()}
        merged.update(_normalize_row(row, columns, preset, effective))
        merged["e1_version"] = E1_VERSION
        out_rows.append(merged)

    # Default to evaluators/E1/artifact/ and refuse anything outside the repo.
    output_file = resolve_output_path(out_path, input_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    if output_file.suffix.lower() == ".jsonl":
        _write_jsonl(output_file, out_fields, out_rows)
    else:
        _write_csv(output_file, out_fields, out_rows)

    meta_path = _write_meta(output_file, effective, source, input_file, len(out_rows))
    return {
        "rows": len(out_rows),
        "columns_normalized": columns,
        "out_path": _display_path(output_file),
        "meta_path": _display_path(meta_path),
        "e1_version": E1_VERSION,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m evaluators.E1",
        description=(
            "E1 - text normalization for the SRS-evaluation matching cascade. "
            "Prepares strings for E2/E3; makes no matching decision."
        ),
    )
    parser.add_argument(
        "--source",
        required=True,
        choices=[*sorted(SOURCES), "text"],
        help="Input preset. 'text' normalizes a single --text string.",
    )
    parser.add_argument("--in", dest="in_path", help="Input file (required unless --source text).")
    parser.add_argument(
        "--out",
        dest="out_path",
        help=(
            "Output .csv or .jsonl file. Defaults to "
            "evaluators/E1/artifact/<input-stem>__e1.csv. Must be inside the "
            "repository; E1 never writes to /tmp or outside the checkout."
        ),
    )
    parser.add_argument("--text", help="The string to normalize, with --source text.")
    parser.add_argument(
        "--label",
        action="store_true",
        help="With --source text, use normalize_label (short labels/identifiers).",
    )
    parser.add_argument("--config", help="Path to a config.yaml holding the E1 section.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point. Returns the process exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        cfg = load_config(args.config)
    except E1ConfigError as exc:
        print(f"E1 config error: {exc}", file=sys.stderr)
        return 2

    if args.source == "text":
        if args.text is None:
            print("E1 error: --source text requires --text.", file=sys.stderr)
            return 2
        try:
            fn = normalize_label if args.label else normalize
            result = fn(args.text, cfg)
        except E1ConfigError as exc:
            print(f"E1 config error: {exc}", file=sys.stderr)
            return 2
        payload = {
            "raw": result.raw,
            "normalized": result.normalized,
            "has_negation_cue": result.has_negation_cue,
            "main_predicate_negated": result.main_predicate_negated,
            "negation_scope": result.negation_scope,
            "negation_cues": result.negation_cues,
            "state_mentions": result.state_mentions,
            "e1_version": result.e1_version,
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    if not args.in_path:
        print(f"E1 error: --source {args.source} requires --in.", file=sys.stderr)
        return 2
    try:
        summary = run_e1(args.source, args.in_path, args.out_path, cfg)
    except (E1InputError, E1ConfigError) as exc:
        print(f"E1 error: {exc}", file=sys.stderr)
        return 2

    print(
        f"E1 {summary['e1_version']}: {summary['rows']} rows -> {summary['out_path']} "
        f"(normalized: {', '.join(summary['columns_normalized'])}; "
        f"metadata: {summary['meta_path']})"
    )
    return 0
