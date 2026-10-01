"""Unit tests for metric 8 (Consistency), rules CM-01..CM-05.

Each rule gets at least a passing and a failing case on small synthetic CSVs,
plus the empty-input and unknown-term-to-ontology_gaps paths.
"""

from __future__ import annotations

import csv
import json
from dataclasses import replace
from pathlib import Path

import pytest

from pipeline.stage1.config import ConsistencyConfig
from pipeline.stage1.consistency import (
    CONSISTENCY_VERSION,
    ConsistencyError,
    MissingColumnError,
    run_consistency,
)

# Column sets mirroring the real Stage 1 outputs.
CLASS_FIELDS = [
    "element_id", "element_type", "canonical_name", "owner_class", "detail", "tier",
    "canonical_name__normalized", "owner_class__normalized",
]
ACTIVITY_FIELDS = [
    "element_id", "element_type", "verb", "object", "swimlane", "detail", "tier",
    "object__normalized", "swimlane__normalized",
]
REQ_FIELDS = [
    "gold_req_id", "statement", "actor", "object",
    "statement__normalized", "statement__state_mentions",
]


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> Path:
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fields})
    return path


@pytest.fixture
def build(tmp_path, cfg, artifact_tmp):
    """Build a run from synthetic rows and return its payload + outputs."""

    def _build(
        class_rows=None,
        activity_rows=None,
        requirement_rows=None,
        rules=("CM-01", "CM-02", "CM-03", "CM-04", "CM-05"),
        class_fields=CLASS_FIELDS,
        activity_fields=ACTIVITY_FIELDS,
        req_fields=REQ_FIELDS,
        run_id="T",
    ):
        class_csv = _write_csv(tmp_path / "c.csv", class_fields, class_rows or [])
        activity_csv = _write_csv(tmp_path / "a.csv", activity_fields, activity_rows or [])
        req_csv = _write_csv(tmp_path / "r.csv", req_fields, requirement_rows or [])
        effective = replace(cfg, consistency=ConsistencyConfig(rules=tuple(rules)))
        payload = run_consistency(
            run_id, class_csv, activity_csv, req_csv, artifact_tmp, effective
        )
        instances = list(
            csv.DictReader(
                open(artifact_tmp / f"{run_id}__consistency_instances.csv",
                     encoding="utf-8-sig")
            )
        )
        gaps = list(
            csv.DictReader(
                open(artifact_tmp / f"{run_id}__ontology_gaps.csv", encoding="utf-8-sig")
            )
        )
        return payload, instances, gaps

    return _build


def _statuses(instances, rule_id):
    return [i["status"] for i in instances if i["rule_id"] == rule_id]


# --- CM-01 ---------------------------------------------------------------


def test_cm01_pass_known_swimlane(build):
    _, instances, _ = build(
        activity_rows=[
            {"element_id": "SL-01", "element_type": "swimlane", "swimlane": "Warehouse"}
        ],
        rules=["CM-01"],
    )
    assert _statuses(instances, "CM-01") == ["pass"]


def test_cm01_pass_via_alias(build):
    """An alias is a legitimate name, not an inconsistency."""
    _, instances, _ = build(
        activity_rows=[
            {"element_id": "SL-01", "element_type": "swimlane", "swimlane": "Fulfilment"}
        ],
        rules=["CM-01"],
    )
    assert _statuses(instances, "CM-01") == ["pass"]


def test_cm01_fail_unknown_swimlane_and_logs_gap(build):
    _, instances, gaps = build(
        activity_rows=[
            {"element_id": "SL-01", "element_type": "swimlane", "swimlane": "Legal Dept"}
        ],
        rules=["CM-01"],
    )
    assert _statuses(instances, "CM-01") == ["fail"]
    assert any(g["term"] == "Legal Dept" and g["rule_id"] == "CM-01" for g in gaps)


def test_cm01_one_instance_per_swimlane_element(build):
    """Actions inside a lane must not each produce an instance."""
    _, instances, _ = build(
        activity_rows=[
            {"element_id": "SL-01", "element_type": "swimlane", "swimlane": "Customer"},
            {"element_id": "AC-01", "element_type": "action", "object": "order",
             "swimlane": "Customer"},
            {"element_id": "AC-02", "element_type": "action", "object": "order",
             "swimlane": "Customer"},
        ],
        rules=["CM-01"],
    )
    assert len(_statuses(instances, "CM-01")) == 1


