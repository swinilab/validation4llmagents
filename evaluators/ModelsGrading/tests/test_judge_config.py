"""The judge's endpoint and key come from config.yaml; a key is never recorded."""

from __future__ import annotations

import pytest
import yaml

from evaluators.ModelsGrading import judge as judge_module
from evaluators.ModelsGrading.configload import ConfigError, load_config, public_config
from evaluators.ModelsGrading.judge import JudgeError, make_judge

from .conftest import ROOT

BASE = {"judge_model": "m", "judge_temperature": 0,
        "judge_api_base": "https://judge.example/v1", "judge_api_key": "secret-key"}


class _Response:
    status_code = 200
    text = ""

    def json(self):
        return {"choices": [{"message": {"content": "reply"}}]}


@pytest.fixture
def captured(monkeypatch):
    calls = []

    def post(url, headers, json, timeout):
        calls.append({"url": url, "headers": headers, "body": json})
        return _Response()

    monkeypatch.setattr(judge_module.requests, "post", post)
    return calls


def test_no_judge_model_means_no_judge():
    assert make_judge({**BASE, "judge_model": None}) is None


def test_endpoint_and_key_come_from_the_config(captured, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert make_judge(BASE)("prompt") == "reply"
    call = captured[0]
    assert call["url"] == "https://judge.example/v1/chat/completions"
    assert call["headers"]["Authorization"] == "Bearer secret-key"
    assert call["body"]["model"] == "m" and call["body"]["temperature"] == 0


def test_empty_key_falls_back_to_the_environment(captured, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "from-env")
    make_judge({**BASE, "judge_api_key": ""})("prompt")
    assert captured[0]["headers"]["Authorization"] == "Bearer from-env"


def test_openrouter_base_reads_the_openrouter_variable(captured, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    config = {**BASE, "judge_api_key": None,
              "judge_api_base": "https://openrouter.ai/api/v1"}
    make_judge(config)("prompt")
    assert captured[0]["headers"]["Authorization"] == "Bearer or-key"


def test_missing_key_is_a_clear_error(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(JudgeError, match="judge_api_key"):
        make_judge({**BASE, "judge_api_key": ""})


def test_manifest_config_has_no_secret():
    assert "judge_api_key" not in public_config(BASE)
    assert public_config(BASE)["judge_model"] == "m"


def test_loader_requires_a_judge_api_base(tmp_path):
    raw = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    raw["judge_api_base"] = ""
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ConfigError, match="judge_api_base"):
        load_config(path)
