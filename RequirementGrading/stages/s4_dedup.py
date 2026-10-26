"""s4_dedup.py — Stage S4: Deduplication of generated units via single-linkage clustering."""

from __future__ import annotations

import json
from pathlib import Path

from RequirementGrading.config import GradingConfig
from RequirementGrading.stages.s1_sim import load_similarity_matrix


def run_s4(
    units_file: Path,
    sim_npy_path: Path,
    out_dir: Path,
    config: GradingConfig,
) -> Path:
    """Execute Stage S4: Single-linkage clustering on sim_gg >= dedup_threshold."""
    units_data = json.loads(units_file.read_text(encoding="utf-8"))
    gen_units = units_data.get("gen", [])
    m = len(gen_units)

    if m == 0:
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "04_dedup.json"
        out_file.write_text(json.dumps({"kept": [], "redundant": []}, indent=2), encoding="utf-8")
        return out_file

    sim, sim_gg = load_similarity_matrix(sim_npy_path)

    # 1. Build adjacency list for single-linkage (connected components)
    adj = {i: set() for i in range(m)}
    for i in range(m):
        for j in range(i + 1, m):
            if sim_gg[i, j] >= config.dedup_threshold:
                adj[i].add(j)
                adj[j].add(i)

    # 2. Find connected components (clusters)
    visited = set()
    clusters: list[list[int]] = []
    for i in range(m):
        if i not in visited:
            component = []
            queue = [i]
            visited.add(i)
            while queue:
                curr = queue.pop(0)
                component.append(curr)
                for neighbor in adj[curr]:
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)
            clusters.append(component)

    # 3. Within each cluster, select representative:
    #   1) Highest cosine to ANY gold unit
    #   2) Ties broken by unit_id ascending
    kept_ids: list[str] = []
    redundant_records: list[dict[str, str]] = []

    for cluster in clusters:
        if len(cluster) == 1:
            kept_ids.append(gen_units[cluster[0]]["unit_id"])
            continue

        def cluster_sort_key(idx: int):
            gen_id = gen_units[idx]["unit_id"]
            # Maximum cosine to any gold unit
            max_sim_to_gold = float(sim[:, idx].max()) if sim.shape[0] > 0 else 0.0
            return (-max_sim_to_gold, gen_id)

        sorted_cluster = sorted(cluster, key=cluster_sort_key)
        rep_idx = sorted_cluster[0]
        rep_id = gen_units[rep_idx]["unit_id"]
        kept_ids.append(rep_id)

        for red_idx in sorted_cluster[1:]:
            red_id = gen_units[red_idx]["unit_id"]
            redundant_records.append({
                "gen_id": red_id,
                "cluster_rep": rep_id,
            })

    # Sort kept_ids by file order
    gen_id_order = {u["unit_id"]: i for i, u in enumerate(gen_units)}
    kept_ids.sort(key=lambda x: gen_id_order.get(x, 0))

    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "04_dedup.json"
    payload = {
        "kept": kept_ids,
        "redundant": redundant_records,
    }
    out_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out_file
