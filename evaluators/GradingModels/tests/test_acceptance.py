"""Acceptance tests (spec §14).

The implementation must pass all of these before any real run. Numbering
follows the spec's list; each test names the clause it enforces.
"""

from __future__ import annotations

import json
import shutil

import pytest

from GradingModels.configload import (DIAGRAMS, GOLD_INVENTORY, ConfigError,
                                      load_rules)
from GradingModels.parser import (collapse_by_label, parse_behavioral,
                                  parse_structural)
from GradingModels.stages import s0_syntax

from .conftest import ROOT, SECTION


def _kinds(elements) -> dict[str, int]:
    out: dict[str, int] = {}
    for element in elements:
        out[element.kind] = out.get(element.kind, 0) + 1
    return out


def _collapsed(text, parser, rules):
    result = parser(text, rules)
    kept, _ = collapse_by_label(result.elements)
    return result, kept


# --- 1. Gold parses --------------------------------------------------------

def test_01_gold_parses_at_validity_one(gold_structural_text,
                                        gold_behavioral_text, rules):
    """§14.1, §4.3: both gold files reach validity 1.0.

    The gating test for the whole section: §16.1 recorded that the prototype
    could read neither `detach` nor the `split` family, which `G3` uses.
    """
    structural = parse_structural(gold_structural_text, rules)
    behavioral = parse_behavioral(gold_behavioral_text, rules)
    assert structural.validity() == 1.0, structural.rejections
    assert behavioral.validity() == 1.0, behavioral.rejections
    assert structural.parse_error is None
    assert behavioral.parse_error is None


def test_01b_gold_inventory_exact(gold_structural_text, gold_behavioral_text,
                                  rules):
    """§5.7: assert the gold inventory exactly, per kind, not just the total."""
    _, structural = _collapsed(gold_structural_text, parse_structural, rules)
    _, behavioral = _collapsed(gold_behavioral_text, parse_behavioral, rules)
    assert _kinds(structural) == GOLD_INVENTORY["structural"]
    assert _kinds(behavioral) == GOLD_INVENTORY["behavioral"]
    assert len(structural) == 50
    assert len(behavioral) == 39


def test_01c_gold_transitions_match_the_table(gold_behavioral_text, rules):
    """§5.5: gold yields exactly the 11 tabulated transitions."""
    _, elements = _collapsed(gold_behavioral_text, parse_behavioral, rules)
    actual = {
        (e.fields["source"], tuple(sorted(e.fields["guard"])), e.fields["target"])
        for e in elements if e.kind == "transition"
    }
    expected = {
        ("Make an Order", (), "Receive order"),
        ("Receive order", ("accepted",), "Fill Order"),
        ("Receive order", ("declined",), "Close Order"),
        ("Fill Order", (), "Ship Order"),
        ("Fill Order", (), "Send Invoice"),
        ("Send Invoice", (), "Make Payment"),
        ("Make Payment", ("declined",), "Reject Payment"),
        ("Reject Payment", (), "Make Payment"),
        ("Make Payment", ("authorized",), "Accept Payment"),
        ("Ship Order", (), "Close Order"),
        ("Accept Payment", (), "Close Order"),
    }
    assert actual == expected
    assert len(actual) == 11


# --- 2. Identity -----------------------------------------------------------

@pytest.fixture(scope="module")
def identity_run(gold_structural_text, gold_behavioral_text):
    """One shared identity run: grading gold against itself."""
    from .conftest import Harness
    item = Harness("test-identity-shared")
    item.cleanup()
    item.write(gold_structural_text, gold_behavioral_text)
    completed = item.run()
    assert completed.returncode == 0, completed.stderr
    metrics = item.metrics()
    axis = item.read("05_axis.json")
    yield metrics, axis
    item.cleanup()


def test_02_identity(identity_run):
    """§14.2: Recall == 1.0, Precision == 1.0, 50 and 39 matched, zero pending,
    zero rule rejections, all six control items pass."""
    metrics, axis = identity_run
    assert metrics["status"] == "final"
    assert metrics["pending_type"] == 0
    assert metrics["pending_guard"] == 0
    assert metrics["pending_rubric"] == 0

    for diagram, total in (("structural", 50), ("behavioral", 39)):
        block = metrics[diagram]
        assert block["gate"] == "pass"
        assert block["recall"] == 1.0, diagram
        assert block["precision"] == 1.0, diagram
        assert block["f1"] == 1.0, diagram
        primary = [row for row in block["sweep"]
                   if row["threshold"] == metrics["primary_threshold"]][0]
        assert primary["matched_gold"] == total
        assert primary["matched_gen"] == total

    assert metrics["diagnostics"]["rule_rejections"] == {}
    assert all(verdict == "pass" for verdict in metrics["control"].values()), \
        metrics["control"]
    assert all(record["verdict"] == "PASS" for record in axis["records"])


