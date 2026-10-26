"""Human-authored review files (spec §3, §7.4.7, §7.6).

`ModelsGrading/review/` is human-authored and version-controlled. The pipeline
reads it and appends new empty question rows. It must never overwrite a filled
cell (§1 invariant 3).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable

TYPE_LEDGER = "type_ledger.csv"
GUARD_LEDGER = "guard_ledger.csv"
RUBRIC_LLM = "rubric_llm.csv"
RUBRIC_HUMAN = "rubric_human.csv"
KAPPA_ROUNDS = "kappa_rounds.json"

TYPE_FIELDS = ["gold_id", "gen_id", "gold_type", "gen_type", "cosine",
               "verdict", "reviewer", "timestamp", "note"]
GUARD_FIELDS = ["gold_id", "gen_id", "gold_guard", "gen_guard", "path_detail",
                "verdict", "reviewer", "timestamp", "note"]
# The LLM's labels must not appear in the human file. Blindness is enforced by
# the schema, not by instruction (§7.6).
RUBRIC_LLM_FIELDS = ["element_id", "kind", "label", "traceable", "consistent",
                     "rationale", "judge_model", "timestamp"]
RUBRIC_HUMAN_FIELDS = ["element_id", "kind", "label", "traceable", "consistent",
                       "reviewer", "timestamp"]

VALID_VERDICTS = {"PASS", "FAIL"}


class LedgerError(RuntimeError):
    """A ledger cell is outside its allowed vocabulary (§13) -> FAILED."""


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _write_csv(path: Path, fields: list[str], rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields,
                                extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def verdict_map(rows: list[dict[str, str]], path: Path) -> dict[tuple[str, str], str]:
    """Filled verdicts, keyed by `(gold_id, gen_id)`.

    A verdict outside `{PASS, FAIL}` aborts, naming the row (§13).
    """
    out: dict[tuple[str, str], str] = {}
    for number, row in enumerate(rows, start=2):   # header is line 1
        verdict = (row.get("verdict") or "").strip()
        if not verdict:
            continue
        if verdict not in VALID_VERDICTS:
            raise LedgerError(
                f"{path}: line {number}: verdict {verdict!r} is outside "
                f"{sorted(VALID_VERDICTS)} "
                f"(gold_id={row.get('gold_id')!r}, gen_id={row.get('gen_id')!r})")
        out[(row.get("gold_id", ""), row.get("gen_id", ""))] = verdict
    return out


def sync_ledger(path: Path, fields: list[str],
                questions: list[dict[str, Any]]) -> tuple[int, list[dict], list[str]]:
    """Merge newly needed question rows into a ledger.

    Returns `(pending_count, rows_written, stale_keys)`. Existing rows are
    preserved verbatim -- a row with a filled verdict is never modified, and a
    row whose pair is no longer assigned is kept in the file and reported as
    stale (§13).
    """
    existing = read_csv(path)
    verdict_map(existing, path)     # validates; raises on a bad cell
    by_key = {(row.get("gold_id", ""), row.get("gen_id", "")): row
              for row in existing}
    wanted = {(q["gold_id"], q["gen_id"]): q for q in questions}

    rows: list[dict] = list(existing)
    for key, question in wanted.items():
        if key in by_key:
            continue
        rows.append({field: question.get(field, "") for field in fields})

    stale = sorted(f"{k[0]}|{k[1]}" for k in by_key if k not in wanted)
    pending = sum(1 for row in rows
                  if (row.get("gold_id", ""), row.get("gen_id", "")) in wanted
                  and not (row.get("verdict") or "").strip())

    _write_csv(path, fields, rows)
    return pending, rows, stale


def sync_rubric_human(path: Path, sample: list[dict[str, Any]]) -> int:
    """Write the blind human sample, preserving filled rows. Returns pending."""
    existing = read_csv(path)
    by_id = {row.get("element_id", ""): row for row in existing}
    rows: list[dict] = list(existing)
    for item in sample:
        if item["element_id"] in by_id:
            continue
        rows.append({field: item.get(field, "") for field in RUBRIC_HUMAN_FIELDS})

    wanted = {item["element_id"] for item in sample}
    pending = sum(
        1 for row in rows
        if row.get("element_id", "") in wanted
        and not ((row.get("traceable") or "").strip()
                 and (row.get("consistent") or "").strip())
    )
    _write_csv(path, RUBRIC_HUMAN_FIELDS, rows)
    return pending


def write_rubric_llm(path: Path, rows: list[dict[str, Any]]) -> None:
    _write_csv(path, RUBRIC_LLM_FIELDS, rows)


def read_kappa_rounds(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def write_kappa_rounds(path: Path, rounds: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rounds, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")


def as_bool(value: str) -> bool | None:
    """Read a human-written yes/no cell."""
    text = (value or "").strip().lower()
    if text in ("1", "true", "yes", "y", "pass"):
        return True
    if text in ("0", "false", "no", "n", "fail"):
        return False
    return None
