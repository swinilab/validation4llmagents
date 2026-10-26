"""Stage S7 -- metrics (spec §10).

Computed for every `t` in `config.sweep_models`, per diagram, independently.

The two numerators are different quantities (§10): `matched_gold` counts gold
elements, `matched_gen` counts generated elements. Under one-to-one assignment
they coincide within a kind block, which makes substituting one for the other
silently harmless on well-formed submissions and wrong on the ones that matter.
Each is computed from its own side and asserted.

No weighted composite score: a figure of the form
`S = 0.35*F1_node + 0.40*F1_edge + 0.25*F1_sem` is not computed and not
reported (§10, §15).
"""

from __future__ import annotations

import collections
from typing import Any

from .. import ledgers
from ..configload import GOLD_INVENTORY
from .s0_syntax import GATE_PASS, NA


def _passing(axis_records: list[dict], diagram: str, threshold: float) -> list[dict]:
    out: list[dict] = []
    for record in axis_records:
        if record["diagram"] != diagram or record["verdict"] != "PASS":
            continue
        cosine = record.get("cosine")
        # A by-construction pair carries no cosine (§7.3): it inherits the
        # threshold decision of the action pair it was built from, which is
        # itself filtered here, so including it is correct.
        if cosine is not None and cosine < threshold:
            continue
        out.append(record)
    return out


def _f1(precision: float, recall: float) -> float:
    # §10, §13: F1 is defined as 0 when Precision + Recall == 0.
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def run(elements: dict, axis_records: list[dict], syntax: dict, rubric: dict,
        config: dict, diagrams) -> dict[str, Any]:
    out: dict[str, Any] = {}

    for diagram in diagrams:
        block = elements[diagram]
        gate = syntax[diagram].get("gate")
        gold_total = sum(GOLD_INVENTORY[diagram].values())
        n_gen = len(block["gen"])

        summary: dict[str, Any] = {
            "syntax_validity": syntax[diagram]["validity"],
            "gate": gate,
            "n_gen": n_gen,
            "gold_total": gold_total,
        }

        if gate != GATE_PASS:
            # §4.2: a failed or missing gate records the semantic metrics as
            # the string "n/a", never 0, and contributes nothing to aggregates.
            summary.update({"recall": NA, "precision": NA, "f1": NA,
                            "rubric_pass": NA, "sweep": NA})
            out[diagram] = summary
            continue

        rubric_pass = _rubric_pass_for(rubric, diagram)
        summary["rubric_pass"] = rubric_pass

        sweep: list[dict[str, Any]] = []
        for threshold in sorted(config["sweep_models"]):
            passing = _passing(axis_records, diagram, threshold)
            matched_gold = len({r["gold_id"] for r in passing})
            matched_gen = len({r["gen_id"] for r in passing})
            # Each numerator is computed from its own side (§10), never by
            # reusing the other. Assignment is one-to-one within a kind block
            # (§7.3), so each passing pair must contribute one distinct gold
            # element and one distinct generated element; a divergence means a
            # pair was double-counted on one side and the metric on that side
            # would be wrong.
            assert matched_gold == len(passing), (
                f"matched_gold {matched_gold} != {len(passing)} passing pairs: "
                "a gold element holds more than one PASS pair, which one-to-one "
                "assignment forbids")
            assert matched_gen == len(passing), (
                f"matched_gen {matched_gen} != {len(passing)} passing pairs: "
                "a generated element holds more than one PASS pair, which "
                "one-to-one assignment forbids")

            recall = matched_gold / gold_total if gold_total else 0.0
            precision = ((matched_gen + rubric_pass) / n_gen) if n_gen else 0.0
            sweep.append({
                "threshold": threshold,
                "recall": round(recall, 4),
                "precision": round(precision, 4),
                "f1": round(_f1(precision, recall), 4),
                "matched_gold": matched_gold,
                "matched_gen": matched_gen,
            })

        summary["sweep"] = sweep
        primary = next(row for row in sweep
                       if row["threshold"] == config["threshold_models"])
        summary.update({"recall": primary["recall"],
                        "precision": primary["precision"],
                        "f1": primary["f1"]})
        out[diagram] = summary

    return out


def _rubric_pass_for(rubric: dict, diagram: str) -> int:
    detail = rubric.get("unmatched_detail") or []
    judged = {row["element_id"]: row for row in rubric.get("judged", [])}
    count = 0
    for element in detail:
        if element["diagram"] != diagram:
            continue
        row = judged.get(element["element_id"], {})
        traceable = ledgers.as_bool(row.get("traceable", ""))
        consistent = ledgers.as_bool(row.get("consistent", ""))
        if traceable and consistent:
            count += 1
    return count