# --- 3. Gate ---------------------------------------------------------------

def test_03_gate_records_na_not_zero(harness, gold_structural_text,
                                     gold_behavioral_text):
    """§14.3, §4.2: one unsupported construct makes that diagram's semantics
    `"n/a"` and not `0`, leaves the other diagram unaffected, and exits 0."""
    item = harness("gate")
    broken = gold_behavioral_text.replace(
        "@enduml", "state Nonsense <<unsupported>>\n@enduml")
    item.write(gold_structural_text, broken)
    completed = item.run()
    assert completed.returncode == 0, completed.stderr

    metrics = item.metrics()
    behavioral = metrics["behavioral"]
    assert behavioral["gate"] == "fail"
    for key in ("recall", "precision", "f1"):
        assert behavioral[key] == s0_syntax.NA, (key, behavioral[key])
        assert behavioral[key] != 0
    assert behavioral["syntax_validity"] < 1.0

    structural = metrics["structural"]
    assert structural["gate"] == "pass"
    assert structural["recall"] == 1.0
    assert metrics["diagnostics"]["gate_blocked"]["behavioral"]["rejections"]


def test_03b_na_survives_a_json_round_trip(harness, gold_structural_text,
                                           gold_behavioral_text):
    """§4.2: serializers must not coerce `"n/a"` to null or 0."""
    item = harness("na-roundtrip")
    item.write(gold_structural_text,
               gold_behavioral_text.replace("@enduml", "detach extra junk\n@enduml"))
    assert item.run().returncode == 0
    raw = (item.run_dir / "07_metrics.json").read_text("utf-8")
    assert '"n/a"' in raw
    reloaded = json.loads(raw)
    assert reloaded["behavioral"]["recall"] == "n/a"


# --- 4. Rule sensitivity ---------------------------------------------------

MUTATIONS = [
    pytest.param(
        "structural", ("totalAmount : Decimal", "totalAmount : String"),
        "A:Order.totalAmount", "type", id="type"),
    pytest.param(
        "structural", ('Order "1" *-- "1..*" OrderItem', 'Order "1" -- "1..*" OrderItem'),
        "R:Order--OrderItem", "rel_type", id="rel_type"),
    pytest.param(
        "structural", ('Customer "1" -- "0..*" Order', 'Customer "0..*" -- "1" Order'),
        "R:Customer--Order", "rel_multiplicity", id="rel_multiplicity"),
    pytest.param(
        "behavioral", (":Payment [completed]; <<obj>>", ":Payment [paid]; <<obj>>"),
        "OBJ:Payment[completed]", "status", id="status"),
]


@pytest.mark.parametrize("diagram,replacement,element_id,counter", MUTATIONS)
def test_04_rule_sensitivity(harness, gold_structural_text, gold_behavioral_text,
                             diagram, replacement, element_id, counter):
    """§14.4: each mutation in isolation makes the named element `not_covered`
    and increments the named counter."""
    item = harness(f"mutation-{counter}")
    old, new = replacement
    structural, behavioral = gold_structural_text, gold_behavioral_text
    if diagram == "structural":
        assert old in structural
        structural = structural.replace(old, new, 1)
    else:
        assert old in behavioral
        behavioral = behavioral.replace(old, new)
    item.write(structural, behavioral)
    assert item.run("--on-pending", "provisional").returncode == 0

    axis = item.read("05_axis.json")
    covered = {r["gold_id"] for r in axis["records"] if r["verdict"] == "PASS"}
    assert element_id not in covered, f"{element_id} should be not_covered"

    rejections = item.metrics()["diagnostics"]["rule_rejections"]
    assert rejections.get(counter, 0) >= 1, (counter, rejections)