def test_cm01_missing_normalized_columns_is_a_clear_error(build):
    with pytest.raises(MissingColumnError) as excinfo:
        build(
            activity_rows=[{"element_id": "SL-01", "element_type": "swimlane",
                            "swimlane": "Customer"}],
            activity_fields=[f for f in ACTIVITY_FIELDS if f != "swimlane__normalized"],
            rules=["CM-01"],
        )
    assert "swimlane__normalized" in str(excinfo.value)


# --- CM-02 ---------------------------------------------------------------


def test_cm02_pass_class_object(build):
    _, instances, _ = build(
        activity_rows=[
            {"element_id": "AC-01", "element_type": "action", "verb": "generate",
             "object": "Order"}
        ],
        rules=["CM-02"],
    )
    assert _statuses(instances, "CM-02") == ["pass"]


def test_cm02_pass_attribute_object(build):
    _, instances, _ = build(
        activity_rows=[
            {"element_id": "AC-01", "element_type": "action", "verb": "calculate",
             "object": "total_amount"}
        ],
        rules=["CM-02"],
    )
    assert _statuses(instances, "CM-02") == ["pass"]


def test_cm02_fail_unknown_object_and_logs_gap(build):
    _, instances, gaps = build(
        activity_rows=[
            {"element_id": "AC-01", "element_type": "action", "verb": "verify",
             "object": "unicorn count"}
        ],
        rules=["CM-02"],
    )
    assert _statuses(instances, "CM-02") == ["fail"]
    assert any(g["term"] == "unicorn count" for g in gaps)


def test_cm02_action_without_object_makes_no_instance(build):
    _, instances, _ = build(
        activity_rows=[
            {"element_id": "AC-01", "element_type": "action", "verb": "start", "object": ""}
        ],
        rules=["CM-02"],
    )
    assert _statuses(instances, "CM-02") == []


# --- CM-03 ---------------------------------------------------------------


def test_cm03_pass_class_mentioned(build):
    _, instances, _ = build(
        class_rows=[{"element_id": "CL-01", "element_type": "class",
                     "canonical_name": "Order"}],
        requirement_rows=[{"gold_req_id": "R1", "statement": "The system stores the order.",
                           "statement__normalized": "system store order",
                           "statement__state_mentions": ""}],
        rules=["CM-03"],
    )
    assert _statuses(instances, "CM-03") == ["pass"]


def test_cm03_pass_plural_mention(build):
    """Stage 1 keeps surface plurals, so 'order lines' must match OrderLine."""
    _, instances, _ = build(
        class_rows=[{"element_id": "CL-01", "element_type": "class",
                     "canonical_name": "OrderLine"}],
        requirement_rows=[{"gold_req_id": "R1",
                           "statement": "Each order shall comprise order lines.",
                           "statement__normalized": "each order comprise order lines",
                           "statement__state_mentions": ""}],
        rules=["CM-03"],
    )
    assert _statuses(instances, "CM-03") == ["pass"]


def test_cm03_fail_class_never_mentioned(build):
    _, instances, _ = build(
        class_rows=[{"element_id": "CL-01", "element_type": "class",
                     "canonical_name": "AuditLog"}],
        requirement_rows=[{"gold_req_id": "R1", "statement": "The system stores the order.",
                           "statement__normalized": "system store order",
                           "statement__state_mentions": ""}],
        rules=["CM-03"],
    )
    assert _statuses(instances, "CM-03") == ["fail"]


def test_cm03_attributes_do_not_create_instances(build):
    _, instances, _ = build(
        class_rows=[{"element_id": "AT-01", "element_type": "attribute",
                     "canonical_name": "order_id", "owner_class": "Order"}],
        requirement_rows=[{"gold_req_id": "R1", "statement": "x",
                           "statement__normalized": "x", "statement__state_mentions": ""}],
        rules=["CM-03"],
    )
    assert _statuses(instances, "CM-03") == []


# --- CM-04 ---------------------------------------------------------------


