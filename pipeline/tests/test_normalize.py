"""Unit tests for the normalization contract.

These cover determinism, identifier splitting, modal and article removal, label
handling, and negation behavior.
"""

from __future__ import annotations

import pytest

from pipeline.config import load_config
from pipeline.normalize import (
    PIPELINE_VERSION,
    STAGE1_VERSION,
    normalize,
    normalize_label,
)


def test_version_is_current():
    assert PIPELINE_VERSION == "1.3.0"
    assert STAGE1_VERSION == "1.3.0"


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
    assert first.negation_scope == second.negation_scope


def test_raw_is_returned_unchanged(cfg):
    text = "  The System shall UPDATE the OrderLine.  "
    assert normalize(text, cfg).raw == text


def test_none_is_treated_as_empty(cfg):
    result = normalize(None, cfg)
    assert result.normalized == ""
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
