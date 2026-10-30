# main.py — Entry point for the SWELAB Empirical Study Pipeline
from __future__ import annotations

import argparse
import sys
from datetime import datetime

# Windows console encoding fix
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from report_summary import summarize
from workflow_pipeline import run_pipeline
from workflow_factory import GRADER_NAMES, build


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="SWELAB Empirical Study Pipeline (ChatDev + Ollama & Grading)"
    )
    parser.add_argument(
        "--phase",
        choices=["gen", "grade", "all", "summary"],
        default="all",
        help="Pipeline phase to execute: gen (generation), grade (grading), or all. "
             "summary prints the final metrics of every run in generated/ and "
             "writes them as CSV (no generation, no grading).",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="summary phase: CSV to write (default generated/final_metrics.csv).",
    )
    parser.add_argument(
        "--grade",
        nargs="+",
        choices=list(GRADER_NAMES),
        default=None,
        help="Grading modules to run in the grade phase: reqs (requirements), "
             "models (structural + behavioral), vmx (traceability matrix). "
             "Default: all three. Results go into the run dir.",
    )
    parser.add_argument(
        "--on-pending",
        choices=["provisional", "halt"],
        default="provisional",
        help="Grading modules: halt = stop and write review files for a human, "
             "provisional = resolve unreviewed pairs with the configured default. "
             "(VMX grading is automatic and ignores it.)",
    )
    parser.add_argument(
        "--run-id",
        default=f"RUN_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        help="Opaque identifier for this run. Used to name artifacts and reports.",
    )
    parser.add_argument(
        "--prompt",
        dest="prompt_file",
        default=None,
        help="Path to the generation prompt file (defaults to config agent.prompt_template).",
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to pipeline configuration YAML.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if args.phase == "summary":
        sys.exit(summarize("generated", args.out))
    components = build(config_path=args.config)
    run_pipeline(
        components,
        phase=args.phase,
        run_id=args.run_id,
        prompt_file=args.prompt_file,
        grade=args.grade,
        on_pending=args.on_pending,
    )


if __name__ == "__main__":
    main()
