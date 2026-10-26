"""Stage S5 -- rule layer (spec §7.4).

Runs once, over every assigned pair, using `label_raw` and the structured fields
from §5. The assignment proposes; this layer decides. A pair that fails here is
**not a match** -- it never enters `matched` and so never reaches any numerator
(§7.5).

`matched` is defined only after this layer. A rejected pair does *not* get a
second chance at the rubric: the rubric is for generated elements with no
assigned PASS pair at all, not a salvage route for pairs this layer threw out
(§7.5). There is one collection, built after filtering.
"""

from __future__ import annotations

from typing import Any

from ..configload import all_statuses
from ..parser.normalize import normalize_label

PASS = "PASS"
FAIL = "FAIL"
MANUAL = "MANUAL"

SOURCE_RULE = "rule"
SOURCE_LEDGER = "ledger"
SOURCE_DEFAULT = "default"

# Which ledger a MANUAL pair is routed to (§7.4.7).
LEDGER_TYPE = "type"
LEDGER_GUARD = "guard"


def _verdict(verdict: str, failed_check: str | None = None,
             detail: str | None = None, ledger: str | None = None) -> dict:
    return {"verdict": verdict, "failed_check": failed_check,
            "detail": detail, "ledger": ledger}


# --- §7.4.1 attribute type compatibility ----------------------------------

def check_attribute(gold: dict, gen: dict, rules: dict,
                    enum_map: dict[str, str] | None = None) -> dict:
    table: dict[str, dict] = rules["type_table"]
    gold_type = gold.get("type_norm")
    gen_type = gen.get("type_norm")

    if gold_type is None:
        # Gold carries no type, so there is no compatibility question to ask.
        return _verdict(PASS)

    # A type naming a declared enum is an enum-typed attribute, not a primitive
    # one: `status : OrderStatus` is compared by the enum the two sides matched
    # in M2, because the type table describes primitives only (§7.4.1) and the
    # enum's own literal set is graded separately by its `enum` element
    # (§7.4.2). Without this, every enum-typed gold attribute would be routed
    # to the ledger as an unlisted type and the identity run could not pass.
    enum_map = enum_map or {}
    if gold_type in enum_map:
        if gen_type is not None and enum_map[gold_type] == gen_type:
            return _verdict(PASS)
        return _verdict(FAIL, "type",
                        f"gold={gold_type} (enum) gen={gen_type} "
                        f"(expected {enum_map[gold_type]})")

    row = _lookup_row(table, gold_type)
    if row is None:
        # Gold's own type is in no row and names no declared enum: the table is
        # a draft (§16.2), so this is a configuration gap, not a submission
        # error, and a human decides it.
        return _verdict(MANUAL, "type",
                        f"gold type {gold_type!r} is in no type_table row",
                        LEDGER_TYPE)
    if gen_type is None:
        return _verdict(FAIL, "type",
                        f"gold={gold_type} gen=<none> (attribute carries no type)")

    if _in_list(row["accept"], gen_type) or _same_type(gold_type, gen_type):
        return _verdict(PASS)
    if _in_list(row["fail"], gen_type):
        return _verdict(FAIL, "type", f"gold={gold_type} gen={gen_type} (fail list)")
    if _in_list(row["warn"], gen_type):
        return _verdict(MANUAL, "type",
                        f"gold={gold_type} gen={gen_type} (warn list)", LEDGER_TYPE)
    # A gen type in no list at all: `type_unlisted: manual` (§9.3).
    if rules["type_unlisted"] == "manual":
        return _verdict(MANUAL, "type",
                        f"gold={gold_type} gen={gen_type} (unlisted)", LEDGER_TYPE)
    return _verdict(FAIL, "type", f"gold={gold_type} gen={gen_type} (unlisted)")


def _lookup_row(table: dict, gold_type: str) -> dict | None:
    for key, row in table.items():
        if key.lower() == gold_type.lower():
            return row
    return None


