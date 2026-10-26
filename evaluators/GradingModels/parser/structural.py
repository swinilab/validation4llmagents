"""Structural PlantUML -> elements (spec §5.1).

Yields `class`, `attribute`, `enum`, `literal` and `relationship` elements.
Dependency arrows `..>` from a class to an enum are dropped at extraction and
recorded in `dropped`: they restate a data-type relation already carried by the
attribute's type, so counting them would double-count it (§5.1).
"""

from __future__ import annotations

import re

from .ir import Declaration, Element, ParseResult, Rejection, Violation
from .normalize import normalize_label, normalize_type, split_type_annotation

# Lines that carry no element and are ignored outright (§5.2 last paragraph).
_IGNORED_DIRECTIVES = (
    "title", "skinparam", "hide", "show", "scale", "caption", "footer",
    "header", "legend", "end legend", "left to right direction",
    "top to bottom direction", "allowmixing", "allow_mixing", "set namespace",
    "together", "end together", "page", "mainframe",
)

_BLOCK_OPEN = re.compile(
    r"^(?P<kw>abstract\s+class|class|interface|enum|entity|struct|protocol|annotation|exception|metaclass)"
    r"\s+(?P<name>\"[^\"]+\"|[A-Za-z_][\w.]*)"
    r"(?P<rest>.*)$",
    re.IGNORECASE,
)

# A relationship edge. The arrow body is matched loosely and classified by
# `rel_type_map` from rules.yaml, so no arrow spelling is hard-coded here.
_EDGE = re.compile(
    r"^(?P<left>\"[^\"]+\"|[A-Za-z_][\w.]*)\s*"
    r"(?P<lmult>\"[^\"]*\")?\s*"
    r"(?P<arrow>[-.*o<>|+#^}{)(\[\]]{2,})\s*"
    r"(?P<rmult>\"[^\"]*\")?\s*"
    r"(?P<right>\"[^\"]+\"|[A-Za-z_][\w.]*)\s*"
    r"(?::\s*(?P<label>.*))?$"
)

_METHOD = re.compile(r"^[^(]*\([^)]*\)")

_COMMENT = re.compile(r"^\s*'")


def _unquote(name: str) -> str:
    return name[1:-1] if len(name) >= 2 and name.startswith('"') else name


def _decorations(arrow: str) -> tuple[str, str]:
    """Split an arrow body into its head and tail decorations."""
    return arrow.rstrip("-."), arrow.lstrip("-.")


def _arrow_matches(arrow: str, key: str) -> bool:
    """Does an arrow body carry the decoration a `rel_type_map` key names?

    PlantUML lets the line part grow (`--` / `---`) and lets a head sit on
    either end (`*--` / `--*`), so a key is matched by its decoration rather
    than by string equality.
    """
    key_head, key_tail = _decorations(key)
    arrow_head, arrow_tail = _decorations(arrow)
    key_line = "." if "." in key else "-"
    arrow_line = "." if "." in arrow else "-"
    if key_line != arrow_line:
        return False
    if not key_head and not key_tail:
        # Plain line: it must carry no decoration at all on either end.
        return not arrow_head and not arrow_tail
    # A decorated key matches when its decoration appears at either end, so
    # `*--` also matches `--*`: the same composition written the other way.
    present = {d for d in (arrow_head, arrow_tail) if d}
    return key_head in present or key_tail in present


def _classify_arrow(arrow: str, rules: dict) -> tuple[str | None, bool, bool]:
    """Classify an arrow body.

    Returns `(rel_type, directed, dropped)`. `rel_type` is None when the arrow
    matches nothing in `rel_type_map`, which is an `unknown_rel_arrow`
    violation (§5.6).
    """
    for dropped_arrow in rules["drop_arrows"]:
        if _arrow_matches(arrow, dropped_arrow):
            return None, False, True

    rel_map: dict[str, str] = rules["rel_type_map"]
    # Longest key first, so `<|--` is tested before `--`.
    for key in sorted(rel_map, key=len, reverse=True):
        if _arrow_matches(arrow, key):
            return rel_map[key], (">" in arrow or "<" in arrow), False
    return None, False, False