def test_04b_swimlane_mutation(harness, gold_structural_text,
                               gold_behavioral_text):
    """§14.4: `Fill Order` moved to the Customer lane -> `swimlane` counter."""
    item = harness("mutation-swimlane")
    behavioral = gold_behavioral_text.replace(
        "if () then ([accepted])\n  :Fill Order;",
        "if () then ([accepted])\n  |Customer|\n  :Fill Order;", 1)
    item.write(gold_structural_text, behavioral)
    assert item.run("--on-pending", "provisional").returncode == 0

    axis = item.read("05_axis.json")
    covered = {r["gold_id"] for r in axis["records"] if r["verdict"] == "PASS"}
    assert "LANE:Fill Order" not in covered
    rejections = item.metrics()["diagnostics"]["rule_rejections"]
    assert rejections.get("swimlane", 0) >= 1, rejections


def test_04c_branch_inversion_is_detected(harness, gold_structural_text,
                                          gold_behavioral_text):
    """§14.4, final row: swapping `accepted` / `declined` on transitions 2 and 3.

    The important one. Node and edge counts are unchanged, so a pipeline that
    passes everything else and fails this has no way to detect branch
    inversion.
    """
    item = harness("mutation-guard")
    behavioral = (gold_behavioral_text
                  .replace("if () then ([accepted])", "if () then ([INVERTED])", 1)
                  .replace("else ([declined])", "else ([accepted])", 1)
                  .replace("if () then ([INVERTED])", "if () then ([declined])", 1))
    assert "then ([declined])" in behavioral and "else ([accepted])" in behavioral
    item.write(gold_structural_text, behavioral)
    assert item.run("--on-pending", "provisional").returncode == 0

    axis = item.read("05_axis.json")
    covered = {r["gold_id"] for r in axis["records"] if r["verdict"] == "PASS"}
    assert "T:Receive order->Fill Order" not in covered
    assert "T:Receive order->Close Order" not in covered
    rejections = item.metrics()["diagnostics"]["rule_rejections"]
    assert rejections.get("guard", 0) >= 1, rejections


def test_04d_enum_literal_trap(harness, gold_structural_text,
                               gold_behavioral_text):
    """§7.4.2: a payment using `paid` produces a different literal set."""
    item = harness("mutation-literal")
    structural = gold_structural_text.replace(
        "enum PaymentStatus {\n  pending\n  completed\n  failed\n}",
        "enum PaymentStatus {\n  pending\n  paid\n  failed\n}", 1)
    assert "paid\n  failed" in structural
    item.write(structural, gold_behavioral_text)
    assert item.run("--on-pending", "provisional").returncode == 0

    axis = item.read("05_axis.json")
    covered = {r["gold_id"] for r in axis["records"] if r["verdict"] == "PASS"}
    assert "E:PaymentStatus" not in covered
    assert item.metrics()["diagnostics"]["rule_rejections"].get("enum_literals", 0) >= 1


# --- 5. Decision label invariance -----------------------------------------

def test_05_decision_label_invariance(harness, identity_run,
                                      gold_structural_text, gold_behavioral_text):
    """§14.5: replacing `if ()` with `if (Order valid?)`, leaving guards
    untouched, must change no metric (§7.4.6: guards scored, labels ignored)."""
    baseline, _ = identity_run
    item = harness("decision-label")
    behavioral = gold_behavioral_text.replace("if () then", "if (Order valid?) then")
    assert "if (Order valid?)" in behavioral
    item.write(gold_structural_text, behavioral)
    assert item.run().returncode == 0

    for diagram in DIAGRAMS:
        assert item.metrics()[diagram]["sweep"] == baseline[diagram]["sweep"], diagram


# --- 6. Loop presentation invariance --------------------------------------

def test_06_loop_presentation_invariance(harness, identity_run,
                                         gold_structural_text,
                                         gold_behavioral_text):
    """§14.6, §5.3: repeating `Make Payment` and `Payment [pending]` a third
    time must change no element count and no metric."""
    baseline, _ = identity_run
    item = harness("loop-presentation")
    # Unroll one retry iteration inside the loop body: `Make Payment` and
    # `Payment [pending]` are drawn a third time, still only ever reached from
    # `Reject Payment`, so the behaviour is identical and only the drawing
    # changed. Appending a second `Make Payment` in plain sequence instead
    # would add a real `Make Payment -> Make Payment` transition, which is a
    # different control flow rather than a presentation choice.
    behavioral = gold_behavioral_text.replace(
        """    |Accountant|
    while () is ([declined])
      :Reject Payment;
      :Payment [failed]; <<obj>>
      |Customer|
      :Make Payment;
      :Payment [pending]; <<obj>>
      |Accountant|
    endwhile ([authorized])
""",
        """    |Accountant|
    while () is ([declined])
      :Reject Payment;
      :Payment [failed]; <<obj>>
      |Customer|
      :Make Payment;
      :Payment [pending]; <<obj>>
      |Accountant|
      if () then ([declined])
        :Reject Payment;
        :Payment [failed]; <<obj>>
        |Customer|
        :Make Payment;
        :Payment [pending]; <<obj>>
        |Accountant|
      endif
    endwhile ([authorized])
""", 1)
    assert behavioral != gold_behavioral_text
    item.write(gold_structural_text, behavioral)
    assert item.run().returncode == 0

    metrics = item.metrics()
    assert metrics["behavioral"]["n_gen"] == baseline["behavioral"]["n_gen"]
    assert metrics["behavioral"]["sweep"] == baseline["behavioral"]["sweep"]


