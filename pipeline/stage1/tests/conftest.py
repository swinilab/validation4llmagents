"""Shared fixtures for the Stage 1 test suite."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = Path(__file__).resolve().parent / "fixtures"

# Allow `pytest pipeline/stage1/tests` from the repository root without install.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pipeline.stage1.config import load_config  # noqa: E402


def normalize_ws(text: str) -> str:
    """Collapse whitespace, so assertions do not depend on tokenizer spacing."""
    return " ".join(text.split())


@pytest.fixture(scope="session")
def cfg():
    """The effective Stage 1 config for this repository."""
    return load_config()


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def artifact_tmp(repo_root: Path):
    """A scratch output directory inside the repo.

    Stage 1 refuses to write outside the checkout, so tests cannot use
    ``tmp_path`` for module *output*. Cleaned up afterwards.
    """
    import shutil
    import uuid

    directory = (
        repo_root / "pipeline" / "stage1" / "artifact" / f"_test_{uuid.uuid4().hex[:8]}"
    )
    directory.mkdir(parents=True, exist_ok=True)
    try:
        yield directory
    finally:
        shutil.rmtree(directory, ignore_errors=True)


@pytest.fixture(scope="session")
def gold_diagram_paths(repo_root: Path) -> dict[str, Path]:
    """The gold class and activity diagrams, for the regression test."""
    base = repo_root / "materials" / "M4-gold-v0.2" / "gold"
    paths = {
        "class": base / "gold-class.puml",
        "activity": base / "gold-activity.puml",
    }
    for kind, path in paths.items():
        if not path.is_file():
            pytest.skip(f"gold {kind} diagram not found in this checkout")
    return paths


@pytest.fixture(scope="session")
def gold_requirements_path(repo_root: Path) -> Path:
    """The real gold requirements CSV, wherever this repo keeps it.

    The canonical location in the task description is ``gold/``; this repository
    currently stores the M4 gold pack under ``materials/``.
    """
    candidates = [
        repo_root / "gold" / "gold-requirements.csv",
        repo_root / "materials" / "M4-gold-v0.2" / "gold" / "gold-requirements.csv",
        repo_root / "materials" / "gold-requirements.csv",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    pytest.skip("gold-requirements.csv not found in this checkout")


@pytest.fixture(scope="session")
def gold_class_elements_path(repo_root: Path) -> Path:
    candidates = [
        repo_root / "gold" / "gold-class-elements.csv",
        repo_root / "materials" / "M4-gold-v0.2" / "gold" / "gold-class-elements.csv",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    pytest.skip("gold-class-elements.csv not found in this checkout")


@pytest.fixture(scope="session")
def gold_activity_elements_path(repo_root: Path) -> Path:
    candidates = [
        repo_root / "gold" / "gold-activity-elements.csv",
        repo_root / "materials" / "M4-gold-v0.2" / "gold" / "gold-activity-elements.csv",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    pytest.skip("gold-activity-elements.csv not found in this checkout")
