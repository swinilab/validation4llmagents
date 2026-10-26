"""run.py — CLI runner for RequirementGrading pipeline."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

# Ensure repo root is on sys.path
_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from RequirementGrading.config import GradingConfig, RulesConfig
from RequirementGrading.stages import (
    run_s0,
    run_s1,
    run_s2,
    run_s3,
    run_s4,
    run_s5,
    run_s6,
)


def get_git_commit(dir_path: Path) -> str | None:
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(dir_path.resolve()),
            capture_output=True,
            text=True,
            check=True,
        )
        return res.stdout.strip()
    except Exception:
        return None


def run_pipeline(
    run_id: str,
    submission_path: Path | str | None = None,
    gold_path: Path | str | None = None,
    on_pending: str = "halt",
    stage: str = "all",
    force: bool = False,
    base_dir: Path | str | None = None,
) -> int:
    started_at = datetime.now().isoformat()
    grading_dir = Path(base_dir) if base_dir else Path(__file__).resolve().parent
    repo_root = grading_dir.parent

    # 1. Load Configurations
    config_path = repo_root / "config.yaml"
    rules_path = grading_dir / "rules.yaml"

    try:
        cfg = GradingConfig.load(config_path)
        rules = RulesConfig.load(rules_path)
    except Exception as exc:
        print(f"❌ Configuration error: {exc}", file=sys.stderr)
        return 1

    # 2. Resolve Paths
    if not gold_path:
        # Check config, then materials/G1-requirements.json, then gold/G1-requirements.json
        candidate_golds = [
            repo_root / cfg.gold_path,
            repo_root / "materials" / "G1-requirements.json",
            repo_root / "gold" / "G1-requirements.json",
        ]
        resolved_gold = next((g for g in candidate_golds if g.is_file()), None)
        if not resolved_gold:
            print(f"❌ Gold requirements file not found in candidates: {[str(c) for c in candidate_golds]}", file=sys.stderr)
            return 1
        gold_path = resolved_gold
    else:
        gold_path = Path(gold_path)

    if not submission_path:
        candidate_submissions = [
            repo_root / "generated" / run_id / "requirements.json",
            repo_root / "generated" / run_id / "artifacts" / "requirements.json",
            repo_root / "submissions" / run_id / "requirements.json",
            repo_root / "generated" / "requirements.json",
        ]
        resolved_sub = next((s for s in candidate_submissions if s.is_file()), None)
        if not resolved_sub:
            print(f"❌ Submission requirements file not found for run '{run_id}'. Checked:", file=sys.stderr)
            for c in candidate_submissions:
                print(f"   - {c}", file=sys.stderr)
            return 1
        submission_path = resolved_sub
    else:
        submission_path = Path(submission_path)

    run_cache_dir = grading_dir / "run" / run_id
    review_dir = grading_dir / "review"
    run_cache_dir.mkdir(parents=True, exist_ok=True)
    review_dir.mkdir(parents=True, exist_ok=True)

    print(f"==================================================")
    print(f"  REQUIREMENT GRADING PIPELINE — {run_id}")
    print(f"==================================================")
    print(f"  • Gold        : {gold_path}")
    print(f"  • Submission  : {submission_path}")
    print(f"  • Cache       : {run_cache_dir}")
    print(f"  • Review      : {review_dir}")
    print(f"  • On Pending  : {on_pending}")

    # Stage S0: Units
    s0_file = run_cache_dir / "00_units.json"
    if force or not s0_file.is_file() or stage in ("S0", "all"):
        print("\n[S0] Extracting units and validating format...")
        try:
            s0_file = run_s0(
                run_id=run_id,
                submission_path=submission_path,
                gold_path=gold_path,
                out_dir=run_cache_dir,
                config=cfg,
                rules=rules,
            )
        except Exception as exc:
            print(f"❌ S0 Failed: {exc}", file=sys.stderr)
            return 1

    if stage == "S0":
        return 0

    # Stage S1: Similarity
    s1_npy = run_cache_dir / "01_sim.npy"
    s1_index = run_cache_dir / "01_sim_index.json"
    if force or not s1_npy.is_file() or not s1_index.is_file() or stage in ("S1", "all"):
        print("\n[S1] Computing sentence embeddings & similarity matrix...")
        try:
            s1_npy, s1_index = run_s1(
                units_file=s0_file,
                out_dir=run_cache_dir,
                config=cfg,
            )
        except Exception as exc:
            print(f"❌ S1 Failed: {exc}", file=sys.stderr)
            return 1

    if stage == "S1":
        return 0

    # Stage S2: Candidates
    s2_file = run_cache_dir / "02_candidates.json"
    if force or not s2_file.is_file() or stage in ("S2", "all"):
        print(f"\n[S2] Generating candidate pairs at review threshold ({min(cfg.sweep):.2f})...")
        try:
            s2_file = run_s2(
                units_file=s0_file,
                sim_npy_path=s1_npy,
                out_dir=run_cache_dir,
                config=cfg,
            )
        except Exception as exc:
            print(f"❌ S2 Failed: {exc}", file=sys.stderr)
            return 1

    if stage == "S2":
        return 0

    # Stage S3: Axis evaluation
    s3_file = run_cache_dir / "03_axis.json"
    s3_status = "DONE"
    pending_polarity = 0
    if force or not s3_file.is_file() or stage in ("S3", "all"):
        print("\n[S3] Evaluating candidate pairs with Rule Layer (Axes 1-3)...")
        try:
            s3_file, s3_status, pending_polarity = run_s3(
                units_file=s0_file,
                candidates_file=s2_file,
                out_dir=run_cache_dir,
                review_dir=review_dir,
                run_id=run_id,
                config=cfg,
                rules=rules,
                on_pending=on_pending,
            )
        except Exception as exc:
            print(f"❌ S3 Failed: {exc}", file=sys.stderr)
            return 1

        if s3_status == "NEEDS_REVIEW":
            ledger_path = review_dir / run_id / "polarity_ledger.csv"
            print(f"\n⚠️ NEEDS_REVIEW (Polarity Ledger): {pending_polarity} empty rows await adjudication.")
            print(f"👉 Review file path: {ledger_path.resolve()}")
            return 2

    if stage == "S3":
        return 0

    # Stage S4: Dedup
    s4_file = run_cache_dir / "04_dedup.json"
    if force or not s4_file.is_file() or stage in ("S4", "all"):
        print(f"\n[S4] Deduplicating generated units (threshold: {cfg.dedup_threshold:.2f})...")
        try:
            s4_file = run_s4(
                units_file=s0_file,
                sim_npy_path=s1_npy,
                out_dir=run_cache_dir,
                config=cfg,
            )
        except Exception as exc:
            print(f"❌ S4 Failed: {exc}", file=sys.stderr)
            return 1

    if stage == "S4":
        return 0

    # Stage S5: Rubric
    rubric_pass_count = 0
    pending_rubric = 0
    if stage in ("S5", "all"):
        print("\n[S5] Evaluating rubric for unmatched units...")
        try:
            rubric_pass_count, s5_status, pending_rubric = run_s5(
                units_file=s0_file,
                axis_file=s3_file,
                dedup_file=s4_file,
                out_dir=run_cache_dir,
                review_dir=review_dir,
                run_id=run_id,
                config=cfg,
                on_pending=on_pending,
            )
        except Exception as exc:
            print(f"❌ S5 Failed: {exc}", file=sys.stderr)
            return 1

        if s5_status == "NEEDS_REVIEW":
            human_csv = review_dir / run_id / "rubric_human.csv"
            print(f"\n⚠️ NEEDS_REVIEW (Rubric Human): {pending_rubric} empty rows await adjudication.")
            print(f"👉 Review file path: {human_csv.resolve()}")
            return 2

    if stage == "S5":
        return 0

    # Stage S6: Metrics
    is_provisional = (on_pending == "provisional")
    s6_file = run_cache_dir / "05_metrics.json"
    if force or not s6_file.is_file() or stage in ("S6", "all"):
        print("\n[S6] Calculating Requirement Recall, Precision, F1 across sweep...")
        try:
            s6_file = run_s6(
                units_file=s0_file,
                candidates_file=s2_file,
                axis_file=s3_file,
                dedup_file=s4_file,
                out_dir=run_cache_dir,
                run_id=run_id,
                config=cfg,
                rubric_pass_count=rubric_pass_count,
                pending_polarity=pending_polarity,
                pending_rubric=pending_rubric,
                is_provisional=is_provisional,
            )
        except Exception as exc:
            print(f"❌ S6 Failed: {exc}", file=sys.stderr)
            return 1

    # Write manifest.json (§10)
    import sentence_transformers
    manifest_file = run_cache_dir / "manifest.json"
    manifest_payload = {
        "run_id": run_id,
        "submission_path": str(submission_path),
        "gold_path": str(gold_path),
        "embedding_model": cfg.embedding_model,
        "embedding_revision": cfg.embedding_revision,
        "sentence_transformers_version": sentence_transformers.__version__,
        "pooling": cfg.pooling,
        "normalized": cfg.normalize_embeddings,
        "config": cfg.raw_dict,
        "rules": rules.raw_dict,
        "review_commit": get_git_commit(review_dir),
        "started_at": started_at,
        "finished_at": datetime.now().isoformat(),
    }
    manifest_file.write_text(json.dumps(manifest_payload, indent=2), encoding="utf-8")

    # Print summary table
    metrics_data = json.loads(s6_file.read_text(encoding="utf-8"))
    print("\n" + "=" * 60)
    print(f"  REQUIREMENTS GRADING SUMMARY — Status: {metrics_data.get('status').upper()}")
    print("=" * 60)
    print(f"{'Threshold':>10}  {'Recall':>8}  {'Precision':>10}  {'F1':>8}  {'Gold Matched':>13}")
    print("-" * 60)
    for row in metrics_data.get("sweep", []):
        th = row["threshold"]
        marker = " *" if abs(th - cfg.threshold) < 1e-4 else "  "
        print(f"{th:>8.2f}{marker}  {row['recall']:>8.4f}  {row['precision']:>10.4f}  {row['f1']:>8.4f}  {row['matched_gold']:>7}/{metrics_data.get('gold_total')}")
    print("-" * 60)
    print(f"(* = primary threshold)")
    print(f"Metrics saved to: {s6_file.resolve()}\n")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Requirement Grading Runner (M2)")
    parser.add_argument("run_id_pos", nargs="?", default=None, help="Unique identifier (positional)")
    parser.add_argument("--run-id", default=None, help="Unique identifier for the generation run")
    parser.add_argument("--submission-path", default=None, help="Path to submission requirements.json")
    parser.add_argument("--gold-path", default=None, help="Path to gold G1-requirements.json")
    parser.add_argument("--on-pending", choices=["halt", "provisional"], default="halt",
                        help="Action when human adjudication is pending (halt or provisional)")
    parser.add_argument("--stage", choices=["all", "S0", "S1", "S2", "S3", "S4", "S5", "S6"], default="all",
                        help="Specific stage to run, or all")
    parser.add_argument("--force", action="store_true", help="Force re-running stages even if cache exists")

    args = parser.parse_args()
    run_id = args.run_id or args.run_id_pos
    if not run_id:
        parser.error("the following arguments are required: --run-id (or run_id positional)")

    exit_code = run_pipeline(
        run_id=run_id,
        submission_path=args.submission_path,
        gold_path=args.gold_path,
        on_pending=args.on_pending,
        stage=args.stage,
        force=args.force,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
