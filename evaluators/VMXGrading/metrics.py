"""The two VMX metrics (M2-metrics §1.1).

    VMX Requirement Coverage
        requirements whose VMX row is filled in / requirements in requirements.json
    VMX Referential Integrity
        VMX references that resolve to a declared item / all VMX references

`n/a` means not measured and is never coerced to 0 (an empty denominator is not a
score of zero).
"""

from __future__ import annotations

from .configload import ROLES
from .table import Row

NA = "n/a"


def _ratio(numerator: int, denominator: int):
    return round(numerator / denominator, 4) if denominator else NA


def coverage(requirement_ids: list[str] | None, rows: list[Row] | None,
             rules: dict) -> dict:
    """VMX Requirement Coverage.

    The denominator is the requirements the agent listed, not the VMX rows, so a
    requirement with no row counts against the agent. `requirement_ids` None means
    the list is unavailable (score `n/a`); `rows` None means there is no VMX, so
    no requirement is covered.
    """
    if requirement_ids is None:
        return {"score": NA, "covered": 0, "total": 0, "requirements": [],
                "reason": "requirements.json not available"}

    by_id: dict[str, list[Row]] = {}
    for row in rows or []:
        by_id.setdefault(row.req_id, []).append(row)

    needs_by_prefix = rules["completeness"]
    details: list[dict] = []
    covered = 0
    for req_id in requirement_ids:
        prefix = next((p for p in needs_by_prefix if req_id.startswith(p)), None)
        found = by_id.get(req_id, [])
        if prefix is None:
            outcome, empty = "unknown_prefix", []
        elif not found:
            outcome, empty = "no_row", []
        else:
            empty = [role for role in needs_by_prefix[prefix]
                     if not found[0].refs[role]]
            outcome = "incomplete" if empty else "covered"
        covered += outcome == "covered"
        entry = {"id": req_id, "outcome": outcome}
        if empty:
            entry["empty"] = empty
        if len(found) > 1:
            entry["duplicate_rows"] = len(found)
        details.append(entry)

    return {"score": _ratio(covered, len(requirement_ids)), "covered": covered,
            "total": len(requirement_ids), "requirements": details}


def integrity(rows: list[Row] | None, vocab: dict[str, set[str]]) -> dict:
    """VMX Referential Integrity over every row of the VMX.

    Rows count whether or not their id appears in requirements.json: integrity
    asks only whether what the agent wrote points at something real.
    """
    resolved = 0
    total = 0
    broken: list[dict] = []
    by_role = {role: {"resolved": 0, "total": 0} for role in ROLES}
    for row in rows or []:
        for role in ROLES:
            for ref in row.refs[role]:
                total += 1
                by_role[role]["total"] += 1
                if ref in vocab[role]:
                    resolved += 1
                    by_role[role]["resolved"] += 1
                else:
                    broken.append({"row": row.number, "id": row.req_id,
                                   "column": role, "reference": ref})
    for block in by_role.values():
        block["score"] = _ratio(block["resolved"], block["total"])
    return {"score": _ratio(resolved, total), "resolved": resolved, "total": total,
            "by_column": by_role, "broken": broken}
