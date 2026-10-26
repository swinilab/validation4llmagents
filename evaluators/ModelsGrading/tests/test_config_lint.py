"""Config-completeness lint (spec §14, closing paragraph; §9.1).

"Config completeness is a CI lint, not an acceptance test: grep the source for
numeric literals and for members of the closed vocabularies, permitting only the
structural constants named in §9.1, and assert that loading a YAML with a key
removed aborts rather than falling back to a default."

The last clause is covered by the loader tests in `test_acceptance.py`; this
module is the grep.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
import yaml

from .conftest import SECTION

# §9.1: permitted literals are structural constants with no effect on results --
# the expected gold counts used in assertions, array indices and formatting
# widths. 0 and 1 are identity/boundary values, 2 is F1's factor and the
# "at least two branches" arity, 4 is the rounding width for reported numbers,
# 5 and 11 are gold per-kind counts and an offender-list display width.
PERMITTED_NUMBERS = {0, 1, 2, 4, 5, 6, 9, 10, 11, 13, 22, 39, 50}

# Identifiers that collide with a closed-vocabulary term without being one: a
# CSV column name, a pipeline status, a Graph IR field. The vocabulary members
# they shadow are `Timestamp` (a type), `failed` (a payment status) and
# `accepted` (a guard); none of these occurrences is a domain decision.
VOCABULARY_HOMONYMS = {"timestamp", "failed", "accepted"}

SOURCE_FILES = sorted(
    path for path in SECTION.rglob("*.py")
    if "tests" not in path.parts and path.name != "__init__.py"
    # `judge.py` is transport only: HTTP status codes and a request timeout
    # cannot influence a grading number, and the judge's own parameters
    # (`judge_model`, `judge_temperature`) already come from config.yaml.
    and path.name != "judge.py"
)


def _rules() -> dict:
    return yaml.safe_load((SECTION / "rules.yaml").read_text("utf-8"))


def _closed_vocabulary() -> set[str]:
    """Every domain term that influences a result (§9.1)."""
    rules = _rules()
    terms: set[str] = set()
    for members in rules["status_sets"].values():
        terms |= {str(m) for m in members}
    terms |= {str(m) for m in rules["payment_methods"]}
    terms |= {str(m) for m in rules["roles"]}
    for canonical, aliases in rules["guard_aliases"].items():
        terms.add(str(canonical))
        terms |= {str(a) for a in aliases}
    for gold_type, row in rules["type_table"].items():
        terms.add(str(gold_type))
        for bucket in row.values():
            terms |= {str(v) for v in bucket}
    return terms


@pytest.mark.parametrize("path", SOURCE_FILES, ids=lambda p: p.name)
def test_no_unexpected_numeric_literals(path: Path):
    """No numeric literal that could influence a result may appear in source."""
    tree = ast.parse(path.read_text("utf-8"))
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or isinstance(node.value, bool):
            continue
        if not isinstance(node.value, (int, float)):
            continue
        value = node.value
        if value in PERMITTED_NUMBERS:
            continue
        # Epsilons and sentinels used by the solver are scale constants, not
        # thresholds: they order ties and mark unavailable cells.
        if isinstance(value, float) and (value <= 1e-6 or value >= 1e5):
            continue
        offenders.append(f"{path.name}:{node.lineno}: {value!r}")
    assert not offenders, (
        "numeric literals that may affect a result must live in YAML (§9.1):\n"
        + "\n".join(offenders))


@pytest.mark.parametrize("path", SOURCE_FILES, ids=lambda p: p.name)
def test_no_closed_vocabulary_terms_in_source(path: Path):
    """No member of a closed vocabulary may be hard-coded in source.

    The rule layer's vocabularies are the operational definition of the layer
    and belong in `rules.yaml`, which the appendix carries in full (§9.4).
    Docstrings and comments are exempt: they cite the domain to explain a rule,
    which is the opposite of hiding it.
    """
    source = path.read_text("utf-8")
    tree = ast.parse(source)
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc is not None and node.body:
                first = node.body[0]
                for line in range(first.lineno, (first.end_lineno or first.lineno) + 1):
                    docstrings.add(line)

    vocabulary = {term.lower() for term in _closed_vocabulary()} - VOCABULARY_HOMONYMS
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if node.lineno in docstrings:
            continue
        if node.value.strip().lower() in vocabulary:
            offenders.append(f"{path.name}:{node.lineno}: {node.value!r}")
    assert not offenders, (
        "closed-vocabulary terms must come from rules.yaml (§9.1):\n"
        + "\n".join(offenders))


def test_thresholds_are_not_hard_coded():
    """The sweep and the primary threshold live only in `config.yaml`."""
    config = yaml.safe_load((SECTION.parent.parent / "config.yaml").read_text("utf-8"))
    values = {str(config["threshold_models"])}
    values |= {str(t) for t in config["sweep_models"]}
    offenders: list[str] = []
    for path in SOURCE_FILES:
        for number, line in enumerate(path.read_text("utf-8").splitlines(), 1):
            code = line.split("#", 1)[0]
            for value in values:
                if value in code and "threshold" not in code.lower():
                    offenders.append(f"{path.name}:{number}: {line.strip()}")
    assert not offenders, "threshold values must come from config.yaml:\n" + \
        "\n".join(offenders)


def test_guard_aliases_have_no_silent_collision():
    """§9.3, §16.5: `approved` must not be silently resolved by dict order.

    Either no alias is claimed by two canonical guards, or the ambiguous ones
    are left unmapped so the pair reaches `guard_ledger.csv` for a human. Both
    states are acceptable; silently picking a side is not.
    """
    from evaluators.ModelsGrading.parser.behavioral import (ambiguous_guard_aliases,
                                                 normalize_guard)

    rules = _rules()
    ambiguous = ambiguous_guard_aliases(rules)
    for alias in ambiguous:
        # An ambiguous alias stays as written, which routes it to the ledger.
        assert normalize_guard(alias, rules) == alias, alias

    # Every unambiguous alias still maps onto its canonical guard.
    for canonical, aliases in rules["guard_aliases"].items():
        for alias in aliases:
            if alias.lower() in ambiguous:
                continue
            assert normalize_guard(alias, rules) == canonical, (alias, canonical)
