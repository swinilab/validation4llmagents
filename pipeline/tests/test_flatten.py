"""Tests for diagram flattening (pipeline.flatten)."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from pipeline.flatten import (
    ACT_COLS,
    CLASS_COLS,
    EXIT_OK,
    EXIT_USAGE,
    FlattenError,
    InventoryNotAllowedError,
    apply_tier_map,
    flatten_diagram,
    main,
    parse_activity_elements,
    parse_class_elements,
    run_flatten,
)

SAMPLE_CLASS_PUML = """@startuml
class Customer {
  customer_id : String
  name : String
}

enum OrderStatus {
  PLACED
  CANCELLED
}

Customer "1" --> "0..*" OrderStatus : has status
@enduml
"""

SAMPLE_ACTIVITY_PUML = """@startuml
|Customer|
start
:browse products;
:checkout order;
|System|
if (in stock?) then (yes)
  :reserve items to cart;
else (no)
  :display shortage;
  stop
endif
stop
@enduml
"""


def test_parse_class_elements():
    rows = parse_class_elements(SAMPLE_CLASS_PUML)
    assert len(rows) == 7
    types = [r["element_type"] for r in rows]
    assert types == ["class", "attribute", "attribute", "class", "attribute", "attribute", "relationship"]
    assert rows[0]["canonical_name"] == "Customer"
    assert rows[1]["canonical_name"] == "customer_id"
    assert rows[1]["owner_class"] == "Customer"
    assert rows[3]["detail"] == "stereotype=enum"
    assert rows[4]["detail"] == "literal"
    assert rows[5]["detail"] == "literal"
    assert rows[6]["canonical_name"] == "Customer-OrderStatus"


def test_parse_activity_elements():
    rows = parse_activity_elements(SAMPLE_ACTIVITY_PUML)
    types = [r["element_type"] for r in rows]
    assert "swimlane" in types
    assert "start" in types
    assert "action" in types
    assert "branch" in types
    assert "end" in types

    # Check action verb & target split
    reserve_action = next(r for r in rows if r["element_type"] == "action" and r["verb"] == "reserve")
    assert reserve_action["object"] == "items"
    assert reserve_action["detail"] == "to=cart"

    # Check branch
    branch = next(r for r in rows if r["element_type"] == "branch")
    assert "in stock?" in branch["detail"]
    assert "[yes | no]" in branch["detail"]


def test_flatten_gold_roundtrip(repo_root: Path, artifact_tmp: Path):
    gold_dir = repo_root / "materials" / "M4-gold-v0.2" / "gold"
    class_puml = gold_dir / "gold-class.puml"
    act_puml = gold_dir / "gold-activity.puml"
    tier_map = gold_dir / "gold-tier-map.csv"
    if not class_puml.is_file():
        pytest.skip("gold diagrams not found in this checkout")

    # Flatten class diagram
    class_out = artifact_tmp / "class.csv"
    flatten_diagram(class_puml, out_path=class_out, tier_map=tier_map)

    # Flatten activity diagram
    act_out = artifact_tmp / "act.csv"
    flatten_diagram(act_puml, out_path=act_out, tier_map=tier_map)

    # Verify identical to gold CSVs
    gold_class_csv = (gold_dir / "gold-class-elements.csv").read_text(encoding="utf-8")
    gold_act_csv = (gold_dir / "gold-activity-elements.csv").read_text(encoding="utf-8")

    assert class_out.read_text(encoding="utf-8") == gold_class_csv
    assert act_out.read_text(encoding="utf-8") == gold_act_csv


def test_inventory_allowed_guard(tmp_path: Path, artifact_tmp: Path):
    puml = tmp_path / "test.puml"
    puml.write_text(SAMPLE_CLASS_PUML, encoding="utf-8")

    # Mock parse check report where test.puml is not allowed
    mock_parse_check = {
        "diagrams": [
            {"path": str(puml), "inventory_allowed": False}
        ]
    }

    # Should raise InventoryNotAllowedError by default
    with pytest.raises(InventoryNotAllowedError):
        flatten_diagram(puml, out_path=artifact_tmp / "out.csv", parse_check=mock_parse_check)

    # Should succeed with force=True
    out, rows = flatten_diagram(
        puml, out_path=artifact_tmp / "out.csv", parse_check=mock_parse_check, force=True
    )
    assert out.is_file()
    assert len(rows) > 0


def test_batch_run_flatten(repo_root: Path, artifact_tmp: Path):
    gold_dir = repo_root / "materials" / "M4-gold-v0.2" / "gold"
    class_puml = gold_dir / "gold-class.puml"
    act_puml = gold_dir / "gold-activity.puml"
    if not class_puml.is_file():
        pytest.skip("gold diagrams not found in this checkout")

    payload = run_flatten(
        run_id="BATCH_TEST",
        class_puml=class_puml,
        activity_puml=act_puml,
        out_dir=artifact_tmp,
    )
    assert payload["run_id"] == "BATCH_TEST"
    assert payload["total_elements"] == 147
    assert "class_csv" in payload["outputs"]
    assert "activity_csv" in payload["outputs"]

    class_csv_path = repo_root / payload["outputs"]["class_csv"]
    meta_path = class_csv_path.with_name(class_csv_path.name + ".meta.json")
    assert class_csv_path.is_file()
    assert meta_path.is_file()


def test_cli_flatten_single_and_batch(repo_root: Path, artifact_tmp: Path):
    gold_dir = repo_root / "materials" / "M4-gold-v0.2" / "gold"
    class_puml = gold_dir / "gold-class.puml"
    act_puml = gold_dir / "gold-activity.puml"
    if not class_puml.is_file():
        pytest.skip("gold diagrams not found in this checkout")

    # Single mode CLI
    out_single = artifact_tmp / "cli_single.csv"
    code = main(["--kind", "class", "--in", str(class_puml), "--out", str(out_single)])
    assert code == EXIT_OK
    assert out_single.is_file()

    # Batch mode CLI
    code_batch = main([
        "--run-id", "CLI_BATCH",
        "--class-puml", str(class_puml),
        "--activity-puml", str(act_puml),
        "--out-dir", str(artifact_tmp),
    ])
    assert code_batch == EXIT_OK
    assert (artifact_tmp / "CLI_BATCH__class-elements.csv").is_file()
    assert (artifact_tmp / "CLI_BATCH__activity-elements.csv").is_file()
