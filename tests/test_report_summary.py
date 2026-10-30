"""The final-metrics summary finds the run directories itself and reports the ten M2 metrics."""

from __future__ import annotations

import csv
import json

from report_summary import (
    COLUMNS, METRICS, collect, find_reports, render_table, summarize)


def _report(recall=0.4, struct_gate="pass", struct_recall=0.84, message="status=final"):
    return {"grading": {
        "reqs": {"passed": True, "message": message, "details": {"metrics": {
            "primary_threshold": 0.75,
            "sweep": [{"threshold": 0.7, "recall": 0.1, "precision": 0.1, "f1": 0.1},
                      {"threshold": 0.75, "recall": recall, "precision": 0.97, "f1": 0.5}],
            "kappa": 0.9, "kappa_n": 30}}},
        "models": {"passed": True, "message": "status=final", "details": {"metrics": {
            "structural": {"gate": struct_gate, "syntax_validity": 0.98,
                           "recall": struct_recall, "precision": 0.9, "f1": 0.87},
            "behavioral": {"gate": "fail", "syntax_validity": 0.875, "recall": "n/a",
                           "precision": "n/a", "f1": "n/a"},
            "kappa": 1.0, "kappa_n": 7}}},
        "vmx": {"passed": True, "message": "status=final", "details": {"metrics": {
            "coverage": {"score": 1.0}, "integrity": {"score": 0.995}}}},
    }}


def _make_run(root, name, report, report_name=None):
    run = root / name
    run.mkdir(parents=True)
    (run / (report_name or f"report_{name}.json")).write_text(
        json.dumps(report), encoding="utf-8")


def test_the_csv_has_the_ten_m2_metrics_and_no_f1():
    assert len(METRICS) == 10 and len(set(METRICS)) == 10
    assert COLUMNS[0] == "run" and COLUMNS[1:11] == METRICS
    assert not any("f1" in column for column in COLUMNS)


def test_runs_are_discovered_from_their_reports(tmp_path):
    _make_run(tmp_path, "b-run", _report())
    _make_run(tmp_path, "a-run", _report())
    (tmp_path / "no-report").mkdir()
    (tmp_path / "stray.csv").write_text("x", encoding="utf-8")
    assert list(find_reports(tmp_path)) == ["a-run", "b-run"]


def test_a_report_with_another_name_is_still_found(tmp_path):
    _make_run(tmp_path, "RUN_x", _report(), report_name="report_other.json")
    assert list(find_reports(tmp_path)) == ["RUN_x"]


def test_each_metric_comes_from_its_own_field(tmp_path):
    _make_run(tmp_path, "r1", _report(recall=0.443))
    (row,) = collect(tmp_path)
    assert row["run"] == "r1"
    # Requirement metrics are read at the primary threshold, not at 0.7.
    assert row["requirement_recall"] == 0.443
    assert row["requirement_precision"] == 0.97
    assert row["structural_semantic_recall"] == 0.84
    assert row["structural_semantic_precision"] == 0.9
    assert row["structural_syntax_validity"] == 0.98
    assert row["behavioral_syntax_validity"] == 0.875
    assert row["vmx_requirement_coverage"] == 1.0
    assert row["vmx_referential_integrity"] == 0.995
    assert row["requirements_kappa"] == 0.9 and row["requirements_kappa_n"] == 30
    assert row["models_kappa"] == 1.0 and row["models_kappa_n"] == 7
    assert row["reqs_status"] == "final"


def test_not_measured_stays_n_a_and_syntax_validity_is_still_shown(tmp_path):
    report = _report(struct_gate="fail", struct_recall="n/a")
    _make_run(tmp_path, "r1", report)
    (row,) = collect(tmp_path)
    assert row["structural_syntax_gate"] == "fail"
    assert row["structural_semantic_recall"] == "n/a"
    assert row["behavioral_semantic_recall"] == "n/a"
    assert row["behavioral_semantic_precision"] == "n/a"
    assert row["behavioral_syntax_validity"] == 0.875


def test_a_module_that_did_not_run_is_blank(tmp_path):
    report = _report()
    del report["grading"]["vmx"], report["grading"]["models"]
    _make_run(tmp_path, "partial", report)
    (row,) = collect(tmp_path)
    assert row["vmx_requirement_coverage"] == "" and row["structural_syntax_gate"] == "" \
        and row["structural_semantic_recall"] == "" and row["requirement_recall"] == 0.4


def test_summarize_writes_the_csv_and_prints_every_run(tmp_path, capsys):
    _make_run(tmp_path, "r1", _report())
    _make_run(tmp_path, "r2", _report(recall=0.2))
    out = tmp_path / "out" / "m.csv"
    assert summarize(tmp_path, out) == 0
    rows = list(csv.DictReader(out.open(encoding="utf-8", newline="")))
    assert [r["run"] for r in rows] == ["r1", "r2"]
    assert tuple(rows[0]) == COLUMNS
    printed = capsys.readouterr().out
    for header in ("ReqRec", "StrRec", "BehRec", "VMXCov", "ReqPrec", "StrPrec",
                   "BehPrec", "StrSyn", "BehSyn", "VMXInt"):
        assert header in printed
    assert "r1" in printed and "r2" in printed


def test_no_reports_is_an_error(tmp_path):
    assert summarize(tmp_path, tmp_path / "x.csv") == 1
    assert not (tmp_path / "x.csv").exists()


def test_unreadable_report_is_skipped_not_fatal(tmp_path, capsys):
    _make_run(tmp_path, "good", _report())
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "report_bad.json").write_text("{not json", encoding="utf-8")
    assert [r["run"] for r in collect(tmp_path)] == ["good"]
    assert "skipped" in capsys.readouterr().err


def test_table_pads_columns(tmp_path):
    _make_run(tmp_path, "short", _report())
    _make_run(tmp_path, "a-much-longer-run-name", _report())
    header, _rule, *body = render_table(collect(tmp_path)).splitlines()
    start = header.index("ReqRec")
    # The long run name must not push the first metric column out of line.
    assert all(line[start] != " " and line[start - 1] == " " for line in body)
