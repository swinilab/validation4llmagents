"""Judge reply handling (spec §7.6): tolerant parsing, retry, raw-reply log."""

from __future__ import annotations

import json

import pytest

from evaluators.ModelsGrading.judge import JudgeError
from evaluators.ModelsGrading.stages import s7_rubric

CONFIG = {"judge_model": "m", "judge_temperature": 0, "judge_max_attempts": 3}
ELEMENT = {"element_id": "E1", "kind": "class", "diagram": "structural"}
GOOD = "traceable: yes\nconsistent: no\nrationale: Invented capability."


def _lines(path):
    return [json.loads(line) for line in path.read_text("utf-8").splitlines()]


def test_parse_exact_format():
    assert s7_rubric.parse_judge_reply(GOOD) == (True, False, "Invented capability.")


@pytest.mark.parametrize("reply", [
    "**traceable:** **Yes**.\n- consistent: no, it contradicts\n`rationale`: x",
    "Traceable: YES\nConsistent: No.\nRationale: x",
])
def test_parse_tolerates_markdown_and_punctuation(reply):
    traceable, consistent, _ = s7_rubric.parse_judge_reply(reply)
    assert (traceable, consistent) == (True, False)


@pytest.mark.parametrize("reply", ["", "I think it is fine.", "traceable: maybe"])
def test_unreadable_condition_stays_none(reply):
    traceable, consistent, _ = s7_rubric.parse_judge_reply(reply)
    assert traceable is None and consistent is None


def test_retries_until_reply_parses_and_logs_every_call(tmp_path):
    replies = iter(["no idea", GOOD])
    log = tmp_path / "judge.jsonl"
    result = s7_rubric._ask_judge(lambda prompt: next(replies), "PROMPT",
                                  ELEMENT, CONFIG, log)
    assert result == (True, False, "Invented capability.")
    rows = _lines(log)
    assert [r["attempt"] for r in rows] == [1, 2]
    assert [r["parsed"] for r in rows] == [False, True]
    assert rows[0]["reply"] == "no idea" and rows[0]["prompt"] == "PROMPT"


def test_never_parsing_leaves_the_element_unscored(tmp_path):
    log = tmp_path / "judge.jsonl"
    traceable, consistent, _ = s7_rubric._ask_judge(
        lambda prompt: "garbled", "P", ELEMENT, CONFIG, log)
    assert traceable is None and consistent is None
    assert len(_lines(log)) == CONFIG["judge_max_attempts"]


def test_transport_error_is_logged_and_raised(tmp_path):
    log = tmp_path / "judge.jsonl"

    def broken(prompt):
        raise JudgeError("HTTP 500")

    with pytest.raises(JudgeError):
        s7_rubric._ask_judge(broken, "P", ELEMENT, CONFIG, log)
    (row,) = _lines(log)
    assert row["error"] == "HTTP 500" and row["reply"] is None