# --- 7. Fork syntax invariance --------------------------------------------

def test_07_fork_syntax_invariance(harness, identity_run, gold_structural_text,
                                   gold_behavioral_text):
    """§14.7: re-expressing the four `split`/`end split` blocks without `split`
    must leave the behavioral metrics unchanged and control item 3 passing."""
    baseline, _ = identity_run
    item = harness("fork-syntax")
    behavioral = (gold_behavioral_text
                  .replace("    split\n      :Payment [completed]; <<obj>>\n"
                           "      detach\n    split again\n"
                           "      :Invoice [paid]; <<obj>>\n    end split\n",
                           "    :Payment [completed]; <<obj>>\n"
                           "    :Invoice [paid]; <<obj>>\n", 1)
                  .replace("split\n  :Order [closed]; <<obj>>\n  detach\n"
                           "split again\n  stop\nend split\n",
                           ":Order [closed]; <<obj>>\nstop\n", 1))
    assert "split" not in behavioral
    item.write(gold_structural_text, behavioral)
    assert item.run().returncode == 0

    metrics = item.metrics()
    assert metrics["behavioral"]["sweep"] == baseline["behavioral"]["sweep"]
    assert metrics["control"]["item_3"] == "pass"


# --- 8. Control-node exclusion --------------------------------------------

def test_08_control_nodes_do_not_enter_the_denominator(
        harness, identity_run, gold_structural_text, gold_behavioral_text):
    """§14.8, §5.2: a redundant `if/endif` must leave `N_gen` unchanged."""
    baseline, _ = identity_run
    item = harness("control-exclusion")
    behavioral = gold_behavioral_text.replace(
        ":Close Order;", "if () then ([accepted])\nendif\n:Close Order;", 1)
    item.write(gold_structural_text, behavioral)
    assert item.run("--on-pending", "provisional").returncode == 0
    assert item.metrics()["behavioral"]["n_gen"] == baseline["behavioral"]["n_gen"]


# --- 9. Dependency asymmetry ----------------------------------------------

def test_09_dependency_asymmetry(harness, gold_structural_text,
                                 gold_behavioral_text):
    """§14.9, §7.1: renaming `Customer` to `Warehouse` makes M1 miss it.

    Its four gold attributes must be `not_covered`, and the four generated
    attributes must reach the rubric rather than being counted as failures.
    """
    item = harness("asymmetry")
    structural = gold_structural_text.replace("Customer", "Warehouse")
    item.write(structural, gold_behavioral_text)
    assert item.run("--on-pending", "provisional").returncode == 0

    axis = item.read("05_axis.json")
    covered = {r["gold_id"] for r in axis["records"] if r["verdict"] == "PASS"}
    gold_attributes = [f"A:Customer.{name}" for name in
                       ("name", "address", "phone", "bankAccount")]
    for attribute in gold_attributes:
        assert attribute not in covered, attribute

    # The gen side reaches the rubric: it is in the unmatched set, not recorded
    # as a failed pair.
    rubric_llm = (item.review_dir / "rubric_llm.csv").read_text("utf-8")
    for name in ("name", "address", "phone", "bankAccount"):
        assert f"A:Warehouse.{name}" in rubric_llm, name
    failed_gen = {r["gen_id"] for r in axis["records"] if r["verdict"] == "FAIL"}
    assert not any(f"A:Warehouse.{n}" in failed_gen
                   for n in ("name", "address", "phone", "bankAccount"))


# --- 10. Nesting ----------------------------------------------------------

