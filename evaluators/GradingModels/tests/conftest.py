"""Shared fixtures for the acceptance tests (spec §14)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SECTION = ROOT / "evaluators" / "GradingModels"
GOLD_STRUCTURAL = ROOT / "gold" / "G2-structural.puml"
GOLD_BEHAVIORAL = ROOT / "gold" / "G3-behavioral.puml"


@pytest.fixture(scope="session")
def rules() -> dict:
    from GradingModels.configload import load_rules
    return load_rules(SECTION / "rules.yaml")


@pytest.fixture(scope="session")
def config() -> dict:
    from GradingModels.configload import load_config
    return load_config(ROOT / "config.yaml")


@pytest.fixture(scope="session")
def gold_structural_text() -> str:
    return GOLD_STRUCTURAL.read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def gold_behavioral_text() -> str:
    return GOLD_BEHAVIORAL.read_text(encoding="utf-8")


class Harness:
    """Writes a submission, runs the pipeline, reads the metrics back.

    Each harness run gets its own `run_id`, so runs never share the disposable
    cache or a review directory.
    """

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.submission = ROOT / "submissions" / run_id
        self.run_dir = SECTION / "run" / run_id
        self.review_dir = SECTION / "review" / run_id

    def write(self, structural: str | None = None,
              behavioral: str | None = None) -> None:
        self.submission.mkdir(parents=True, exist_ok=True)
        if structural is not None:
            (self.submission / "structural.puml").write_text(structural,
                                                             encoding="utf-8")
        if behavioral is not None:
            (self.submission / "behavioral.puml").write_text(behavioral,
                                                             encoding="utf-8")

    def run(self, *extra: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SECTION / "run.py"), "--run-id", self.run_id,
             *extra],
            cwd=str(ROOT), capture_output=True, text=True, timeout=900)

    def metrics(self) -> dict:
        return json.loads((self.run_dir / "07_metrics.json").read_text("utf-8"))

    def read(self, name: str) -> dict:
        return json.loads((self.run_dir / name).read_text("utf-8"))

    def cleanup(self) -> None:
        for path in (self.submission, self.run_dir, self.review_dir):
            shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def harness(request):
    created: list[Harness] = []

    def make(suffix: str) -> Harness:
        item = Harness(f"test-{request.node.name}-{suffix}".replace("/", "_")[:80])
        item.cleanup()
        created.append(item)
        return item

    yield make
    for item in created:
        item.cleanup()
