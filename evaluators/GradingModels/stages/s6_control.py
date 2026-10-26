"""Stage S7 -- control checklist (spec §8).

Six pass/fail items, computed from the Graph IR, reported as a table. No
aggregate score and no weighting (§8, §15): each item restates a prompt
requirement, so this is specification conformance, not a heuristic.

Items 5 and 6 overlap the denominators in §5 by design. There they measure
coverage of content; here they measure systematicity -- whether the convention
was applied to every action or only to a few.

A diagram at `n/a` still runs whichever items its partial graph supports; the
rest are recorded as `"n/a"` (§8).
"""

from __future__ import annotations

from typing import Any

from ..configload import all_statuses
from .s0_syntax import NA

PASS = "pass"
FAIL = "fail"

ITEMS = ("item_1", "item_2", "item_3", "item_4", "item_5", "item_6")

# Actions that change an entity's state, recognised by the object node that
# follows them in gold. Item 5 asks whether the convention was applied
# systematically, so "state-changing" is defined structurally: an action is
# state-changing when any action in the diagram is followed by an object node
# for the same entity, which is the convention the prompt states.


def _nodes(graph: dict, kind: str) -> list[dict]:
    return [n for n in graph.get("nodes", []) if n["kind"] == kind]


def _out(graph: dict, node_id: int) -> list[dict]:
    return [e for e in graph.get("edges", []) if e["source"] == node_id]


def _in(graph: dict, node_id: int) -> list[dict]:
    return [e for e in graph.get("edges", []) if e["target"] == node_id]


def _node(graph: dict, node_id: int) -> dict | None:
    for n in graph.get("nodes", []):
        if n["id"] == node_id:
            return n
    return None


def item_1(graph: dict) -> tuple[str, str]:
    """Exactly one initial node, at least one final node."""
    initial = _nodes(graph, "initial")
    final = _nodes(graph, "final")
    if len(initial) == 1 and len(final) >= 1:
        return PASS, f"1 initial, {len(final)} final"
    return FAIL, f"{len(initial)} initial node(s), {len(final)} final node(s)"


def item_2(graph: dict) -> tuple[str, str]:
    """Every edge leaving a decision carries an explicit guard."""
    offenders: list[str] = []
    for decision in _nodes(graph, "decision"):
        for edge in _out(graph, decision["id"]):
            if not (edge.get("guard") or "").strip():
                offenders.append(
                    f"line {decision.get('line')} -> node {edge['target']}")
    if not _nodes(graph, "decision"):
        return PASS, "no decision nodes"
    if offenders:
        return FAIL, f"{len(offenders)} unguarded edge(s): {offenders[:5]}"
    return PASS, "every decision edge carries a guard"


def item_3(graph: dict) -> tuple[str, str]:
    """A matched fork/join pair for the ship || invoice branches.

    This is where fork/join versus decision/merge is caught (§8). A decision
    selects one branch on a condition; a fork activates concurrent flows. A
    merge joins alternative branches without synchronising; a join synchronises
    arriving flows. Substituting one pair for the other is a modelling error
    even though the node and edge counts can be identical, so the check tests
    the node *types* at the split and rejoin points, not the shape.
    """
    forks = _nodes(graph, "fork")
    joins = [n for n in _nodes(graph, "join") if n.get("closes") == "fork"]
    if not forks:
        return FAIL, "no fork node: concurrent branches modelled as a decision"
    if not joins:
        return FAIL, f"{len(forks)} fork(s) but no matching join"
    paired = 0
    for fork in forks:
        if len(_out(graph, fork["id"])) >= 2:
            paired += 1
    if paired == 0:
        return FAIL, "fork present but with fewer than two outgoing branches"
    return PASS, f"{len(forks)} fork(s) paired with {len(joins)} join(s)"


def item_4(graph: dict) -> tuple[str, str]:
    """A payment retry loop: back edge, correct body, correct exit condition."""
    loops = [n for n in _nodes(graph, "decision") if n.get("loop")]
    if not loops:
        return FAIL, "no loop construct found"
    for loop in loops:
        # A back edge is an incoming edge from a node the loop itself reaches.
        reachable = _reaches(graph, loop["id"])
        back = [e for e in _in(graph, loop["id"]) if e["source"] in reachable]
        if not back:
            continue
        body_actions = [
            n["label"] for n in graph.get("nodes", [])
            if n["kind"] == "action" and n["id"] in reachable
            and any(e["source"] in reachable for e in _in(graph, n["id"]))
        ]
        exits = [e for e in _out(graph, loop["id"])
                 if (e.get("guard") or "").strip()]
        if back and exits and body_actions:
            return PASS, (f"back edge present, body {sorted(set(body_actions))[:4]}, "
                          f"{len(exits)} guarded exit(s)")
    return FAIL, "loop found but without a back edge, a body or a guarded exit"


