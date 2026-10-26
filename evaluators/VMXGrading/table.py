"""Reading `VMX.csv` and `requirements.json` (M2-metrics §1.1, §1.2)."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from pathlib import Path

from .configload import ROLES


@dataclass
class Row:
    number: int  # 1-based position among the data rows
    req_id: str
    refs: dict[str, list[str]] = field(default_factory=dict)


def split_refs(cell: str, separator: str) -> list[str]:
    """Split a reference cell: trimmed, empties dropped, de-duplicated (§1.2)."""
    seen: dict[str, None] = {}
    for part in cell.split(separator):
        part = part.strip()
        if part:
            seen.setdefault(part, None)
    return list(seen)


def read_requirement_ids(path: Path) -> list[str]:
    """Ids listed in `requirements.json` (a list, or an object with `requirements`)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("requirements")
    if not isinstance(data, list):
        raise ValueError(f"{path}: expected a list or an object with 'requirements'")
    ids: list[str] = []
    for entry in data:
        if isinstance(entry, dict) and isinstance(entry.get("id"), str):
            ids.append(entry["id"])
    return ids


def read_vmx(path: Path, rules: dict) -> tuple[list[Row], dict]:
    """Parse `VMX.csv` into rows keyed by the schema's column names.

    Columns are matched by exact header name. A header that is absent, or spelled
    differently, is listed in `missing_columns` and read as empty for every row.
    The `SRS-Req-ID` column is an identifier, not a reference (§1.2).
    """
    columns = rules["columns"]
    separator = rules["separator"]
    text = path.read_text(encoding="utf-8-sig")
    table = [r for r in csv.reader(io.StringIO(text)) if any(c.strip() for c in r)]
    if not table:
        return [], {"header": [], "missing_columns": sorted(columns.values()),
                    "unknown_columns": []}

    header = [h.strip() for h in table[0]]
    index = {name: header.index(name) for name in columns.values() if name in header}
    schema = {
        "header": header,
        "missing_columns": [n for n in columns.values() if n not in index],
        "unknown_columns": [h for h in header if h not in columns.values()],
    }

    def cell(row: list[str], name: str) -> str:
        position = index.get(name)
        return row[position] if position is not None and position < len(row) else ""

    rows: list[Row] = []
    for number, raw in enumerate(table[1:], start=1):
        refs = {role: split_refs(cell(raw, columns[role]), separator)
                for role in ROLES}
        rows.append(Row(number=number, req_id=cell(raw, columns["id"]).strip(),
                        refs=refs))
    return rows, schema
