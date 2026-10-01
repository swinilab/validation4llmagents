"""Stage 1 - text normalization for the SRS-evaluation matching cascade.

Stage 1 turns a raw string into one canonical form so that Stage 2 (ontology frame match)
and Stage 3 (embedding cosine) compare like with like. Stage 1 never decides whether two
items match, and it does no Stage 2/Stage 3 work: no actor stripping, no frame extraction,
no alias lookup, no synonym mapping, no embeddings.

Pipeline order (the order is part of the contract):

1. negation detection on the raw sentence
2. lowercase
3. identifier splitting (camelCase / PascalCase / snake_case)
4. modal removal
5. article / determiner removal, auxiliary removal
6. verb lemmatization (participial modifiers keep their surface form)
7. state protection (ontology states used *as states* keep their surface form)
8. negation scope resolution on the dependency parse

Negation cues are never deleted from ``normalized`` (changed in 1.1.0): the
words carry meaning Stage 3 must see. Scope is reported separately, so a downstream
stage can tell "shall not store X" from "store X only while it has not been
marked".

Everything is deterministic and offline: one spaCy pipeline, no network, no
randomness.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Sequence

import yaml

from .config import Stage1Config, Stage1ConfigError, load_config

STAGE1_VERSION = "1.2.0"

__all__ = [
    "STAGE1_VERSION",
    "NEGATION_CUES",
    "NON_NEGATING_PHRASES",
    "Normalized",
    "StateVocabulary",
    "load_state_vocabulary",
    "normalize",
    "normalize_label",
]

# Re-exported so callers can inspect the default list without importing config.
from .config import NON_NEGATING_PHRASES  # noqa: E402  (placed after STAGE1_VERSION)

# --------------------------------------------------------------------------
# Negation
# --------------------------------------------------------------------------

# Surface cues, matched on the raw sentence (step 1) before any token is
# removed. Detection stays sentence-level; *scope* is decided afterwards from
# the dependency parse (see :func:`_negation_scope`). "only if", "halts" and
# "fails" are intentionally absent - they are conditions/verbs, not negation.
NEGATION_CUES: tuple[str, ...] = (
    "cannot",
    "n't",
    "not",
    "never",
    "none",
    "without",
    "nor",
    "no",
)

# ``no`` is a cue only as a determiner, so it needs a word-boundary match that
# excludes "no." in abbreviations; the others are plain word matches.
_CUE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("cannot", re.compile(r"\bcannot\b", re.IGNORECASE)),
    ("n't", re.compile(r"\w+(n['’]t)\b", re.IGNORECASE)),
    ("not", re.compile(r"\bnot\b", re.IGNORECASE)),
    ("never", re.compile(r"\bnever\b", re.IGNORECASE)),
    ("none", re.compile(r"\bnone\b", re.IGNORECASE)),
    ("without", re.compile(r"\bwithout\b", re.IGNORECASE)),
    ("nor", re.compile(r"\bnor\b", re.IGNORECASE)),
    ("no", re.compile(r"\bno\b(?!\.)", re.IGNORECASE)),
)

# Every negation word Stage 1 recognises in the *token stream*. None of these is ever
# dropped from ``normalized`` (1.1.0). ``n't`` is expanded to ``not`` so that
# "doesn't store" and "does not store" share one token sequence.
_NEGATION_WORDS: frozenset[str] = frozenset({
    "not",
    "n't",
    "n’t",
    "no",
    "never",
    "cannot",
    "nor",
    "none",
    "without",
})

# Contraction forms spaCy emits for "n't", normalized to ``not``.
_CONTRACTED_NOT: frozenset[str] = frozenset({"n't", "n’t", "nt"})

# Scope values reported in ``negation_scope``.
SCOPE_NONE = "none"
SCOPE_MAIN = "main"
SCOPE_SUBORDINATE = "subordinate"

# Dependency labels that mark a clause as *not* the main clause. A cue whose
# governing verb sits under one of these is in a condition, relative clause,
# participial adjunct or complement, so the main requirement stays affirmative.
_SUBORDINATE_DEPS: frozenset[str] = frozenset({
    "advcl",
    "relcl",
    "acl",
    "ccomp",
    "xcomp",
    "pcomp",
    "csubj",
    "csubjpass",
    "prep",
    "pobj",
    "npadvmod",
    "appos",
})

# Auxiliary / modal dependencies: a ``neg`` on one of these belongs to the verb
# it supports, so "shall not store" is a negation of ``store``.
_AUX_DEPS: frozenset[str] = frozenset({"aux", "auxpass"})

# --------------------------------------------------------------------------
# Identifier splitting and token shaping
# --------------------------------------------------------------------------

# PascalCase / camelCase boundaries, including acronym runs ("HTTPServer").
_CAMEL_BOUNDARIES: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?<=[a-z0-9])(?=[A-Z])"),
    re.compile(r"(?<=[A-Z])(?=[A-Z][a-z])"),
)

# A token that may be an identifier: no whitespace, and a letter somewhere.
_IDENTIFIER_CHARS = re.compile(r"^[A-Za-z0-9_]+$")

# Characters kept inside a token: letters, digits, internal hyphen, decimal
# point / thousands comma inside numbers, and a trailing percent sign.
_KEEP_TOKEN = re.compile(r"^[a-z0-9]+(?:[-.,%][a-z0-9]+)*%?$")

_NUMERIC_TAIL = re.compile(r"^[-.,%]+|[-.,]+$")

# Possessive markers dropped in step 4 (straight and curly apostrophe). spaCy
# emits "'s" / "’s" as a separate PART token with dep ``case``; the bare "'"
# after a plural ("customers' orders") is the same marker.
_POSSESSIVE_FORMS: frozenset[str] = frozenset({"'s", "’s", "'", "’", "s'", "’s"})


def _split_identifier(word: str) -> list[str]:
    """Split one whitespace-free identifier into its constituent words.

    ``OrderLine`` -> ``['Order', 'Line']``; ``payment_failed`` ->
    ``['payment', 'failed']``. A word that is not an identifier is returned
    unchanged, so ordinary prose and values such as ``aes-256`` survive.
    """
    if not _IDENTIFIER_CHARS.match(word):
        return [word]
    parts = [p for p in word.split("_") if p]
    if not parts:
        return [word]
    out: list[str] = []
    for part in parts:
        pieces = [part]
        for pattern in _CAMEL_BOUNDARIES:
            pieces = [sub for piece in pieces for sub in pattern.split(piece)]
        out.extend(p for p in pieces if p)
    return out or [word]


def _expand_identifiers(text: str) -> str:
    """Apply identifier splitting to every whitespace-separated word."""
    return " ".join(
        piece for word in text.split() for piece in _split_identifier(word)
    )


# --------------------------------------------------------------------------
# Ontology state vocabulary
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class StateVocabulary:
    """Order states and their aliases, read from the ontology at runtime.

    The ontology distinguishes canonical state names (``order_lifecycle``
    ``canonical_sequence`` plus ``order_exceptions.canonical``) from the alias
    lists under ``state_aliases``. Stage 1 keeps the two apart because the state-use
    rules treat them differently: an alias is a state mention only in the
    explicit ``<alias> state`` form, whereas a canonical name is also
    recognised structurally (see :func:`_is_state_use`).

    Attributes:
        canonical_single: One-word canonical state names (``shipped``).
        canonical_multi: Multi-word canonical names, as token tuples
            (``('payment', 'failed')``).
        alias_single: One-word aliases (``boxed``, ``retrieved``).
        alias_multi: Multi-word aliases, as token tuples
            (``('handed', 'over')``).
        canonical: Every canonical term, space-joined.
        all_terms: Canonical names and aliases together, space-joined.
    """

    canonical_single: frozenset[str]
    canonical_multi: tuple[tuple[str, ...], ...]
    alias_single: frozenset[str]
    alias_multi: tuple[tuple[str, ...], ...]

    @property
    def canonical(self) -> frozenset[str]:
        """Every canonical state term, space-joined."""
        return frozenset(self.canonical_single) | frozenset(
            " ".join(m) for m in self.canonical_multi
        )

    @property
    def all_terms(self) -> frozenset[str]:
        """Canonical names and aliases together, space-joined."""
        aliases = frozenset(self.alias_single) | frozenset(
            " ".join(m) for m in self.alias_multi
        )
        return self.canonical | aliases

    @property
    def single(self) -> frozenset[str]:
        """Every one-word state term, canonical or alias."""
        return frozenset(self.canonical_single) | frozenset(self.alias_single)

    @property
    def multi(self) -> tuple[tuple[str, ...], ...]:
        """Every multi-word state term, longest first."""
        merged = set(self.canonical_multi) | set(self.alias_multi)
        return tuple(sorted(merged, key=lambda m: (-len(m), m)))

    @property
    def max_multi_len(self) -> int:
        """Longest multi-word state, in tokens (0 when there are none)."""
        return max((len(m) for m in self.multi), default=0)

    def is_canonical(self, term: str) -> bool:
        """True when ``term`` (space-joined, lowercase) is a canonical name."""
        return term in self.canonical


def _normalize_state_term(term: Any) -> str:
    """Turn an ontology state term into its normalized word form."""
    return " ".join(_expand_identifiers(str(term).replace("-", "_")).lower().split())


# Ontology keys under ``states`` that hold provenance or structure rather than
# state names: transition pairs (already-collected names) and the requirement
# ids each block was derived from.
_NON_STATE_KEYS: frozenset[str] = frozenset({"legal_transitions", "source_reqs"})


def _collect_terms(node: Any, key: str | None, terms: set[str]) -> None:
    """Collect every string leaf under ``node``, skipping non-state keys."""
    if key in _NON_STATE_KEYS:
        return
    if isinstance(node, str):
        terms.add(node)
    elif isinstance(node, dict):
        for sub_key, value in node.items():
            _collect_terms(value, sub_key, terms)
    elif isinstance(node, (list, tuple)):
        for item in node:
            _collect_terms(item, key, terms)


def _split_canonical_and_aliases(states: Any) -> tuple[set[str], set[str]]:
    """Separate canonical state names from aliases in the ontology block.

    The canonical names are the keys of ``state_aliases`` together with every
    string leaf outside it (the lifecycle sequence and the exception list);
    the aliases are the values of ``state_aliases``. When the ontology has no
    ``state_aliases`` mapping the distinction is unavailable, so every term is
    reported as canonical and the caller is expected to note the limitation.
    """
    canonical: set[str] = set()
    aliases: set[str] = set()
    if not isinstance(states, dict):
        _collect_terms(states, None, canonical)
        return canonical, aliases

    for key, value in states.items():
        if key in _NON_STATE_KEYS:
            continue
        if key == "state_aliases" and isinstance(value, dict):
            for state_name, alias_list in value.items():
                canonical.add(str(state_name))
                _collect_terms(alias_list, key, aliases)
            continue
        _collect_terms(value, key, canonical)
    # A term that is both (an alias listed under its own name) stays canonical.
    aliases -= canonical
    return canonical, aliases


def load_state_vocabulary(ontology_path: Path) -> StateVocabulary:
    """Read order states and aliases from the ontology file.

    The ontology is opened read-only and never written to.

    Raises:
        Stage1ConfigError: If the file is missing or unparsable, or if no state
            terms can be found. Stage 1 fails loudly rather than silently running
            without state protection.
    """
    path = Path(ontology_path)
    if not path.is_file():
        raise Stage1ConfigError(f"Ontology file not found: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise Stage1ConfigError(f"Cannot parse ontology {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise Stage1ConfigError(f"Ontology {path} must contain a YAML mapping.")

    states = data.get("states")
    if not states:
        raise Stage1ConfigError(
            f"Ontology {path} has no 'states' section. Stage 1 needs order states and "
            "aliases to protect state words; refusing to run without them."
        )

    raw_canonical, raw_aliases = _split_canonical_and_aliases(states)
    canonical = {_normalize_state_term(t) for t in raw_canonical} - {""}
    aliases = ({_normalize_state_term(t) for t in raw_aliases} - {""}) - canonical

    if not canonical and not aliases:
        raise Stage1ConfigError(
            f"Ontology {path} 'states' section yielded no state terms. "
            "Refusing to run without state protection."
        )

    def split(terms: set[str]) -> tuple[frozenset[str], tuple[tuple[str, ...], ...]]:
        single = frozenset(t for t in terms if " " not in t)
        multi = tuple(sorted(
            (tuple(t.split()) for t in terms if " " in t),
            key=lambda m: (-len(m), m),
        ))
        return single, multi

    canonical_single, canonical_multi = split(canonical)
    alias_single, alias_multi = split(aliases)
    return StateVocabulary(
        canonical_single=canonical_single,
        canonical_multi=canonical_multi,
        alias_single=alias_single,
        alias_multi=alias_multi,
    )


# --------------------------------------------------------------------------
# spaCy pipeline (loaded once, reused; deterministic)
# --------------------------------------------------------------------------

_NLP_LOCK = threading.Lock()


@lru_cache(maxsize=4)
def _load_nlp(model_name: str):
    """Load and cache a spaCy pipeline by name."""
    try:
        import spacy
    except ImportError as exc:  # pragma: no cover - dependency missing
        raise Stage1ConfigError(
            "spaCy is required by Stage 1. Install it with: "
            "pip install -r pipeline/stage1/requirements.txt"
        ) from exc
    try:
        return spacy.load(model_name)
    except OSError as exc:
        raise Stage1ConfigError(
            f"spaCy model '{model_name}' is not installed. Install it with: "
            "pip install -r pipeline/stage1/requirements.txt"
        ) from exc


@lru_cache(maxsize=4)
def _cached_vocabulary(ontology_path: str, mtime_ns: int) -> StateVocabulary:
    """State vocabulary cached per (path, mtime) so edits are picked up."""
    del mtime_ns  # part of the cache key only
    return load_state_vocabulary(Path(ontology_path))


def _vocabulary_for(cfg: Stage1Config) -> StateVocabulary:
    path = Path(cfg.ontology_path)
    if not path.is_file():
        raise Stage1ConfigError(f"Ontology file not found: {path}")
    return _cached_vocabulary(str(path.resolve()), path.stat().st_mtime_ns)


@lru_cache(maxsize=1)
def _default_config() -> Stage1Config:
    return load_config()


# --------------------------------------------------------------------------
# Result type
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Normalized:
    """The result of normalizing one string.

    Attributes:
        raw: The input string, unchanged (identifiers keep their original form).
        normalized: Single-space-separated normalized tokens. Negation cues are
            always present here (1.1.0).
        has_negation_cue: True when any negation cue appears anywhere in the
            string. This is what ``negated`` meant before 1.1.0.
        main_predicate_negated: True when the negation applies to the main
            predicate of the sentence (see :func:`_negation_scope`).
        negation_scope: ``main``, ``subordinate`` or ``none``.
        negation_cues: The surface cues that matched, in sentence order.
        state_mentions: Ontology state terms used *as states* in this string.
        tokens: Per-token detail: ``text``, ``lemma``, ``pos``, ``kept``, and
            ``reason_removed`` when the token was dropped.
        stage1_version: :data:`STAGE1_VERSION` at the time of the call.
    """

    raw: str
    normalized: str
    has_negation_cue: bool
    main_predicate_negated: bool
    negation_scope: str
    negation_cues: list[str]
    state_mentions: list[str]
    tokens: list[dict]
    stage1_version: str


# --------------------------------------------------------------------------
# Step 1: negation cue detection (surface)
# --------------------------------------------------------------------------


def _masked_for_cues(text: str, non_negating: Sequence[str]) -> str:
    """Blank out non-negating phrases so their cue words do not match.

    "no more than 0.1%" states a bound, not a negation, so the ``no`` inside it
    must not fire. Replacing each occurrence with spaces of equal length keeps
    every other offset intact.
    """
    masked = text
    for phrase in non_negating:
        if not phrase:
            continue
        pattern = re.compile(
            r"\b" + r"\s+".join(map(re.escape, phrase.split())) + r"\b", re.IGNORECASE
        )
        masked = pattern.sub(lambda m: " " * len(m.group(0)), masked)
    return masked


def _detect_negation(text: str, cfg: Stage1Config) -> tuple[bool, list[str]]:
    """Find negation cues on the raw sentence.

    Returns ``(has_cue, cues)`` where ``cues`` are the matched surface forms in
    sentence order, de-duplicated. Phrases in ``non_negating_phrases`` are
    masked out first, so "no more than 2 seconds" produces no cue.
    """
    masked = _masked_for_cues(text, cfg.non_negating_phrases)
    hits: list[tuple[int, str]] = []
    for label, pattern in _CUE_PATTERNS:
        for match in pattern.finditer(masked):
            # "n't" reports the contraction suffix, not the whole word.
            group = 1 if label == "n't" else 0
            surface = masked[match.start(group):match.end(group)].lower()
            hits.append((match.start(group), surface))

    cues: list[str] = []
    for _, surface in sorted(hits):
        if surface not in cues:
            cues.append(surface)
    return bool(cues), cues


def _non_negating_token_spans(doc, cfg: Stage1Config) -> set[int]:
    """Token indices covered by a non-negating phrase such as "no more than".

    Scope resolution runs on the parse, so the surface mask of
    :func:`_masked_for_cues` is not enough: the same phrases have to be located
    in token space to stop their ``no`` from being read as a negation.
    """
    covered: set[int] = set()
    lowered = [t.lower_ for t in doc]
    for phrase in cfg.non_negating_phrases:
        words = phrase.split()
        if not words:
            continue
        span = len(words)
        for start in range(len(doc) - span + 1):
            if lowered[start:start + span] == words:
                covered.update(range(start, start + span))
    return covered


# --------------------------------------------------------------------------
# Step 8: negation scope on the dependency parse
# --------------------------------------------------------------------------


def _root_of(doc):
    """The sentence root, or None for an empty/rootless parse."""
    for token in doc:
        if token.dep_ == "ROOT":
            return token
    return None


def _governing_verb(token):
    """Walk up from a cue to the verb whose predicate it negates.

    A ``neg`` dependent attaches directly to its verb; a ``neg`` on an
    auxiliary ("shall not") attaches to the auxiliary's head. A determiner
    ``no`` attaches to a noun, so the noun's head is returned and the caller
    checks whether that noun is a direct object of the root.
    """
    head = token.head
    while head.i != token.i and head.dep_ in _AUX_DEPS:
        token, head = head, head.head
    return head


def _is_main_clause(token, root) -> bool:
    """True when ``token`` is the root itself, or a coordinated main verb.

    A genuinely coordinated main verb ("shall reject X **and inform** Y") is
    still the main clause. A ``conj`` link is only trusted when the conjunct
    carries the root's own verb form (same fine-grained tag), because
    ``en_core_web_sm`` routinely re-attaches a subordinate clause's conjunct to
    the root instead: in "cancel an order only while it is in the placed state
    **and has not been marked** as picked", ``marked`` (VBN, with its own
    auxiliaries) is parsed as a conjunct of the root ``allow`` (VB) although it
    belongs to the ``while`` clause. Requiring the tags to agree keeps that
    misattachment out of the main clause; see the README's known failure modes.
    """
    # spaCy hands out a fresh Token wrapper on every access, so identity must
    # be compared by index, never with ``is``.
    seen: set[int] = set()
    current = token
    while current.i not in seen:
        seen.add(current.i)
        if current.i == root.i:
            return True
        if current.dep_ in _SUBORDINATE_DEPS:
            return False
        if current.dep_ == "conj" and current.tag_ != root.tag_:
            return False
        if current.head.i == current.i:
            return False
        current = current.head
    return False


def _negation_scope(doc, cfg: Stage1Config) -> str:
    """Decide whether a negation cue reaches the sentence's main predicate.

    Returns :data:`SCOPE_MAIN`, :data:`SCOPE_SUBORDINATE` or
    :data:`SCOPE_NONE`. The rule, deliberately narrow:

    ``main`` when either

    * a ``neg`` dependent (``not``, ``n't``, ``never``, or the ``not`` half of
      ``cannot``) attaches to the root verb, or to an auxiliary/modal of the
      root verb - "shall not store", "must never expose"; or
    * the determiner ``no`` modifies a **direct object** of the root verb -
      "shall store no unencrypted primary account numbers".

    ``subordinate`` when a cue was found but sits in a conditional, relative,
    participial, complement or prepositional structure - "only while it has
    not been marked", "an order that is not in the placed state", "modifiable
    by no role", "leaving no order in ...", "without modification to ...".

    Known limits: the decision is only as good as ``en_core_web_sm``'s parse.
    Sentences whose root spaCy misidentifies, and negations expressed lexically
    ("prevent", "deny", "reject", "fail to") rather than by a cue word, are not
    detected. See the README.
    """
    root = _root_of(doc)
    if root is None:
        return SCOPE_NONE

    masked = _non_negating_token_spans(doc, cfg)
    found_cue = False

    for token in doc:
        if token.i in masked:
            continue
        lower = token.lower_
        if lower not in _NEGATION_WORDS:
            continue
        found_cue = True

        if token.dep_ == "neg" or lower in {"never", "cannot"}:
            if _is_main_clause(_governing_verb(token), root):
                return SCOPE_MAIN
            continue

        if lower == "no" and token.pos_ == "DET":
            noun = token.head
            # "shall store no X": the determiner's noun is the root's dobj.
            if noun.dep_ in {"dobj", "obj"} and noun.head.i == root.i:
                return SCOPE_MAIN
            continue

        # ``without``, ``nor``, ``none`` never negate the main predicate on
        # their own: they introduce an adjunct, a coordination or a noun.

    return SCOPE_SUBORDINATE if found_cue else SCOPE_NONE


# --------------------------------------------------------------------------
# Step 7: state mentions
# --------------------------------------------------------------------------

# Nouns whose participial modifier / predicate may name an order state. A state
# word attached to any other noun ("returned items", "reserved inventory") is
# an ordinary participle, not a state mention.
_ORDER_NOUNS: frozenset[str] = frozenset({"order", "orders"})

# Pronouns that may stand for an order in "if it is shipped". Relative pronouns
# are resolved to the noun their clause attaches to before this is consulted.
_ORDER_PRONOUNS: frozenset[str] = frozenset({"it", "they", "them"})

# Relative pronouns whose referent is the noun the relative clause modifies:
# "an order that is not in the placed state or has already been picked".
_RELATIVE_PRONOUNS: frozenset[str] = frozenset({"that", "which", "who"})

# Words that, immediately after a candidate, mark it as a state. This is the
# only rule an alias may satisfy.
_STATE_RIGHT_CUES: frozenset[str] = frozenset({"state", "status", "states", "statuses"})

# Verbs that introduce a state as the object of ``to``/``in``:
# "transition the order to placed", "put the order in cancelled".
_STATE_VERBS: frozenset[str] = frozenset({
    "transition",
    "transitions",
    "transitioned",
    "move",
    "moves",
    "moved",
    "set",
    "sets",
    "put",
    "puts",
    "change",
    "changes",
    "changed",
    "advance",
    "advances",
    "advanced",
    "reach",
    "reaches",
    "reached",
    "return",
    "returns",
})

_SKIPPABLE: frozenset[str] = frozenset({"a", "an", "the", "its", "their", "his", "her"})


def _next_word(doc, index: int) -> Any:
    """The next non-punctuation token after ``index``, or None."""
    cursor = index
    while cursor < len(doc) and doc[cursor].is_punct:
        cursor += 1
    return doc[cursor] if cursor < len(doc) else None


def _prev_word(doc, index: int, *, skip_determiners: bool = True) -> Any:
    """The previous meaningful token before ``index``, or None."""
    cursor = index - 1
    while cursor >= 0 and (
        doc[cursor].is_punct
        or (skip_determiners and doc[cursor].lower_ in _SKIPPABLE)
    ):
        cursor -= 1
    return doc[cursor] if cursor >= 0 else None


def _followed_by_state_word(doc, index: int, span_len: int) -> bool:
    """Rule 1: the span is immediately followed by ``state``/``status``."""
    nxt = _next_word(doc, index + span_len)
    return nxt is not None and nxt.lower_ in _STATE_RIGHT_CUES


def _modifies_order_noun(token) -> bool:
    """Rule 2a: participial modifier of ``order``/``orders``.

    ``a placed order`` / ``shipped orders``. spaCy sometimes hangs the modifier
    off an intervening ``as``/preposition ("marked as picked"); that case is
    handled by :func:`_complement_of_as` instead.
    """
    return token.dep_ == "amod" and token.head.lower_ in _ORDER_NOUNS


def _clause_head(token):
    """The verb that carries ``token``'s subject.

    A conjunct predicate shares the subject of the verb it is coordinated with
    ("an order that **is** not in the placed state or **has been picked**"), so
    ``conj`` links are followed up to the first non-conjunct verb. A copular
    complement's subject sits on the copula, so ``acomp``/``attr``/``oprd``
    step up one level too.
    """
    seen: set[int] = set()
    current = token
    while current.i not in seen and current.dep_ in {"conj", "acomp", "attr", "oprd"}:
        seen.add(current.i)
        if current.head.i == current.i:
            break
        current = current.head
    return current


def _subject_names_order(doc, subject) -> bool:
    """True when ``subject`` denotes an order, directly or as a relative pronoun."""
    if subject.lower_ in _ORDER_NOUNS or subject.lower_ in _ORDER_PRONOUNS:
        return True
    if subject.lower_ not in _RELATIVE_PRONOUNS:
        return False
    # "an order that is ...": the relative clause hangs off the noun it
    # modifies, so the pronoun's antecedent is that clause's head noun.
    clause = subject.head
    while clause.dep_ in {"conj", "acomp", "attr", "oprd"} and clause.head.i != clause.i:
        clause = clause.head
    return clause.dep_ in {"relcl", "acl"} and clause.head.lower_ in _ORDER_NOUNS


def _predicates_order(doc, token) -> bool:
    """Rule 2b: the span is the predicate of ``order``/``it`` as subject.

    ``when an order is placed``, ``if it is shipped``, and - through
    :func:`_clause_head` - ``an order that ... has already been picked``. spaCy
    analyses the first two as a passive participle with the order as
    ``nsubjpass``; the copular reading parsed as ``acomp`` is accepted too.
    """
    clause = _clause_head(token)
    subjects = [
        child
        for child in clause.children
        if child.dep_ in {"nsubj", "nsubjpass"}
    ]
    return any(_subject_names_order(doc, subject) for subject in subjects)


def _complement_of_as(doc, index: int) -> bool:
    """Rule 2c: the complement after ``as`` in ``mark ... order as picked``."""
    prev = _prev_word(doc, index)
    return prev is not None and prev.lower_ == "as"


def _object_of_state_preposition(doc, index: int) -> bool:
    """Rule 2d: object of ``to``/``in`` after ``order`` or a state verb.

    ``transition the order to placed``, ``the order is in cancelled``. The
    preposition must be reached directly (articles are skipped), and the word
    before it must be ``order``/``orders`` or one of :data:`_STATE_VERBS`.
    """
    prep = _prev_word(doc, index)
    if prep is None or prep.lower_ not in {"to", "in", "into"}:
        return False
    anchor = _prev_word(doc, prep.i)
    if anchor is None:
        return False
    return anchor.lower_ in _ORDER_NOUNS or anchor.lower_ in _STATE_VERBS


def _is_state_use(doc, index: int, span_len: int, *, canonical: bool) -> bool:
    """Decide whether the tokens at ``index`` are a *state* mention.

    Rule 1 - ``<term> state`` - accepts aliases as well as canonical names.
    Rules 2a-2d apply to canonical names only, because an alias used bare is
    far more often an ordinary participle ("returned items", "reserved
    inventory", "retrieved order") than a state.
    """
    if _followed_by_state_word(doc, index, span_len):
        return True
    if not canonical:
        return False

    last = doc[index + span_len - 1]
    return (
        _modifies_order_noun(last)
        or _predicates_order(doc, last)
        or _complement_of_as(doc, index)
        or _object_of_state_preposition(doc, index)
    )


def _find_state_spans(doc, vocab: StateVocabulary) -> dict[int, tuple[int, str]]:
    """Map each state span's start index to ``(length, surface form)``.

    Longer spans are matched first so ``payment failed`` wins over ``failed``.
    A span is recorded only when :func:`_is_state_use` accepts it; a state word
    used as an ordinary verb or participle is left to normal token handling.
    """
    spans: dict[int, tuple[int, str]] = {}
    claimed: set[int] = set()
    lowered = [t.lower_ for t in doc]

    multi = vocab.multi
    canonical_multi = set(vocab.canonical_multi)
    for length in sorted({len(c) for c in multi}, reverse=True):
        for start in range(len(doc) - length + 1):
            if any(i in claimed for i in range(start, start + length)):
                continue
            window = tuple(lowered[start:start + length])
            if window not in multi:
                continue
            if _is_state_use(doc, start, length, canonical=window in canonical_multi):
                surface = " ".join(doc[i].text for i in range(start, start + length))
                spans[start] = (length, surface)
                claimed.update(range(start, start + length))

    singles = vocab.single
    for index, token in enumerate(doc):
        if index in claimed or token.lower_ not in singles:
            continue
        if _is_state_use(
            doc, index, 1, canonical=token.lower_ in vocab.canonical_single
        ):
            spans[index] = (1, token.text)
            claimed.add(index)
    return spans


# --------------------------------------------------------------------------
# Token shaping
# --------------------------------------------------------------------------


def _join_hyphen_and_percent(doc) -> dict[int, tuple[int, str]]:
    """Group tokens that must stay one word: ``aes-256``, ``30-day``, ``0.1%``.

    spaCy splits on hyphens and separates a trailing ``%``. This returns a map
    from start index to ``(length, joined surface)`` for each such group.
    """
    groups: dict[int, tuple[int, str]] = {}
    index = 0
    while index < len(doc):
        end = index
        pieces = [doc[index].text]
        # Absorb ``- word`` pairs written without spaces (30-day, aes-256).
        while (
            end + 2 < len(doc)
            and doc[end + 1].text == "-"
            and not doc[end + 1].whitespace_
            and not doc[end].whitespace_
            and doc[end + 2].text.isalnum()
        ):
            pieces.extend(["-", doc[end + 2].text])
            end += 2
        # Absorb an immediately following percent sign (0.1%).
        if end + 1 < len(doc) and doc[end + 1].text == "%" and not doc[end].whitespace_:
            pieces.append("%")
            end += 1
        if end > index:
            groups[index] = (end - index + 1, "".join(pieces))
            index = end + 1
        else:
            index += 1
    return groups


def _clean_surface(text: str) -> str:
    """Strip punctuation Stage 1 does not keep, preserving internal hyphens/decimals."""
    lowered = text.lower()
    # Drop anything outside the kept character set.
    kept = re.sub(r"[^a-z0-9\-.,%]+", "", lowered)
    if _KEEP_TOKEN.match(kept):
        return kept
    # Trim stray leading/trailing separators (", 2,000." -> "2,000").
    trimmed = _NUMERIC_TAIL.sub("", kept)
    return trimmed if _KEEP_TOKEN.match(trimmed) else re.sub(r"[^a-z0-9\-]+", "", trimmed)


def _is_possessive(token) -> bool:
    """True for the possessive marker ``'s`` / ``’s`` (and the bare plural one).

    spaCy tags it ``PART``/``POS`` with dependency ``case``. Testing the tag
    rather than the surface keeps a genuine contraction ("it's") out of scope -
    that one is tagged ``AUX``.
    """
    return token.tag_ == "POS" or (
        token.dep_ == "case" and token.lower_ in _POSSESSIVE_FORMS
    )


def _is_root_copula(token, root) -> bool:
    """True when ``token`` is the sentence's own copula (``is out of stock``).

    A copula that *is* the root carries the predication and stays; an auxiliary
    supporting another verb ("have been marked") does not.
    """
    return root is not None and token.i == root.i and token.pos_ == "AUX"


def _lemma_for(token, cfg: Stage1Config) -> str:
    """Lemma used in ``normalized`` for a non-state token.

    Verbs and auxiliaries are lemmatized **unless** they are participial
    modifiers (``amod``): ``the acting role`` and ``the resulting state`` are
    adjectives in everything but spaCy's coarse tag, and lemmatizing them to
    ``act`` / ``result`` destroys the phrase. Nouns keep their surface form
    unless ``singularize_nouns`` is on; everything else is untouched, so
    numbers and adjectives survive verbatim.
    """
    if token.pos_ in {"VERB", "AUX"} and token.dep_ != "amod":
        return token.lemma_.lower()
    if cfg.singularize_nouns and token.pos_ in {"NOUN", "PROPN"}:
        return token.lemma_.lower()
    return token.lower_


# --------------------------------------------------------------------------
# Core
# --------------------------------------------------------------------------


def _normalize_impl(
    text: str,
    cfg: Stage1Config,
    *,
    is_label: bool,
) -> Normalized:
    """Shared implementation of :func:`normalize` and :func:`normalize_label`."""
    if text is None:
        text = ""
    raw = str(text)

    # Step 1: negation cues, on the raw sentence, before anything is removed.
    has_cue, cues = _detect_negation(raw, cfg)

    # Steps 2-3: identifier splitting then lowercase. Splitting runs on the
    # original casing because camelCase boundaries are exactly the case
    # boundaries; ``raw`` keeps the unsplit identifier for the caller.
    staged = _expand_identifiers(raw) if cfg.split_identifiers else raw
    staged = " ".join(staged.lower().split())

    if not staged:
        return Normalized(
            raw=raw,
            normalized="",
            has_negation_cue=has_cue,
            main_predicate_negated=False,
            negation_scope=SCOPE_NONE,
            negation_cues=cues,
            state_mentions=[],
            tokens=[],
            stage1_version=STAGE1_VERSION,
        )

    with _NLP_LOCK:
        doc = _load_nlp(cfg.spacy_model)(staged)

    vocab = _vocabulary_for(cfg)
    state_spans = _find_state_spans(doc, vocab)
    joined = _join_hyphen_and_percent(doc)
    root = _root_of(doc)

    # Step 8: scope. Only computed when a cue was seen on the raw sentence, so
    # detection order stays "surface first, parse second".
    scope = _negation_scope(doc, cfg) if has_cue else SCOPE_NONE

    tokens: list[dict] = []
    out: list[str] = []
    state_mentions: list[str] = []

    index = 0
    first_kept_decided = False
    while index < len(doc):
        token = doc[index]

        # A multi-token group that must stay one word (aes-256, 0.1%).
        if index in joined and index not in state_spans:
            length, surface = joined[index]
            cleaned = _clean_surface(surface)
            keep = bool(cleaned)
            tokens.append({
                "text": surface,
                "lemma": cleaned or surface,
                "pos": token.pos_,
                "kept": keep,
                **({} if keep else {"reason_removed": "punctuation"}),
            })
            if keep:
                out.append(cleaned)
                first_kept_decided = True
            index += length
            continue

        # Step 7: a state span keeps its surface form and is reported.
        if index in state_spans:
            length, surface = state_spans[index]
            cleaned = " ".join(filter(None, (_clean_surface(p) for p in surface.split())))
            if cleaned:
                out.append(cleaned)
                state_mentions.append(cleaned)
                first_kept_decided = True
            for offset in range(length):
                sub = doc[index + offset]
                tokens.append({
                    "text": sub.text,
                    "lemma": sub.lower_,
                    "pos": sub.pos_,
                    "kept": bool(cleaned),
                    "state": True,
                })
            index += length
            continue

        surface = token.lower_
        # ``normalize_label`` never drops the first meaningful token, so a class
        # named "Will" or an action labelled "Can" survives.
        protected_first = is_label and not first_kept_decided and not token.is_punct

        # A negation word is never removed (1.1.0): the cue carries meaning Stage 3
        # must see, and its scope is reported separately.
        is_negation = surface in _NEGATION_WORDS

        reason: str | None = None
        if token.is_space:
            reason = "whitespace"
        elif _is_possessive(token):
            reason = "possessive"
        elif token.is_punct:
            reason = "punctuation"
        elif is_negation:
            reason = None
        elif not protected_first and surface in cfg.modals and token.pos_ in {"AUX", "VERB"}:
            reason = "modal"
        elif not protected_first and surface in cfg.articles and token.pos_ == "DET":
            reason = "article"
        elif (
            not protected_first
            and token.dep_ in _AUX_DEPS
            and not _is_root_copula(token, root)
        ):
            reason = "auxiliary"

        if is_negation:
            # "n't" is written out so the contraction and the full form agree.
            lemma = "not" if surface in _CONTRACTED_NOT else surface
        else:
            lemma = _lemma_for(token, cfg)
        cleaned = _clean_surface(lemma) if reason is None else ""
        if reason is None and not cleaned:
            reason = "punctuation"

        entry: dict[str, Any] = {
            "text": token.text,
            "lemma": lemma,
            "pos": token.pos_,
            "kept": reason is None,
        }
        if reason is not None:
            entry["reason_removed"] = reason
        tokens.append(entry)

        if reason is None:
            out.append(cleaned)
            first_kept_decided = True
        index += 1

    return Normalized(
        raw=raw,
        normalized=" ".join(out),
        has_negation_cue=has_cue,
        main_predicate_negated=scope == SCOPE_MAIN,
        negation_scope=scope,
        negation_cues=cues,
        state_mentions=state_mentions,
        tokens=tokens,
        stage1_version=STAGE1_VERSION,
    )


def normalize(text: str, cfg: Stage1Config | None = None) -> Normalized:
    """Normalize a full sentence or requirement statement.

    Args:
        text: The raw string. ``None`` is treated as empty.
        cfg: Effective config; the repository ``config.yaml`` is used when None.

    Returns:
        A :class:`Normalized` result. Stage 1 makes no matching decision.
    """
    return _normalize_impl(text, cfg or _default_config(), is_label=False)


def normalize_label(label: str, cfg: Stage1Config | None = None) -> Normalized:
    """Normalize a short diagram label or identifier.

    Differs from :func:`normalize` in one way: the first meaningful token is
    never removed, so a label such as ``Can`` or ``The Order`` keeps its head
    word. No actor stripping is attempted - that belongs to Stage 2. Guard brackets
    (``[stock available]``) are dropped as punctuation.
    """
    return _normalize_impl(label, cfg or _default_config(), is_label=True)


def library_versions() -> dict[str, str]:
    """Versions of the libraries whose behavior affects the output."""
    import platform

    versions = {"python": platform.python_version(), "stage1": STAGE1_VERSION}
    try:
        import spacy

        versions["spacy"] = spacy.__version__
    except ImportError:  # pragma: no cover
        versions["spacy"] = "not installed"
    try:
        versions["pyyaml"] = yaml.__version__
    except AttributeError:  # pragma: no cover
        pass
    return versions


def model_version(cfg: Stage1Config) -> str:
    """Version of the loaded spaCy pipeline, for the metadata sidecar."""
    try:
        return str(_load_nlp(cfg.spacy_model).meta.get("version", "unknown"))
    except Stage1ConfigError:  # pragma: no cover
        return "unknown"


def iter_normalized(texts: Iterable[str], cfg: Stage1Config | None = None) -> list[Normalized]:
    """Normalize many strings with one config, in order."""
    effective = cfg or _default_config()
    return [_normalize_impl(t, effective, is_label=False) for t in texts]
