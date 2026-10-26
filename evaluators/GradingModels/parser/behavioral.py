"""Behavioral PlantUML (activity, new syntax) -> Graph IR + elements (spec §5.2).

Yields `action`, `object_node`, `swimlane` and `transition` elements.

Control nodes are built into the Graph IR -- the transition walk (§5.5) and the
control checklist (§8) both need them -- but they never enter any denominator
(§5.2). `<style>` blocks, `title` lines, comments and `skinparam` directives are
ignored and do not enter any denominator either.

The parser is a single pass that maintains a stack of open control structures.
Each statement becomes a node; edges are added from the set of currently
"dangling" predecessors, which is how `if/else`, `fork`, `split` and `while`
re-converge without needing a second pass.
"""

from __future__ import annotations

import re

from .ir import Declaration, Element, ParseResult, Rejection, Violation
from .normalize import normalize_label

_IGNORED_DIRECTIVES = (
    "title", "skinparam", "hide", "show", "scale", "caption", "footer",
    "header", "legend", "end legend", "left to right direction",
    "top to bottom direction", "mainframe",
)

# `:activity;` -- may span lines and may carry a trailing <<stereotype>>.
_ACTIVITY = re.compile(r"^:(?P<body>.*);\s*(?P<stereo><<[^>]*>>)?\s*$", re.DOTALL)
# An object node: `Entity [status]`, per §5.2.
_OBJECT_NODE = re.compile(r"^(?P<entity>[^\[\]]+?)\s*\[(?P<status>[^\]]*)\]$")
_SWIMLANE = re.compile(r"^\|(?:[^|]*\|)?(?P<name>[^|]*)\|$")
_IF = re.compile(r"^if\s*\((?P<cond>.*?)\)\s*then\s*(?:\((?P<guard>.*?)\))?\s*$", re.I)
_ELSEIF = re.compile(r"^elseif\s*\((?P<cond>.*?)\)\s*then\s*(?:\((?P<guard>.*?)\))?\s*$", re.I)
_ELSE = re.compile(r"^else\s*(?:\((?P<guard>.*?)\))?\s*$", re.I)
_WHILE = re.compile(r"^while\s*\((?P<cond>.*?)\)\s*(?:is\s*\((?P<guard>.*?)\))?\s*$", re.I)
_ENDWHILE = re.compile(r"^endwhile\s*(?:\((?P<guard>.*?)\))?\s*$", re.I)
_REPEATWHILE = re.compile(r"^repeat\s+while\s*\((?P<cond>.*?)\)\s*(?:is\s*\((?P<guard>.*?)\))?\s*$", re.I)
_PARTITION = re.compile(r"^(?:partition|group|package|rectangle)\b.*\{?\s*$", re.I)
_LABEL = re.compile(r"^label\s+(?P<name>\S+)\s*$", re.I)
_GOTO = re.compile(r"^goto\s+(?P<name>\S+)\s*$", re.I)
_ARROW_LABEL = re.compile(r"^-(?:\[[^\]]*\])?->\s*(?P<label>.*?)\s*;?\s*$")
_COMMENT = re.compile(r"^\s*'")


class _Graph:
    """Control-flow graph. Nodes carry a kind; edges may carry a guard."""

    def __init__(self) -> None:
        self.nodes: dict[int, dict] = {}
        self.edges: list[dict] = []
        self._next = 0

    def add_node(self, kind: str, label: str = "", line: int | None = None,
                 **extra) -> int:
        node_id = self._next
        self._next += 1
        self.nodes[node_id] = {"id": node_id, "kind": kind, "label": label,
                               "line": line, **extra}
        return node_id

    def add_edge(self, src: int, dst: int, guard: str = "") -> None:
        self.edges.append({"source": src, "target": dst, "guard": guard})

    def out_edges(self, node_id: int) -> list[dict]:
        return [e for e in self.edges if e["source"] == node_id]

    def in_edges(self, node_id: int) -> list[dict]:
        return [e for e in self.edges if e["target"] == node_id]

    def to_json(self) -> dict:
        return {"nodes": list(self.nodes.values()), "edges": self.edges}


