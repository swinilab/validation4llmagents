"""s1_sim.py — Stage S1: Sentence embeddings and cosine similarity matrix."""

from __future__ import annotations

import json
from pathlib import Path
import numpy as np

from RequirementGrading.config import GradingConfig


_MODEL_CACHE = {}


def get_embedding_model(model_name: str, revision: str | None = None):
    """Load or get cached SentenceTransformer model."""
    from sentence_transformers import SentenceTransformer
    key = (model_name, revision)
    if key not in _MODEL_CACHE:
        kwargs = {}
        if revision:
            kwargs["revision"] = revision
        _MODEL_CACHE[key] = SentenceTransformer(model_name, **kwargs)
    return _MODEL_CACHE[key]


def run_s1(
    units_file: Path,
    out_dir: Path,
    config: GradingConfig,
) -> tuple[Path, Path]:
    """Execute Stage S1: Compute similarity matrices and write 01_sim.npy and 01_sim_index.json."""
    from sentence_transformers import util

    data = json.loads(units_file.read_text(encoding="utf-8"))
    gold = data.get("gold", [])
    gen = data.get("gen", [])

    gold_ids = [u["unit_id"] for u in gold]
    gen_ids = [u["unit_id"] for u in gen]

    gold_texts = [u["text_norm"] for u in gold]
    gen_texts = [u["text_norm"] for u in gen]

    if not gold_texts:
        raise ValueError("Gold units list is empty in 00_units.json")

    model = get_embedding_model(config.embedding_model, config.embedding_revision)

    emb_gold = model.encode(gold_texts, normalize_embeddings=config.normalize_embeddings)

    if gen_texts:
        emb_gen = model.encode(gen_texts, normalize_embeddings=config.normalize_embeddings)
        sim = util.cos_sim(emb_gold, emb_gen).numpy()
        sim_gg = util.cos_sim(emb_gen, emb_gen).numpy()
    else:
        sim = np.zeros((len(gold_texts), 0), dtype=np.float32)
        sim_gg = np.zeros((0, 0), dtype=np.float32)

    out_dir.mkdir(parents=True, exist_ok=True)
    sim_npy_path = out_dir / "01_sim.npy"
    index_json_path = out_dir / "01_sim_index.json"

    # Save both matrices into 01_sim.npy
    np.save(sim_npy_path, {"sim": sim, "sim_gg": sim_gg}, allow_pickle=True)

    # Also write 01_sim_index.json
    index_payload = {
        "gold_ids": gold_ids,
        "gen_ids": gen_ids,
        "sim_shape": list(sim.shape),
        "sim_gg_shape": list(sim_gg.shape),
    }
    index_json_path.write_text(json.dumps(index_payload, indent=2), encoding="utf-8")

    return sim_npy_path, index_json_path


def load_similarity_matrix(sim_npy_path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Load sim and sim_gg from 01_sim.npy."""
    loaded = np.load(sim_npy_path, allow_pickle=True)
    if isinstance(loaded, np.lib.npyio.NpzFile):
        return loaded["sim"], loaded["sim_gg"]
    item = loaded.item()
    return item["sim"], item["sim_gg"]
