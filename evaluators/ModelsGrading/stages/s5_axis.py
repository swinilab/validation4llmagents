"""Stage S5 driver -- verdicts and ledgers (spec §7.4.7).

Produces `05_axis.json`, one record per assigned pair, with `verdict`,
`failed_check`, `detail` and `source` in {rule, ledger, default}.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .. import ledgers
from .s5_rules import (FAIL, LEDGER_GUARD, LEDGER_TYPE, MANUAL, PASS,
                       SOURCE_DEFAULT, SOURCE_LEDGER, SOURCE_RULE,
                       evaluate_pair)


def _by_id(elements: list[dict]) -> dict[str, dict]:
    return {e["element_id"]: e for e in elements}


def run(elements: dict, match: dict, rules: dict, config: dict, diagrams,
        review_dir: Path, on_pending: str) -> dict[str, Any]:
    """Evaluate every assigned pair, then resolve MANUAL from the ledgers."""
    records: list[dict[str, Any]] = []
    type_questions: list[dict[str, Any]] = []
    guard_questions: list[dict[str, Any]] = []

    for diagram in diagrams:
        block = elements[diagram]
        gold_by_id = _by_id(block["gold"])
        gen_by_id = _by_id(block["gen"])
        class_map = match[diagram]["class_map"]
        enum_map = match[diagram]["enum_map"]

        for pair in match[diagram]["assigned"]:
            gold = gold_by_id[pair["gold_id"]]
            gen = gen_by_id[pair["gen_id"]]
            outcome = evaluate_pair(pair["kind"], gold, gen, rules, class_map,
                                    enum_map)
            record = {
                "diagram": diagram, "kind": pair["kind"],
                "gold_id": pair["gold_id"], "gen_id": pair["gen_id"],
                "cosine": pair.get("cosine"),
                "verdict": outcome["verdict"],
                "failed_check": outcome["failed_check"],
                "detail": outcome["detail"],
                "source": SOURCE_RULE,
            }
            if outcome["verdict"] == MANUAL:
                record["ledger"] = outcome["ledger"]
                if outcome["ledger"] == LEDGER_TYPE:
                    type_questions.append({
                        "gold_id": pair["gold_id"], "gen_id": pair["gen_id"],
                        "gold_type": gold.get("type_norm") or "",
                        "gen_type": gen.get("type_norm") or "",
                        "cosine": pair.get("cosine") or "",
                    })
                else:
                    guard_questions.append({
                        "gold_id": pair["gold_id"], "gen_id": pair["gen_id"],
                        "gold_guard": ";".join(sorted(_as_list(gold.get("guard")))),
                        "gen_guard": ";".join(sorted(_as_list(gen.get("guard")))),
                        "path_detail": outcome["detail"] or "",
                    })
            records.append(record)

    type_path = review_dir / ledgers.TYPE_LEDGER
    guard_path = review_dir / ledgers.GUARD_LEDGER
    pending_type, type_rows, stale_type = ledgers.sync_ledger(
        type_path, ledgers.TYPE_FIELDS, type_questions)
    pending_guard, guard_rows, stale_guard = ledgers.sync_ledger(
        guard_path, ledgers.GUARD_FIELDS, guard_questions)

    type_verdicts = ledgers.verdict_map(type_rows, type_path)
    guard_verdicts = ledgers.verdict_map(guard_rows, guard_path)
    resolved = {LEDGER_TYPE: {}, LEDGER_GUARD: {}}

    for record in records:
        if record["verdict"] != MANUAL:
            continue
        key = (record["gold_id"], record["gen_id"])
        source = type_verdicts if record["ledger"] == LEDGER_TYPE else guard_verdicts
        if key in source:
            record["verdict"] = source[key]
            record["source"] = SOURCE_LEDGER
            bucket = resolved[record["ledger"]]
            bucket[record["verdict"]] = bucket.get(record["verdict"], 0) + 1
        elif on_pending == "provisional":
            # §7.4.7: pending pairs take `config.manual_default`
            # (`not_covered`, i.e. treated as FAIL).
            record["verdict"] = FAIL
            record["source"] = SOURCE_DEFAULT
            record["detail"] = (
                f"{record['detail']} [provisional: {config['manual_default']}]")

    pending_total = pending_type + pending_guard
    return {
        "records": records,
        "pending_type": 0 if on_pending == "provisional" else pending_type,
        "pending_guard": 0 if on_pending == "provisional" else pending_guard,
        "pending_total": 0 if on_pending == "provisional" else pending_total,
        "stale_ledger_rows": {"type": stale_type, "guard": stale_guard},
        "manual_resolved": resolved,
        "review_files": {"type": str(type_path), "guard": str(guard_path)},
    }


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    return [str(v) for v in value if str(v).strip()]