def parse_behavioral(text: str, rules: dict) -> ParseResult:
    result = ParseResult()
    if "@startuml" not in text:
        result.parse_error = "no @startuml found"
        return result

    graph = _Graph()
    # `pending` holds (node_id, guard) pairs awaiting a successor.
    pending: list[tuple[int, str]] = []
    stack: list[dict] = []
    lane: str | None = None
    lane_declared: list[str] = []
    in_style = False
    pending_arrow_label = ""
    labels: dict[str, int] = {}
    gotos: list[tuple[str, list[tuple[int, str]]]] = []

    def connect(target: int, guard_extra: str = "") -> None:
        nonlocal pending_arrow_label
        for src, guard in pending:
            combined = guard or guard_extra or pending_arrow_label
            graph.add_edge(src, target, combined)
        pending.clear()
        pending_arrow_label = ""

    statements = _logical_lines(text)

    for lineno, line in statements:
        low = line.lower()

        if low.startswith("<style"):
            in_style = True
            continue
        if in_style:
            if low.startswith("</style"):
                in_style = False
            continue
        if low.startswith("@startuml") or low.startswith("@enduml"):
            continue
        if _COMMENT.match(line) or low.startswith("/'"):
            continue
        if any(low == d or low.startswith(d + " ") for d in _IGNORED_DIRECTIVES):
            continue
        if low.startswith("note"):
            continue
        if low in ("}", "end group", "end partition"):
            continue

        swim = _SWIMLANE.match(line)
        if swim:
            lane = swim.group("name").strip()
            if lane not in lane_declared:
                lane_declared.append(lane)
            result.declarations.append(
                Declaration(lineno, line, "swimlane", accepted=True))
            continue

        arrow = _ARROW_LABEL.match(line)
        if arrow:
            pending_arrow_label = arrow.group("label").strip()
            result.declarations.append(
                Declaration(lineno, line, "arrow", accepted=True))
            continue

        if low in ("start",):
            node = graph.add_node("initial", line=lineno)
            connect(node)
            pending.append((node, ""))
            result.declarations.append(
                Declaration(lineno, line, "initial", accepted=True))
            continue

        if low in ("stop", "end"):
            node = graph.add_node("final", line=lineno, final_kind=low)
            connect(node)
            # A final node terminates its branch: nothing dangles afterwards.
            result.declarations.append(
                Declaration(lineno, line, "final", accepted=True))
            continue

        if low == "detach":
            # `detach` removes the dangling edge: the branch simply ends without
            # a final node. Gold uses it twice (§16.1).
            pending.clear()
            result.declarations.append(
                Declaration(lineno, line, "detach", accepted=True))
            continue

        if low == "kill":
            pending.clear()
            result.declarations.append(
                Declaration(lineno, line, "kill", accepted=True))
            continue

        label_stmt = _LABEL.match(line)
        if label_stmt:
            node = graph.add_node("label", label_stmt.group("name"), line=lineno)
            connect(node)
            pending.append((node, ""))
            labels[label_stmt.group("name")] = node
            result.declarations.append(
                Declaration(lineno, line, "label", accepted=True))
            continue

        goto_stmt = _GOTO.match(line)
        if goto_stmt:
            gotos.append((goto_stmt.group("name"), list(pending)))
            pending.clear()
            result.declarations.append(
                Declaration(lineno, line, "goto", accepted=True))
            continue

        if _PARTITION.match(line) and not line.startswith(":"):
            result.declarations.append(
                Declaration(lineno, line, "partition", accepted=True))
            continue

        # --- branching ---------------------------------------------------
        if_stmt = _IF.match(line)
        if if_stmt:
            node = graph.add_node("decision", if_stmt.group("cond") or "", line=lineno)
            connect(node)
            guard = (if_stmt.group("guard") or "").strip()
            stack.append({"type": "if", "decision": node, "branch_ends": [],
                          "line": lineno, "guards": [guard], "has_else": False})
            pending.append((node, guard))
            result.declarations.append(
                Declaration(lineno, line, "decision", accepted=True))
            continue

        elseif_stmt = _ELSEIF.match(line)
        if elseif_stmt and stack and stack[-1]["type"] == "if":
            frame = stack[-1]
            frame["branch_ends"].extend(pending)
            pending.clear()
            guard = (elseif_stmt.group("guard") or "").strip()
            frame["guards"].append(guard)
            pending.append((frame["decision"], guard))
            result.declarations.append(
                Declaration(lineno, line, "decision", accepted=True))
            continue

        else_stmt = _ELSE.match(line)
        if else_stmt and stack and stack[-1]["type"] == "if":
            frame = stack[-1]
            frame["branch_ends"].extend(pending)
            pending.clear()
            guard = (else_stmt.group("guard") or "").strip()
            frame["has_else"] = True
            frame["guards"].append(guard)
            pending.append((frame["decision"], guard))
            result.declarations.append(
                Declaration(lineno, line, "decision", accepted=True))
            continue

        if low.startswith("endif"):
            if not stack or stack[-1]["type"] != "if":
                result.declarations.append(
                    Declaration(lineno, line, "unknown", accepted=False))
                result.rejections.append(Rejection(lineno, line, "unbalanced_block"))
                continue
            frame = stack.pop()
            frame["branch_ends"].extend(pending)
            pending.clear()
            if not frame["has_else"]:
                # An if with no else: the decision itself is a dangling branch.
                frame["branch_ends"].append((frame["decision"], ""))
            merge = graph.add_node("merge", line=lineno)
            for src, guard in frame["branch_ends"]:
                graph.add_edge(src, merge, guard)
            pending.append((merge, ""))
            result.declarations.append(
                Declaration(lineno, line, "merge", accepted=True))
            continue

        while_stmt = _WHILE.match(line)
        if while_stmt:
            node = graph.add_node("decision", while_stmt.group("cond") or "",
                                  line=lineno, loop=True)
            connect(node)
            guard = (while_stmt.group("guard") or "").strip()
            stack.append({"type": "while", "decision": node, "line": lineno})
            pending.append((node, guard))
            result.declarations.append(
                Declaration(lineno, line, "decision", accepted=True))
            continue

        endwhile_stmt = _ENDWHILE.match(line)
        if endwhile_stmt and stack and stack[-1]["type"] == "while":
            frame = stack.pop()
            # The loop body flows back to the test.
            for src, guard in pending:
                graph.add_edge(src, frame["decision"], guard)
            pending.clear()
            exit_guard = (endwhile_stmt.group("guard") or "").strip()
            pending.append((frame["decision"], exit_guard))
            result.declarations.append(
                Declaration(lineno, line, "merge", accepted=True))
            continue

        if low == "repeat":
            node = graph.add_node("merge", line=lineno, repeat=True)
            connect(node)
            stack.append({"type": "repeat", "entry": node, "line": lineno})
            pending.append((node, ""))
            result.declarations.append(
                Declaration(lineno, line, "merge", accepted=True))
            continue

        repeatwhile = _REPEATWHILE.match(line)
        if repeatwhile and stack and stack[-1]["type"] == "repeat":
            frame = stack.pop()
            node = graph.add_node("decision", repeatwhile.group("cond") or "",
                                  line=lineno, loop=True)
            connect(node)
            guard = (repeatwhile.group("guard") or "").strip()
            graph.add_edge(node, frame["entry"], guard)
            pending.append((node, ""))
            result.declarations.append(
                Declaration(lineno, line, "decision", accepted=True))
            continue

        # --- concurrency -------------------------------------------------
        if low == "fork" or low == "split":
            kind = "fork" if low == "fork" else "split"
            node = graph.add_node(kind, line=lineno)
            connect(node)
            stack.append({"type": kind, "split": node, "branch_ends": [],
                          "line": lineno})
            pending.append((node, ""))
            result.declarations.append(
                Declaration(lineno, line, kind, accepted=True))
            continue

        if low in ("fork again", "split again"):
            expected = "fork" if low.startswith("fork") else "split"
            if not stack or stack[-1]["type"] != expected:
                result.declarations.append(
                    Declaration(lineno, line, "unknown", accepted=False))
                result.rejections.append(Rejection(lineno, line, "unbalanced_block"))
                continue
            frame = stack[-1]
            frame["branch_ends"].extend(pending)
            pending.clear()
            pending.append((frame["split"], ""))
            result.declarations.append(
                Declaration(lineno, line, expected, accepted=True))
            continue

        if low in ("end fork", "endfork", "end split", "endsplit", "end merge"):
            expected = "fork" if "fork" in low else "split"
            if not stack or stack[-1]["type"] != expected:
                result.declarations.append(
                    Declaration(lineno, line, "unknown", accepted=False))
                result.rejections.append(Rejection(lineno, line, "unbalanced_block"))
                continue
            frame = stack.pop()
            frame["branch_ends"].extend(pending)
            pending.clear()
            # `end merge` closes a split without synchronising (§8 item 3 cares
            # about the node type, so the distinction is kept in the IR).
            join_kind = "join" if expected == "fork" else (
                "merge" if low == "end merge" else "join")
            join = graph.add_node(join_kind, line=lineno, closes=expected)
            for src, guard in frame["branch_ends"]:
                graph.add_edge(src, join, guard)
            pending.append((join, ""))
            result.declarations.append(
                Declaration(lineno, line, join_kind, accepted=True))
            continue

        if low == "break":
            result.declarations.append(
                Declaration(lineno, line, "break", accepted=True))
            continue

        # --- activities and object nodes ---------------------------------
        activity = _ACTIVITY.match(line)
        if activity:
            body = activity.group("body").strip()
            stereotype = (activity.group("stereo") or "").strip()
            obj = _OBJECT_NODE.match(body)
            if obj:
                entity = obj.group("entity").strip()
                status = obj.group("status").strip()
                if not status:
                    result.violations.append(
                        Violation("object_node_malformed",
                                  f"object node {body!r} has an empty status",
                                  line=lineno))
                node = graph.add_node("object_node", body, line=lineno,
                                      entity=entity, status=status,
                                      stereotype=stereotype, lane=lane)
                result.declarations.append(
                    Declaration(lineno, line, "object_node", accepted=True))
            else:
                node = graph.add_node("action", body, line=lineno,
                                      stereotype=stereotype, lane=lane)
                if lane is None:
                    result.violations.append(
                        Violation("action_outside_swimlane",
                                  f"action {body!r} sits in no lane", line=lineno))
                result.declarations.append(
                    Declaration(lineno, line, "action", accepted=True))
            connect(node)
            pending.append((node, ""))
            continue

        # Anything left is a construct this parser does not know.
        result.declarations.append(Declaration(lineno, line, "unknown", accepted=False))
        result.rejections.append(Rejection(lineno, line, "unsupported_construct"))

    # Resolve gotos now that every label is known.
    for name, sources in gotos:
        target = labels.get(name)
        if target is None:
            result.violations.append(
                Violation("empty_label", f"goto {name!r} has no matching label"))
            continue
        for src, guard in sources:
            graph.add_edge(src, target, guard)

    if stack:
        for frame in stack:
            result.violations.append(
                Violation("unbalanced_block",
                          f"{frame['type']} opened at line {frame['line']} never closed",
                          line=frame["line"]))
            result.rejections.append(
                Rejection(frame["line"], frame["type"], "unbalanced_block"))
            result.declarations.append(
                Declaration(frame["line"], frame["type"], "unknown", accepted=False))

    result.graph = graph.to_json()
    result.graph["lanes"] = lane_declared
    _emit_elements(result, graph, rules)
    return result


