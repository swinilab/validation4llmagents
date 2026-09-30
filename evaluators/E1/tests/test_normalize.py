"""Unit tests for E1's normalization contract.

These cover the behaviour E1 promised from 1.0.0 - determinism, identifier
splitting, modal and article removal, label handling, state protection and the
ontology reader - updated for the 1.1.0 column names.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from evaluators.E1.config import E1ConfigError, load_config
from evaluators.E1.normalize import (
    E1_VERSION,
    load_state_vocabulary,
    normalize,
    normalize_label,
)


def test_version_is_1_1_0():
    assert E1_VERSION == "1.1.0"


# --------------------------------------------------------------------------
# Determinism
# --------------------------------------------------------------------------

SAMPLES = [
    "The system shall not store unencrypted primary account numbers.",
    "The system shall transition the order to the placed state.",
    "OrderLine",
    "payment_failed",
    "",
]


@pytest.mark.parametrize("text", SAMPLES)
def test_normalize_is_deterministic(text, cfg):
    first = normalize(text, cfg)
    second = normalize(text, cfg)
    assert first.normalized == second.normalized
    assert first.negation_cues == second.negation_cues
    assert first.state_mentions == second.state_mentions
    assert first.negation_scope == second.negation_scope


def test_raw_is_returned_unchanged(cfg):
    text = "  The System shall UPDATE the OrderLine.  "
    assert normalize(text, cfg).raw == text


def test_none_is_treated_as_empty(cfg):
    result = normalize(None, cfg)
    assert result.normalized == ""
    assert result.state_mentions == []
    assert result.negation_scope == "none"


# --------------------------------------------------------------------------
# Identifier splitting and label normalization
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "label, expected",
    [
        ("OrderLine", "order line"),
        # spaCy splits the bare token "id"; the snake_case boundaries are what
        # this test pins, so the expectation records the tokenizer's output.
        ("order_line_id", "order line i d"),
        ("PaymentTransaction", "payment transaction"),
        ("HTTPServer", "http server"),
        ("[stock available]", "stock available"),
    ],
)
def test_label_normalization(label, expected, cfg):
    assert normalize_label(label, cfg).normalized == expected


def test_label_keeps_its_first_word_even_when_it_is_a_modal(cfg):
    """A class named "Can" must not normalize to the empty string."""
    assert normalize_label("Can", cfg).normalized == "can"
    assert normalize_label("Will", cfg).normalized == "will"


def test_sentence_normalization_drops_modals_and_articles(cfg):
    result = normalize("The system shall update the order.", cfg)
    tokens = result.normalized.split()
    assert "shall" not in tokens
    assert "the" not in tokens
    assert tokens[0] == "system"


def test_identifier_splitting_can_be_disabled():
    cfg = load_config(overrides={"split_identifiers": False})
    assert "order line" not in normalize("OrderLine", cfg).normalized


# --------------------------------------------------------------------------
# Numbers and units survive intact
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, token",
    [
        ("encrypted with AES-256 at rest", "aes-256"),
        ("within a 30-day window", "30-day"),
        ("an error rate of 0.1%", "0.1%"),
        ("2,000 concurrent user sessions", "2,000"),
    ],
)
def test_numeric_tokens_are_kept_whole(text, token, cfg):
    assert token in normalize(text, cfg).normalized.split()


# --------------------------------------------------------------------------
# State vocabulary from the ontology
# --------------------------------------------------------------------------


def test_ontology_separates_canonical_names_from_aliases(cfg):
    vocab = load_state_vocabulary(Path(cfg.ontology_path))
    assert vocab.canonical == {
        "draft",
        "placed",
        "picked",
        "packed",
        "shipped",
        "payment failed",
        "cancelled",
        "returned",
        "refunded",
    }
    # A few aliases, to confirm the alias side is populated and disjoint.
    for alias in ("new", "retrieved", "boxed", "declined", "ordered"):
        assert alias in vocab.all_terms
        assert not vocab.is_canonical(alias)


def test_missing_ontology_is_an_error(tmp_path):
    with pytest.raises(E1ConfigError):
        load_state_vocabulary(tmp_path / "nope.yaml")


def test_ontology_without_states_is_an_error(tmp_path):
    path = tmp_path / "ontology.yaml"
    path.write_text("entities: []\n", encoding="utf-8")
    with pytest.raises(E1ConfigError):
        load_state_vocabulary(path)


def test_ontology_file_is_not_modified(cfg):
    path = Path(cfg.ontology_path)
    before = path.read_bytes()
    normalize("transition the order to the shipped state", cfg)
    assert path.read_bytes() == before


# --------------------------------------------------------------------------
# State protection
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("transition the order to the shipped state", ["shipped"]),
        ("move it to the payment failed state", ["payment failed"]),
        ("a placed order", ["placed"]),
        ("when an order is cancelled", ["cancelled"]),
        ("mark the order as picked", ["picked"]),
        ("the declined state", ["declined"]),
    ],
)
def test_state_uses_are_reported(text, expected, cfg):
    assert normalize(text, cfg).state_mentions == expected


@pytest.mark.parametrize(
    "text",
    [
        "the carrier shipped the goods",
        "the warehouse approves returned items",
        "release reserved inventory",
        "display a retrieved order",
    ],
)
def test_non_state_uses_are_not_reported(text, cfg):
    assert normalize(text, cfg).state_mentions == []
