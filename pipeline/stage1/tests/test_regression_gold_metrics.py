"""Gold regression for metrics 7 and 8.

Runs both modules over the real M4 gold pack. The expectation is that gold
scores perfectly; where it does not, the test reports exactly which rule and
which instance disagreed rather than relaxing the rule.

This lives in the test suite on purpose. No module contains a "gold" branch or
a must-pass assertion: ``run_id`` is an opaque label to both modules.
"""

from __future__ import annotations

import csv
import shutil
from pathlib import Path

import pytest

from pipeline.stage1.cli import run_stage1
from pipeline.stage1.consistency import run_consistency
from pipeline.stage1.parse_check import run_parse_check


@pytest.fixture(scope="session")
def plantuml_available(cfg) -> bool:
    jar = cfg.parse_check.plantuml_jar
    if jar:
        from pipeline.stage1.config import REPO_ROOT

        candidate = Path(jar)
        if not candidate.is_absolute():
            candidate = REPO_ROOT / candidate
        if candidate.is_file() and shutil.which(cfg.parse_check.java_cmd):
            return True
    return shutil.which(cfg.parse_check.plantuml_cmd) is not None


def test_gold_diagram_validity_is_one(cfg, artifact_tmp, gold_diagram_paths, plantuml_available):
    """Metric 7 on the gold diagrams must be 1.0."""
    if not plantuml_available:
        pytest.skip("PlantUML is not available in this environment")

    payload = run_parse_check(
        "GOLDREG",
        [gold_diagram_paths["class"], gold_diagram_paths["activity"]],
        artifact_tmp / "GOLDREG__parse_check.json",
        cfg,
    )

    if payload["diagram_validity"] != 1.0:
        failures = [
            f"{d['path']}: " + "; ".join(
                f"[{v['rule_id']}]{':' + str(v['line']) if v['line'] else ''} {v['message']}"
                for v in d["violations"]
            )
            for d in payload["diagrams"]
            if not d["valid"]
        ]
        pytest.fail(
            "Gold diagram_validity is "
            f"{payload['diagram_validity']}, expected 1.0. Failing diagrams:\n"
            + "\n".join(failures)
        )


@pytest.fixture(scope="session")
def gold_stage1_outputs(
    tmp_path_factory,
    cfg,
    repo_root,
    gold_class_elements_path,
    gold_activity_elements_path,
    gold_requirements_path,
):
    """Stage 1 output of the three gold CSVs, written to a scratch directory."""
    directory = repo_root / "pipeline" / "stage1" / "artifact" / "_test_goldreg"
    directory.mkdir(parents=True, exist_ok=True)
    outputs = {}
    for key, source, path in (
        ("class", "class-inv", gold_class_elements_path),
        ("activity", "activity-inv", gold_activity_elements_path),
        ("requirements", "gold-reqs", gold_requirements_path),
    ):
        out = directory / f"{path.stem}__stage1.csv"
        run_stage1(source, path, out, cfg)
        outputs[key] = out
    try:
        yield outputs
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_gold_consistency_is_one(cfg, artifact_tmp, gold_stage1_outputs):
    """Metric 8 on the gold pack must be 1.0.

    All five rules run. CM-01 became runnable in normalize 1.2.0, which added
    ``swimlane__normalized`` and ``owner_class__normalized``.
    """
    payload = run_consistency(
        "GOLDREG",
        gold_stage1_outputs["class"],
        gold_stage1_outputs["activity"],
        gold_stage1_outputs["requirements"],
        artifact_tmp,
        cfg,
    )

    if payload["consistency"] != 1.0:
        rows = list(
            csv.DictReader(
                open(artifact_tmp / "GOLDREG__consistency_instances.csv",
                     encoding="utf-8-sig")
            )
        )
        failures = [
            f"  {r['rule_id']} | {r['instance']} | {r['detail']}"
            for r in rows
            if r["status"] == "fail"
        ]
        per_rule = ", ".join(
            f"{rule}: {counts['failed']}/{counts['total']} failed"
            for rule, counts in sorted(payload["per_rule"].items())
        )
        pytest.fail(
            f"Gold consistency is {payload['consistency']:.4f}, expected 1.0 "
            f"({payload['total_failed']}/{payload['total_instances']} instances "
            f"failed; {per_rule}). Failing instances:\n" + "\n".join(failures)
        )
