"""s6_metrics.py — Stage S6: Compute Requirement Recall, Precision, F1 and Diagnostics across threshold sweep."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..config import GradingConfig
from ..models import Candidate


def run_s6(
    units_file: Path,
    candidates_file: Path,
    axis_file: Path,
    dedup_file: Path,
    out_dir: Path,
    run_id: str,
    config: GradingConfig,
    rubric: dict,
    pending_polarity: int,
    is_provisional: bool,
) -> Path:
    """Execute Stage S6: Compute metrics and diagnostics across the sweep.

    `rubric` is the result of S5: its pass count enters Precision at the primary
    threshold, and its κ and pending count are reported.
    """
    rubric_pass_count = rubric["rubric_pass"]
    units_data = json.loads(units_file.read_text(encoding="utf-8"))
    gold = units_data.get("gold", [])
    gen = units_data.get("gen", [])
    violations = units_data.get("violations", [])

    gold_total = len(gold)
    gold_by_id = {u["unit_id"]: u for u in gold}
    gen_by_id = {u["unit_id"]: u for u in gen}

    dedup_data = json.loads(dedup_file.read_text(encoding="utf-8"))
    kept_ids = set(dedup_data.get("kept", []))
    redundant_list = dedup_data.get("redundant", [])
    s_size = len(kept_ids)

    candidates_raw = json.loads(candidates_file.read_text(encoding="utf-8"))
    cand_by_pair = {(c["gold_id"], c["gen_id"]): c for c in candidates_raw}

    axis_results = json.loads(axis_file.read_text(encoding="utf-8"))
    axis_by_pair = {(r["gold_id"], r["gen_id"]): r for r in axis_results}

    # Evaluate for each threshold in sweep
    sweep_results = []
    primary_diagnostics = {}

    for t in sorted(config.sweep):
        # Filter candidate pairs with cosine >= t
        matched_gold_set = set()
        matched_gen_set = set()

        for (gid, sid), cand in cand_by_pair.items():
            if cand.get("excluded") is not None:
                continue
            cos = cand.get("cosine", 0.0)
            if cos < t:
                continue

            axis_res = axis_by_pair.get((gid, sid))
            if axis_res and axis_res.get("verdict") == "PASS":
                matched_gold_set.add(gid)
                if sid in kept_ids:
                    matched_gen_set.add(sid)

        matched_gold = len(matched_gold_set)
        matched_gen = len(matched_gen_set)

        recall = round(matched_gold / gold_total, 4) if gold_total > 0 else 0.0
        precision_num = matched_gen + (rubric_pass_count if t == config.threshold else 0)
        precision = round(precision_num / s_size, 4) if s_size > 0 else 0.0

        if precision + recall > 0:
            f1 = round(2.0 * precision * recall / (precision + recall), 4)
        else:
            f1 = 0.0

        row = {
            "threshold": round(float(t), 2),
            "recall": recall,
            "precision": precision,
            "f1": f1,
            "matched_gold": matched_gold,
            "matched_gen": matched_gen,
        }
        sweep_results.append(row)

        if abs(t - config.threshold) < 1e-4:
            # Diagnostics at primary threshold
            cross_us_count = 0
            for (gid, sid), cand in cand_by_pair.items():
                if cand.get("excluded") is not None or cand.get("cosine", 0.0) < t:
                    continue
                ax = axis_by_pair.get((gid, sid))
                if ax and ax.get("verdict") == "PASS" and sid in kept_ids:
                    g_u = gold_by_id.get(gid)
                    s_u = gen_by_id.get(sid)
                    if g_u and s_u and g_u["parent_id"] != s_u["parent_id"]:
                        cross_us_count += 1

            # Cross-kind would cover
            cross_kind_covered_gold = set()
            for cand in candidates_raw:
                if cand.get("excluded") == "cross_kind" and cand.get("cosine", 0.0) >= t:
                    gid = cand["gold_id"]
                    if gid not in matched_gold_set:
                        cross_kind_covered_gold.add(gid)

            # Axis rejections
            rejections = {"polarity": 0, "identifier": 0, "numeric": 0}
            for (gid, sid), cand in cand_by_pair.items():
                if cand.get("excluded") is not None or cand.get("cosine", 0.0) < t:
                    continue
                ax = axis_by_pair.get((gid, sid))
                if ax and ax.get("verdict") == "FAIL":
                    fa = ax.get("failed_axis")
                    if fa in rejections:
                        rejections[fa] += 1

            # Manual resolved
            manual_resolved = {"PASS": 0, "FAIL": 0}
            for ax in axis_results:
                if ax.get("source") == "ledger":
                    v = ax.get("verdict")
                    if v in manual_resolved:
                        manual_resolved[v] += 1

            # AC per story distribution
            stories_ac_count = {}
            for u in gen:
                if u["kind"] == "ac":
                    pid = u["parent_id"]
                    stories_ac_count[pid] = stories_ac_count.get(pid, 0) + 1

            # AC length
            gen_ac_lens = [len(u["text_raw"].split()) for u in gen if u["kind"] == "ac"]
            gold_ac_lens = [len(u["text_raw"].split()) for u in gold if u["kind"] == "ac"]
            mean_gen_len = round(sum(gen_ac_lens) / len(gen_ac_lens), 1) if gen_ac_lens else 0.0
            mean_gold_len = round(sum(gold_ac_lens) / len(gold_ac_lens), 1) if gold_ac_lens else 0.0

            # Format violations
            violation_counts = {}
            for v in violations:
                c = v.get("code", "unknown")
                violation_counts[c] = violation_counts.get(c, 0) + 1

            primary_diagnostics = {
                "cross_us_matches": cross_us_count,
                "cross_kind_would_cover": len(cross_kind_covered_gold),
                "axis_rejections": rejections,
                "dedup_removed": len(redundant_list),
                "manual_resolved": manual_resolved,
                "ac_per_story": stories_ac_count,
                "ac_length": {
                    "mean_gen_tokens": mean_gen_len,
                    "mean_gold_tokens": mean_gold_len,
                },
                "format_violations": violation_counts,
            }

    status_str = "provisional" if is_provisional else "final"
    manual_def = config.manual_default if is_provisional else None

    out_payload = {
        "run_id": run_id,
        "primary_threshold": config.threshold,
        "status": status_str,
        "s_size": s_size,
        "gold_total": gold_total,
        "rubric_pass": rubric_pass_count,
        "pending_polarity": pending_polarity,
        "pending_rubric": rubric["pending_rubric"],
        "judge_model": config.judge_model,
        "kappa": rubric.get("kappa"),
        "kappa_n": rubric.get("kappa_n"),
        "kappa_accept": config.kappa_accept,
        "kappa_accepted": rubric.get("kappa_accepted"),
        "manual_default": manual_def,
        "sweep": sweep_results,
        "diagnostics": primary_diagnostics,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "05_metrics.json"
    out_file.write_text(json.dumps(out_payload, indent=2), encoding="utf-8")
    return out_file
