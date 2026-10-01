"""Ontology lookup shared by the Stage 1 analysis modules.

The ontology (``materials/M2-orderman-ontology.yaml`` v1.1) is the only source
of truth for what a term *means*. This module turns it into a lookup index and
answers one question: given a surface form, which canonical concept is it?

Matching rules, as specified for metric 8:

* longest alias first, so ``Payment provider service`` wins over ``Payment``;
* case-insensitive, applied after Stage 1 normalization has already folded
  case, split identifiers and stripped articles;
* lookup only. A term that is not in the ontology is **not** added to it and is
  not guessed at - the caller records it as a gap instead.

The ontology is opened read-only and never modified.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

from .config import Stage1ConfigError, sha256_of

__all__ = [
    "KIND_ACTOR",
    "KIND_ATTRIBUTE",
    "KIND_ENTITY",
    "Concept",
    "Ontology",
    "canonical_key",
    "load_ontology",
]

# The three concept kinds the consistency rules look up. Deliberately narrow:
# action verbs and quality attributes are not resolved here because no rule in
# CM-01..CM-05 matches against them.
KIND_ENTITY = "entity"
KIND_ATTRIBUTE = "attribute"
KIND_ACTOR = "actor"

# Separators that identifier-style names use. Stage 1 already splits camelCase
# for the columns it normalizes, but raw columns (``swimlane``, ``owner_class``)
# reach us unsplit, so the key form has to be robust on its own.
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def canonical_key(text: str) -> str:
    """Fold a surface form to the key used for ontology comparison.

    Splits camelCase/PascalCase, lowercases, and reduces every run of
    non-alphanumeric characters to a single space. ``PaymentGateway``,
    ``payment_gateway`` and ``Payment Gateway`` all key to ``payment gateway``,
    so a diagram's identifier style never changes the verdict.

    Args:
        text: Any surface form.

    Returns:
        The comparison key, possibly the empty string.
    """
    if not text:
        return ""
    spaced = _CAMEL_BOUNDARY.sub(" ", str(text))
    lowered = spaced.lower()
    return _NON_ALNUM.sub(" ", lowered).strip()


@dataclass(frozen=True)
class Concept:
    """One resolved ontology concept.

    Attributes:
        canonical: The ontology's canonical name, in its original spelling.
        kind: One of :data:`KIND_ENTITY`, :data:`KIND_ATTRIBUTE`,
            :data:`KIND_ACTOR`.
        matched_alias: The surface form that produced the match, as written in
            the ontology (equal to ``canonical`` on a direct hit).
        owner: For an attribute, the entity that declares it; otherwise None.
    """

    canonical: str
    kind: str
    matched_alias: str
    owner: str | None = None

    @property
    def identity(self) -> str:
        """A stable identity for CM-05, distinguishing kinds that share a name.

        ``Customer`` exists as both an entity and an actor; they are the same
        concept for consistency purposes, so entity and actor share an identity
        namespace while attributes stay separate (an attribute ``name`` must not
        collide with a class called ``Name``).
        """
        if self.kind == KIND_ATTRIBUTE:
            return f"{KIND_ATTRIBUTE}:{self.owner}.{self.canonical}"
        return f"concept:{canonical_key(self.canonical)}"


class Ontology:
    """An indexed, read-only view of the orderman ontology.

    The index maps a :func:`canonical_key` to a :class:`Concept`. Aliases are
    registered alongside canonical names; when two concepts claim the same
    surface form, the canonical name wins and the longer alias wins over the
    shorter, which is what "longest alias first" means once keys are exact.
    """

    def __init__(self, data: Mapping[str, Any], path: Path) -> None:
        self.path = path
        self.version = str(data.get("version", ""))
        self._index: dict[str, Concept] = {}
        self._states: dict[str, str] = {}
        self._legal_transitions: frozenset[tuple[str, str]] = frozenset()
        self._transition_verbs: tuple[str, ...] = ()
        self._build(data)

    # -- construction ----------------------------------------------------

    def _register(self, key_source: str, concept: Concept, *, is_canonical: bool) -> None:
        """Add one surface form to the index, resolving collisions by rank."""
        key = canonical_key(key_source)
        if not key:
            return
        existing = self._index.get(key)
        if existing is None:
            self._index[key] = concept
            return
        # Rank, highest first:
        #   1. kind - an entity or actor outranks an attribute. "Carrier" is a
        #      class in its own right *and* the name of Shipment.carrier; the
        #      class is the more specific answer, and without this the
        #      attribute (registered later) would silently shadow it.
        #   2. canonical name over alias.
        #   3. the longer surface form.
        # Ties keep the first registration, which is the ontology's own
        # declaration order, so the index is deterministic.
        def rank(candidate: Concept, surface: str, canonical: bool) -> tuple[int, int, int]:
            kind_rank = 0 if candidate.kind == KIND_ATTRIBUTE else 1
            return (kind_rank, 1 if canonical else 0, len(surface))

        existing_is_canonical = canonical_key(existing.canonical) == key
        if rank(concept, key_source, is_canonical) > rank(
            existing, existing.matched_alias, existing_is_canonical
        ):
            self._index[key] = concept

    def _build(self, data: Mapping[str, Any]) -> None:
        entities = data.get("entities") or {}
        if not isinstance(entities, dict):
            raise Stage1ConfigError(
                f"Ontology {self.path}: 'entities' must be a mapping."
            )
        for name, body in entities.items():
            body = body or {}
            concept = Concept(canonical=str(name), kind=KIND_ENTITY, matched_alias=str(name))
            self._register(str(name), concept, is_canonical=True)
            for alias in body.get("aliases") or ():
                self._register(
                    str(alias),
                    Concept(str(name), KIND_ENTITY, str(alias)),
                    is_canonical=False,
                )
            for attribute in body.get("attributes") or ():
                attr = Concept(
                    canonical=str(attribute),
                    kind=KIND_ATTRIBUTE,
                    matched_alias=str(attribute),
                    owner=str(name),
                )
                self._register(str(attribute), attr, is_canonical=True)

        actors = data.get("actors") or {}
        if not isinstance(actors, dict):
            raise Stage1ConfigError(f"Ontology {self.path}: 'actors' must be a mapping.")
        for name, body in actors.items():
            body = body or {}
            concept = Concept(canonical=str(name), kind=KIND_ACTOR, matched_alias=str(name))
            self._register(str(name), concept, is_canonical=True)
            for alias in body.get("aliases") or ():
                self._register(
                    str(alias),
                    Concept(str(name), KIND_ACTOR, str(alias)),
                    is_canonical=False,
                )

        states = data.get("states") or {}
        if not isinstance(states, dict):
            raise Stage1ConfigError(f"Ontology {self.path}: 'states' must be a mapping.")
        lifecycle = (states.get("order_lifecycle") or {}).get("canonical_sequence") or ()
        exceptions = (states.get("order_exceptions") or {}).get("canonical") or ()
        for state in (*lifecycle, *exceptions):
            self._states[canonical_key(state)] = str(state)
        for canonical, aliases in (states.get("state_aliases") or {}).items():
            self._states.setdefault(canonical_key(canonical), str(canonical))
            for alias in aliases or ():
                self._states[canonical_key(alias)] = str(canonical)

        transitions: set[tuple[str, str]] = set()
        raw_transitions = states.get("legal_transitions") or ()
        for pair in raw_transitions:
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                raise Stage1ConfigError(
                    f"Ontology {self.path}: every legal_transitions entry must be "
                    f"a [from, to] pair; got {pair!r}."
                )
            transitions.add((self.resolve_state(pair[0]) or str(pair[0]),
                             self.resolve_state(pair[1]) or str(pair[1])))
        self._legal_transitions = frozenset(transitions)

        verbs = (data.get("action_verbs") or {}).get("transition") or ()
        # Longest first so "update the order to" is tried before "update".
        self._transition_verbs = tuple(
            sorted((str(v) for v in verbs), key=len, reverse=True)
        )

    # -- lookup ----------------------------------------------------------

    def resolve(self, text: str, kinds: Iterable[str] | None = None) -> Concept | None:
        """Resolve a surface form to a concept, or None when unknown.

        Args:
            text: The surface form, already Stage 1-normalized where available.
            kinds: Restrict the answer to these kinds. None accepts any.

        Returns:
            The matching :class:`Concept`, or None if the ontology does not
            know this term. Never invents a concept.
        """
        concept = self._index.get(canonical_key(text))
        if concept is None:
            return None
        if kinds is not None and concept.kind not in set(kinds):
            return None
        return concept

    def resolve_state(self, text: str) -> str | None:
        """Resolve a state name or alias to its canonical state name."""
        return self._states.get(canonical_key(text))

    @property
    def states(self) -> tuple[str, ...]:
        """Every canonical state name, sorted for deterministic output."""
        return tuple(sorted(set(self._states.values())))

    @property
    def legal_transitions(self) -> frozenset[tuple[str, str]]:
        """The ontology's ``states.legal_transitions`` as canonical pairs."""
        return self._legal_transitions

    @property
    def transition_verbs(self) -> tuple[str, ...]:
        """``action_verbs.transition`` surface forms, longest first."""
        return self._transition_verbs

    def sha256(self) -> str:
        """SHA-256 of the ontology file, recorded in every output."""
        return sha256_of(self.path)


def _load_ontology_uncached(path: Path) -> Ontology:
    if not path.is_file():
        raise Stage1ConfigError(f"Ontology file not found: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise Stage1ConfigError(f"Cannot parse ontology {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise Stage1ConfigError(f"Ontology {path} must contain a YAML mapping.")
    return Ontology(data, path)


@lru_cache(maxsize=4)
def _load_ontology_cached(resolved: str, mtime: float) -> Ontology:
    return _load_ontology_uncached(Path(resolved))


def load_ontology(path: Path | str) -> Ontology:
    """Load and index the ontology, cached per (path, mtime).

    Args:
        path: The ontology YAML. Opened read-only.

    Returns:
        The indexed :class:`Ontology`.

    Raises:
        Stage1ConfigError: If the file is missing, unparsable, or malformed.
    """
    resolved = Path(path).resolve()
    if not resolved.is_file():
        raise Stage1ConfigError(f"Ontology file not found: {resolved}")
    return _load_ontology_cached(str(resolved), resolved.stat().st_mtime)
