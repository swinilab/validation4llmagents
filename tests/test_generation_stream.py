from __future__ import annotations

import json
import time

from agents import gen
from interfaces.base import Status


class _StreamingResponse:
    status_code = 200

    def __enter__(self) -> _StreamingResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    @staticmethod
    def iter_lines():
        time.sleep(0.08)
        yield (
            "data: "
            + json.dumps({"choices": [{"delta": {"content": "Hello, World!"}}]})
        ).encode()
        yield b"data: [DONE]"


def test_streaming_generation_reports_wait_and_saves_content(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(gen, "HAS_CHATDEV", False)
    monkeypatch.setattr(gen, "GENERATION_PROGRESS_INTERVAL_SECONDS", 0.02)
    monkeypatch.setattr(gen.requests, "post", lambda *_args, **_kwargs: _StreamingResponse())

    result = gen.ChatDevGenerationAgent(
        {"agent": {"generated_dir": str(tmp_path), "stream": True}}
    ).generate("Say hello", run_id="test")

    captured = capsys.readouterr()
    assert result.status is Status.PASS
    assert "Waiting for first output" in captured.err
    assert "first output" in captured.err
    assert (tmp_path / "test" / "generation_raw.md").read_text() == "Hello, World!"


def test_openrouter_uses_environment_api_key(tmp_path, monkeypatch):
    monkeypatch.setattr(gen, "HAS_CHATDEV", False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key")
    captured_headers = {}

    def fake_post(*_args, **kwargs):
        captured_headers.update(kwargs["headers"])
        return _StreamingResponse()

    monkeypatch.setattr(gen.requests, "post", fake_post)
    agent = gen.ChatDevGenerationAgent(
        {
            "agent": {
                "api_base": "https://openrouter.ai/api/v1",
                "generated_dir": str(tmp_path),
                "stream": True,
            }
        }
    )

    result = agent.generate("Say hello", run_id="openrouter-test")

    assert result.status is Status.PASS
    assert captured_headers["Authorization"] == "Bearer test-openrouter-key"


def test_openrouter_requires_environment_api_key(tmp_path, monkeypatch):
    monkeypatch.setattr(gen, "HAS_CHATDEV", False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(
        gen.requests,
        "post",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unexpected API call")),
    )

    result = gen.ChatDevGenerationAgent(
        {
            "agent": {
                "api_base": "https://openrouter.ai/api/v1",
                "generated_dir": str(tmp_path),
            }
        }
    ).generate("Say hello", run_id="openrouter-no-key")

    assert result.status is Status.ERROR
    assert "OPENROUTER_API_KEY is required" in result.metadata["error"]
