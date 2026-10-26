"""Stage S2 -- similarity matrix (spec §6).

Embedding is applied to `label_norm` only, per diagram, per kind block.

No intra-generation matrix is computed: there is no cosine dedup (§5.3).
Encoding happens exactly once per `run_id`, never per threshold.

For `transition` and `swimlane` no embedding is computed at all. Both are matched
purely by the identity of already-matched actions (§7.3), so a similarity row
would never be read.
"""

from __future__ import annotations

from typing import Any

import numpy as np

# Kinds matched by construction from already-matched actions (§6, §7.3).
NO_EMBEDDING_KINDS = frozenset({"transition", "swimlane"})


def _encoder(config: dict):
    """Load the pinned sentence-transformer once (§6, §9.4)."""
    from sentence_transformers import SentenceTransformer

    kwargs: dict[str, Any] = {}
    if config.get("embedding_revision"):
        kwargs["revision"] = config["embedding_revision"]
    return SentenceTransformer(config["embedding_model"], **kwargs)


def encode_text(model, texts: list[str], config: dict) -> np.ndarray:
    return np.asarray(model.encode(
        texts,
        normalize_embeddings=config["normalize_embeddings"],
        show_progress_bar=False,
    ), dtype=np.float64)


def embed_label(element: dict) -> str:
    """The string actually encoded for one element (§6).

    For `attribute` it is `"<owner> <name>"`, so that `Invoice date` and
    `Payment date` are separated in the embedding as well as by the two-tier
    rule in §7.2. For `object_node` only the entity part is encoded; the status
    is compared exactly by the rule layer (§7.4.4). S1 already wrote
    `label_norm` accordingly.
    """
    return element["label_norm"]


def run(elements: dict, config: dict, diagrams) -> tuple[dict, dict]:
    """Build the per-(diagram, kind) cosine blocks.

    Returns `(arrays, index)`: `arrays` maps `"<diagram>/<kind>"` to a
    `(len(gold), len(gen))` matrix; `index` records the row and column
    `element_id`s so the matrix can be read back without re-encoding.
    """
    arrays: dict[str, np.ndarray] = {}
    index: dict[str, Any] = {}
    model = None

    for diagram in diagrams:
        block = elements[diagram]
        kinds = sorted(
            {e["kind"] for e in block["gold"]} | {e["kind"] for e in block["gen"]}
        )
        for kind in kinds:
            key = f"{diagram}/{kind}"
            gold = [e for e in block["gold"] if e["kind"] == kind]
            gen = [e for e in block["gen"] if e["kind"] == kind]
            index[key] = {
                "gold": [e["element_id"] for e in gold],
                "gen": [e["element_id"] for e in gen],
                "embedded": kind not in NO_EMBEDDING_KINDS,
            }
            if kind in NO_EMBEDDING_KINDS or not gold or not gen:
                arrays[key] = np.zeros((len(gold), len(gen)), dtype=np.float64)
                continue
            if model is None:
                model = _encoder(config)
            emb_gold = encode_text(model, [embed_label(e) for e in gold], config)
            emb_gen = encode_text(model, [embed_label(e) for e in gen], config)
            arrays[key] = emb_gold @ emb_gen.T

    return arrays, index