def test_cm04_pass_legal_transition(build):
    _, instances, _ = build(
        requirement_rows=[{
            "gold_req_id": "R1",
            "statement": "The system shall mark a placed order as picked.",
            "statement__normalized": "system mark placed order as picked",
            "statement__state_mentions": "placed; picked",
        }],
        rules=["CM-04"],
    )
    assert _statuses(instances, "CM-04") == ["pass"]


def test_cm04_fail_illegal_transition(build):
    """draft -> shipped is not in legal_transitions."""
    _, instances, _ = build(
        requirement_rows=[{
            "gold_req_id": "R1",
            "statement": "The system shall mark a draft order as shipped.",
            "statement__normalized": "system mark draft order as shipped",
            "statement__state_mentions": "draft; shipped",
        }],
        rules=["CM-04"],
    )
    assert _statuses(instances, "CM-04") == ["fail"]


def test_cm04_guard_clause_creates_no_instance(build):
    """Two states mentioned as a *condition* state no transition.

    This is the conservative half of the rule: without it, gold requirements
    such as "cancel only while placed and not yet picked" would be scored as
    illegal transitions.
    """
    _, instances, _ = build(
        requirement_rows=[{
            "gold_req_id": "R1",
            "statement": "A customer may cancel only while placed and not picked.",
            "statement__normalized": "customer cancel only while be in placed state and not picked",
            "statement__state_mentions": "placed; picked",
        }],
        rules=["CM-04"],
    )
    assert _statuses(instances, "CM-04") == []


def test_cm04_single_state_creates_no_instance(build):
    _, instances, _ = build(
        requirement_rows=[{
            "gold_req_id": "R1", "statement": "The order is placed.",
            "statement__normalized": "order be placed",
            "statement__state_mentions": "placed",
        }],
        rules=["CM-04"],
    )
    assert _statuses(instances, "CM-04") == []


def test_cm04_from_to_pattern(build):
    _, instances, _ = build(
        requirement_rows=[{
            "gold_req_id": "R1",
            "statement": "Move the order from picked to packed.",
            "statement__normalized": "move order from picked to packed",
            "statement__state_mentions": "picked; packed",
        }],
        rules=["CM-04"],
    )
    assert _statuses(instances, "CM-04") == ["pass"]


# --- CM-05 ---------------------------------------------------------------


def test_cm05_pass_consistent_naming(build):
    _, instances, _ = build(
        class_rows=[{"element_id": "CL-01", "element_type": "class",
                     "canonical_name": "Order"}],
        activity_rows=[{"element_id": "AC-01", "element_type": "action",
                        "verb": "generate", "object": "Order"}],
        rules=["CM-05"],
    )
    assert _statuses(instances, "CM-05") == ["pass"]


def test_cm05_identifier_style_is_not_an_inconsistency(build):
    """PaymentGateway / payment_gateway is one name, written two ways."""
    _, instances, _ = build(
        class_rows=[{"element_id": "CL-01", "element_type": "class",
                     "canonical_name": "PaymentGateway"}],
        activity_rows=[{"element_id": "SL-01", "element_type": "swimlane",
                        "swimlane": "payment_gateway"}],
        rules=["CM-05"],
    )
    assert _statuses(instances, "CM-05") == ["pass"]


def test_cm05_fail_two_distinct_names(build):
    """A class called Order in one source and Buyer in another, same slot."""
    _, instances, _ = build(
        class_rows=[{"element_id": "CL-01", "element_type": "class",
                     "canonical_name": "Customer"}],
        activity_rows=[{"element_id": "SL-01", "element_type": "swimlane",
                        "swimlane": "Client"}],
        rules=["CM-05"],
    )
    # Customer and Client are the same ontology concept reached by two
    # different *names*, which is exactly what CM-05 is for.
    assert _statuses(instances, "CM-05") == ["fail"]


def test_cm05_single_source_creates_no_instance(build):
    _, instances, _ = build(
        class_rows=[{"element_id": "CL-01", "element_type": "class",
                     "canonical_name": "Order"}],
        rules=["CM-05"],
    )
    assert _statuses(instances, "CM-05") == []


# --- empty input and scoring --------------------------------------------


def test_empty_input_yields_null_not_one(build):
    """No instances must never be reported as a perfect score."""
    payload, instances, _ = build(rules=["CM-02", "CM-03", "CM-04", "CM-05"])
    assert payload["total_instances"] == 0
    assert payload["consistency"] is None
    assert payload["no_instances"] is True
    assert instances == []


