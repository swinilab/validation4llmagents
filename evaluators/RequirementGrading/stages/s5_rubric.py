"""s5_rubric.py — Stage S5: Rubric adjudication for unmatched generated units."""

from __future__ import annotations

import csv
import json
import random
from datetime import datetime
from pathlib import Path
from typing import Any

from RequirementGrading.config import GradingConfig
from RequirementGrading.models import Unit


def load_csv_rows(path: Path) -> dict[str, dict[str, str]]:
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return {r["gen_id"]: r for r in reader if "gen_id" in r}


def append_csv_rows(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = path.is_file()
    with path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        for r in rows:
            writer.writerow(r)


def compute_cohens_kappa(labels1: list[bool], labels2: list[bool]) -> float:
    """Compute Cohen's kappa for two binary raters."""
    if len(labels1) != len(labels2) or not labels1:
        return 0.0

    n = len(labels1)
    agree = sum(1 for a, b in zip(labels1, labels2) if a == b)
    p_o = agree / n

    p1_true = sum(1 for a in labels1 if a) / n
    p2_true = sum(1 for b in labels2 if b) / n

    p_e = (p1_true * p2_true) + ((1 - p1_true) * (1 - p2_true))

    if abs(1.0 - p_e) < 1e-9:
        return 1.0 if p_o == 1.0 else 0.0

    return (p_o - p_e) / (1.0 - p_e)


def run_s5(
    units_file: Path,
    axis_file: Path,
    dedup_file: Path,
    out_dir: Path,
    review_dir: Path,
    run_id: str,
    config: GradingConfig,
    on_pending: str = "halt",
) -> tuple[int, str, int]:
    """Execute Stage S5.

    Returns:
      (rubric_pass_count, stage_status, pending_count)
    """
    units_data = json.loads(units_file.read_text(encoding="utf-8"))
    gen_by_id = {u["unit_id"]: u for u in units_data.get("gen", [])}

    dedup_data = json.loads(dedup_file.read_text(encoding="utf-8"))
    kept_ids = set(dedup_data.get("kept", []))

    axis_results = json.loads(axis_file.read_text(encoding="utf-8"))

    # Matched units at primary threshold
    matched_gen_at_primary = {
        r["gen_id"] for r in axis_results
        if r.get("verdict") == "PASS" and r.get("gen_id") in kept_ids
    }

    # Unmatched set: units in S with no PASS pair at primary threshold
    unmatched_ids = [gid for gid in kept_ids if gid not in matched_gen_at_primary]
    unmatched_ids.sort()

    run_review_dir = review_dir / run_id
    run_review_dir.mkdir(parents=True, exist_ok=True)

    human_csv_path = run_review_dir / "rubric_human.csv"
    llm_csv_path = run_review_dir / "rubric_llm.csv"
    kappa_path = run_review_dir / "kappa_rounds.json"

    existing_human = load_csv_rows(human_csv_path)

    # 1. Sample units for human rubric if needed
    previous_sampled = set(existing_human.keys())
    if kappa_path.is_file():
        try:
            k_rounds = json.loads(kappa_path.read_text(encoding="utf-8"))
            for r in k_rounds:
                previous_sampled.update(r.get("gen_ids", []))
        except Exception:
            pass

    eligible_for_sample = [uid for uid in unmatched_ids if uid not in previous_sampled]
    rng = random.Random(config.random_seed)
    rng.shuffle(eligible_for_sample)
    sample_to_add = eligible_for_sample[:config.kappa_sample_size]

    if sample_to_add:
        new_human_rows = []
        for uid in sample_to_add:
            u_text = gen_by_id[uid]["text_raw"]
            new_human_rows.append({
                "gen_id": uid,
                "gen_text": u_text,
                "traceable": "",
                "consistent": "",
                "reviewer": "",
                "timestamp": "",
            })
        append_csv_rows(
            human_csv_path,
            ["gen_id", "gen_text", "traceable", "consistent", "reviewer", "timestamp"],
            new_human_rows,
        )
        existing_human = load_csv_rows(human_csv_path)

    # Count empty human reviews
    pending_human = 0
    rubric_pass_count = 0

    if on_pending == "provisional":
        # In provisional mode, all unmatched units treated as failing the rubric
        rubric_pass_count = 0
        status = "DONE"
    else:
        for uid, row in existing_human.items():
            t_val = row.get("traceable", "").strip().lower()
            c_val = row.get("consistent", "").strip().lower()
            if not t_val or not c_val:
                pending_human += 1
            elif t_val in ("true", "1", "yes", "pass") and c_val in ("true", "1", "yes", "pass"):
                rubric_pass_count += 1

        status = "NEEDS_REVIEW" if pending_human > 0 else "DONE"

    return rubric_pass_count, status, pending_human
