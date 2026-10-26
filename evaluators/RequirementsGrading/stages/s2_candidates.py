"""s2_candidates.py — Stage S2: Candidate pair generation at lowest sweep threshold."""

from __future__ import annotations

import json
from pathlib import Path

from ..config import GradingConfig
from ..models import Candidate
from .s1_sim import load_similarity_matrix


def run_s2(
    units_file: Path,
    sim_npy_path: Path,
    out_dir: Path,
    config: GradingConfig,
) -> Path:
    """Execute Stage S2: Generate candidates and write 02_candidates.json."""
    units_data = json.loads(units_file.read_text(encoding="utf-8"))
    gold = units_data.get("gold", [])
    gen = units_data.get("gen", [])

    sim, _ = load_similarity_matrix(sim_npy_path)

    review_threshold = min(config.sweep)
    candidates: list[Candidate] = []

    for g_idx, g_unit in enumerate(gold):
        for s_idx, s_unit in enumerate(gen):
            score = float(sim[g_idx, s_idx])
            if score >= review_threshold:
                is_cross_kind = (g_unit["kind"] != s_unit["kind"])
                excluded = "cross_kind" if (is_cross_kind and not config.allow_cross_kind) else None
                candidates.append(Candidate(
                    gold_id=g_unit["unit_id"],
                    gen_id=s_unit["unit_id"],
                    cosine=score,
                    excluded=excluded,
                ))

    # Deterministic sort: gold_id ascending, then cosine descending, then gen_id ascending
    candidates.sort(key=lambda c: (c.gold_id, -c.cosine, c.gen_id))

    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "02_candidates.json"
    payload = [c.to_dict() for c in candidates]
    out_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out_file
