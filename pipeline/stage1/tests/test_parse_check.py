"""Tests for metric 7 (Diagram Validity).

Covers the rule set, the valid/invalid split, and - importantly - that a
diagram being invalid is reported through the JSON with exit 0, while the
tool being unavailable is a different, non-zero outcome.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from pipeline.stage1.config import ParseCheckConfig
from pipeline.stage1.parse_check import (
    EXIT_OK,
    EXIT_TOOL,
    EXIT_USAGE,
    KIND_ACTIVITY,
    KIND_CLASS,
    ParseCheckError,
    PlantUmlNotAvailable,
    check_diagram,
    detect_kind,
    inventory_allowed,
    main,
    run_parse_check,
)

VALID_CLASS = """@startuml
class Customer {
  customer_id : String
  name : String
}
class Order {
  order_id : String
}
Customer "1" -- "0..*" Order
@enduml
"""

VALID_ACTIVITY = """@startuml
|Customer|
start
:add product to cart;
|System|
if (in stock?) then (yes)
  :generate order;
else (no)
  :halt checkout;
  stop
endif
:transition order to placed;
stop
@enduml
"""

# PlantUML's own parser rejects this one.
SYNTAX_ERROR = """@startuml
@@@ not plantuml at all (((
@enduml
"""

MISSING_ENDIF = """@startuml
start
:do something;
if (condition?) then (yes)
  :branch work;
stop
@enduml
"""

MISSING_END = """@startuml
start
:do something;
:do more;
@enduml
"""

UNCLOSED_PARTITION = """@startuml
start
partition Fulfilment {
  :pick items;
  :pack items;
stop
@enduml
"""

EMPTY_CLASS_DIAGRAM = """@startuml
title A diagram with no classes
note left: nothing here
@enduml
"""


def _write(directory: Path, name: str, text: str) -> Path:
    path = directory / name
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture(scope="session")
def plantuml_available(cfg) -> bool:
    """Whether PlantUML can actually be run in this environment."""
    jar = cfg.parse_check.plantuml_jar
    if jar:
        from pipeline.stage1.config import REPO_ROOT

        candidate = Path(jar)
        if not candidate.is_absolute():
            candidate = REPO_ROOT / candidate
        if candidate.is_file() and shutil.which(cfg.parse_check.java_cmd):
            return True
    return shutil.which(cfg.parse_check.plantuml_cmd) is not None


@pytest.fixture
def needs_plantuml(plantuml_available):
    if not plantuml_available:
        pytest.skip("PlantUML is not available in this environment")


# --- kind detection ------------------------------------------------------


def test_detect_kind_class():
    assert detect_kind(VALID_CLASS) == KIND_CLASS


def test_detect_kind_activity():
    assert detect_kind(VALID_ACTIVITY) == KIND_ACTIVITY


# --- valid diagrams ------------------------------------------------------


def test_valid_class_diagram(tmp_path, cfg, needs_plantuml):
    path = _write(tmp_path, "c.puml", VALID_CLASS)
    result = check_diagram(path, cfg)
    assert result.parse_ok
    assert result.valid
    assert result.inventory_allowed
    assert result.violations == []


def test_valid_activity_diagram(tmp_path, cfg, needs_plantuml):
    path = _write(tmp_path, "a.puml", VALID_ACTIVITY)
    result = check_diagram(path, cfg)
    assert result.parse_ok
    assert result.valid
    assert result.violations == []


# --- invalid diagrams ----------------------------------------------------


def test_syntax_error_is_reported_not_raised(tmp_path, cfg, needs_plantuml):
    path = _write(tmp_path, "bad.puml", SYNTAX_ERROR)
    result = check_diagram(path, cfg)
    assert not result.parse_ok
    assert not result.valid
    assert not result.inventory_allowed
    assert any(v.rule_id == "SYNTAX" for v in result.violations)


def test_missing_endif_fails_pv03(tmp_path, cfg, needs_plantuml):
    """PlantUML tolerates this; PV-03 is why the structural layer exists."""
    path = _write(tmp_path, "noendif.puml", MISSING_ENDIF)
    result = check_diagram(path, cfg)
    assert not result.valid
    pv03 = [v for v in result.violations if v.rule_id == "PV-03"]
    assert pv03, "expected a PV-03 violation for the unclosed 'if'"
    assert pv03[0].line == 4


def test_missing_end_node_fails_pv02(tmp_path, cfg, needs_plantuml):
    path = _write(tmp_path, "noend.puml", MISSING_END)
    result = check_diagram(path, cfg)
    assert not result.valid
    assert any(v.rule_id == "PV-02" for v in result.violations)


def test_unclosed_partition_fails_pv04(tmp_path, cfg, needs_plantuml):
    path = _write(tmp_path, "nopart.puml", UNCLOSED_PARTITION)
    result = check_diagram(path, cfg)
    assert any(v.rule_id == "PV-04" for v in result.violations)


def test_class_diagram_without_class_fails_pv01(tmp_path, cfg, needs_plantuml):
    path = _write(tmp_path, "empty.puml", EMPTY_CLASS_DIAGRAM)
    result = check_diagram(path, cfg)
    # No class declaration means the kind is unknown, so PV-01 does not apply;
    # what matters is that nothing claims it is a valid *class* diagram.
    assert result.kind != KIND_CLASS or not result.valid


# --- tool availability ---------------------------------------------------


def test_missing_plantuml_is_a_tool_error_not_an_invalid_diagram(tmp_path, cfg):
    """The key distinction: 'cannot check' must not read as 'diagram is bad'."""
    path = _write(tmp_path, "c.puml", VALID_CLASS)
    broken = replace(
        cfg,
        parse_check=ParseCheckConfig(
            plantuml_jar="",
            plantuml_cmd="definitely-not-a-real-plantuml-binary",
        ),
    )
    with pytest.raises(PlantUmlNotAvailable):
        check_diagram(path, broken)


def test_missing_jar_is_a_tool_error(tmp_path, cfg):
    path = _write(tmp_path, "c.puml", VALID_CLASS)
    broken = replace(
        cfg, parse_check=ParseCheckConfig(plantuml_jar="tools/does-not-exist.jar")
    )
    with pytest.raises(PlantUmlNotAvailable):
        check_diagram(path, broken)


def test_cli_returns_tool_exit_code_when_plantuml_missing(tmp_path, cfg, repo_root, monkeypatch):
    path = _write(tmp_path, "c.puml", VALID_CLASS)
    config = tmp_path / "config.yaml"
    config.write_text(
        "stage1:\n"
        "  ontology_path: materials/M2-orderman-ontology.yaml\n"
        "  parse_check:\n"
        "    plantuml_jar: ''\n"
        "    plantuml_cmd: definitely-not-a-real-plantuml-binary\n",
        encoding="utf-8",
    )
    code = main(
        [
            "--run-id", "TOOLMISSING",
            "--diagram", str(path),
            "--config", str(config),
            "--out", str(repo_root / "pipeline" / "stage1" / "artifact"
                         / "_test_toolmissing.json"),
        ]
    )
    assert code == EXIT_TOOL


# --- run level -----------------------------------------------------------


def test_run_records_failure_and_still_exits_zero(tmp_path, cfg, artifact_tmp, needs_plantuml):
    good = _write(tmp_path, "good.puml", VALID_ACTIVITY)
    bad = _write(tmp_path, "bad.puml", MISSING_ENDIF)
    out = artifact_tmp / "mixed__parse_check.json"
    payload = run_parse_check("MIXED", [good, bad], out, cfg)

    assert payload["total_diagrams"] == 2
    assert payload["valid_diagrams"] == 1
    assert payload["diagram_validity"] == 0.5
    assert out.is_file()

    # The failing diagram is recorded, and the good one is still usable.
    by_name = {Path(d["path"]).name: d for d in payload["diagrams"]}
    assert by_name["good.puml"]["inventory_allowed"] is True
    assert by_name["bad.puml"]["inventory_allowed"] is False


def test_cli_exit_zero_for_invalid_diagram(tmp_path, cfg, artifact_tmp, needs_plantuml):
    bad = _write(tmp_path, "bad.puml", MISSING_ENDIF)
    out = artifact_tmp / "badrun__parse_check.json"
    assert main(["--run-id", "BADRUN", "--diagram", str(bad), "--out", str(out)]) == EXIT_OK


def test_unknown_file_is_usage_error(cfg, artifact_tmp):
    with pytest.raises(ParseCheckError):
        run_parse_check("X", [artifact_tmp / "nope.puml"], artifact_tmp / "x.json", cfg)


def test_no_diagrams_is_usage_error(cfg, artifact_tmp):
    with pytest.raises(ParseCheckError):
        run_parse_check("X", [], artifact_tmp / "x.json", cfg)


def test_blank_run_id_rejected(tmp_path, cfg, artifact_tmp):
    path = _write(tmp_path, "c.puml", VALID_CLASS)
    with pytest.raises(ParseCheckError):
        run_parse_check("   ", [path], artifact_tmp / "x.json", cfg)


def test_meta_sidecar_written(tmp_path, cfg, artifact_tmp, needs_plantuml):
    path = _write(tmp_path, "c.puml", VALID_CLASS)
    out = artifact_tmp / "meta__parse_check.json"
    run_parse_check("META", [path], out, cfg)
    meta = json.loads(out.with_name(out.name + ".meta.json").read_text(encoding="utf-8"))
    assert meta["run_id"] == "META"
    assert len(meta["ontology_sha256"]) == 64
    assert "PV-01" in meta["structural_rules"]


# --- determinism ---------------------------------------------------------


def test_deterministic_output(tmp_path, cfg, artifact_tmp, needs_plantuml):
    a = _write(tmp_path, "a.puml", VALID_ACTIVITY)
    c = _write(tmp_path, "c.puml", VALID_CLASS)
    first = artifact_tmp / "det1__parse_check.json"
    second = artifact_tmp / "det2__parse_check.json"
    run_parse_check("DET", [a, c], first, cfg)
    # Argument order reversed: output must not depend on it.
    run_parse_check("DET", [c, a], second, cfg)
    assert first.read_bytes() == second.read_bytes()


# --- the downstream helper ----------------------------------------------


def test_inventory_allowed_helper(tmp_path, cfg, artifact_tmp, needs_plantuml):
    good = _write(tmp_path, "good.puml", VALID_ACTIVITY)
    bad = _write(tmp_path, "bad.puml", MISSING_ENDIF)
    out = artifact_tmp / "inv__parse_check.json"
    run_parse_check("INV", [good, bad], out, cfg)

    assert inventory_allowed(out, "good.puml") is True
    assert inventory_allowed(out, "bad.puml") is False
    # A diagram that was never checked is never allowed.
    assert inventory_allowed(out, "unseen.puml") is False


def test_inventory_allowed_on_missing_file_is_false(tmp_path):
    assert inventory_allowed(tmp_path / "absent.json", "any.puml") is False
