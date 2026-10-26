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

def _gold_paths() -> dict[str, Path]:
    """Gold files as the `gold:` section of config.yaml names them."""
    from GradingModels.configload import load_gold_paths
    return load_gold_paths(ROOT / "config.yaml")


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
    return _gold_paths()["structural"].read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def gold_behavioral_text() -> str:
    return _gold_paths()["behavioral"].read_text(encoding="utf-8")


class Harness:
    """Writes a submission, runs the pipeline, reads the metrics back.

    Each harness lives in its own `base` directory (a pytest temp dir), so runs
    never share the disposable cache or a review directory, and nothing is
    written into the repository.
    """

    def __init__(self, run_id: str, base: Path) -> None:
        self.run_id = run_id
        self.base = base
        self.submission = base / "submission"
        self.out = base / "RUN"
        self.run_dir = self.out / "grading_models" / "run"
        self.review_dir = self.out / "grading_models" / "review"

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
            [sys.executable, str(SECTION / "run.py"),
             "--submission", str(self.submission), "--out", str(self.out),
             "--run-id", self.run_id, *extra],
            cwd=str(ROOT), capture_output=True, text=True, timeout=900)

    def metrics(self) -> dict:
        return json.loads((self.run_dir / "07_metrics.json").read_text("utf-8"))

    def read(self, name: str) -> dict:
        return json.loads((self.run_dir / name).read_text("utf-8"))

    def cleanup(self) -> None:
        shutil.rmtree(self.base, ignore_errors=True)


@pytest.fixture
def harness(request, tmp_path):
    created: list[Harness] = []

    def make(suffix: str) -> Harness:
        run_id = f"test-{request.node.name}-{suffix}".replace("/", "_")[:80]
        item = Harness(run_id, tmp_path / run_id)
        item.cleanup()
        created.append(item)
        return item

    yield make
    for item in created:
        item.cleanup()
