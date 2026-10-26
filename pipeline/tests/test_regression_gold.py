"""Regression tests for Stage 1 1.1.0 against the real gold requirements file.

Every expectation here comes from the 1.1.0 defect review of the v1.0.0 output
on the 49-row gold set. They pin the four fixed defects (negation kept, scoped
negation flags, state-mention precision, possessive handling) and the two
quality improvements (participial adjectives, auxiliary removal).
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from pipeline.stage1.normalize import normalize

# The only gold row whose main predicate is negated.
MAIN_NEGATED_ROWS: set[str] = {"GR-30"}

# Every gold row containing a negation cue anywhere.
CUE_ROWS: set[str] = {"GR-15", "GR-30", "GR-31", "GR-36", "GR-37", "GR-39"}


@pytest.fixture(scope="module")
def gold_rows(gold_requirements_path: Path) -> list[dict[str, str]]:
    """The gold CSV, read read-only."""
    with open(gold_requirements_path, "r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


@pytest.fixture(scope="module")
def results(gold_rows, cfg) -> dict[str, object]:
    """One :class:`Normalized` per gold row, keyed by requirement id."""
    return {row["gold_req_id"]: normalize(row["statement"], cfg) for row in gold_rows}


def test_gold_row_count(results):
    """The gold set is 49 rows; a change here invalidates every expectation."""
    assert len(results) == 49


# --------------------------------------------------------------------------
# 1. Negation cues stay in ``normalized`` (defect 1)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "req_id, word, count",
    [
        ("GR-30", "not", 1),
        ("GR-31", "no", 1),
        ("GR-36", "no", 2),
        ("GR-37", "without", 1),
        ("GR-15", "not", 1),
        ("GR-39", "not", 1),
    ],
)
def test_negation_words_are_kept(results, req_id, word, count):
    tokens = results[req_id].normalized.split()
    assert tokens.count(word) == count, results[req_id].normalized


def test_no_negation_word_is_ever_dropped(results):
    """No gold row loses a cue that step 1 recorded."""
    for req_id, result in results.items():
        for cue in result.negation_cues:
            expected = "not" if cue in {"n't", "n’t"} else cue
            if expected == "cannot":
                continue  # spaCy splits it; the "not" half is what survives
            assert expected in result.normalized.split(), (req_id, cue)


# --------------------------------------------------------------------------
# 2. Scoped negation flags (defect 2)
# --------------------------------------------------------------------------


def test_main_predicate_negated_only_for_gr30(results):
    flagged = {req_id for req_id, r in results.items() if r.main_predicate_negated}
    assert flagged == MAIN_NEGATED_ROWS


def test_has_negation_cue_matches_review(results):
    flagged = {req_id for req_id, r in results.items() if r.has_negation_cue}
    assert flagged == CUE_ROWS


def test_negation_scope_agrees_with_the_flags(results):
    """``negation_scope`` is the readable form of the two booleans."""
    for req_id, result in results.items():
        if result.main_predicate_negated:
            assert result.negation_scope == "main", req_id
        elif result.has_negation_cue:
            assert result.negation_scope == "subordinate", req_id
        else:
            assert result.negation_scope == "none", req_id


def test_old_negated_attribute_is_gone(results):
    """``negated`` was removed in 1.1.0; nothing may still read it."""
    assert not hasattr(results["GR-30"], "negated")


# --------------------------------------------------------------------------
# 3. Possessives (defect 4)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "req_id, phrase",
    [
        ("GR-25", "customer delivery address"),
        ("GR-35", "customer payment method"),
    ],
)
def test_possessive_marker_is_dropped(results, req_id, phrase):
    normalized = results[req_id].normalized
    assert "s" not in normalized.split(), normalized
    assert phrase in normalized, normalized


def test_curly_apostrophe_possessive(cfg):
    straight = normalize("the Customer's delivery address", cfg)
    curly = normalize("the Customer’s delivery address", cfg)
    assert straight.normalized == curly.normalized == "customer delivery address"


# --------------------------------------------------------------------------
# 5. Participial adjectives keep their surface form (improvement I1)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "req_id, phrase",
    [
        ("GR-31", "acting role"),
        ("GR-31", "resulting state"),
        ("GR-26", "processed revenue"),
        ("GR-33", "scheduled maintenance"),
        ("GR-02", "desired quantity"),
    ],
)
def test_participial_modifiers_are_not_lemmatized(results, req_id, phrase):
    assert phrase in results[req_id].normalized, results[req_id].normalized


def test_a_main_verb_is_still_lemmatized(cfg):
    """I1 narrows lemmatization to non-``amod`` verbs; it does not disable it."""
    assert "retrieve" in normalize("The Warehouse retrieves items.", cfg).normalized.split()


# --------------------------------------------------------------------------
# 6. Auxiliaries are dropped (improvement I2)
# --------------------------------------------------------------------------


def test_no_gold_row_contains_have_be(results):
    offenders = [r for r, res in results.items() if "have be" in res.normalized]
    assert offenders == []


def test_auxiliary_chain_is_removed(cfg):
    result = normalize("the order has been marked as picked", cfg)
    tokens = result.normalized.split()
    assert "have" not in tokens and "be" not in tokens, result.normalized


def test_root_copula_is_kept(cfg):
    """A copula that *is* the root carries the predication and stays."""
    assert "be" in normalize("any cart item is out of stock", cfg).normalized.split()


# --------------------------------------------------------------------------
# 7. Cross-form consistency
# --------------------------------------------------------------------------


def test_negated_and_affirmative_differ_only_by_not(cfg):
    negated = normalize("The system shall not store X.", cfg)
    affirmative = normalize("The system shall store X.", cfg)

    negated_tokens = negated.normalized.split()
    assert "not" in negated_tokens
    negated_tokens.remove("not")
    assert negated_tokens == affirmative.normalized.split()

    assert negated.main_predicate_negated is True
    assert affirmative.main_predicate_negated is False


def test_article_choice_does_not_change_the_output(cfg):
    indefinite = normalize("when an order is placed", cfg)
    definite = normalize("when the order is placed", cfg)
    assert indefinite.normalized == definite.normalized


# --------------------------------------------------------------------------
# 8. Agent phrasing
# --------------------------------------------------------------------------


def test_no_object_of_root_negates_the_main_predicate(cfg):
    result = normalize(
        "The system shall store no unencrypted primary account numbers.", cfg
    )
    assert result.main_predicate_negated is True
    assert result.negation_scope == "main"
    assert "no" in result.normalized.split()


def test_gold_and_agent_wording_agree_on_the_verb(cfg):
    """The gold "have been retrieved" and an agent's "retrieves" both lemmatize.

    v1.0.0 kept the gold side as the state ``retrieved`` while an agent writing
    "retrieves" produced ``retrieve``, so the two sides could never match.
    """
    gold = normalize("once its items have been retrieved from the shelves", cfg)
    agent = normalize("the Warehouse retrieves the items from the shelves", cfg)
    assert "retrieve" in gold.normalized.split(), gold.normalized
    assert "retrieve" in agent.normalized.split(), agent.normalized


# --------------------------------------------------------------------------
# Numeric bounds are not negations
# --------------------------------------------------------------------------


@pytest.mark.parametrize("req_id", ["GR-27", "GR-28", "GR-35"])
def test_no_more_than_is_a_bound_not_a_negation(results, req_id):
    result = results[req_id]
    assert result.has_negation_cue is False
    assert result.negation_scope == "none"
    assert "no more than" in result.normalized, result.normalized


@pytest.mark.parametrize("req_id", ["GR-32", "GR-33"])
def test_at_least_is_a_bound(results, req_id):
    assert results[req_id].has_negation_cue is False
    assert "at least" in results[req_id].normalized
