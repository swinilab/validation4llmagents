"""Acceptance tests for VMXGrading (M2-metrics §1.1, §1.2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from evaluators.ModelsGrading.configload import load_rules as load_model_rules
from evaluators.VMXGrading import metrics, table, vocab
from evaluators.VMXGrading.configload import ConfigError, load_rules
from evaluators.VMXGrading.run import EXIT, MODEL_RULES, grade

SECTION = Path(__file__).resolve().parents[1]

HEADER = "SRS-Req-ID,Domain-Req-ID,Structural-Elements,Behavorial-Elements"

STRUCTURAL = """@startuml
class Customer {
  name : String
  +address : String
}
class Order {
  String orderDate
}
enum OrderStatus {
  pending
}
@enduml
"""

BEHAVIORAL = """@startuml
|Customer|
start
:Make an Order;
stop
@enduml
"""

DOMAIN = {"FR_INPUT": {"REQ-F-01": {}, "REQ-F-02": {}},
          "NFR_INPUT": {"REQ-N-01": {}}}


@pytest.fixture(scope="module")
def rules() -> dict:
    return load_rules(SECTION / "rules.yaml")


@pytest.fixture(scope="module")
def model_rules() -> dict:
    return load_model_rules(MODEL_RULES)


def parse(vmx_text: str, rules: dict, tmp_path: Path):
    path = tmp_path / "VMX.csv"
    path.write_text(vmx_text, encoding="utf-8")
    return table.read_vmx(path, rules)


def lookup(**overrides) -> dict:
    base = {"source": {"REQ-F-01", "REQ-F-02", "REQ-N-01"},
            "structural": {"Customer", "Customer.name", "Order"},
            "behavioral": {"Make an Order"}}
    base.update(overrides)
    return base


# --- references ----------------------------------------------------------------

def test_split_refs_trims_drops_empties_and_dedupes():
    assert table.split_refs(" A ; B;;A ;  ", ";") == ["A", "B"]
    assert table.split_refs("", ";") == []
    assert table.split_refs("  ;  ", ";") == []


def test_id_column_is_not_a_reference(rules, tmp_path):
    rows, _ = parse(f"{HEADER}\nUS-01,REQ-F-01,Customer,\n", rules, tmp_path)
    result = metrics.integrity(rows, lookup())
    assert result["total"] == 2   # REQ-F-01 and Customer, not US-01


def test_attribute_name_forms():
    assert vocab.attribute_name("name : String") == "name"
    assert vocab.attribute_name("+address : String [0..1]") == "address"
    assert vocab.attribute_name("-String orderDate") == "orderDate"
    assert vocab.attribute_name("<<id>> +code : String") == "code"
    assert vocab.attribute_name("   ") is None


# --- coverage ------------------------------------------------------------------

def test_coverage_conditions_per_prefix(rules, tmp_path):
    rows, _ = parse(
        f"{HEADER}\n"
        "US-01,REQ-F-01,Customer,\n"        # source + structural -> covered
        "US-02,REQ-F-02,,\n"                # no structural      -> incomplete
        "NFR-01,REQ-N-01,,\n"               # source only        -> covered
        "NFR-02,,,\n",                      # no source          -> incomplete
        rules, tmp_path)
    ids = ["US-01", "US-02", "NFR-01", "NFR-02", "US-03"]
    result = metrics.coverage(ids, rows, rules)
    outcomes = {r["id"]: r["outcome"] for r in result["requirements"]}
    assert outcomes == {"US-01": "covered", "US-02": "incomplete",
                        "NFR-01": "covered", "NFR-02": "incomplete",
                        "US-03": "no_row"}
    assert (result["covered"], result["total"]) == (2, 5)
    assert result["score"] == 0.4


def test_coverage_denominator_is_requirements_json_not_vmx_rows(rules, tmp_path):
    rows, _ = parse(f"{HEADER}\nUS-01,REQ-F-01,Customer,\n"
                    "US-99,REQ-F-01,Customer,\n", rules, tmp_path)
    result = metrics.coverage(["US-01", "US-02"], rows, rules)
    assert (result["covered"], result["total"]) == (1, 2)


def test_unknown_prefix_cannot_be_covered(rules, tmp_path):
    rows, _ = parse(f"{HEADER}\nXYZ-01,REQ-F-01,Customer,\n", rules, tmp_path)
    result = metrics.coverage(["XYZ-01"], rows, rules)
    assert result["requirements"][0]["outcome"] == "unknown_prefix"
    assert result["score"] == 0.0


def test_duplicate_rows_use_first_and_are_reported(rules, tmp_path):
    rows, _ = parse(f"{HEADER}\nUS-01,,,\nUS-01,REQ-F-01,Customer,\n", rules, tmp_path)
    entry = metrics.coverage(["US-01"], rows, rules)["requirements"][0]
    assert entry["outcome"] == "incomplete"
    assert entry["duplicate_rows"] == 2


# --- integrity -----------------------------------------------------------------

def test_integrity_counts_broken_references_per_column(rules, tmp_path):
    rows, _ = parse(
        f"{HEADER}\n"
        'US-01,"REQ-F-01;REQ-F-77","Customer;Customer.nope",Make an Order\n'
        "US-02,REQ-F-02,Order,Ship\n", rules, tmp_path)
    result = metrics.integrity(rows, lookup())
    assert (result["resolved"], result["total"]) == (5, 8)
    assert result["by_column"]["source"]["total"] == 3
    assert result["by_column"]["structural"]["resolved"] == 2
    assert result["by_column"]["behavioral"]["resolved"] == 1
    assert {(b["id"], b["reference"]) for b in result["broken"]} == {
        ("US-01", "REQ-F-77"), ("US-01", "Customer.nope"), ("US-02", "Ship")}


def test_integrity_is_exact_and_case_sensitive(rules, tmp_path):
    rows, _ = parse(f"{HEADER}\nUS-01,,customer,make an order\n", rules, tmp_path)
    assert metrics.integrity(rows, lookup())["resolved"] == 0


def test_integrity_without_references_is_na_not_zero(rules, tmp_path):
    rows, _ = parse(f"{HEADER}\nUS-01,,,\n", rules, tmp_path)
    assert metrics.integrity(rows, lookup())["score"] == metrics.NA
    assert metrics.integrity(None, lookup())["score"] == metrics.NA


# --- schema --------------------------------------------------------------------

def test_misspelled_column_is_reported_and_read_as_empty(rules, tmp_path):
    header = "SRS-Req-ID,Domain-Req-ID,Structural-Elements,Behavioral-Elements"
    rows, schema = parse(f"{header}\nUS-01,REQ-F-01,Customer,Make an Order\n",
                         rules, tmp_path)
    assert schema["missing_columns"] == ["Behavorial-Elements"]
    assert schema["unknown_columns"] == ["Behavioral-Elements"]
    assert rows[0].refs["behavioral"] == []


def test_bom_and_blank_lines_are_tolerated(rules, tmp_path):
    path = tmp_path / "VMX.csv"
    path.write_bytes(("﻿" + HEADER + "\n\nUS-01,REQ-F-01,Customer,\n\n")
                     .encode("utf-8"))
    rows, schema = table.read_vmx(path, rules)
    assert schema["missing_columns"] == []
    assert [r.req_id for r in rows] == ["US-01"]


# --- vocabularies --------------------------------------------------------------

def test_structural_vocab_has_classes_enums_and_qualified_attributes(model_rules):
    names = vocab.structural_vocab(
        __import__("evaluators.ModelsGrading.parser", fromlist=["x"])
        .parse_structural(STRUCTURAL, model_rules))
    assert names == {"Customer", "Customer.name", "Customer.address",
                     "Order", "Order.orderDate", "OrderStatus"}


def test_behavioral_vocab_is_actions_only(model_rules):
    from evaluators.ModelsGrading.parser import parse_behavioral
    assert vocab.behavioral_vocab(parse_behavioral(BEHAVIORAL, model_rules)) == {
        "Make an Order"}


def test_missing_diagram_has_empty_vocabulary(model_rules, tmp_path):
    names, status = vocab.parse_vocab(tmp_path / "none.puml", "structural", model_rules)
    assert names == set() and status["status"] == "missing"


# --- config --------------------------------------------------------------------

def test_rules_loader_rejects_unknown_role(tmp_path):
    bad = yaml.safe_load((SECTION / "rules.yaml").read_text(encoding="utf-8"))
    bad["completeness"]["US-"] = ["source", "bogus"]
    path = tmp_path / "rules.yaml"
    path.write_text(yaml.safe_dump(bad), encoding="utf-8")
    with pytest.raises(ConfigError):
        load_rules(path)


def test_rules_loader_rejects_unknown_key(tmp_path):
    bad = yaml.safe_load((SECTION / "rules.yaml").read_text(encoding="utf-8"))
    bad["threshold"] = 0.75
    path = tmp_path / "rules.yaml"
    path.write_text(yaml.safe_dump(bad), encoding="utf-8")
    with pytest.raises(ConfigError):
        load_rules(path)


# --- the runner ----------------------------------------------------------------

@pytest.fixture
def harness(tmp_path):
    domain = tmp_path / "domain.json"
    domain.write_text(json.dumps(DOMAIN), encoding="utf-8")
    config = tmp_path / "config.yaml"
    config.write_text(yaml.safe_dump({"gold": {"domain": "domain.json"}}),
                      encoding="utf-8")
    submission = tmp_path / "submission"
    submission.mkdir()
    out = tmp_path / "RUN"

    class Harness:
        def write(self, **files: str) -> None:
            for name, text in files.items():
                (submission / name).write_text(text, encoding="utf-8")

        def run(self) -> int:
            return grade(submission, out, run_id="t", config_path=config)

        def metrics(self) -> dict:
            return json.loads((out / "grading" / "vmx" / "run" / "03_metrics.json")
                              .read_text(encoding="utf-8"))

    instance = Harness()
    instance.submission = submission
    return instance


def full_submission(h) -> None:
    h.write(**{
        "requirements.json": json.dumps({"requirements": [
            {"id": "US-01"}, {"id": "NFR-01"}]}),
        "VMX.csv": f"{HEADER}\nUS-01,REQ-F-01,Customer;Customer.name,Make an Order\n"
                   "NFR-01,REQ-N-01,,\n",
        "structural.puml": STRUCTURAL,
        "behavioral.puml": BEHAVIORAL,
    })


def test_run_scores_a_consistent_submission_at_one(harness):
    full_submission(harness)
    assert harness.run() == EXIT["DONE"]
    result = harness.metrics()
    assert result["status"] == "final"
    assert result["coverage"]["score"] == 1.0
    assert result["integrity"]["score"] == 1.0
    assert result["diagnostics"]["broken_references"] == 0


def test_run_is_deterministic(harness):
    full_submission(harness)
    harness.run()
    first = harness.metrics()
    harness.run()
    assert harness.metrics() == first


def test_missing_vmx_is_graded_not_failed(harness):
    full_submission(harness)
    (harness.submission / "VMX.csv").unlink()
    assert harness.run() == EXIT["DONE"]
    result = harness.metrics()
    assert result["coverage"]["score"] == 0.0     # measured: nothing linked
    assert result["integrity"]["score"] == "n/a"  # nothing to measure
    assert result["inputs"]["vmx"]["status"] == "missing"


def test_missing_requirements_makes_coverage_na(harness):
    full_submission(harness)
    (harness.submission / "requirements.json").unlink()
    assert harness.run() == EXIT["DONE"]
    assert harness.metrics()["coverage"]["score"] == "n/a"


def test_unreadable_domain_input_fails(harness, tmp_path):
    full_submission(harness)
    (tmp_path / "domain.json").write_text("{}", encoding="utf-8")
    assert harness.run() == EXIT["FAILED"]
