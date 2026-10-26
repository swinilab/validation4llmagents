"""Runner for the Models grading pipeline (spec §11).

    python run.py --run-id gpt5-run01 [--diagram structural|behavioral|both]
                  [--on-pending halt|provisional] [--stage all|S0..S7] [--force]

Exit codes (§11):

    DONE          0   all stages complete, metrics final
    NEEDS_REVIEW  2   a review file awaits human input; path printed to stdout
    FAILED        1   unrecoverable error (gold invalid, submission unreadable)

A failed syntax gate is **not** FAILED. It is a graded outcome: the run
completes with `n/a` semantics for that diagram and exits 0 (§11).

Each stage skips itself when its output file already exists, unless `--force`.
`GradingModels/run/` is a disposable cache: deleting it and re-running must
reproduce identical results, given the same `GradingModels/review/` answers
(§1 invariant 2).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from GradingModels.configload import (DIAGRAMS, ConfigError, load_config,
                                      load_rules)
from GradingModels.judge import JudgeError, make_judge
from GradingModels.ledgers import LedgerError
from GradingModels.parser import (PARSER_VERSION, SUPPORTED_CONSTRUCTS,
                                  UNSUPPORTED_CONSTRUCTS, parse_behavioral,
                                  parse_structural)
from GradingModels.stages import (s0_syntax, s1_elements, s2_similarity,
                                  s3_candidates, s4_match, s5_axis,
                                  s6_control, s7_rubric, s8_metrics)
from GradingModels.stages.s1_elements import GoldInventoryError

DONE, FAILED, NEEDS_REVIEW = "DONE", "FAILED", "NEEDS_REVIEW"
EXIT = {DONE: 0, FAILED: 1, NEEDS_REVIEW: 2}

SECTION = Path(__file__).resolve().parent
ROOT = SECTION.parent.parent

GOLD_FILES = {"structural": "G2-structural.puml",
              "behavioral": "G3-behavioral.puml"}
GOLD_PARSERS = {"structural": parse_structural, "behavioral": parse_behavioral}

STAGES = ["S0", "S1", "S2", "S3", "S4", "S5", "S6", "S7"]

OUTPUTS = {
    "S0": "00_syntax.json",
    "S1": "01_elements.json",
    "S2": "02_sim.npy",
    "S3": "03_candidates.json",
    "S4": "04_match.json",
    "S5": "05_axis.json",
    "S6": "06_control.json",
    "S7": "07_metrics.json",
}


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _review_commit(path: Path) -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(path.parent),
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def load_gold(rules: dict, diagrams) -> dict:
    """Parse gold and enforce §4.3: both gold files must parse at validity 1.0.

    Aborts with FAILED before touching any submission.
    """
    parsed: dict[str, Any] = {}
    for diagram in diagrams:
        path = ROOT / "gold" / GOLD_FILES[diagram]
        if not path.is_file():
            raise GoldInventoryError(f"gold file not found: {path}")
        result = GOLD_PARSERS[diagram](
            path.read_text(encoding="utf-8"), rules)
        if result.validity() != 1.0:
            raise GoldInventoryError(
                f"gold {diagram} does not parse at validity 1.0 "
                f"(got {result.validity():.4f}); rejections: "
                f"{[r.to_json() for r in result.rejections]}")
        parsed[diagram] = result
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="run.py", description="M2 Models grading pipeline")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--diagram", choices=["structural", "behavioral", "both"],
                        default="both")
    parser.add_argument("--on-pending", choices=["halt", "provisional"],
                        default="halt")
    parser.add_argument("--stage", choices=["all"] + STAGES, default="all")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    diagrams = DIAGRAMS if args.diagram == "both" else (args.diagram,)
    run_dir = SECTION / "run" / args.run_id
    review_dir = SECTION / "review" / args.run_id
    submission_dir = ROOT / "submissions" / args.run_id
    started = _now()

    try:
        config = load_config(ROOT / "config.yaml")
        rules = load_rules(SECTION / "rules.yaml")
    except ConfigError as error:
        print(f"FAILED: {error}", file=sys.stderr)
        return EXIT[FAILED]

    if not submission_dir.is_dir():
        print(f"FAILED: submission directory not found: {submission_dir}",
              file=sys.stderr)
        return EXIT[FAILED]

    try:
        gold_parsed = load_gold(rules, diagrams)
    except GoldInventoryError as error:
        print(f"FAILED: {error}", file=sys.stderr)
        return EXIT[FAILED]

    run_dir.mkdir(parents=True, exist_ok=True)
    wanted = STAGES if args.stage == "all" else [args.stage]

    def fresh(stage: str) -> bool:
        """Should this stage run? A stage skips itself when its output exists."""
        if stage not in wanted:
            return False
        if args.force:
            return True
        return not (run_dir / OUTPUTS[stage]).is_file()

    try:
        # --- S0 syntax gate ------------------------------------------------
        syntax, gen_parsed = s0_syntax.run(submission_dir, rules, config, diagrams)
        if fresh("S0") or not (run_dir / OUTPUTS["S0"]).is_file():
            _write_json(run_dir / OUTPUTS["S0"], syntax)

        graded = [d for d in diagrams if syntax[d].get("gate") == s0_syntax.GATE_PASS]

        # --- S1 elements ---------------------------------------------------
        elements = s1_elements.run(gold_parsed, gen_parsed, diagrams)
        if fresh("S1") or not (run_dir / OUTPUTS["S1"]).is_file():
            _write_json(run_dir / OUTPUTS["S1"], elements)

        # --- S2 similarity -------------------------------------------------
        sim_path = run_dir / OUTPUTS["S2"]
        index_path = run_dir / "02_sim_index.json"
        if fresh("S2") or not sim_path.is_file() or not index_path.is_file():
            arrays, index = s2_similarity.run(elements, config, graded)
            np.savez(sim_path.with_suffix(".npz"), **arrays)
            sim_path.write_bytes(sim_path.with_suffix(".npz").read_bytes())
            sim_path.with_suffix(".npz").unlink()
            _write_json(index_path, index)
        else:
            with np.load(sim_path, allow_pickle=False) as data:
                arrays = {k: data[k] for k in data.files}
            index = _read_json(index_path)

        # --- S3 candidates -------------------------------------------------
        candidates = s3_candidates.run(elements, arrays, index, config, graded)
        if fresh("S3") or not (run_dir / OUTPUTS["S3"]).is_file():
            _write_json(run_dir / OUTPUTS["S3"], candidates)

        # --- S4 assignment -------------------------------------------------
        match = s4_match.run(elements, candidates, config, graded)
        if fresh("S4") or not (run_dir / OUTPUTS["S4"]).is_file():
            _write_json(run_dir / OUTPUTS["S4"], match)

        # --- S5 rule layer -------------------------------------------------
        axis = s5_axis.run(elements, match, rules, config, graded, review_dir,
                           args.on_pending)
        if fresh("S5") or not (run_dir / OUTPUTS["S5"]).is_file():
            _write_json(run_dir / OUTPUTS["S5"], axis)

        # --- S6 control checklist ------------------------------------------
        control = s6_control.run(gen_parsed, rules, diagrams)
        if fresh("S6") or not (run_dir / OUTPUTS["S6"]).is_file():
            _write_json(run_dir / OUTPUTS["S6"], control)

        # Halt before the rubric if the rule layer still needs a human: later
        # stages would otherwise be computed from provisional verdicts (§11).
        if axis["pending_total"] and args.on_pending == "halt":
            _print_review(axis["review_files"]["type"], axis["pending_type"])
            _print_review(axis["review_files"]["guard"], axis["pending_guard"])
            _write_manifest(run_dir, review_dir, args, config, rules, started,
                            submission_dir, diagrams)
            print(NEEDS_REVIEW)
            return EXIT[NEEDS_REVIEW]

        # --- S6 rubric -----------------------------------------------------
        rubric = s7_rubric.run(elements, axis["records"], config, graded,
                               review_dir, ROOT / "gold" / "domain-requirements.md",
                               args.on_pending, judge=make_judge(config))
        rubric["manual_resolved"] = axis["manual_resolved"]

        # --- S7 metrics ----------------------------------------------------
        metrics = s8_metrics.run(elements, axis["records"], syntax, rubric,
                                 config, diagrams)
        pending = (axis["pending_type"] + axis["pending_guard"]
                   + rubric["pending_rubric"])
        payload: dict[str, Any] = {
            "run_id": args.run_id,
            "primary_threshold": config["threshold_models"],
            "status": "final" if pending == 0 else "provisional",
            "pending_type": axis["pending_type"],
            "pending_guard": axis["pending_guard"],
            "pending_rubric": rubric["pending_rubric"],
            "manual_default": (config["manual_default"]
                               if args.on_pending == "provisional" else None),
            "kappa": rubric.get("kappa"),
            "kappa_n": rubric.get("kappa_n"),
            "kappa_pool": config["kappa_pool"],
            "control": {k: control[k] for k in s6_control.ITEMS},
            "diagnostics": s8_metrics.diagnostics(
                elements, axis["records"], syntax, match, candidates, rubric,
                gen_parsed, config, diagrams),
        }
        payload["diagnostics"]["stale_ledger_rows"] = axis["stale_ledger_rows"]
        payload.update(metrics)
        _write_json(run_dir / OUTPUTS["S7"], payload)
        _write_manifest(run_dir, review_dir, args, config, rules, started,
                        submission_dir, diagrams)

        if rubric["pending_rubric"] and args.on_pending == "halt":
            _print_review(rubric["review_files"]["human"],
                          rubric["pending_rubric"])
            print(NEEDS_REVIEW)
            return EXIT[NEEDS_REVIEW]

        print(DONE)
        return EXIT[DONE]

    except (GoldInventoryError, LedgerError, ConfigError, JudgeError) as error:
        print(f"FAILED: {error}", file=sys.stderr)
        return EXIT[FAILED]


def _print_review(path: str, empty_rows: int) -> None:
    if empty_rows:
        print(f"review needed: {Path(path).resolve()} ({empty_rows} empty row(s))")


def _write_manifest(run_dir: Path, review_dir: Path, args, config: dict,
                    rules: dict, started: str, submission_dir: Path,
                    diagrams) -> None:
    try:
        import sentence_transformers
        st_version = sentence_transformers.__version__
    except Exception:
        st_version = None
    manifest = {
        "run_id": args.run_id,
        "submission_dir": str(submission_dir),
        "gold_paths": {d: str(ROOT / "gold" / GOLD_FILES[d]) for d in diagrams},
        "diagrams": list(diagrams),
        "embedding_model": config["embedding_model"],
        "embedding_revision": config["embedding_revision"],
        "sentence_transformers_version": st_version,
        "pooling": config["pooling"],
        "normalized": config["normalize_embeddings"],
        "parser_version": PARSER_VERSION,
        "supported_constructs": SUPPORTED_CONSTRUCTS,
        "unsupported_constructs": UNSUPPORTED_CONSTRUCTS,
        "on_pending": args.on_pending,
        "config": config,
        "rules": rules,
        "review_commit": _review_commit(review_dir),
        "started_at": started,
        "finished_at": _now(),
    }
    _write_json(run_dir / "manifest.json", manifest)


if __name__ == "__main__":
    raise SystemExit(main())
