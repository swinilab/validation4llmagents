"""workflow_factory.py — Minimal pipeline factory.

Constructs generation, grading and report components from config.yaml.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import yaml

from agents.gen import ChatDevGenerationAgent
from interfaces.base import IGenerationAgent, IReportWriter, IValidator
from report_writer import TextReportWriter
from evaluators.ModelsGradingEvaluator import ModelsGradingEvaluator
from evaluators.RequirementsGradingEvaluator import RequirementsGradingEvaluator
from evaluators.VMXGradingEvaluator import VMXGradingEvaluator

# The grading modules, in the order the pipeline runs them.
GRADER_NAMES = ("reqs", "models", "vmx")


@dataclass
class PipelineComponents:
    generation_agent: IGenerationAgent
    report_writer: IReportWriter
    config: dict[str, Any]
    # Grading modules, selected with `--grade <name> ...` (all of them by default).
    graders: dict[str, IValidator] = field(default_factory=dict)


def build(config_path: str = "config.yaml") -> PipelineComponents:
    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    report_dir = cfg.get("output", {}).get("report_dir", "generated/reports/")

    return PipelineComponents(
        generation_agent=ChatDevGenerationAgent(config=cfg),
        report_writer=TextReportWriter(report_dir=report_dir, config=cfg),
        config=cfg,
        graders={
            "reqs": RequirementsGradingEvaluator(config_path=config_path),
            "models": ModelsGradingEvaluator(config_path=config_path),
            "vmx": VMXGradingEvaluator(config_path=config_path),
        },
    )