def _in_list(values: list, candidate: str) -> bool:
    return any(str(v).lower() == candidate.lower() for v in values)


def _same_type(gold_type: str, gen_type: str) -> bool:
    return gold_type.lower() == gen_type.lower()


# --- §7.4.2 enum literal sets ---------------------------------------------

def check_enum(gold: dict, gen: dict, rules: dict) -> dict:
    """Enums match on name by embedding, then their literal sets are compared
    exactly after case normalization. Literals are a closed set, so there is no
    similarity question to ask.

    The domain contains a deliberate trap: an invoice becomes `paid`, a payment
    becomes `completed`. A submission using `paid` for a payment produces a
    different literal set and fails.
    """
    gold_literals = {str(x).lower() for x in gold.get("literals", [])}
    gen_literals = {str(x).lower() for x in gen.get("literals", [])}
    if gold_literals == gen_literals:
        return _verdict(PASS)
    missing = sorted(gold_literals - gen_literals)
    extra = sorted(gen_literals - gold_literals)
    return _verdict(FAIL, "enum_literals",
                    f"missing={missing} extra={extra}")


# --- §7.4.3 relationship ---------------------------------------------------

def check_relationship(gold: dict, gen: dict, rules: dict,
                       class_map: dict[str, str]) -> dict:
    """All four conditions must hold (§7.4.3).

    `"1" -- "0..*"` written the other way round is a failure, not a presentation
    variant. An `Order *-- OrderItem` composition rendered as a plain
    association is a failure: `REQ-F-07` requires composition to be explicit
    where the part does not exist independently.
    """
    if (class_map.get(gold["source"]) != gen["source"]
            or class_map.get(gold["target"]) != gen["target"]):
        return _verdict(FAIL, "rel_endpoint",
                        f"gold={gold['source']}--{gold['target']} "
                        f"gen={gen['source']}--{gen['target']}")
    if str(gold["rel_type"]).lower() != str(gen["rel_type"]).lower():
        return _verdict(FAIL, "rel_type",
                        f"gold={gold['rel_type']} gen={gen['rel_type']}")
    if (_mult(gold["mult_source"]) != _mult(gen["mult_source"])
            or _mult(gold["mult_target"]) != _mult(gen["mult_target"])):
        return _verdict(FAIL, "rel_multiplicity",
                        f"gold={gold['mult_source']!r}..{gold['mult_target']!r} "
                        f"gen={gen['mult_source']!r}..{gen['mult_target']!r}")
    if bool(gold["directed"]) != bool(gen["directed"]):
        return _verdict(FAIL, "rel_direction",
                        f"gold directed={gold['directed']} gen directed={gen['directed']}")
    return _verdict(PASS)


def _mult(value: str | None) -> str:
    return (value or "").strip()


# --- §7.4.4 object node status --------------------------------------------

def check_object_node(gold: dict, gen: dict, rules: dict) -> dict:
    """The entity part matched by embedding; the status compared **exactly**
    against the whitelist (§7.4.4).

    `Order [filled]` and `Order [shipped]` carry near-identical embeddings and
    are two different elements; only the exact status comparison separates them.
    """
    whitelist = all_statuses(rules)
    gen_status = (gen.get("status") or "").strip()
    gold_status = (gold.get("status") or "").strip()
    if gen_status not in whitelist:
        return _verdict(FAIL, "status_unknown",
                        f"gen status {gen_status!r} is outside the whitelist")
    if gold_status != gen_status:
        return _verdict(FAIL, "status",
                        f"gold={gold_status!r} gen={gen_status!r}")
    return _verdict(PASS)


# --- §7.4.5 swimlane -------------------------------------------------------