def test_consistency_formula(build):
    payload, _, _ = build(
        activity_rows=[
            {"element_id": "AC-01", "element_type": "action", "object": "Order"},
            {"element_id": "AC-02", "element_type": "action", "object": "nonsense term"},
        ],
        rules=["CM-02"],
    )
    assert payload["total_instances"] == 2
    assert payload["total_failed"] == 1
    assert payload["consistency"] == 0.5


def test_per_rule_counts(build):
    payload, _, _ = build(
        activity_rows=[{"element_id": "AC-01", "element_type": "action",
                        "object": "nonsense term"}],
        rules=["CM-02"],
    )
    assert payload["per_rule"]["CM-02"] == {"total": 1, "failed": 1}


# --- outputs and determinism --------------------------------------------


def test_outputs_and_meta_written(build, artifact_tmp):
    build(
        activity_rows=[{"element_id": "AC-01", "element_type": "action", "object": "Order"}],
        rules=["CM-02"],
        run_id="OUT",
    )
    json_path = artifact_tmp / "OUT__consistency.json"
    assert json_path.is_file()
    assert (artifact_tmp / "OUT__consistency_instances.csv").is_file()
    assert (artifact_tmp / "OUT__ontology_gaps.csv").is_file()
    meta = json.loads(
        (json_path.with_name(json_path.name + ".meta.json")).read_text(encoding="utf-8")
    )
    assert meta["run_id"] == "OUT"
    assert len(meta["ontology_sha256"]) == 64
    assert meta["consistency_version"] == CONSISTENCY_VERSION


def test_instances_csv_schema(build, artifact_tmp):
    _, instances, _ = build(
        activity_rows=[{"element_id": "AC-01", "element_type": "action", "object": "Order"}],
        rules=["CM-02"],
    )
    assert list(instances[0]) == [
        "run_id", "rule_id", "instance", "status", "detail",
        "ontology_sha256", "tool_version",
    ]


def test_deterministic_outputs(tmp_path, cfg, artifact_tmp):
    """Two runs on identical input produce byte-identical files."""
    class_csv = _write_csv(
        tmp_path / "c.csv", CLASS_FIELDS,
        [{"element_id": "CL-01", "element_type": "class", "canonical_name": "Order"},
         {"element_id": "CL-02", "element_type": "class", "canonical_name": "Customer"}],
    )
    activity_csv = _write_csv(
        tmp_path / "a.csv", ACTIVITY_FIELDS,
        [{"element_id": "AC-01", "element_type": "action", "object": "Order"},
         {"element_id": "AC-02", "element_type": "action", "object": "mystery thing"}],
    )
    req_csv = _write_csv(
        tmp_path / "r.csv", REQ_FIELDS,
        [{"gold_req_id": "R1", "statement": "The system stores the order.",
          "statement__normalized": "system store order", "statement__state_mentions": ""}],
    )
    effective = replace(
        cfg, consistency=ConsistencyConfig(rules=("CM-02", "CM-03", "CM-04", "CM-05"))
    )

    first_dir = artifact_tmp / "run1"
    second_dir = artifact_tmp / "run2"
    run_consistency("D", class_csv, activity_csv, req_csv, first_dir, effective)
    run_consistency("D", class_csv, activity_csv, req_csv, second_dir, effective)

    for name in ("D__consistency.json", "D__consistency_instances.csv",
                 "D__ontology_gaps.csv"):
        assert (first_dir / name).read_bytes() == (second_dir / name).read_bytes(), name


# --- input validation ----------------------------------------------------


def test_missing_requirement_columns_rejected(build):
    with pytest.raises(MissingColumnError):
        build(
            req_fields=[f for f in REQ_FIELDS if f != "statement__state_mentions"],
            rules=["CM-04"],
        )


def test_missing_file_rejected(tmp_path, cfg, artifact_tmp):
    with pytest.raises(ConsistencyError):
        run_consistency(
            "X", tmp_path / "absent.csv", tmp_path / "absent.csv",
            tmp_path / "absent.csv", artifact_tmp, cfg,
        )


def test_blank_run_id_rejected(build):
    with pytest.raises(ConsistencyError):
        build(run_id="  ", rules=["CM-02"])
