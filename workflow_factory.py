"""workflow_factory.py — Minimal pipeline factory.

Constructs generation and evaluation pipeline components from config.yaml.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import yaml

from agents.gen import ChatDevGenerationAgent
from interfaces.base import IGenerationAgent, IReportWriter, IValidator
from report_writer import TextReportWriter
from evaluators.ModelGradingEvaluator import ModelGradingEvaluator
from evaluators.SRSEvaluator import SRSEvaluator, Stage1Evaluator


@dataclass
class PipelineComponents:
    generation_agent: IGenerationAgent
    validator: IValidator
    report_writer: IReportWriter
    config: dict[str, Any]
    # Optional grading modules, selected with `--grade <name>`.
    graders: dict[str, IValidator] = field(default_factory=dict)

    @property
    def stage1_validator(self) -> IValidator:
        """Backward compatibility alias for validator."""
        return self.validator


def build(config_path: str = "config.yaml") -> PipelineComponents:
    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    report_dir = cfg.get("output", {}).get("report_dir", "generated/reports/")

    return PipelineComponents(
        generation_agent=ChatDevGenerationAgent(config=cfg),
        validator=SRSEvaluator(config=cfg),
        report_writer=TextReportWriter(report_dir=report_dir),
        config=cfg,
        graders={"models": ModelGradingEvaluator(config_path=config_path)},
    )
