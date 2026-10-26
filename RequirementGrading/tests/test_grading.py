"""test_grading.py — Acceptance tests for RequirementGrading (§13)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
import pytest

from RequirementGrading.config import GradingConfig, RulesConfig
from RequirementGrading.stages.s0_units import extract_units_from_file, normalize_text
from RequirementGrading.stages.s3_axis import RuleEvaluator


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GRADING_DIR = REPO_ROOT / "RequirementGrading"
GOLD_PATH = REPO_ROOT / "materials" / "G1-requirements.json"
RULES_PATH = GRADING_DIR / "rules.yaml"


@pytest.fixture
def rules() -> RulesConfig:
    return RulesConfig.load(RULES_PATH)


@pytest.fixture
def evaluator(rules: RulesConfig) -> RuleEvaluator:
    return RuleEvaluator(rules)


def test_normalization_rules(rules: RulesConfig):
    # Markdown stripped, trailing period removed, whitespace collapsed
    raw = "**Each order item** records a quantity, a unit price and `one product`. "
    norm = normalize_text(raw, rules)
    assert norm == "Each order item records a quantity, a unit price and one product"
    assert not norm.endswith(".")


def test_axis1_polarity_reject_first(evaluator: RuleEvaluator):
    # 'registers no order' contains 'registers' (accept), but reject must win!
    assert evaluator.classify_polarity("The system registers no order.") == "reject"
    assert evaluator.classify_polarity("The system registers the order.") == "accept"
    assert evaluator.classify_polarity("The system leaves the state unchanged.") == "reject"
    assert evaluator.classify_polarity("The system sets status to closed.") == "accept"
    assert evaluator.classify_polarity("No state change occurs.") == "none"


def test_axis2_transitions(evaluator: RuleEvaluator):
    text1 = "Changes status from pending to filled."
    text2 = "Changes status from filled to pending."
    t1 = evaluator.extract_transitions(text1)
    t2 = evaluator.extract_transitions(text2)
    assert t1 == {("pending", "filled")}
    assert t2 == {("filled", "pending")}
    assert t1 != t2


def test_axis2_case_sensitive_roles(evaluator: RuleEvaluator):
    # Roles are case-sensitive: Customer, OrderStaff, Accountant
    tokens_correct = evaluator.extract_identifier_tokens("When Customer submits order, OrderStaff reviews.")
    assert "Customer" in tokens_correct
    assert "OrderStaff" in tokens_correct
    assert "customer" not in tokens_correct

    tokens_lower = evaluator.extract_identifier_tokens("When customer submits order, orderstaff reviews.")
    assert "Customer" not in tokens_lower
    assert "OrderStaff" not in tokens_lower


def test_axis2_deliberate_trap_invoice_vs_payment(evaluator: RuleEvaluator):
    # Invoice becomes paid, payment becomes completed.
    # If a payment criterion says 'payment is paid', it yields 'payment' and 'paid'
    # whereas gold yields 'payment' and 'completed'.
    gold_text = "The payment status becomes completed."
    gen_text = "The payment status becomes paid."
    pass_ok, detail = evaluator.evaluate_axis2_identifiers(gold_text, gen_text)
    assert not pass_ok
    assert "subcheck=2b tokens" in detail


def test_axis2_cardinality_normalization(evaluator: RuleEvaluator):
    text1 = "A customer has at most one bank account."
    text2 = "A customer has no more than one bank account."
    c1 = evaluator.extract_cardinality(text1)
    c2 = evaluator.extract_cardinality(text2)
    assert c1["at most one"] == 1
    assert c2["at most one"] == 1
    assert c1 == c2


def test_axis3_numeric_sensitivity(evaluator: RuleEvaluator):
    gold = "The system shall respond within 2 seconds for at least 95% of submissions."
    gen_wrong = "The system shall respond within 3 seconds for at least 95% of submissions."
    pass_ok, detail = evaluator.evaluate_axis3_numeric(gold, gen_wrong, "nfr")
    assert not pass_ok
    assert "missing values" in detail

    gen_right = "The system responds within 2 seconds for at least 95% of submissions."
    pass_ok2, _ = evaluator.evaluate_axis3_numeric(gold, gen_right, "nfr")
    assert pass_ok2