def check_swimlane(gold: dict, gen: dict, rules: dict) -> dict:
    """The lane of the matched action compared against the role whitelist,
    case-sensitively (§7.4.5). The cheapest deterministic check in the section,
    and it tests a prompt requirement directly."""
    roles: list[str] = rules["roles"]
    gold_lane = (gold.get("lane") or "").strip()
    gen_lane = (gen.get("lane") or "").strip()
    if rules["roles_case_sensitive"]:
        known = gen_lane in roles
        equal = gold_lane == gen_lane
    else:
        lowered = [r.lower() for r in roles]
        known = gen_lane.lower() in lowered
        equal = gold_lane.lower() == gen_lane.lower()
    if not known:
        return _verdict(FAIL, "swimlane",
                        f"gen lane {gen_lane!r} is outside the role whitelist")
    if not equal:
        return _verdict(FAIL, "swimlane", f"gold={gold_lane!r} gen={gen_lane!r}")
    return _verdict(PASS)


# --- §7.4.6 transition guard ----------------------------------------------

def check_transition(gold: dict, gen: dict, rules: dict) -> dict:
    """Guards are compared after normalization (§7.4.6).

    This is the check that catches branch inversion. Swapping `accepted` and
    `declined` on transitions 2 and 3 leaves every node and every edge in place
    and inverts the business meaning; nothing else in the pipeline would notice.

    Decision labels are never scored: gold writes `if () then ([accepted])` with
    an empty condition, so the whole meaning sits in the guard.
    """
    gold_guard = _guard_set(gold.get("guard"))
    gen_guard = _guard_set(gen.get("guard"))

    if gold_guard == gen_guard:
        return _verdict(PASS)
    if gold_guard and gen_guard:
        if _unrecognised(gen.get("guard"), rules):
            return _verdict(MANUAL, "guard",
                            f"gold={sorted(gold_guard)} gen={sorted(gen_guard)} "
                            "(gen guard outside every alias set)",
                            LEDGER_GUARD)
        return _verdict(FAIL, "guard",
                        f"gold={sorted(gold_guard)} gen={sorted(gen_guard)}")
    if gold_guard and not gen_guard:
        # Gold non-empty, gen guard outside every alias set -> MANUAL (§7.4.6).
        return _verdict(MANUAL, "guard",
                        f"gold={sorted(gold_guard)} gen=<empty>", LEDGER_GUARD)
    # Gold empty, gen non-empty -> MANUAL (§7.4.6).
    return _verdict(MANUAL, "guard",
                    f"gold=<empty> gen={sorted(gen_guard)}", LEDGER_GUARD)


def _guard_set(guard: Any) -> set[str]:
    if guard is None:
        return set()
    if isinstance(guard, str):
        return {guard} if guard.strip() else set()
    return {g for g in guard if str(g).strip()}


def _unrecognised(guard: Any, rules: dict) -> bool:
    """Is any guard label outside every alias set (§7.4.6)?"""
    aliases = {a.lower() for members in rules["guard_aliases"].values()
               for a in members}
    aliases |= {k.lower() for k in rules["guard_aliases"]}
    for label in _guard_set(guard):
        if str(label).strip().lower() not in aliases:
            return True
    return False


# --- dispatch --------------------------------------------------------------

_CHECKS = {
    "attribute": check_attribute,
    "enum": check_enum,
    "object_node": check_object_node,
    "swimlane": check_swimlane,
    "transition": check_transition,
}


def evaluate_pair(kind: str, gold: dict, gen: dict, rules: dict,
                  class_map: dict[str, str],
                  enum_map: dict[str, str] | None = None) -> dict:
    """Apply the applicable checks to one assigned pair.

    `class` and `literal` carry no structured field beyond their label, which
    the embedding already compared, so every applicable check passes for them.
    """
    if kind == "relationship":
        return check_relationship(gold, gen, rules, class_map)
    if kind == "attribute":
        return check_attribute(gold, gen, rules, enum_map)
    check = _CHECKS.get(kind)
    if check is None:
        return _verdict(PASS)
    return check(gold, gen, rules)
