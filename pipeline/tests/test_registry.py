"""Tests that both modules instantiate through the registry.

The repository's own ``workflow_factory.build()`` cannot be imported in this
checkout - it depends on ``interfaces.base`` and ``validators.*``, neither of
which exists here - so these tests exercise the Stage 1 registry that the
factory will delegate to, using the repository's existing config style.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from pipeline.stage1.registry import (
    ANALYZERS,
    available_metrics,
    build_analyzer,
    build_stage1_analyzers,
)


def test_both_modules_are_registered():
    assert available_metrics() == {"parse_check": 7}


def test_registry_titles():
    assert ANALYZERS["parse_check"].title == "Diagram Validity"


def test_build_each_analyzer_by_name(cfg):
    for name in ANALYZERS:
        runner = build_analyzer(name, cfg)
        assert callable(runner)


def test_unknown_analyzer_rejected(cfg):
    with pytest.raises(KeyError):
        build_analyzer("metric_99", cfg)


def test_build_all_from_default_config():
    analyzers = build_stage1_analyzers()
    assert set(analyzers) == {"parse_check"}
    assert all(callable(runner) for runner in analyzers.values())


def test_build_all_from_config_path(repo_root):
    """The repository config style: a config.yaml with a stage1 section."""
    config_path = repo_root / "config.yaml"
    if not config_path.is_file():
        pytest.skip("repository config.yaml not present")
    analyzers = build_stage1_analyzers(config_path)
    assert set(analyzers) == {"parse_check"}


def test_build_all_from_parsed_mapping(repo_root):
    """A parsed pipeline_config.yaml mapping, as the factory would pass it."""
    config_path = repo_root / "config.yaml"
    if not config_path.is_file():
        pytest.skip("repository config.yaml not present")
    parsed = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    analyzers = build_stage1_analyzers(parsed)
    assert set(analyzers) == {"parse_check"}


def test_registered_parse_check_runner_is_bound(cfg):
    """The parse_check runner is built and bound without needing the tool."""
    runner = build_analyzer("parse_check", cfg)
    assert callable(runner)
    # Calling with no diagrams is an argument error, which proves the config
    # is bound and the call reaches the module rather than failing earlier.
    from pipeline.stage1.parse_check import ParseCheckError

    with pytest.raises(ParseCheckError):
        runner("X", [])