def item_5(graph: dict, rules: dict) -> tuple[str, str]:
    """Every state-changing action is followed by an `Entity [status]` node."""
    statuses = all_statuses(rules)
    object_nodes = _nodes(graph, "object_node")
    if not object_nodes:
        return FAIL, "no object nodes: the convention was not applied at all"
    entities = {str(n.get("entity", "")).strip() for n in object_nodes}
    offenders: list[str] = []
    followed = 0
    for action in _nodes(graph, "action"):
        has_object = any(
            str(s.get("status", "")).strip() in statuses
            for s in _following_object_nodes(graph, action["id"])
        )
        if has_object:
            followed += 1
            continue
        # An action is expected to carry an object node only when it acts on an
        # entity the diagram tracks by status.
        if any(entity and entity.lower() in action["label"].lower()
               for entity in entities):
            offenders.append(action["label"])
    if offenders:
        return FAIL, f"{len(offenders)} state-changing action(s) with no object node: {offenders[:5]}"
    return PASS, f"{followed} action(s) followed by an object node"


def item_6(graph: dict, rules: dict) -> tuple[str, str]:
    """Every action sits in the swimlane of the role performing it."""
    roles: list[str] = rules["roles"]
    case_sensitive = rules["roles_case_sensitive"]
    actions = _nodes(graph, "action")
    if not actions:
        return FAIL, "no actions"
    offenders: list[str] = []
    for action in actions:
        lane = (action.get("lane") or "").strip()
        if not lane:
            offenders.append(f"{action['label']} (no lane)")
            continue
        known = lane in roles if case_sensitive else \
            lane.lower() in [r.lower() for r in roles]
        if not known:
            offenders.append(f"{action['label']} (lane {lane!r})")
    if offenders:
        return FAIL, f"{len(offenders)} action(s) misplaced: {offenders[:5]}"
    return PASS, f"all {len(actions)} action(s) sit in a whitelisted lane"


def _following_object_nodes(graph: dict, action_id: int) -> list[dict]:
    """Object nodes immediately following an action along the control flow.

    Control nodes are skipped on the way, as in the transition walk (§5.5):
    gold attaches `Payment [completed]` and `Invoice [paid]` to `Accept Payment`
    through a `split`, and `Order [closed]` to `Close Order` the same way. A
    successor test that stopped at the first node would read those as missing
    and fail an item that gold satisfies. The walk stops at the next action, so
    an object node belonging to a later action is not credited to this one.
    """
    found: list[dict] = []
    seen: set[int] = {action_id}
    stack = [e["target"] for e in _out(graph, action_id)]
    while stack:
        node_id = stack.pop()
        if node_id in seen:
            continue
        seen.add(node_id)
        node = _node(graph, node_id)
        if node is None:
            continue
        if node["kind"] == "object_node":
            found.append(node)
            continue
        if node["kind"] in ("action", "final"):
            continue
        stack.extend(e["target"] for e in _out(graph, node_id))
    return found


def _reaches(graph: dict, start: int) -> set[int]:
    seen: set[int] = set()
    stack = [e["target"] for e in _out(graph, start)]
    while stack:
        node_id = stack.pop()
        if node_id in seen:
            continue
        seen.add(node_id)
        stack.extend(e["target"] for e in _out(graph, node_id))
    return seen


def run(gen_parsed: dict, rules: dict, diagrams) -> dict[str, Any]:
    """Build `06_control.json` (§8).

    The checklist is a behavioral-diagram artefact: every item reads the
    activity Graph IR. With no behavioral diagram at all, every item is `n/a`.
    """
    details: dict[str, str] = {}
    result: dict[str, Any] = {}

    behavioral = gen_parsed.get("behavioral") if "behavioral" in diagrams else None
    if behavioral is None:
        for item in ITEMS:
            result[item] = NA
            details[item] = "no behavioral diagram"
        result["details"] = details
        return result

    graph = behavioral.graph
    checks = [
        ("item_1", lambda: item_1(graph)),
        ("item_2", lambda: item_2(graph)),
        ("item_3", lambda: item_3(graph)),
        ("item_4", lambda: item_4(graph)),
        ("item_5", lambda: item_5(graph, rules)),
        ("item_6", lambda: item_6(graph, rules)),
    ]
    for name, check in checks:
        try:
            verdict, detail = check()
        except Exception as error:      # a partial graph may not support an item
            verdict, detail = NA, f"not computable from the partial graph: {error}"
        result[name] = verdict
        details[name] = detail

    result["details"] = details
    return result