def parse_structural(text: str, rules: dict) -> ParseResult:
    result = ParseResult()
    if "@startuml" not in text:
        result.parse_error = "no @startuml found"
        return result

    classes: dict[str, int] = {}
    enums: dict[str, int] = {}
    members: list[tuple[str, str, str, int]] = []   # (owner, kind, raw, line)
    edges: list[dict] = []

    owner: str | None = None
    owner_kind: str | None = None
    depth = 0
    in_style = False

    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or _COMMENT.match(raw_line):
            continue
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
        if low.startswith("/'"):
            continue
        if any(low == d or low.startswith(d + " ") for d in _IGNORED_DIRECTIVES):
            continue
        if low.startswith("note"):
            continue

        # Inside a class or enum body.
        if owner is not None:
            if line.startswith("}"):
                depth -= 1
                if depth <= 0:
                    owner, owner_kind, depth = None, None, 0
                continue
            if line.endswith("{"):
                depth += 1
                continue
            members.append((owner, "literal" if owner_kind == "enum" else "attribute",
                            line, lineno))
            continue

        block = _BLOCK_OPEN.match(line)
        if block:
            name = _unquote(block.group("name"))
            kw = block.group("kw").lower()
            kind = "enum" if kw == "enum" else "class"
            target = enums if kind == "enum" else classes
            if name in target:
                result.violations.append(
                    Violation("duplicate_declaration",
                              f"{kind} {name} declared more than once", line=lineno))
                result.declarations.append(
                    Declaration(lineno, line, kind, accepted=False))
                result.rejections.append(
                    Rejection(lineno, line, "duplicate_declaration"))
                continue
            target[name] = lineno
            result.declarations.append(Declaration(lineno, line, kind, accepted=True))
            if "{" in block.group("rest"):
                owner, owner_kind, depth = name, kind, 1
            continue

        edge = _EDGE.match(line)
        if edge:
            rel_type, directed, dropped = _classify_arrow(edge.group("arrow"), rules)
            left, right = _unquote(edge.group("left")), _unquote(edge.group("right"))
            if dropped:
                # Dropped arrows are not graded, so they are not declarations.
                result.dropped.append({
                    "line": lineno, "source": line,
                    "source_element": left, "target_element": right,
                    "reason": "class_enum_dependency",
                })
                continue
            result.declarations.append(
                Declaration(lineno, line, "relationship", accepted=rel_type is not None))
            if rel_type is None:
                result.violations.append(
                    Violation("unknown_rel_arrow",
                              f"arrow {edge.group('arrow')!r} is in no rel_type_map entry",
                              line=lineno))
                result.rejections.append(Rejection(lineno, line, "malformed_edge"))
                continue
            edges.append({
                "line": lineno, "left": left, "right": right,
                "lmult": _unquote(edge.group("lmult") or '""'),
                "rmult": _unquote(edge.group("rmult") or '""'),
                "arrow": edge.group("arrow"), "rel_type": rel_type,
                "directed": directed,
                "label": (edge.group("label") or "").strip(),
            })
            continue

        # Anything left is a construct this parser does not know.
        result.declarations.append(Declaration(lineno, line, "unknown", accepted=False))
        result.rejections.append(Rejection(lineno, line, "unsupported_construct"))

    if owner is not None or depth > 0:
        result.violations.append(
            Violation("unbalanced_block", f"block {owner!r} never closed"))
        result.rejections.append(Rejection(0, str(owner), "unbalanced_block"))
        result.declarations.append(Declaration(0, str(owner), "unknown", accepted=False))

    _emit_elements(result, classes, enums, members, edges, rules)
    result.graph = {"classes": sorted(classes), "enums": sorted(enums)}
    return result


def _emit_elements(result: ParseResult, classes: dict[str, int],
                   enums: dict[str, int], members: list[tuple[str, str, str, int]],
                   edges: list[dict], rules: dict) -> None:
    for name, lineno in classes.items():
        result.elements.append(Element(
            element_id=f"C:{name}", kind="class", label_raw=name,
            label_norm=normalize_label(name, rules), line=lineno,
            fields={"name": name}))

    for name, lineno in enums.items():
        literals = sorted(
            normalize_label(raw, rules)
            for owner, kind, raw, _ in members
            if owner == name and kind == "literal"
        )
        result.elements.append(Element(
            element_id=f"E:{name}", kind="enum", label_raw=name,
            label_norm=normalize_label(name, rules), line=lineno,
            fields={"name": name, "literals": literals}))

    for owner, kind, raw, lineno in members:
        if kind == "literal":
            label = normalize_label(raw, rules)
            if not label:
                result.violations.append(
                    Violation("empty_label", "enum literal empty after normalization",
                              line=lineno))
                continue
            result.declarations.append(
                Declaration(lineno, raw, "literal", accepted=True))
            result.elements.append(Element(
                element_id=f"L:{owner}.{label}", kind="literal", label_raw=raw,
                label_norm=label, line=lineno,
                fields={"owner": owner, "name": label}))
            continue

        if _METHOD.match(raw):
            # A method is a declaration the parser understands, but §5.1 gives
            # it no element kind: accepted, and simply not graded.
            result.declarations.append(
                Declaration(lineno, raw, "method", accepted=True))
            continue

        head, type_raw = split_type_annotation(raw)
        name = normalize_label(head, rules)
        if not name:
            result.violations.append(
                Violation("empty_label", "attribute empty after normalization",
                          line=lineno))
            continue
        element_id = f"A:{owner}.{name}"
        if type_raw is None:
            result.violations.append(
                Violation("attribute_no_type", f"{owner}.{name} carries no type",
                          element_id=element_id, line=lineno))
        result.declarations.append(
            Declaration(lineno, raw, "attribute", accepted=True))
        result.elements.append(Element(
            element_id=element_id, kind="attribute", label_raw=raw,
            # §6: an attribute is encoded as "<owner> <name>", so that
            # `Invoice date` and `Payment date` are separated in the embedding.
            label_norm=f"{owner} {name}", line=lineno,
            fields={"owner": owner, "name": name,
                    "type_raw": type_raw, "type_norm": normalize_type(type_raw)}))

    for edge in edges:
        left, right = edge["left"], edge["right"]
        element_id = f"R:{left}--{right}"
        if not edge["lmult"] or not edge["rmult"]:
            result.violations.append(
                Violation("relationship_no_multiplicity",
                          f"{left}--{right} declares no multiplicity on one or both ends",
                          element_id=element_id, line=edge["line"]))
        result.elements.append(Element(
            element_id=element_id, kind="relationship",
            label_raw=edge["label"] or f"{left}--{right}",
            label_norm=normalize_label(edge["label"] or f"{left} {right}", rules),
            line=edge["line"],
            fields={"source": left, "target": right,
                    "rel_type": edge["rel_type"],
                    "mult_source": edge["lmult"], "mult_target": edge["rmult"],
                    "directed": edge["directed"], "label_raw": edge["label"]}))