def _logical_lines(text: str) -> list[tuple[int, str]]:
    """Group physical lines into statements.

    An activity may span several lines (`:first\\nsecond;`), so lines are
    accumulated until the statement terminator is seen.
    """
    out: list[tuple[int, str]] = []
    buffer: list[str] = []
    start = 0
    for lineno, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if not buffer:
            if not stripped:
                continue
            if stripped.startswith(":") and not re.search(r";\s*(<<[^>]*>>)?\s*$", stripped):
                buffer = [stripped]
                start = lineno
                continue
            out.append((lineno, stripped))
        else:
            buffer.append(stripped)
            if re.search(r";\s*(<<[^>]*>>)?\s*$", stripped):
                out.append((start, " ".join(buffer)))
                buffer = []
    if buffer:
        out.append((start, " ".join(buffer)))
    return out


# --- transition walk (§5.5) ------------------------------------------------

def _walk_transitions(graph: _Graph, rules: dict) -> list[dict]:
    """Pairs of actions consecutive along the control flow (§5.5).

    The walk skips every control node and object node between two actions,
    accumulating guard labels on the way. It branches at every decision and
    fork, so one action may yield several transitions. Cycles are bounded by
    visiting each `(node, incoming_edge)` pair at most once per walk, which
    terminates the payment retry loop without suppressing its back edge.
    """
    transitions: list[dict] = []
    actions = [n for n in graph.nodes.values() if n["kind"] == "action"]

    for action in actions:
        # Each walk starts fresh so that a shared downstream path is explored
        # once per originating action.
        stack: list[tuple[int, tuple[str, ...], frozenset]] = []
        for edge in graph.out_edges(action["id"]):
            guards = (edge["guard"],) if edge["guard"] else ()
            stack.append((edge["target"], guards, frozenset({(action["id"], id(edge))})))

        while stack:
            node_id, guards, seen = stack.pop()
            node = graph.nodes[node_id]
            if node["kind"] == "action":
                transitions.append({
                    "source": action["label"], "target": node["label"],
                    "guards": [g for g in guards if g],
                    "source_id": action["id"], "target_id": node_id,
                })
                continue
            if node["kind"] == "final":
                continue
            for edge in graph.out_edges(node_id):
                key = (node_id, id(edge))
                if key in seen:
                    continue
                next_guards = guards + ((edge["guard"],) if edge["guard"] else ())
                stack.append((edge["target"], next_guards, seen | {key}))

    return transitions


