"""Stage S3 -- candidate generation (spec §7.2).

Candidates are built once, at `review_threshold = min(config.sweep_models)`.
The candidate set at any higher threshold is a subset, which is what makes human
adjudication reusable (§7.2, §1 invariant 4).

The type constraint is structural, not a filter: the similarity matrix is built
per kind block (§6), so a class can only ever be a candidate for a class and an
action only for an action. An action is never considered against a decision
merely because the text is close.

No truncation: every pair above the threshold is a candidate (§7.2).
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .s2_similarity import NO_EMBEDDING_KINDS


def review_threshold(config: dict) -> float:
    return min(config["sweep_models"])


def _by_id(elements: list[dict]) -> dict[str, dict]:
    return {e["element_id"]: e for e in elements}


def run(elements: dict, arrays: dict, index: dict, config: dict,
        diagrams) -> list[dict[str, Any]]:
    """Emit candidate pairs in deterministic order (§7.2).

    Order: `gold_id` ascending, then cosine descending, then `gen_id` ascending.
    """
    threshold = review_threshold(config)
    candidates: list[dict[str, Any]] = []

    for diagram in diagrams:
        block = elements[diagram]
        gold_by_id = _by_id(block["gold"])
        gen_by_id = _by_id(block["gen"])
        kinds = sorted({k.split("/", 1)[1] for k in index if k.startswith(diagram + "/")})

        for kind in kinds:
            if kind in NO_EMBEDDING_KINDS:
                # Matched by construction in S4 from already-matched actions.
                continue
            key = f"{diagram}/{kind}"
            matrix = arrays[key]
            gold_ids = index[key]["gold"]
            gen_ids = index[key]["gen"]
            rows: list[dict[str, Any]] = []

            for i, gold_id in enumerate(gold_ids):
                for j, gen_id in enumerate(gen_ids):
                    cosine = float(matrix[i, j])
                    if cosine < threshold:
                        continue
                    excluded = _exclusion(kind, gold_by_id[gold_id],
                                          gen_by_id[gen_id], elements, diagram)
                    rows.append({
                        "diagram": diagram, "kind": kind,
                        "gold_id": gold_id, "gen_id": gen_id,
                        "cosine": round(cosine, 4), "excluded": excluded,
                    })

            rows.sort(key=lambda r: (r["gold_id"], -r["cosine"], r["gen_id"]))
            candidates.extend(rows)

    return candidates


def _exclusion(kind: str, gold: dict, gen: dict, elements: dict,
               diagram: str) -> str | None:
    """The attribute two-tier rule (§7.2).

    An attribute pair is admissible only if `owner(gold)` matched `owner(gen)`
    in M1. M1 has not run yet at S3, so the owner constraint is recorded here
    as a *potential* exclusion and resolved in S4, where the class assignment is
    known. Recording it at this stage would require the solver's output, so the
    only exclusion decidable now is a structural one: an attribute whose owner
    class is absent from the diagram entirely can never have a matched owner.
    """
    if kind != "attribute":
        return None
    gold_owners = {e["name"] for e in elements[diagram]["gold"] if e["kind"] == "class"}
    gen_owners = {e["name"] for e in elements[diagram]["gen"] if e["kind"] == "class"}
    if gold["owner"] not in gold_owners or gen["owner"] not in gen_owners:
        return "owner_unmatched"
    return None