def test_10_candidate_sets_are_nested(gold_structural_text, rules, config):
    """§14.10, §7.2: the candidate set at 0.70 is a superset of the set at 0.85.

    Nesting is what makes human adjudication reusable, so it is asserted on the
    candidate sets directly rather than inferred from the ledgers.
    """
    from GradingModels.stages import (s1_elements, s2_similarity,
                                      s3_candidates)
    gold = {"structural": parse_structural(gold_structural_text, rules)}
    gen = {"structural": parse_structural(gold_structural_text, rules)}
    elements = s1_elements.run(gold, gen, ("structural",))
    arrays, index = s2_similarity.run(elements, config, ("structural",))

    sets = {}
    for threshold in (min(config["sweep_models"]), max(config["sweep_models"])):
        local = dict(config, sweep_models=[threshold], threshold_models=threshold)
        pairs = s3_candidates.run(elements, arrays, index, local, ("structural",))
        sets[threshold] = {(p["gold_id"], p["gen_id"]) for p in pairs}

    low, high = min(config["sweep_models"]), max(config["sweep_models"])
    assert sets[high] <= sets[low]


def test_10b_sweep_appends_no_new_ledger_rows(harness, gold_structural_text,
                                              gold_behavioral_text):
    """§14.10: running the full sweep appends zero new rows to either ledger
    after the first pass at the review threshold."""
    item = harness("nesting-ledger")
    # A warn-list type produces a real MANUAL row to observe.
    structural = gold_structural_text.replace("price : Decimal", "price : Float", 1)
    item.write(structural, gold_behavioral_text)
    assert item.run().returncode == 2        # NEEDS_REVIEW: a type warning

    first = (item.review_dir / "type_ledger.csv").read_text("utf-8")
    shutil.rmtree(item.run_dir, ignore_errors=True)
    assert item.run().returncode == 2
    assert (item.review_dir / "type_ledger.csv").read_text("utf-8") == first


# --- 11. Permutation invariance -------------------------------------------

def test_11_permutation_invariance(harness, identity_run, gold_structural_text,
                                   gold_behavioral_text):
    """§14.11, §7.3: shuffling declaration order must leave every metric and
    every assignment identical."""
    baseline, baseline_axis = identity_run
    item = harness("permutation")
    item.write(_reorder_structural(gold_structural_text), gold_behavioral_text)
    assert item.run().returncode == 0

    metrics = item.metrics()
    assert metrics["structural"]["sweep"] == baseline["structural"]["sweep"]

    def pairs(axis):
        return sorted((r["gold_id"], r["gen_id"], r["verdict"])
                      for r in axis["records"] if r["diagram"] == "structural")

    assert pairs(item.read("05_axis.json")) == pairs(baseline_axis)


def _reorder_structural(text: str) -> str:
    """Reverse the order of the class blocks, leaving their content alone."""
    head, _, tail = text.partition("class Customer {")
    body, _, edges = ("class Customer {" + tail).partition("Customer \"1\"")
    blocks = [block for block in body.split("\n\n") if block.strip()]
    return head + "\n\n".join(reversed(blocks)) + "\n\nCustomer \"1\"" + edges


# --- 12. Resumability -----------------------------------------------------

def test_12_resumability(harness, gold_structural_text, gold_behavioral_text):
    """§14.12, §1 invariant 2: deleting `run/` and re-running with the same
    `review/` must reproduce bit-identical metrics."""
    item = harness("resume")
    item.write(gold_structural_text, gold_behavioral_text)
    assert item.run().returncode == 0
    first = (item.run_dir / "07_metrics.json").read_text("utf-8")

    shutil.rmtree(item.run_dir)
    assert item.run().returncode == 0
    second = (item.run_dir / "07_metrics.json").read_text("utf-8")

    assert json.loads(first) == json.loads(second)


# --- 13. Ledger immutability ----------------------------------------------

def test_13_ledger_immutability(harness, gold_structural_text,
                                gold_behavioral_text):
    """§14.13, §1 invariant 3: re-running must not alter a row with a non-empty
    verdict."""
    item = harness("ledger-immutable")
    structural = gold_structural_text.replace("price : Decimal", "price : Float", 1)
    item.write(structural, gold_behavioral_text)
    assert item.run().returncode == 2

    ledger = item.review_dir / "type_ledger.csv"
    rows = ledger.read_text("utf-8").splitlines()
    assert len(rows) >= 2
    header, first = rows[0], rows[1]
    fields = header.split(",")
    values = first.split(",")
    values[fields.index("verdict")] = "PASS"
    values[fields.index("reviewer")] = "tester"
    values[fields.index("timestamp")] = "2026-10-25T00:00:00Z"
    filled = ",".join(values)
    ledger.write_text("\n".join([header, filled, *rows[2:]]) + "\n", encoding="utf-8")
    before = ledger.read_text("utf-8")

    shutil.rmtree(item.run_dir, ignore_errors=True)
    item.run()
    assert ledger.read_text("utf-8") == before


