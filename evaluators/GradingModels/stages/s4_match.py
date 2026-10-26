"""Stage S4 -- staged assignment (spec §7.1, §7.3).

Matching is not one pass. Four element kinds are matchable only after their
prerequisites have been matched, so the stages run in dependency order and a
later stage reads the decisions of an earlier one:

    Structural:  M1 class -+-> M3 attribute      (needs owner class matched)
                 M2 enum --+-> M4 literal        (needs owner enum matched)
                              M5 relationship    (needs both endpoints matched)

    Behavioral:  M1 action -+-> M2 swimlane      (needs its action matched)
                            +-> M3 transition    (needs both endpoints matched)
                 M4 object_node                  (independent)

One-to-one within each kind block, unlike Requirements Recall, which allows
many-to-one coverage (§7.3, §15): a gold class is a named thing that either is
or is not in the submission, and two generated classes both claiming to be
`Order` is a modelling defect rather than a finer-grained rendering of one.

Ties are broken by `gold_id` then `gen_id` ascending, so the result does not
depend on input ordering or on the solver's internal tie-breaking (§7.3).
"""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy.optimize import linear_sum_assignment

# Dependency order per diagram (§7.1). `swimlane` and `transition` skip the
# solver: each is matched by construction from already-matched actions.
MATCH_ORDER = {
    "structural": ["class", "enum", "attribute", "literal", "relationship"],
    "behavioral": ["action", "object_node", "swimlane", "transition"],
}

SOLVER_KINDS = frozenset({"class", "enum", "attribute", "literal",
                          "relationship", "action", "object_node"})


def _assign(pairs: list[dict], bonus: dict[tuple[str, str], float] | None = None
            ) -> list[dict]:
    """Hungarian assignment over candidate pairs, maximising total cosine.

    Ties are resolved deterministically: the cost matrix is built from an index
    ordering sorted by element id, and equal-cosine alternatives are separated
    by a lexicographic epsilon ordering so the solver cannot pick arbitrarily.

    `bonus` adds a preference to named pairs. It exists for `object_node`,
    whose identity includes its exact status (§7.4.4): entity-only embedding
    makes `Order [filled]` and `Order [shipped]` nearly identical, so without a
    preference the solver would pair them arbitrarily and the exact status
    check would fail an otherwise correct submission. The preference steers the
    assignment without removing the mismatched pair from candidacy, so a
    genuinely wrong status is still reported by the rule layer and counted in
    `rule_rejections` (§12) rather than silently disappearing.
    """
    if not pairs:
        return []

    gold_ids = sorted({p["gold_id"] for p in pairs})
    gen_ids = sorted({p["gen_id"] for p in pairs})
    gold_pos = {g: i for i, g in enumerate(gold_ids)}
    gen_pos = {s: j for j, s in enumerate(gen_ids)}

    # Unavailable pairs get a cost that can never win.
    big = 1.0e6
    cost = np.full((len(gold_ids), len(gen_ids)), big, dtype=np.float64)
    lookup: dict[tuple[int, int], dict] = {}
    for pair in pairs:
        i, j = gold_pos[pair["gold_id"]], gen_pos[pair["gen_id"]]
        # Maximise cosine == minimise its negation. The tie-break epsilon is
        # strictly smaller than any cosine difference the matrix records
        # (cosines are rounded to 4 decimals in S3), so it orders ties only.
        epsilon = (i * len(gen_ids) + j) * 1.0e-9
        preference = (bonus or {}).get((pair["gold_id"], pair["gen_id"]), 0.0)
        cost[i, j] = -pair["cosine"] - preference + epsilon
        lookup[(i, j)] = pair

    rows, cols = linear_sum_assignment(cost)
    assigned: list[dict] = []
    for i, j in zip(rows, cols):
        pair = lookup.get((int(i), int(j)))
        if pair is None:
            continue    # a filler cell, not a real candidate
        assigned.append(pair)
    assigned.sort(key=lambda p: (p["gold_id"], p["gen_id"]))
    return assigned


def _by_id(elements: list[dict]) -> dict[str, dict]:
    return {e["element_id"]: e for e in elements}