def ambiguous_guard_aliases(rules: dict) -> dict[str, list[str]]:
    """Aliases claimed by more than one canonical guard (§9.3, §16.5).

    §9.3 notes that `approved` could sit under both `accepted` and
    `authorized`, to be resolved by the guard's position -- order acceptance
    versus payment authorisation -- rather than guessed. Rather than encode an
    untested positional rule, `normalize_guard` leaves an ambiguous label
    unmapped, which routes the pair to `guard_ledger.csv` for a human (§7.4.6)
    and keeps §16.5 visible instead of silently decided.
    """
    owners: dict[str, list[str]] = {}
    for canonical, aliases in rules["guard_aliases"].items():
        for alias in [canonical, *aliases]:
            owners.setdefault(str(alias).lower(), []).append(canonical)
    return {alias: sorted(set(canonicals))
            for alias, canonicals in owners.items() if len(set(canonicals)) > 1}


def normalize_guard(guard: str, rules: dict) -> str:
    """Map a guard label onto its canonical form (§7.4.6).

    An alias claimed by two canonical guards is left as written: the rule layer
    then sees a label outside every alias set and routes it to the ledger,
    rather than this function picking a side by dictionary order.
    """
    text = guard.strip().strip("[]").strip()
    if not text:
        return ""
    lowered = text.lower()
    if lowered in ambiguous_guard_aliases(rules):
        return text
    for canonical, aliases in rules["guard_aliases"].items():
        if lowered == canonical.lower() or lowered in [a.lower() for a in aliases]:
            return canonical
    return text


