"""The report is kept as raw JSON, merged across invocations, and rendered to text."""

from __future__ import annotations

import json

from interfaces.base import GenerationResult, Status, ValidationResult
from report_to_txt import main as render_main
from report_writer import TextReportWriter

CONFIG = {"embedding_model": "org/embedder", "embedding_revision": None,
          "judge_model": "judge-1"}


def _result(kind: str, passed: bool = True, **details) -> ValidationResult:
    return ValidationResult(stage=2, name=kind, passed=passed, message="ok",
                            details={"grading_kind": kind, **details})


def _generation(run_dir, model="gpt-oss:120b") -> GenerationResult:
    return GenerationResult(status=Status.PASS, model=model, code=str(run_dir / "ws"),
                            output_dir=run_dir,
                            metadata={"agent": "ChatDev", "reasoning": "temperature 0.7"})


def _writer(config=CONFIG) -> TextReportWriter:
    return TextReportWriter(report_dir="unused", config=config)


def _write(writer, run_dir, kinds, generation=None, config=None, passed=True):
    """One invocation against `run_dir`; returns the text report."""
    run_dir.mkdir(parents=True, exist_ok=True)
    gen = generation or GenerationResult(status=Status.PASS, model="standalone",
                                         code=str(run_dir), output_dir=run_dir)
    path = writer.write(generation=gen,
                        validation_results=[_result(k, passed) for k in kinds],
                        all_passed=passed, run_id="t")
    return open(path, encoding="utf-8").read()


def _json(run_dir) -> dict:
    return json.loads(next(run_dir.glob("report_*.json")).read_text(encoding="utf-8"))


# --- overview ----------------------------------------------------------------

def test_overview_lists_the_embedding_and_judge_models(tmp_path):
    text = _write(_writer(), tmp_path, ["reqs", "models", "vmx"])
    assert "OVERVIEW" in text
    assert "Embedding model : org/embedder (revision: unpinned)" in text
    assert "Judge model     : judge-1" in text


def test_overview_follows_the_modules_that_ran(tmp_path):
    reqs = _write(_writer(), tmp_path / "a", ["reqs"])
    assert "Embedding model" in reqs and "Judge model     : judge-1" in reqs
    assert "OVERVIEW" not in _write(_writer(), tmp_path / "b", ["vmx"])


def test_unset_judge_and_pinned_revision(tmp_path):
    text = _write(_writer({**CONFIG, "judge_model": None, "embedding_revision": "abc123"}),
                  tmp_path, ["models"])
    assert "(revision: abc123)" in text
    assert "Judge model     : not set" in text


def test_no_overview_without_grading(tmp_path):
    assert "OVERVIEW" not in _write(_writer(), tmp_path, [])


# --- the raw JSON ------------------------------------------------------------

def test_the_report_is_stored_as_json_next_to_the_text(tmp_path):
    _write(_writer(), tmp_path, ["reqs"], generation=_generation(tmp_path))
    report = _json(tmp_path)
    assert report["schema"] == 1 and set(report["grading"]) == {"reqs"}
    assert report["generation"]["model"] == "gpt-oss:120b"
    assert report["grading"]["reqs"]["models_used"]["judge_model"] == "judge-1"
    assert (tmp_path / f"report_{tmp_path.name}.txt").is_file()


# --- merging across invocations ---------------------------------------------

def test_a_second_invocation_with_other_flags_keeps_the_first(tmp_path):
    _write(_writer(), tmp_path, ["reqs"])
    text = _write(_writer(), tmp_path, ["models"])
    assert set(_json(tmp_path)["grading"]) == {"reqs", "models"}
    assert "reqs" in text and "models" in text
    assert text.index("reqs") < text.index("models")


def test_running_a_module_again_replaces_only_its_entry(tmp_path):
    writer = _writer()
    writer.write(_generation(tmp_path), [_result("reqs", metrics={"v": 1}),
                                         _result("vmx")], True, run_id="t")
    writer.write(_generation(tmp_path), [_result("reqs", metrics={"v": 2})], True,
                 run_id="other-id")
    grading = _json(tmp_path)["grading"]
    assert grading["reqs"]["details"]["metrics"] == {"v": 2}
    assert "vmx" in grading


def test_a_grade_only_call_does_not_overwrite_the_generation_record(tmp_path):
    _write(_writer(), tmp_path, [], generation=_generation(tmp_path))
    _write(_writer(), tmp_path, ["reqs"])        # standalone generation
    assert _json(tmp_path)["generation"]["model"] == "gpt-oss:120b"


def test_the_verdict_reflects_every_module_in_the_report(tmp_path):
    _write(_writer(), tmp_path, ["reqs"], passed=False)
    text = _write(_writer(), tmp_path, ["models"], passed=True)
    assert "RESULT: FAIL" in text            # reqs still failing
    text = _write(_writer(), tmp_path, ["reqs"], passed=True)
    assert "RESULT: PASS" in text


# --- the parser script -------------------------------------------------------

def test_the_text_can_be_rebuilt_from_the_json_alone(tmp_path, capsys):
    text = _write(_writer(), tmp_path, ["reqs", "vmx"], generation=_generation(tmp_path))
    source = next(tmp_path.glob("report_*.json"))
    out = tmp_path / "again.txt"
    assert render_main([str(source), "-o", str(out)]) == 0
    again = out.read_text(encoding="utf-8")
    assert again == text
    assert render_main([str(tmp_path / "missing.json")]) == 1