def run(elements: dict, candidates: list[dict], config: dict,
        diagrams) -> dict[str, Any]:
    """Assign pairs per diagram, in dependency order.

    The assignment is computed at the review threshold (the candidate set), and
    each pair keeps its cosine so the per-threshold filter in S7 is a simple
    comparison -- no re-solving per threshold, because the candidate sets are
    nested and a one-to-one assignment over a subset of a nested family is
    reproduced by filtering (§7.2).
    """
    out: dict[str, Any] = {}

    for diagram in diagrams:
        block = elements[diagram]
        gold_by_id = _by_id(block["gold"])
        gen_by_id = _by_id(block["gen"])
        pairs_by_kind: dict[str, list[dict]] = {}
        for pair in candidates:
            if pair["diagram"] == diagram and pair["excluded"] is None:
                pairs_by_kind.setdefault(pair["kind"], []).append(pair)

        assigned: list[dict] = []
        # gold name -> gen name, for the prerequisite lookups below.
        class_map: dict[str, str] = {}
        enum_map: dict[str, str] = {}
        action_map: dict[str, str] = {}
        excluded_extra: list[dict] = []

        for kind in MATCH_ORDER[diagram]:
            if kind in SOLVER_KINDS:
                pairs = pairs_by_kind.get(kind, [])
                if kind == "attribute":
                    pairs, dropped = _filter_owner(pairs, gold_by_id, gen_by_id,
                                                   class_map)
                    excluded_extra.extend(dropped)
                if kind == "literal":
                    pairs, dropped = _filter_owner(pairs, gold_by_id, gen_by_id,
                                                   enum_map)
                    excluded_extra.extend(dropped)
                bonus = (_status_bonus(pairs, gold_by_id, gen_by_id)
                         if kind == "object_node" else None)
                kind_assigned = _assign(pairs, bonus)
                for pair in kind_assigned:
                    pair = dict(pair)
                    pair["stage"] = kind
                    assigned.append(pair)
                    if kind == "class":
                        class_map[gold_by_id[pair["gold_id"]]["name"]] = \
                            gen_by_id[pair["gen_id"]]["name"]
                    elif kind == "enum":
                        enum_map[gold_by_id[pair["gold_id"]]["name"]] = \
                            gen_by_id[pair["gen_id"]]["name"]
                    elif kind == "action":
                        action_map[gold_by_id[pair["gold_id"]]["label_norm"]] = \
                            gen_by_id[pair["gen_id"]]["label_norm"]
                continue

            # Matched by construction (§7.3).
            if kind == "swimlane":
                assigned.extend(_match_swimlanes(block, action_map))
            elif kind == "transition":
                assigned.extend(_match_transitions(block, action_map))

        out[diagram] = {
            "assigned": assigned,
            "excluded": excluded_extra,
            "class_map": class_map,
            "enum_map": enum_map,
            "action_map": action_map,
        }

    return out


def _status_bonus(pairs: list[dict], gold_by_id: dict,
                  gen_by_id: dict) -> dict[tuple[str, str], float]:
    """Prefer object-node pairs whose exact status agrees (§7.4.4).

    The bonus exceeds 1.0, the widest possible cosine gap, so an exact status
    match always outranks a closer-reading entity label with the wrong status.
    """
    exact = 2.0
    return {
        (pair["gold_id"], pair["gen_id"]): exact
        for pair in pairs
        if (gold_by_id[pair["gold_id"]].get("status") or "")
        == (gen_by_id[pair["gen_id"]].get("status") or "")
    }


def _filter_owner(pairs: list[dict], gold_by_id: dict, gen_by_id: dict,
                  owner_map: dict[str, str]) -> tuple[list[dict], list[dict]]:
    """Keep only pairs whose owner matched in the prerequisite stage (§7.2).

    A prerequisite that failed to match makes its dependants unmatchable. The
    asymmetry that follows is intended (§7.1): the unmatched *gold* member is
    `not_covered`, while the unmatched *gen* member falls through to the rubric.
    """
    kept: list[dict] = []
    dropped: list[dict] = []
    for pair in pairs:
        gold_owner = gold_by_id[pair["gold_id"]]["owner"]
        gen_owner = gen_by_id[pair["gen_id"]]["owner"]
        if owner_map.get(gold_owner) == gen_owner:
            kept.append(pair)
        else:
            row = dict(pair)
            row["excluded"] = "owner_unmatched"
            dropped.append(row)
    return kept, dropped


def _match_swimlanes(block: dict, action_map: dict[str, str]) -> list[dict]:
    """A gold swimlane matches the gen swimlane of the gen action its gold
    action matched (§7.3)."""
    gold_lanes = {e["action"]: e for e in block["gold"] if e["kind"] == "swimlane"}
    gen_lanes = {e["action"]: e for e in block["gen"] if e["kind"] == "swimlane"}
    out: list[dict] = []
    for gold_action, gold_lane in sorted(gold_lanes.items()):
        gen_action = action_map.get(gold_action)
        if gen_action is None:
            continue
        gen_lane = gen_lanes.get(gen_action)
        if gen_lane is None:
            continue
        out.append({
            "diagram": "behavioral", "kind": "swimlane", "stage": "swimlane",
            "gold_id": gold_lane["element_id"], "gen_id": gen_lane["element_id"],
            "cosine": None, "excluded": None, "by_construction": True,
        })
    return out


def _match_transitions(block: dict, action_map: dict[str, str]) -> list[dict]:
    """A gold transition matches the gen transition whose endpoints are the gen
    actions its gold endpoints matched (§7.3)."""
    gen_by_pair = {
        (e["source"], e["target"]): e
        for e in block["gen"] if e["kind"] == "transition"
    }
    out: list[dict] = []
    for gold in sorted((e for e in block["gold"] if e["kind"] == "transition"),
                       key=lambda e: e["element_id"]):
        gen_source = action_map.get(gold["source"])
        gen_target = action_map.get(gold["target"])
        if gen_source is None or gen_target is None:
            continue
        gen = gen_by_pair.get((gen_source, gen_target))
        if gen is None:
            continue
        out.append({
            "diagram": "behavioral", "kind": "transition", "stage": "transition",
            "gold_id": gold["element_id"], "gen_id": gen["element_id"],
            "cosine": None, "excluded": None, "by_construction": True,
        })
    return out
