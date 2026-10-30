"""`syntax_gate: plantuml` -- the gate follows PlantUML's verdict, not the own parser's."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from evaluators.ModelsGrading.configload import ConfigError, load_config
from evaluators.ModelsGrading.stages import s0_syntax
from evaluators.ModelsGrading.stages.s0_syntax import (
    GATE_FAIL, GATE_MISSING, GATE_PASS, PlantUmlUnavailable, gate_for, plantuml_check)

ROOT = Path(__file__).resolve().parents[3]
JAR = ROOT / "tools" / "plantuml.jar"
needs_plantuml = pytest.mark.skipif(
    not JAR.is_file() or shutil.which("java") is None,
    reason="PlantUML jar or java not available")


class _Result:
    def __init__(self, validity: float) -> None:
        self._validity = validity

    def validity(self) -> float:
        return self._validity


def test_plantuml_gate_ignores_the_own_parsers_validity():
    rejected_by_own_parser = _Result(0.5)
    assert gate_for(rejected_by_own_parser, "plantuml", plantuml_ok=True) == GATE_PASS
    assert gate_for(_Result(1.0), "plantuml", plantuml_ok=False) == GATE_FAIL


def test_plantuml_gate_needs_a_verdict():
    with pytest.raises(ValueError):
        gate_for(_Result(1.0), "plantuml")


def test_missing_file_stays_missing_in_every_mode():
    assert gate_for(None, "plantuml") == GATE_MISSING
    assert gate_for(None, "strict") == GATE_MISSING


def test_strict_gate_is_unchanged():
    assert gate_for(_Result(1.0), "strict") == GATE_PASS
    assert gate_for(_Result(0.98), "strict") == GATE_FAIL
    with pytest.raises(ValueError):
        gate_for(_Result(1.0), "lenient")


def test_missing_jar_is_an_error_not_a_pass(tmp_path):
    puml = tmp_path / "a.puml"
    puml.write_text("@startuml\nclass A\n@enduml\n", encoding="utf-8")
    settings = {"jar": str(tmp_path / "nope.jar"), "java_cmd": "java",
                "timeout_seconds": 5}
    with pytest.raises(PlantUmlUnavailable):
        plantuml_check(puml, settings)


@needs_plantuml
def test_plantuml_check_accepts_a_valid_and_rejects_an_invalid_diagram(tmp_path):
    settings = {"jar": str(JAR), "java_cmd": "java", "timeout_seconds": 60}
    good = tmp_path / "good.puml"
    good.write_text('@startuml\nclass A\nclass B\nA "1" --> "0..*" B : has\n@enduml\n',
                    encoding="utf-8")
    bad = tmp_path / "bad.puml"
    bad.write_text("@startuml\nstart\n:a;\nrepeat while (z?)\nstop\n@enduml\n",
                   encoding="utf-8")
    assert plantuml_check(good, settings) == (True, None)
    ok, error = plantuml_check(bad, settings)
    assert ok is False and error


def test_load_config_accepts_plantuml_and_resolves_the_jar():
    config = load_config(ROOT / "config.yaml")
    assert config["syntax_gate"] in {"strict", "plantuml"}
    assert Path(config["plantuml"]["jar"]).is_absolute() \
        or str(config["plantuml"]["jar"]).endswith("plantuml.jar")
    assert config["plantuml"]["timeout_seconds"] > 0


def test_unknown_gate_value_is_still_a_config_error(tmp_path):
    text = (ROOT / "config.yaml").read_text(encoding="utf-8")
    import re
    broken = re.sub(r"(?m)^syntax_gate:.*$", "syntax_gate: lenient", text)
    path = tmp_path / "config.yaml"
    path.write_text(broken, encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(path)


def test_s0_run_records_the_gate_mode(tmp_path, rules, config):
    (tmp_path / "structural.puml").write_text("@startuml\nclass A\n@enduml\n",
                                              encoding="utf-8")
    cfg = {**config, "syntax_gate": "strict"}
    syntax, _ = s0_syntax.run(tmp_path, rules, cfg, diagrams=("structural", "behavioral"))
    assert syntax["structural"]["gate_mode"] == "strict"
    assert syntax["behavioral"]["gate"] == GATE_MISSING
    assert syntax["behavioral"]["gate_mode"] == "strict"
