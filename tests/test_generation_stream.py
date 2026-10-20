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
