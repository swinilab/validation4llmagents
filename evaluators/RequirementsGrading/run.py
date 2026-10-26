"""Runner for the Requirements grading pipeline (M2 spec, Part 2).

    python -m evaluators.RequirementsGrading.run --submission <dir> --out <dir>
                  [--run-id ID] [--on-pending halt|provisional]
                  [--stage all|S0..S6] [--force]

Run it from the repository root.

`--submission` holds `requirements.json`; `--out` is the run directory (e.g.
`generated/RUN_x`). This module keeps no workspace of its own: everything it
writes goes to `<out>/grading/reqs/{run,review}/`. The gold file comes from the
`gold:` section of `config.yaml`.

Exit codes:

    DONE          0   all stages complete, metrics final
    NEEDS_REVIEW  2   a review file awaits human input; path printed to stdout
    FAILED        1   unrecoverable error (gold invalid, submission unreadable)

`<out>/grading/reqs/run/` is a disposable cache: deleting it and re-running
must reproduce identical results, given the same `<out>/grading/reqs/review/`
answers. The embedding stage (S1) is the only one cached between runs; every
other stage is cheap and recomputed, so a filled review file is always picked up.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from evaluators.ModelsGrading.judge import JudgeError, make_judge

from .config import (ConfigError, GradingConfig, RulesConfig, load_domain_path,
                     load_gold_path)
from .stages import run_s0, run_s1, run_s2, run_s3, run_s4, run_s5, run_s6
from .stages.s1_sim import cache_is_current

DONE, FAILED, NEEDS_REVIEW = "DONE", "FAILED", "NEEDS_REVIEW"
EXIT = {DONE: 0, FAILED: 1, NEEDS_REVIEW: 2}

# Default for `grade(judge=...)`: build the rubric judge from config.yaml.
FROM_CONFIG = object()

SECTION = Path(__file__).resolve().parent
ROOT = SECTION.parent.parent

# Folder created inside the caller's run directory; the only place this module
# writes to. Every grading module gets its own folder under `grading/`.
WORKSPACE = Path("grading") / "reqs"

SUBMISSION_FILE = "requirements.json"

STAGES = ["S0", "S1", "S2", "S3", "S4", "S5", "S6"]

METRICS_FILE = "05_metrics.json"
SIM_FILE = "01_sim.npy"
SIM_INDEX_FILE = "01_sim_index.json"


def _code_commit() -> str | None:
    """HEAD of the repository holding this code: which grader produced the run."""
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(SECTION),
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def _print_review(path: Path, empty_rows: int) -> None:
    if empty_rows:
        print(f"review needed: {path.resolve()} ({empty_rows} empty row(s))")


def grade(submission_dir: str | Path, out_dir: str | Path, *,
          run_id: str | None = None, config_path: str | Path | None = None,
          on_pending: str = "halt", stage: str = "all",
          force: bool = False, judge: Any = FROM_CONFIG) -> int:
    """Grade one submission and write everything under `<out_dir>/grading/reqs/`.

    `submission_dir` holds `requirements.json`. The return value is the exit code
    (`EXIT[DONE]`, `EXIT[NEEDS_REVIEW]` or `EXIT[FAILED]`). `judge` is the rubric
    judge, a callable taking a prompt and returning the reply; by default it is built
    from the `judge_*` keys of the config (none when `judge_model` is unset).
    """
    started_at = datetime.now().isoformat()
    submission_dir = Path(submission_dir)
    workspace = Path(out_dir) / WORKSPACE
    run_dir = workspace / "run"
    review_dir = workspace / "review"
    config_path = Path(config_path) if config_path else ROOT / "config.yaml"
    run_id = run_id or Path(out_dir).resolve().name
    submission_path = submission_dir / SUBMISSION_FILE

    try:
        cfg = GradingConfig.load(config_path)
        rules = RulesConfig.load(SECTION / "rules.yaml")
        gold_path = load_gold_path(config_path)
        domain_path = load_domain_path(config_path)
        if judge is FROM_CONFIG:
            judge = make_judge(cfg.raw_dict)
    except (ConfigError, JudgeError) as error:
        print(f"FAILED: {error}", file=sys.stderr)
        return EXIT[FAILED]

    if not submission_path.is_file():
        print(f"FAILED: {SUBMISSION_FILE} not found in {submission_dir}",
              file=sys.stderr)
        return EXIT[FAILED]

    run_dir.mkdir(parents=True, exist_ok=True)
    # Metrics left by an earlier run must not outlive a run that halts or fails
    # before writing its own.
    (run_dir / METRICS_FILE).unlink(missing_ok=True)

    def stop_after(name: str) -> bool:
        return stage == name

    def halt() -> int:
        """Stop for a human: the manifest is written, as for any other outcome."""
        _write_manifest(run_dir, run_id, cfg, rules, started_at, submission_path,
                        gold_path, on_pending, review_dir)
        print(NEEDS_REVIEW)
        return EXIT[NEEDS_REVIEW]

    print(f"Requirements grading: {run_id}")
    print(f"  gold        : {gold_path}")
    print(f"  submission  : {submission_path}")
    print(f"  run / review: {run_dir} | {review_dir}")
    print(f"  on pending  : {on_pending}")

    try:
        # --- S0 units ------------------------------------------------------
        s0_file = run_s0(run_id=run_id, submission_path=submission_path,
                         gold_path=gold_path, out_dir=run_dir, config=cfg,
                         rules=rules)
        if stop_after("S0"):
            return EXIT[DONE]

        # --- S1 similarity (the one cached stage) ---------------------------
        s1_npy = run_dir / SIM_FILE
        s1_index = run_dir / SIM_INDEX_FILE
        if (force or stage == "S1" or not s1_npy.is_file()
                or not cache_is_current(s0_file, s1_index, cfg)):
            s1_npy, s1_index = run_s1(units_file=s0_file, out_dir=run_dir,
                                      config=cfg)
        if stop_after("S1"):
            return EXIT[DONE]

        # --- S2 candidates -------------------------------------------------
        s2_file = run_s2(units_file=s0_file, sim_npy_path=s1_npy,
                         out_dir=run_dir, config=cfg)
        if stop_after("S2"):
            return EXIT[DONE]

        # --- S3 rule layer -------------------------------------------------
        s3_file, s3_status, pending_polarity = run_s3(
            units_file=s0_file, candidates_file=s2_file, out_dir=run_dir,
            review_dir=review_dir, config=cfg, rules=rules,
            on_pending=on_pending)
        if s3_status == NEEDS_REVIEW:
            _print_review(review_dir / "polarity_ledger.csv", pending_polarity)
            return halt()
        if stop_after("S3"):
            return EXIT[DONE]

        # --- S4 dedup ------------------------------------------------------
        s4_file = run_s4(units_file=s0_file, sim_npy_path=s1_npy,
                         out_dir=run_dir, config=cfg)
        if stop_after("S4"):
            return EXIT[DONE]

        # --- S5 rubric -----------------------------------------------------
        rubric = run_s5(
            units_file=s0_file, candidates_file=s2_file, axis_file=s3_file,
            dedup_file=s4_file, out_dir=run_dir, review_dir=review_dir,
            domain_path=domain_path, config=cfg, on_pending=on_pending,
            judge=judge)
        # Halt before the metrics if the rubric still needs a human: they would
        # otherwise be computed from a rubric count that is not final.
        if rubric["status"] == NEEDS_REVIEW:
            if rubric.get("pending_human"):
                _print_review(review_dir / "rubric_human.csv",
                              rubric["pending_human"])
            if rubric.get("unscored"):
                _print_review(review_dir / "rubric_llm.csv", rubric["unscored"])
            return halt()
        if stop_after("S5"):
            return EXIT[DONE]

        # --- S6 metrics ----------------------------------------------------
        s6_file = run_s6(
            units_file=s0_file, candidates_file=s2_file, axis_file=s3_file,
            dedup_file=s4_file, out_dir=run_dir, run_id=run_id, config=cfg,
            rubric=rubric, pending_polarity=pending_polarity,
            is_provisional=bool(pending_polarity + rubric["unresolved"]))
    except (OSError, KeyError, ValueError, RuntimeError, ConfigError) as error:
        print(f"FAILED: {error}", file=sys.stderr)
        return EXIT[FAILED]

    _write_manifest(run_dir, run_id, cfg, rules, started_at, submission_path,
                    gold_path, on_pending, review_dir)
    _print_summary(s6_file, cfg)

    print(DONE)
    return EXIT[DONE]


def _write_manifest(run_dir: Path, run_id: str, cfg: GradingConfig,
                    rules: RulesConfig, started_at: str, submission_path: Path,
                    gold_path: Path, on_pending: str, review_dir: Path) -> None:
    try:
        import sentence_transformers
        st_version = sentence_transformers.__version__
    except Exception:
        st_version = None
    manifest = {
        "run_id": run_id,
        "submission_path": str(submission_path),
        "gold_path": str(gold_path),
        "embedding_model": cfg.embedding_model,
        "embedding_revision": cfg.embedding_revision,
        "sentence_transformers_version": st_version,
        "pooling": cfg.pooling,
        "normalized": cfg.normalize_embeddings,
        "on_pending": on_pending,
        "config": cfg.public_dict,
        "rules": rules.raw_dict,
        "code_commit": _code_commit(),
        "review_dir": str(review_dir),
        "started_at": started_at,
        "finished_at": datetime.now().isoformat(),
    }
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")


def _print_summary(metrics_file: Path, cfg: GradingConfig) -> None:
    metrics = json.loads(metrics_file.read_text(encoding="utf-8"))
    print("\n" + "=" * 60)
    print(f"  REQUIREMENTS GRADING SUMMARY — status: {metrics['status'].upper()}")
    print("=" * 60)
    print(f"{'Threshold':>10}  {'Recall':>8}  {'Precision':>10}  {'F1':>8}  "
          f"{'Gold matched':>13}")
    print("-" * 60)
    for row in metrics["sweep"]:
        marker = " *" if abs(row["threshold"] - cfg.threshold) < 1e-4 else "  "
        print(f"{row['threshold']:>8.2f}{marker}  {row['recall']:>8.4f}  "
              f"{row['precision']:>10.4f}  {row['f1']:>8.4f}  "
              f"{row['matched_gold']:>7}/{metrics['gold_total']}")
    print("-" * 60)
    print("(* = primary threshold)")
    if metrics.get("kappa") is not None:
        print(f"Judge κ = {metrics['kappa']} (n={metrics['kappa_n']}), "
              f"accept >= {metrics['kappa_accept']}: {metrics['kappa_accepted']}")
        if metrics["kappa_accepted"] is False:
            print("warning: the judge is not validated; revise the prompt and draw "
                  "a new held-out sample (spec 9.3)", file=sys.stderr)
    print(f"Metrics saved to: {metrics_file.resolve()}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m evaluators.RequirementsGrading.run",
        description="M2 Requirements grading pipeline")
    parser.add_argument("--submission", required=True,
                        help=f"directory holding {SUBMISSION_FILE}")
    parser.add_argument("--out", required=True,
                        help="run directory; results go to <out>/grading/reqs/")
    parser.add_argument("--run-id", default=None,
                        help="label for the manifest (default: name of --out)")
    parser.add_argument("--config", default=None,
                        help="config.yaml (default: the project's)")
    parser.add_argument("--on-pending", choices=["halt", "provisional"],
                        default="halt")
    parser.add_argument("--stage", choices=["all"] + STAGES, default="all")
    parser.add_argument("--force", action="store_true",
                        help="recompute the cached embedding stage")
    args = parser.parse_args(argv)
    return grade(args.submission, args.out, run_id=args.run_id,
                 config_path=args.config, on_pending=args.on_pending,
                 stage=args.stage, force=args.force)


if __name__ == "__main__":
    raise SystemExit(main())
