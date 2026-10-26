"""κ settings: `pooled` is refused, and `kappa_accepted` follows `kappa_accept`."""

from __future__ import annotations

import pytest
import yaml

from evaluators.ModelsGrading.configload import ConfigError, load_config

from .conftest import ROOT


def _with(tmp_path, **overrides):
    raw = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    raw.update(overrides)
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return path


def test_pooled_is_refused(tmp_path):
    with pytest.raises(ConfigError, match="pooled"):
        load_config(_with(tmp_path, kappa_pool="pooled"))


def test_per_section_is_accepted(tmp_path):
    assert load_config(_with(tmp_path, kappa_pool="per_section"))["kappa_pool"] \
        == "per_section"