def diagnostics(elements: dict, axis_records: list[dict], syntax: dict,
                match: dict, candidates: list[dict], rubric: dict,
                gen_parsed: dict, config: dict, diagrams) -> dict[str, Any]:
    """The `"diagnostics"` block of `07_metrics.json`, at the primary threshold
    (§12).

    `rule_rejections` is a reported result in its own right: it is the empirical
    justification for having a rule layer at all. So is `gate_blocked` -- the
    number of models that never reached grading, with the construct that
    stopped them, is a finding about model behaviour.
    """
    threshold = config["threshold_models"]

    gate_blocked: dict[str, Any] = {}
    for diagram in diagrams:
        if syntax[diagram].get("gate") != GATE_PASS:
            gate_blocked[diagram] = {
                "gate": syntax[diagram].get("gate"),
                "validity": syntax[diagram]["validity"],
                "rejections": syntax[diagram]["rejections"],
            }

    rule_rejections: dict[str, int] = collections.Counter()
    for record in axis_records:
        if record["verdict"] == "FAIL" and record.get("failed_check"):
            rule_rejections[record["failed_check"]] += 1

    # A diagram blocked at the gate never reached matching, so only graded
    # diagrams have assignment data to report (§4.2).
    graded = [d for d in diagrams if d in match]

    prerequisite_blocked: dict[str, int] = collections.Counter()
    for diagram in graded:
        for row in match[diagram]["excluded"]:
            prerequisite_blocked[f"{diagram}/{row['kind']}"] += 1
    for record in axis_records:
        if record.get("failed_check") == "rel_endpoint":
            prerequisite_blocked[f"{record['diagram']}/relationship"] += 1

    label_collapsed = {
        diagram: {
            "gold": elements[diagram]["collapsed"]["gold"],
            "gen": elements[diagram]["collapsed"]["gen"],
        }
        for diagram in diagrams
    }

    cross_kind: list[dict] = []
    for diagram in diagrams:
        result = gen_parsed.get(diagram)
        if result is None:
            continue
        cross_kind.extend(_cross_kind_near_miss(elements[diagram], threshold))

    elements_per_kind = {
        diagram: {
            "gen": dict(collections.Counter(e["kind"] for e in elements[diagram]["gen"])),
            "gold": dict(collections.Counter(e["kind"] for e in elements[diagram]["gold"])),
        }
        for diagram in diagrams
    }

    format_violations: dict[str, int] = collections.Counter()
    for diagram in diagrams:
        for violation in elements[diagram]["violations"]:
            format_violations[violation["code"]] += 1

    return {
        "threshold": threshold,
        "gate_blocked": gate_blocked,
        "rule_rejections": dict(sorted(rule_rejections.items())),
        "prerequisite_blocked": dict(sorted(prerequisite_blocked.items())),
        "label_collapsed": label_collapsed,
        "dropped_arrows": {d: elements[d]["dropped"] for d in diagrams},
        "cross_kind_near_miss": cross_kind,
        "manual_resolved": rubric.get("manual_resolved", {}),
        "elements_per_kind": elements_per_kind,
        "format_violations": dict(sorted(format_violations.items())),
        "excluded_candidates": dict(sorted(collections.Counter(
            c["excluded"] for c in candidates if c["excluded"]).items())),
    }


def _cross_kind_near_miss(block: dict, threshold: float) -> list[dict]:
    """Pairs the kind blocking prevented -- right text, wrong element type (§12).

    Computed from labels rather than embeddings: a cross-kind cosine matrix is
    never built (§6), so an exact normalized-label collision is the signal
    available without re-encoding, and it is the unambiguous case.
    """
    gold_by_label: dict[str, list[dict]] = {}
    for element in block["gold"]:
        gold_by_label.setdefault(element["label_norm"], []).append(element)

    out: list[dict] = []
    for element in block["gen"]:
        for gold in gold_by_label.get(element["label_norm"], []):
            if gold["kind"] != element["kind"]:
                out.append({
                    "gold_id": gold["element_id"], "gen_id": element["element_id"],
                    "gold_kind": gold["kind"], "gen_kind": element["kind"],
                    "label": element["label_norm"],
                })
    return out