def _emit_elements(result: ParseResult, graph: _Graph, rules: dict) -> None:
    initial = [n for n in graph.nodes.values() if n["kind"] == "initial"]
    reachable = _reachable(graph, [n["id"] for n in initial])

    for node in graph.nodes.values():
        if node["kind"] == "action":
            label = normalize_label(node["label"], rules)
            if not label:
                result.violations.append(
                    Violation("empty_label", "action empty after normalization",
                              line=node["line"]))
                continue
            if node["id"] not in reachable:
                result.violations.append(
                    Violation("orphan_node", f"action {label!r} is unreachable "
                                             "from the initial node",
                              element_id=f"ACT:{label}", line=node["line"]))
            result.elements.append(Element(
                element_id=f"ACT:{label}", kind="action", label_raw=node["label"],
                label_norm=label, line=node["line"],
                fields={"lane": node.get("lane"), "node_id": node["id"]}))

            lane = node.get("lane")
            if lane:
                result.elements.append(Element(
                    element_id=f"LANE:{label}", kind="swimlane",
                    label_raw=lane, label_norm=normalize_label(lane, rules),
                    line=node["line"],
                    fields={"action": label, "lane": lane, "node_id": node["id"]}))

        elif node["kind"] == "object_node":
            entity = normalize_label(node.get("entity", ""), rules)
            status = node.get("status", "").strip()
            if node["id"] not in reachable:
                result.violations.append(
                    Violation("orphan_node",
                              f"object node {entity}[{status}] is unreachable "
                              "from the initial node",
                              element_id=f"OBJ:{entity}[{status}]", line=node["line"]))
            result.elements.append(Element(
                element_id=f"OBJ:{entity}[{status}]", kind="object_node",
                label_raw=node["label"], label_norm=entity, line=node["line"],
                fields={"entity": entity, "status": status, "node_id": node["id"]}))

    for transition in _walk_transitions(graph, rules):
        guards = [normalize_guard(g, rules) for g in transition["guards"]]
        guards = sorted({g for g in guards if g})
        source = normalize_label(transition["source"], rules)
        target = normalize_label(transition["target"], rules)
        result.elements.append(Element(
            element_id=f"T:{source}->{target}", kind="transition",
            label_raw=f"{transition['source']}->{transition['target']}",
            label_norm=f"{source} {target}",
            fields={"source": source, "target": target, "guard": guards}))


def _reachable(graph: _Graph, roots: list[int]) -> set[int]:
    seen: set[int] = set(roots)
    stack = list(roots)
    while stack:
        node_id = stack.pop()
        for edge in graph.out_edges(node_id):
            if edge["target"] not in seen:
                seen.add(edge["target"])
                stack.append(edge["target"])
    return seen
