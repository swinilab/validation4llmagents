"""Stage S1 -- element extraction (spec §5).

Collapses by distinct label (§5.3), records format violations (§5.6), and
asserts the gold inventory exactly, per kind (§5.7). Asserting the per-kind
breakdown, not just the total, is what catches a parser change that moves
elements between kinds while leaving the sum intact.
"""

from __future__ import annotations

import collections
from typing import Any

from ..configload import GOLD_INVENTORY
from ..parser import collapse_by_label, collapse_violations


class GoldInventoryError(RuntimeError):
    """Gold did not yield the frozen inventory (§5.7, §13) -> FAILED."""


def _collapse(result) -> tuple[list, list[dict]]:
    kept, collapsed = collapse_by_label(result.elements)
    result.violations.extend(collapse_violations(collapsed))
    return kept, collapsed


def assert_gold_inventory(diagram: str, elements: list) -> None:
    """Abort unless gold matches `GOLD_INVENTORY` per kind (§5.7)."""
    expected = GOLD_INVENTORY[diagram]
    actual = collections.Counter(e.kind for e in elements)
    for kind, count in sorted(expected.items()):
        if actual.get(kind, 0) != count:
            raise GoldInventoryError(
                f"gold {diagram}: expected {count} {kind} element(s), "
                f"found {actual.get(kind, 0)}")
    unexpected = sorted(set(actual) - set(expected))
    if unexpected:
        raise GoldInventoryError(
            f"gold {diagram}: unexpected element kind(s) {unexpected}")
    total = sum(expected.values())
    if len(elements) != total:
        raise GoldInventoryError(
            f"gold {diagram}: expected {total} elements, found {len(elements)}")


def run(gold_parsed: dict, gen_parsed: dict, diagrams) -> dict[str, Any]:
    """Build `01_elements.json` (§5.7).

    A diagram whose gate failed is still extracted: §4.2 requires its syntax
    validity, its rejected declarations and its computable control items to be
    reported, and the control checklist reads the partial graph.
    """
    payload: dict[str, Any] = {}

    for diagram in diagrams:
        gold_result = gold_parsed[diagram]
        gen_result = gen_parsed[diagram]

        gold_elements, gold_collapsed = _collapse(gold_result)
        assert_gold_inventory(diagram, gold_elements)

        if gen_result is None:
            payload[diagram] = {
                "gold": [e.to_json() for e in gold_elements],
                "gen": [], "dropped": [], "violations": [],
                "collapsed": {"gold": gold_collapsed, "gen": []},
            }
            continue

        gen_elements, gen_collapsed = _collapse(gen_result)
        payload[diagram] = {
            "gold": [e.to_json() for e in gold_elements],
            "gen": [e.to_json() for e in gen_elements],
            "dropped": gen_result.dropped,
            "violations": [v.to_json() for v in gen_result.violations],
            "collapsed": {"gold": gold_collapsed, "gen": gen_collapsed},
        }

    return payload