def test_13b_bad_verdict_aborts(harness, gold_structural_text,
                                gold_behavioral_text):
    """§13: a ledger verdict outside {PASS, FAIL} aborts, naming the row."""
    item = harness("ledger-bad-verdict")
    structural = gold_structural_text.replace("price : Decimal", "price : Float", 1)
    item.write(structural, gold_behavioral_text)
    assert item.run().returncode == 2

    ledger = item.review_dir / "type_ledger.csv"
    rows = ledger.read_text("utf-8").splitlines()
    fields = rows[0].split(",")
    values = rows[1].split(",")
    values[fields.index("verdict")] = "MAYBE"
    ledger.write_text("\n".join([rows[0], ",".join(values), *rows[2:]]) + "\n",
                      encoding="utf-8")

    shutil.rmtree(item.run_dir, ignore_errors=True)
    completed = item.run()
    assert completed.returncode == 1
    assert "MAYBE" in completed.stderr


# --- 14. No dedup key -----------------------------------------------------

def test_14_dedup_threshold_is_rejected(tmp_path):
    """§14.14, §9.2: a run supplying `dedup_threshold` to this section aborts,
    so its absence is deliberate rather than forgotten."""
    from GradingModels.configload import load_config

    config = (ROOT / "config.yaml").read_text("utf-8")
    path = tmp_path / "config.yaml"
    path.write_text(config + "\ndedup_threshold: 0.90\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="dedup_threshold"):
        load_config(path)


# --- loader completeness (§9.1) -------------------------------------------

def test_loader_rejects_a_missing_key(tmp_path):
    """§9.1: both loaders fail loudly on a missing key -- no silent defaults."""
    from GradingModels.configload import load_config

    lines = [line for line in (ROOT / "config.yaml").read_text("utf-8").splitlines()
             if not line.startswith("threshold_models:")]
    path = tmp_path / "config.yaml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="threshold_models"):
        load_config(path)


def test_rules_loader_rejects_an_unknown_key(tmp_path):
    """§9.1: an unknown key in `rules.yaml` aborts."""
    text = (SECTION / "rules.yaml").read_text("utf-8")
    path = tmp_path / "rules.yaml"
    path.write_text(text + "\nmystery_key: 1\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="mystery_key"):
        load_rules(path)


def test_rules_loader_rejects_lowercase_true(tmp_path):
    """§9.3: `normalization.lowercase: true` breaks the role check, so the
    loader must reject it."""
    text = (SECTION / "rules.yaml").read_text("utf-8").replace(
        "lowercase: false", "lowercase: true")
    path = tmp_path / "rules.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ConfigError, match="lowercase"):
        load_rules(path)


# --- edge cases (§13) -----------------------------------------------------

def test_missing_diagram_file(harness, gold_structural_text):
    """§13: a missing diagram is `n/a` with `gate: "missing"`, exit 0, and the
    other diagram is still graded."""
    item = harness("missing-file")
    item.write(structural=gold_structural_text)
    completed = item.run()
    assert completed.returncode == 0, completed.stderr

    metrics = item.metrics()
    assert metrics["behavioral"]["gate"] == "missing"
    assert metrics["behavioral"]["recall"] == s0_syntax.NA
    assert metrics["structural"]["recall"] == 1.0


def test_empty_but_valid_diagram(harness, gold_behavioral_text):
    """§13: a diagram that parses but yields 0 elements gates at validity 1.0,
    and scores Recall 0 / Precision 0 -- not `n/a`."""
    item = harness("empty-diagram")
    item.write("@startuml\n@enduml\n", gold_behavioral_text)
    completed = item.run()
    assert completed.returncode == 0, completed.stderr

    structural = item.metrics()["structural"]
    assert structural["gate"] == "pass"
    assert structural["recall"] == 0.0
    assert structural["precision"] == 0.0
    assert structural["f1"] == 0.0
    assert item.metrics()["status"] == "final"
