"""Identity by distinct label (spec §5.3).

Collapse elements of the same kind sharing an identical normalized label into
one. Applied to gold and submission alike, before anything else is counted.

`G3` contains `Make Payment` and `Payment [pending]` twice -- once outside the
retry loop, once inside its body. Counting by occurrence would penalise an agent
who draws the loop without repeating the node, which is a presentation choice,
not a modelling error.

Collapsing happens *after* the transition walk, so a node appearing twice still
contributes both of its distinct incident transitions.

No cosine-based dedup is performed (§5.3, §15): `Order [filled]` and
`Order [shipped]` sit well above any sane dedup threshold and are two different
elements. Exact-label collapsing closes the denominator-inflation route without
that hazard.
"""

from __future__ import annotations

from .ir import Element, Violation


def collapse_by_label(elements: list[Element]) -> tuple[list[Element], list[dict]]:
    """Collapse same-kind elements sharing an `element_id`.

    `element_id` already encodes kind plus the identifying label (and, for an
    object node, its exact status), so it is the identity key. The first
    occurrence is kept, so the result is deterministic in source order.
    """
    kept: dict[str, Element] = {}
    collapsed: list[dict] = []

    for element in elements:
        existing = kept.get(element.element_id)
        if existing is None:
            kept[element.element_id] = element
            continue
        collapsed.append({
            "element_id": element.element_id,
            "kind": element.kind,
            "kept_line": existing.line,
            "collapsed_line": element.line,
        })

    return list(kept.values()), collapsed


def collapse_violations(collapsed: list[dict]) -> list[Violation]:
    """A `duplicate_label` violation per collapsed occurrence (§5.6)."""
    return [
        Violation(
            "duplicate_label",
            f"{item['kind']} {item['element_id']} also declared at line "
            f"{item['collapsed_line']}; collapsed into the occurrence at line "
            f"{item['kept_line']}",
            element_id=item["element_id"],
            line=item["collapsed_line"],
        )
        for item in collapsed
    ]
