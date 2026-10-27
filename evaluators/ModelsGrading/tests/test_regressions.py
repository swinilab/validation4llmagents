"""Regression tests for three grading defects found in review.

1. A type-first attribute (`+String name`) was read as an untyped attribute named
   `String name`, so the type rule failed it.
2. A swimlane or transition, built from action pairs, ignored the cosine
   threshold, so it counted at thresholds its actions did not reach.
3. A run in provisional mode reported `status: final` although pairs had been
   resolved by `manual_default` rather than by a reviewer.
"""

from __future__ import annotations

import re

from evaluators.ModelsGrading.parser import parse_structural
from evaluators.ModelsGrading.parser.normalize import normalize_type, split_attribute
from evaluators.ModelsGrading.stages import s4_match, s8_metrics


# --- 1. type-first attributes ---------------------------------------------

def test_split_attribute_reads_both_spellings():
    assert split_attribute("name : String") == ("name", "String")
    assert split_attribute("+String name") == ("name", "String")
    assert split_attribute("-BankAccount? bankAccount") == ("bankAccount", "BankAccount?")
    assert split_attribute("Decimal price [0..1]") == ("price", "Decimal [0..1]")
    assert split_attribute("{static} Integer count = 0") == ("count", "Integer")
    assert split_attribute("Map<String, Integer> index") == ("index", "Map<String, Integer>")
    # One word names an untyped attribute: nothing to split.
    assert split_attribute("name") == ("name", None)


def test_type_first_attribute_is_named_and_typed(rules):
    text = ("@startuml\nclass Customer {\n  +String name\n  +BankAccount? account\n"
            "  +Decimal limit [0..1]\n}\n@enduml\n")
    result = parse_structural(text, rules)
    attributes = {e.element_id: e for e in result.elements if e.kind == "attribute"}

    assert set(attributes) == {"A:Customer.name", "A:Customer.account",
                               "A:Customer.limit"}
    assert attributes["A:Customer.name"].fields["type_norm"] == "String"
    assert attributes["A:Customer.account"].fields["type_norm"] == "BankAccount"
    assert attributes["A:Customer.limit"].fields["type_norm"] == "Decimal"
    assert attributes["A:Customer.name"].label_norm == "Customer name"
    assert not [v for v in result.violations if v.code == "attribute_no_type"]


def test_untyped_attribute_is_still_a_violation(rules):
    result = parse_structural("@startuml\nclass A {\n  name\n}\n@enduml\n", rules)
    assert [v.code for v in result.violations] == ["attribute_no_type"]


def test_normalize_type_of_type_first_multiplicity():
    assert normalize_type("Decimal [0..1]") == "Decimal"


def test_type_first_gold_scores_as_identity(harness, gold_structural_text,
                                            gold_behavioral_text):
    """The gold rewritten as `Type name [mult]` must score exactly as the gold."""
    flipped = re.sub(r"^( +)(\w+) : (\w+)( \[[^\]]*\])?$",
                     lambda m: f"{m[1]}{m[3]} {m[2]}{m[4] or ''}",
                     gold_structural_text, flags=re.MULTILINE)
    assert flipped != gold_structural_text
    item = harness("type-first")
    item.write(flipped, gold_behavioral_text)
    assert item.run().returncode == 0

    structural = item.metrics()["structural"]
    assert structural["recall"] == 1.0
    assert structural["precision"] == 1.0
    assert item.metrics()["diagnostics"]["rule_rejections"] == {}


# --- 2. by-construction pairs obey the threshold --------------------------

def _element(kind, element_id, **fields):
    return {"element_id": element_id, "kind": kind, "label_raw": element_id,
            "label_norm": fields.pop("label_norm", element_id), **fields}


def _behavioral_block(names):
    actions = [_element("action", name, lane="Customer") for name in names]
    lanes = [_element("swimlane", f"LANE:{name}", action=name, lane="Customer")
             for name in names]
    transitions = [_element("transition", f"T:{a}->{b}", source=a, target=b, guard=[])
                   for a, b in zip(names, names[1:])]
    return actions + lanes + transitions


def test_swimlane_and_transition_inherit_the_action_cosine():
    names = ["A", "B", "C"]
    block = _behavioral_block(names)
    elements = {"behavioral": {"gold": block, "gen": block}}
    cosines = {"A": 0.95, "B": 0.80, "C": 0.72}
    candidates = [{"diagram": "behavioral", "kind": "action", "gold_id": n,
                   "gen_id": n, "cosine": c, "excluded": None}
                  for n, c in cosines.items()]

    assigned = s4_match.run(elements, candidates, {}, ("behavioral",))[
        "behavioral"]["assigned"]
    by_gold = {pair["gold_id"]: pair for pair in assigned}

    assert by_gold["LANE:A"]["cosine"] == 0.95
    assert by_gold["LANE:C"]["cosine"] == 0.72
    assert by_gold["T:A->B"]["cosine"] == 0.80       # lower of 0.95 and 0.80
    assert by_gold["T:B->C"]["cosine"] == 0.72       # lower of 0.80 and 0.72

    records = [dict(pair, diagram="behavioral", verdict="PASS") for pair in assigned]
    kept = {r["gold_id"] for r in s8_metrics._passing(records, "behavioral", 0.75)}
    assert kept == {"A", "B", "LANE:A", "LANE:B", "T:A->B"}


# --- 3. provisional mode is not final -------------------------------------

def test_provisional_run_with_defaulted_pairs_is_not_final(
        harness, gold_structural_text, gold_behavioral_text):
    """A warn-list type is a MANUAL pair. Provisional mode resolves it with the
    default instead of halting, and the metrics must say so."""
    item = harness("provisional-status")
    structural = gold_structural_text.replace("price : Decimal", "price : Float", 1)
    item.write(structural, gold_behavioral_text)
    assert item.run("--on-pending", "provisional").returncode == 0

    metrics = item.metrics()
    assert metrics["status"] == "provisional"
    assert metrics["unresolved"] >= 1
    assert metrics["manual_default"] is not None


def test_identity_run_stays_final_in_provisional_mode(
        harness, gold_structural_text, gold_behavioral_text):
    item = harness("provisional-identity")
    item.write(gold_structural_text, gold_behavioral_text)
    assert item.run("--on-pending", "provisional").returncode == 0

    metrics = item.metrics()
    assert metrics["status"] == "final"
    assert metrics["unresolved"] == 0
