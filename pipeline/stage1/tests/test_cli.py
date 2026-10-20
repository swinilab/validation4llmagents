"""Tests for the Stage 1 batch runner and CLI.

Covers the source presets, the schema error messages, the metadata sidecar and
the guarantee that running twice produces byte-identical output.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from pipeline.stage1.cli import SOURCES, SUFFIXES, Stage1InputError, main, run_stage1
from pipeline.stage1.config import Stage1ConfigError
from pipeline.stage1.normalize import STAGE1_VERSION


def _read_csv(path: Path) -> list[dict[str, str]]:
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


@pytest.fixture()
def out_dir(repo_root: Path, tmp_path_factory) -> Path:
    """A scratch output directory *inside* the repo, since Stage 1 refuses to leave it."""
    directory = repo_root / "pipeline" / "stage1" / "artifact" / "_test_tmp"
    directory.mkdir(parents=True, exist_ok=True)
    yield directory
    for item in directory.iterdir():
        item.unlink()
    directory.rmdir()


# --------------------------------------------------------------------------
# Output schema
# --------------------------------------------------------------------------


def test_suffixes_are_the_1_1_0_set():
    assert SUFFIXES == (
        "__normalized",
        "__has_negation_cue",
        "__main_predicate_negated",
        "__negation_scope",
        "__negation_cues",
    )
    assert "__negated" not in SUFFIXES


def test_gold_reqs_output_columns(gold_requirements_path: Path, out_dir: Path, cfg):
    out = out_dir / "gold.csv"
    summary = run_stage1("gold-reqs", gold_requirements_path, out, cfg)

    assert summary["rows"] == 49
    assert summary["stage1_version"] == STAGE1_VERSION

    rows = _read_csv(out)
    assert len(rows) == 49
    for suffix in SUFFIXES:
        assert f"statement{suffix}" in rows[0]
    assert "statement__negated" not in rows[0]
    assert rows[0]["stage1_version"] == "1.3.0"


def test_input_file_is_never_modified(gold_requirements_path: Path, out_dir: Path, cfg):
    before = gold_requirements_path.read_bytes()
    run_stage1("gold-reqs", gold_requirements_path, out_dir / "gold.csv", cfg)
    assert gold_requirements_path.read_bytes() == before


# --------------------------------------------------------------------------
# Determinism
# --------------------------------------------------------------------------


def test_running_twice_is_byte_identical(gold_requirements_path: Path, out_dir: Path, cfg):
    first = out_dir / "a.csv"
    second = out_dir / "b.csv"
    run_stage1("gold-reqs", gold_requirements_path, first, cfg)
    run_stage1("gold-reqs", gold_requirements_path, second, cfg)
    assert first.read_bytes() == second.read_bytes()


# --------------------------------------------------------------------------
# Presets
# --------------------------------------------------------------------------


def test_reqs_json_preset(fixtures_dir: Path, out_dir: Path, cfg):
    out = out_dir / "reqs.csv"
    run_stage1("reqs-json", fixtures_dir / "requirements.json", out, cfg)
    rows = _read_csv(out)

    assert len(rows) == 3
    # "shall not refund" negates the main predicate.
    assert rows[0]["statement__main_predicate_negated"] == "true"
    assert rows[0]["statement__negation_scope"] == "main"
    assert "not" in rows[0]["statement__normalized"].split()
    # "no more than 0.1%" is a bound, not a negation.
    assert rows[2]["statement__has_negation_cue"] == "false"


def test_class_inv_preset_uses_label_normalization(fixtures_dir: Path, out_dir: Path, cfg):
    out = out_dir / "class.csv"
    run_stage1("class-inv", fixtures_dir / "class-elements.csv", out, cfg)
    rows = _read_csv(out)

    assert rows[0]["canonical_name__normalized"] == "order line"
    # spaCy splits the bare token "id"; see test_normalize.test_label_normalization.
    assert rows[1]["canonical_name__normalized"] == "order line i d"
    assert rows[2]["canonical_name__normalized"] == "payment"
    # An empty optional column emits empty fields without running the parser.
    assert rows[0]["detail__normalized"] == ""
    assert rows[0]["detail__has_negation_cue"] == "false"
    assert rows[0]["detail__negation_scope"] == "none"


def test_activity_inv_preset(fixtures_dir: Path, out_dir: Path, cfg):
    out = out_dir / "activity.csv"
    run_stage1("activity-inv", fixtures_dir / "activity-elements.csv", out, cfg)
    rows = _read_csv(out)

    assert rows[0]["verb__normalized"] == "validate"
    assert rows[1]["verb__normalized"] == "update"
    assert "detail__state_mentions" not in rows[1]


def test_class_inv_normalizes_owner_class(fixtures_dir: Path, out_dir: Path, cfg):
    """``owner_class`` is a label column: identifiers split, empties stay empty."""
    out = out_dir / "class-owner.csv"
    run_stage1("class-inv", fixtures_dir / "class-elements.csv", out, cfg)
    rows = _read_csv(out)

    assert rows[1]["owner_class__normalized"] == "order line"  # CamelCase
    assert rows[3]["owner_class__normalized"] == "payment gateway"  # snake_case
    assert rows[4]["owner_class__normalized"] == "customers"  # plural kept
    # A class row owns nothing: the cell is empty and the parser never runs.
    assert rows[0]["owner_class"] == ""
    assert rows[0]["owner_class__normalized"] == ""
    assert rows[0]["owner_class__has_negation_cue"] == "false"
    assert rows[0]["owner_class__negation_scope"] == "none"


def test_activity_inv_normalizes_swimlane(fixtures_dir: Path, out_dir: Path, cfg):
    """``swimlane`` is a label column: identifiers split, empties stay empty."""
    out = out_dir / "activity-lane.csv"
    run_stage1("activity-inv", fixtures_dir / "activity-elements.csv", out, cfg)
    rows = _read_csv(out)

    assert rows[0]["swimlane__normalized"] == "system"
    assert rows[3]["swimlane__normalized"] == "payment gateway"  # CamelCase
    assert rows[4]["swimlane__normalized"] == "payment gateway"  # snake_case
    assert rows[5]["swimlane__normalized"] == "customers"  # plural kept
    # A branch belongs to no lane.
    assert rows[6]["swimlane"] == ""
    assert rows[6]["swimlane__normalized"] == ""
    assert rows[6]["swimlane__has_negation_cue"] == "false"
    assert rows[6]["swimlane__negation_scope"] == "none"


def test_camel_and_snake_owner_agree(fixtures_dir: Path, out_dir: Path, cfg):
    """The point of normalizing these columns: spelling variants converge."""
    out = out_dir / "converge.csv"
    run_stage1("activity-inv", fixtures_dir / "activity-elements.csv", out, cfg)
    rows = _read_csv(out)
    assert rows[3]["swimlane__normalized"] == rows[4]["swimlane__normalized"]


def test_new_columns_emit_the_full_suffix_set(fixtures_dir: Path, out_dir: Path, cfg):
    """The two new columns are not special-cased: same six suffixes as the rest."""
    out = out_dir / "suffixes.csv"
    run_stage1("activity-inv", fixtures_dir / "activity-elements.csv", out, cfg)
    header = _read_csv(out)[0].keys()
    for suffix in SUFFIXES:
        assert f"swimlane{suffix}" in header

    out2 = out_dir / "suffixes-class.csv"
    run_stage1("class-inv", fixtures_dir / "class-elements.csv", out2, cfg)
    header2 = _read_csv(out2)[0].keys()
    for suffix in SUFFIXES:
        assert f"owner_class{suffix}" in header2


def test_class_inv_running_twice_is_byte_identical(
    fixtures_dir: Path, out_dir: Path, cfg
):
    """Determinism holds for the preset carrying the new optional column."""
    first = out_dir / "det-1.csv"
    second = out_dir / "det-2.csv"
    run_stage1("class-inv", fixtures_dir / "class-elements.csv", first, cfg)
    run_stage1("class-inv", fixtures_dir / "class-elements.csv", second, cfg)
    assert first.read_bytes() == second.read_bytes()


def test_activity_inv_running_twice_is_byte_identical(
    fixtures_dir: Path, out_dir: Path, cfg
):
    """Determinism holds for the preset carrying the new optional column."""
    first = out_dir / "det-a1.csv"
    second = out_dir / "det-a2.csv"
    run_stage1("activity-inv", fixtures_dir / "activity-elements.csv", first, cfg)
    run_stage1("activity-inv", fixtures_dir / "activity-elements.csv", second, cfg)
    assert first.read_bytes() == second.read_bytes()


def test_jsonl_output(gold_requirements_path: Path, out_dir: Path, cfg):
    out = out_dir / "gold.jsonl"
    run_stage1("gold-reqs", gold_requirements_path, out, cfg)
    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 49
    first = json.loads(lines[0])
    assert first["stage1_version"] == STAGE1_VERSION
    assert "statement__negation_scope" in first


# --------------------------------------------------------------------------
# Metadata sidecar
# --------------------------------------------------------------------------


def test_meta_sidecar_records_the_version(
    gold_requirements_path: Path, out_dir: Path, cfg
):
    out = out_dir / "gold.csv"
    run_stage1("gold-reqs", gold_requirements_path, out, cfg)
    meta = json.loads((out.with_name(out.name + ".meta.json")).read_text(encoding="utf-8"))

    assert meta["stage1_version"] == "1.3.0"
    assert meta["row_count"] == 49
    assert "ontology_sha256" not in meta
    assert "ontology_path" not in meta


# --------------------------------------------------------------------------
# Schema and argument errors
# --------------------------------------------------------------------------


def test_missing_column_names_the_column(fixtures_dir: Path, out_dir: Path, cfg):
    with pytest.raises(Stage1InputError) as excinfo:
        run_stage1("gold-reqs", fixtures_dir / "bad-columns.csv", out_dir / "x.csv", cfg)
    message = str(excinfo.value)
    assert "statement" in message
    assert "requirement_text" in message


def test_unknown_source_is_rejected(gold_requirements_path: Path, cfg):
    with pytest.raises(Stage1InputError):
        run_stage1("nope", gold_requirements_path, None, cfg)


def test_missing_input_file_is_rejected(out_dir: Path, cfg):
    with pytest.raises(Stage1InputError):
        run_stage1("gold-reqs", out_dir / "absent.csv", out_dir / "x.csv", cfg)


def test_output_outside_the_repository_is_refused(
    gold_requirements_path: Path, tmp_path: Path, cfg
):
    with pytest.raises(Stage1ConfigError):
        run_stage1("gold-reqs", gold_requirements_path, tmp_path / "out.csv", cfg)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def test_cli_text_mode_prints_the_new_fields(capsys):
    exit_code = main(["--source", "text", "--text", "The system shall not store X."])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["has_negation_cue"] is True
    assert payload["main_predicate_negated"] is True
    assert payload["negation_scope"] == "main"
    assert "negated" not in payload
    assert "not" in payload["normalized"].split()


def test_cli_label_mode(capsys):
    assert main(["--source", "text", "--text", "OrderLine", "--label"]) == 0
    assert json.loads(capsys.readouterr().out)["normalized"] == "order line"


def test_cli_text_mode_requires_text(capsys):
    assert main(["--source", "text"]) == 2
    assert "--text" in capsys.readouterr().err


def test_cli_file_mode_requires_in(capsys):
    assert main(["--source", "gold-reqs"]) == 2
    assert "--in" in capsys.readouterr().err


def test_every_preset_is_reachable_from_the_cli():
    assert set(SOURCES) == {"reqs-json", "gold-reqs", "class-inv", "activity-inv"}
