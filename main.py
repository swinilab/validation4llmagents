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

from workflow_pipeline import run_pipeline
from workflow_factory import build


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="SWELAB Empirical Study Pipeline (ChatDev + Ollama & Validation)"
    )
    parser.add_argument(
        "--phase",
        choices=["gen", "val", "all"],
        default="all",
        help="Pipeline phase to execute: gen (generation), val (validation), or all.",
    )
    parser.add_argument(
        "--grade",
        nargs="+",
        choices=["models"],
        default=[],
        help="Grading modules to run after validation (results go into the run dir).",
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
    components = build(config_path=args.config)
    run_pipeline(
        components,
        phase=args.phase,
        run_id=args.run_id,
        prompt_file=args.prompt_file,
        grade=args.grade,
    )


if __name__ == "__main__":
    main()