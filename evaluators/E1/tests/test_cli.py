"""Tests for the E1 batch runner and CLI.

Covers the source presets, the schema error messages, the metadata sidecar and
the guarantee that running twice produces byte-identical output.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from evaluators.E1.cli import SOURCES, SUFFIXES, E1InputError, main, run_e1
from evaluators.E1.config import E1ConfigError
from evaluators.E1.normalize import E1_VERSION


def _read_csv(path: Path) -> list[dict[str, str]]:
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


@pytest.fixture()
def out_dir(repo_root: Path, tmp_path_factory) -> Path:
    """A scratch output directory *inside* the repo, since E1 refuses to leave it."""
    directory = repo_root / "evaluators" / "E1" / "artifact" / "_test_tmp"
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
        "__state_mentions",
    )
    assert "__negated" not in SUFFIXES


def test_gold_reqs_output_columns(gold_requirements_path: Path, out_dir: Path, cfg):
    out = out_dir / "gold.csv"
    summary = run_e1("gold-reqs", gold_requirements_path, out, cfg)

    assert summary["rows"] == 49
    assert summary["e1_version"] == E1_VERSION

    rows = _read_csv(out)
    assert len(rows) == 49
    for suffix in SUFFIXES:
        assert f"statement{suffix}" in rows[0]
    assert "statement__negated" not in rows[0]
    assert rows[0]["e1_version"] == "1.1.0"


def test_input_file_is_never_modified(gold_requirements_path: Path, out_dir: Path, cfg):
    before = gold_requirements_path.read_bytes()
    run_e1("gold-reqs", gold_requirements_path, out_dir / "gold.csv", cfg)
    assert gold_requirements_path.read_bytes() == before


# --------------------------------------------------------------------------
# Determinism
# --------------------------------------------------------------------------


def test_running_twice_is_byte_identical(gold_requirements_path: Path, out_dir: Path, cfg):
    first = out_dir / "a.csv"
    second = out_dir / "b.csv"
    run_e1("gold-reqs", gold_requirements_path, first, cfg)
    run_e1("gold-reqs", gold_requirements_path, second, cfg)
    assert first.read_bytes() == second.read_bytes()


# --------------------------------------------------------------------------
# Presets
# --------------------------------------------------------------------------


def test_reqs_json_preset(fixtures_dir: Path, out_dir: Path, cfg):
    out = out_dir / "reqs.csv"
    run_e1("reqs-json", fixtures_dir / "requirements.json", out, cfg)
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
    run_e1("class-inv", fixtures_dir / "class-elements.csv", out, cfg)
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
    run_e1("activity-inv", fixtures_dir / "activity-elements.csv", out, cfg)
    rows = _read_csv(out)

    assert rows[0]["verb__normalized"] == "validate"
    assert rows[1]["verb__normalized"] == "update"
    assert rows[1]["detail__state_mentions"] == "shipped"


def test_jsonl_output(gold_requirements_path: Path, out_dir: Path, cfg):
    out = out_dir / "gold.jsonl"
    run_e1("gold-reqs", gold_requirements_path, out, cfg)
    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 49
    first = json.loads(lines[0])
    assert first["e1_version"] == E1_VERSION
    assert "statement__negation_scope" in first


# --------------------------------------------------------------------------
# Metadata sidecar
# --------------------------------------------------------------------------


def test_meta_sidecar_records_the_version(
    gold_requirements_path: Path, out_dir: Path, cfg
):
    out = out_dir / "gold.csv"
    run_e1("gold-reqs", gold_requirements_path, out, cfg)
    meta = json.loads((out.with_name(out.name + ".meta.json")).read_text(encoding="utf-8"))

    assert meta["e1_version"] == "1.1.0"
    assert meta["row_count"] == 49
    assert len(meta["ontology_sha256"]) == 64
    assert meta["config"]["ontology_path"].endswith(".yaml")


# --------------------------------------------------------------------------
# Schema and argument errors
# --------------------------------------------------------------------------


def test_missing_column_names_the_column(fixtures_dir: Path, out_dir: Path, cfg):
    with pytest.raises(E1InputError) as excinfo:
        run_e1("gold-reqs", fixtures_dir / "bad-columns.csv", out_dir / "x.csv", cfg)
    message = str(excinfo.value)
    assert "statement" in message
    assert "requirement_text" in message


def test_unknown_source_is_rejected(gold_requirements_path: Path, cfg):
    with pytest.raises(E1InputError):
        run_e1("nope", gold_requirements_path, None, cfg)


def test_missing_input_file_is_rejected(out_dir: Path, cfg):
    with pytest.raises(E1InputError):
        run_e1("gold-reqs", out_dir / "absent.csv", out_dir / "x.csv", cfg)


def test_output_outside_the_repository_is_refused(
    gold_requirements_path: Path, tmp_path: Path, cfg
):
    with pytest.raises(E1ConfigError):
        run_e1("gold-reqs", gold_requirements_path, tmp_path / "out.csv", cfg)


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
