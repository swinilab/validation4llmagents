"""Stage 1 - metric 8 (Consistency), rules CM-01..CM-05.

Reads already-flattened CSVs only. It never parses ``.puml``, markdown or
prose: by the time a document reaches this module it has been flattened to the
class-elements, activity-elements and requirements CSVs, and Stage 1 has added
the ``__normalized`` columns.

Scoring is **per instance**, not per rule. Each rule yields zero or more
instances, each of which passes or fails, and::

    consistency = 1 - failed / total

With no instances at all the metric is ``null`` with a ``no_instances`` flag
rather than 1.0, because "nothing was checked" is not "everything was right".

Matching goes through the ontology only (longest alias first, case-insensitive
after normalization). A term the ontology does not know is never added to it;
it is recorded in ``<run_id>__ontology_gaps.csv`` so it can be reviewed later.

This module is gold-agnostic: ``run_id`` is an opaque label, no input is
special-cased, and no rule is relaxed for any particular source.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from .config import (
    REPO_ROOT,
    Stage1Config,
    Stage1ConfigError,
    load_config,
    resolve_output_path,
    sha256_of,
)
from .normalize import STAGE1_VERSION
from .ontology import (
    KIND_ACTOR,
    KIND_ATTRIBUTE,
    KIND_ENTITY,
    Concept,
    Ontology,
    canonical_key,
    load_ontology,
)

__all__ = [
    "CONSISTENCY_VERSION",
    "RULES",
    "ConsistencyError",
    "Instance",
    "MissingColumnError",
    "run_consistency",
    "main",
]

CONSISTENCY_VERSION = "1.0.0"

EXIT_OK = 0
EXIT_USAGE = 2

STATUS_PASS = "pass"
STATUS_FAIL = "fail"

# Rule catalogue. CM-06 (multiplicity) is deliberately not implemented.
RULES: dict[str, str] = {
    "CM-01": "Every activity swimlane resolves to a class or actor in the ontology.",
    "CM-02": "Every action object resolves to a class or attribute in the ontology.",
    "CM-03": "Every class is mentioned in at least one requirement statement.",
    "CM-04": "Every stated order-state transition is in the ontology's legal_transitions.",
    "CM-05": "Each concept uses one canonical name across requirements, class and activity.",
}

# Source labels used in the instance rows and the gaps CSV.
SRC_CLASS = "class-elements"
SRC_ACTIVITY = "activity-elements"
SRC_REQUIREMENTS = "requirements"


class ConsistencyError(RuntimeError):
    """Raised on an input problem that prevents the metric from being computed."""


class MissingColumnError(ConsistencyError):
    """Raised when a required ``__normalized`` column is absent.

    Separate from the generic error so the CLI can name the prerequisite
    precisely: these columns come from Stage 1 normalize, which this module
    does not modify.
    """


@dataclass(frozen=True)
class Instance:
    """One checked instance of one rule."""

    rule_id: str
    instance: str
    status: str
    detail: str

    @property
    def failed(self) -> bool:
        return self.status == STATUS_FAIL


@dataclass
class Gap:
    """An unresolved term, counted per (term, source, rule)."""

    term: str
    source_file: str
    rule_id: str
    count: int = 0


class _GapLog:
    """Collects unknown terms without ever modifying the ontology."""

    def __init__(self) -> None:
        self._gaps: dict[tuple[str, str, str], Gap] = {}

    def add(self, term: str, source_file: str, rule_id: str) -> None:
        term = (term or "").strip()
        if not term:
            return
        key = (term, source_file, rule_id)
        gap = self._gaps.get(key)
        if gap is None:
            self._gaps[key] = Gap(term, source_file, rule_id, 1)
        else:
            gap.count += 1

    def rows(self) -> list[dict[str, Any]]:
        """Gap rows in a stable order: term, then source, then rule."""
        return [
            {
                "term": gap.term,
                "source_file": gap.source_file,
                "rule_id": gap.rule_id,
                "count": gap.count,
            }
            for gap in sorted(
                self._gaps.values(), key=lambda g: (g.term.lower(), g.source_file, g.rule_id)
            )
        ]


# --- input handling ------------------------------------------------------


def _read_csv(path: Path, label: str) -> tuple[list[str], list[dict[str, str]]]:
    """Read one flattened CSV read-only."""
    if not path.is_file():
        raise ConsistencyError(f"{label} CSV not found: {path}")
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise ConsistencyError(f"{path} is empty: no CSV header row found.")
            fields = list(reader.fieldnames)
            rows = [
                {k: ("" if v is None else v) for k, v in row.items() if k is not None}
                for row in reader
            ]
    except OSError as exc:
        raise ConsistencyError(f"Cannot read {label} CSV {path}: {exc}") from exc
    return fields, rows


def _require_columns(
    fields: Sequence[str], required: Sequence[str], path: Path, label: str
) -> None:
    """Fail with a precise message when a prerequisite column is absent."""
    missing = [column for column in required if column not in fields]
    if missing:
        raise MissingColumnError(
            f"{path}: the {label} CSV is missing required column(s) "
            f"{', '.join(missing)}. Columns found: {', '.join(fields) or '(none)'}."
        )


def _normalized_or_raw(row: dict[str, str], column: str) -> str:
    """Prefer ``<column>__normalized``, falling back to the raw column.

    Used where the *text* matters (requirement statements), not where an
    identifier is being looked up - see :func:`_lookup_form`.
    """
    value = (row.get(f"{column}__normalized") or "").strip()
    if value:
        return value
    return (row.get(column) or "").strip()


def _lookup_form(row: dict[str, str], column: str) -> str:
    """The surface form to resolve against the ontology.

    Prefers the **raw** column. Stage 1's ``normalize_label`` lemmatizes and
    strips short labels ("ShoppingCart" -> "shop cart"), which is correct for
    embedding comparison but destroys the identifier an ontology lookup needs.
    :func:`canonical_key` does the case and identifier-style folding instead,
    so no normalization is lost - only the lemmatization that would break the
    match. Falls back to the normalized form when the raw column is absent.
    """
    raw = (row.get(column) or "").strip()
    if raw:
        return raw
    return (row.get(f"{column}__normalized") or "").strip()


# --- CM-01 ---------------------------------------------------------------


def _cm01(
    activity_rows: Sequence[dict[str, str]], onto: Ontology, gaps: _GapLog
) -> list[Instance]:
    """Every swimlane resolves to a class or actor. One instance per swimlane element.

    Scoped to rows whose ``element_type`` is ``swimlane`` so each declared lane
    is counted once, rather than once per action that happens to sit in it.
    """
    instances: list[Instance] = []
    for row in activity_rows:
        if (row.get("element_type") or "").strip().lower() != "swimlane":
            continue
        raw = _lookup_form(row, "swimlane")
        element_id = (row.get("element_id") or "").strip()
        if not raw:
            instances.append(
                Instance("CM-01", element_id or "(unnamed swimlane)", STATUS_FAIL,
                         "Swimlane element has an empty swimlane name.")
            )
            continue
        concept = onto.resolve(raw, kinds=(KIND_ENTITY, KIND_ACTOR))
        if concept is None:
            gaps.add(raw, SRC_ACTIVITY, "CM-01")
            instances.append(
                Instance("CM-01", raw, STATUS_FAIL,
                         f"Swimlane '{raw}' matches no ontology class or actor.")
            )
        else:
            instances.append(
                Instance("CM-01", raw, STATUS_PASS,
                         f"Swimlane '{raw}' resolves to {concept.kind} "
                         f"'{concept.canonical}'.")
            )
    return instances


# --- CM-02 ---------------------------------------------------------------


def _cm02(
    activity_rows: Sequence[dict[str, str]], onto: Ontology, gaps: _GapLog
) -> list[Instance]:
    """Every action object resolves to a class or attribute. One instance per action."""
    instances: list[Instance] = []
    for row in activity_rows:
        if (row.get("element_type") or "").strip().lower() != "action":
            continue
        element_id = (row.get("element_id") or "").strip()
        obj = _lookup_form(row, "object")
        if not obj:
            # An action with no object is not an inconsistency; there is
            # nothing to resolve, so no instance is created.
            continue
        concept = onto.resolve(obj, kinds=(KIND_ENTITY, KIND_ATTRIBUTE))
        label = f"{element_id}:{obj}" if element_id else obj
        if concept is None:
            gaps.add(obj, SRC_ACTIVITY, "CM-02")
            instances.append(
                Instance("CM-02", label, STATUS_FAIL,
                         f"Action object '{obj}' matches no ontology class or attribute.")
            )
        else:
            instances.append(
                Instance("CM-02", label, STATUS_PASS,
                         f"Action object '{obj}' resolves to {concept.kind} "
                         f"'{concept.canonical}'.")
            )
    return instances


# --- CM-03 ---------------------------------------------------------------


def _cm03(
    class_rows: Sequence[dict[str, str]],
    requirement_rows: Sequence[dict[str, str]],
    onto: Ontology,
    gaps: _GapLog,
) -> list[Instance]:
    """Every class is mentioned in at least one requirement. One instance per class.

    A class is "mentioned" when its canonical name or any ontology alias for it
    occurs as a whole-word phrase in a normalized requirement statement.
    """
    # Build the searchable corpus once: the normalized statement of each
    # requirement, keyed for whole-phrase matching.
    corpus: list[tuple[str, str]] = []
    for row in requirement_rows:
        req_id = (row.get("gold_req_id") or row.get("req_id") or "").strip()
        text = _normalized_or_raw(row, "statement")
        corpus.append((req_id, canonical_key(text)))

    instances: list[Instance] = []
    for row in class_rows:
        if (row.get("element_type") or "").strip().lower() != "class":
            continue
        # Resolve against the *raw* name. Stage 1's normalize_label lemmatizes
        # and strips ("ShoppingCart" -> "shop cart", "OrderStatus" ->
        # "order status"), which is right for embedding comparison but loses
        # the identifier an ontology lookup needs. canonical_key does the
        # case/underscore folding instead. The normalized form is still the
        # fallback when the raw column is absent.
        name = _lookup_form(row, "canonical_name")
        if not name:
            continue
        concept = onto.resolve(name, kinds=(KIND_ENTITY, KIND_ACTOR))
        if concept is None:
            gaps.add(name, SRC_CLASS, "CM-03")
            # The class is unknown to the ontology, so only its own surface
            # form can be searched for.
            surface_forms = [name]
            canonical_label = name
        else:
            surface_forms = _surface_forms_for(concept, onto)
            canonical_label = concept.canonical

        hit_req = _find_mention(surface_forms, corpus)
        if hit_req is None:
            instances.append(
                Instance("CM-03", canonical_label, STATUS_FAIL,
                         f"Class '{canonical_label}' is not mentioned in any requirement.")
            )
        else:
            instances.append(
                Instance("CM-03", canonical_label, STATUS_PASS,
                         f"Class '{canonical_label}' is mentioned in {hit_req or 'a requirement'}.")
            )
    return instances


def _surface_forms_for(concept: Concept, onto: Ontology) -> list[str]:
    """Canonical name plus every ontology alias that resolves back to it."""
    forms = {concept.canonical}
    for key, candidate in onto._index.items():  # noqa: SLF001 - same package
        if candidate.identity == concept.identity:
            forms.add(candidate.matched_alias)
    # Longest first: the longest alias is the most specific evidence.
    return sorted(forms, key=len, reverse=True)


def _find_mention(surface_forms: Iterable[str], corpus: Sequence[tuple[str, str]]) -> str | None:
    """Return the first requirement id whose text contains any surface form.

    Matching is whole-phrase, and tolerates a regular plural on the final word:
    Stage 1 keeps surface nouns by default (``singularize_nouns: false``), so
    "Each order shall comprise one or more order lines" must still count as a
    mention of the class ``OrderLine``. Only the trailing ``s``/``es`` of the
    last word is treated this way - no general stemming, which would start
    matching unrelated terms.
    """
    patterns: list[re.Pattern[str]] = []
    for form in surface_forms:
        key = canonical_key(form)
        if not key:
            continue
        patterns.append(re.compile(rf"(?<![a-z0-9]){re.escape(key)}(?:e?s)?(?![a-z0-9])"))
    for req_id, text in corpus:
        if not text:
            continue
        for pattern in patterns:
            if pattern.search(text):
                return req_id
    return None


# --- CM-04 ---------------------------------------------------------------

# Transition patterns. CM-04 is deliberately conservative: a requirement that
# merely mentions two states (a guard such as "only while it is in the placed
# state and not marked as picked") states no transition and yields no instance.
# An instance is created only when one of these ordered patterns matches.
#
# ``{verb}`` is replaced by the ontology's action_verbs.transition surface
# forms, longest first, so "update the order to" is tried before "update".
_TRANSITION_PATTERNS: tuple[tuple[str, str], ...] = (
    # "mark a placed order as picked" - the current state sits between the
    # verb and "as", which is the usual English word order for this frame.
    ("mark_as",
     r"\b(?:mark|marks|marked|set|sets|move|moves|advance|advances)\b"
     r"[^.;]{{0,40}}?\b{from_state}\b[^.;]{{0,40}}?\bas\b[^.;]{{0,20}}?\b{to_state}\b"),
    # "<from> order is marked as <to>" - the state precedes the verb.
    ("state_then_mark",
     r"\b{from_state}\b[^.;]{{0,40}}?\b(?:mark|marks|marked)\b"
     r"[^.;]{{0,20}}?\bas\b[^.;]{{0,20}}?\b{to_state}\b"),
    # "from draft to placed" / "from the draft state to the placed state"
    ("from_to", r"\bfrom\b[^.;]{{0,30}}?\b{from_state}\b[^.;]{{0,40}}?\bto\b[^.;]{{0,30}}?\b{to_state}\b"),
    # "transition order to placed" preceded by the current state
    ("verb_to", r"\b{from_state}\b[^.;]{{0,60}}?\b(?:{verbs})\b[^.;]{{0,30}}?\b{to_state}\b"),
)


def _state_surface_forms(onto: Ontology, state: str) -> list[str]:
    """Canonical state name plus its aliases, longest first."""
    forms = {state}
    for key, canonical in onto._states.items():  # noqa: SLF001 - same package
        if canonical == state:
            forms.add(key)
    return sorted(forms, key=len, reverse=True)


def _cm04(
    requirement_rows: Sequence[dict[str, str]], onto: Ontology, gaps: _GapLog
) -> list[Instance]:
    """Every stated transition is legal. One instance per detected transition.

    Only requirements with two or more state mentions are considered, and only
    when a transition pattern actually matches. No pattern match means no
    instance: CM-04 never guesses that a transition was intended.
    """
    instances: list[Instance] = []
    verbs = "|".join(re.escape(v) for v in onto.transition_verbs) or r"transition"

    for row in requirement_rows:
        req_id = (row.get("gold_req_id") or row.get("req_id") or "").strip()
        mentions = [
            m.strip()
            for m in (row.get("statement__state_mentions") or "").split(";")
            if m.strip()
        ]
        if len(mentions) < 2:
            continue
        text = canonical_key(_normalized_or_raw(row, "statement"))
        if not text:
            continue

        canonical_mentions: list[str] = []
        for mention in mentions:
            resolved = onto.resolve_state(mention)
            if resolved is None:
                gaps.add(mention, SRC_REQUIREMENTS, "CM-04")
                continue
            if resolved not in canonical_mentions:
                canonical_mentions.append(resolved)
        if len(canonical_mentions) < 2:
            continue

        # Try every ordered pair; a requirement may state more than one
        # transition. Each detected transition is its own instance.
        seen: set[tuple[str, str]] = set()
        for from_state in canonical_mentions:
            for to_state in canonical_mentions:
                if from_state == to_state or (from_state, to_state) in seen:
                    continue
                if not _matches_transition(text, from_state, to_state, onto, verbs):
                    continue
                seen.add((from_state, to_state))
                legal = (from_state, to_state) in onto.legal_transitions
                label = f"{req_id}:{from_state}->{to_state}" if req_id else f"{from_state}->{to_state}"
                if legal:
                    instances.append(
                        Instance("CM-04", label, STATUS_PASS,
                                 f"Transition {from_state} -> {to_state} is in "
                                 f"legal_transitions.")
                    )
                else:
                    instances.append(
                        Instance("CM-04", label, STATUS_FAIL,
                                 f"Transition {from_state} -> {to_state} is not in "
                                 f"the ontology's legal_transitions.")
                    )
    return instances


def _matches_transition(
    text: str, from_state: str, to_state: str, onto: Ontology, verbs: str
) -> bool:
    """Whether the text states an ordered ``from_state`` -> ``to_state`` move."""
    from_forms = "|".join(re.escape(f) for f in _state_surface_forms(onto, from_state))
    to_forms = "|".join(re.escape(f) for f in _state_surface_forms(onto, to_state))
    for _name, template in _TRANSITION_PATTERNS:
        pattern = template.format(
            from_state=f"(?:{from_forms})",
            to_state=f"(?:{to_forms})",
            verbs=verbs,
        )
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


# --- CM-05 ---------------------------------------------------------------


def _cm05(
    class_rows: Sequence[dict[str, str]],
    activity_rows: Sequence[dict[str, str]],
    requirement_rows: Sequence[dict[str, str]],
    onto: Ontology,
    gaps: _GapLog,
) -> list[Instance]:
    """One canonical name per concept across the three sources.

    Structured fields only: class ``canonical_name``, activity ``swimlane`` and
    action ``object``, and the requirement ``actor``/``object`` columns when
    present. Requirement prose is not mined for names.

    One instance per concept that appears in more than one source. It fails
    when two distinct surface forms are used that do *not* resolve to the same
    ontology concept - an alias used consistently with its canonical name is
    not an inconsistency, an unresolvable second spelling is.
    """
    # concept identity -> {surface form -> set of sources}
    observed: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    # Unresolvable terms are grouped by their own key so a typo still forms a
    # concept and can be compared against the real one.
    labels: dict[str, str] = {}

    def observe(surface: str, source: str, kinds: tuple[str, ...]) -> None:
        surface = (surface or "").strip()
        if not surface:
            return
        concept = onto.resolve(surface, kinds=kinds)
        if concept is None:
            identity = f"unresolved:{canonical_key(surface)}"
            labels.setdefault(identity, surface)
        else:
            identity = concept.identity
            labels.setdefault(identity, concept.canonical)
        observed[identity][surface].add(source)

    for row in class_rows:
        if (row.get("element_type") or "").strip().lower() == "class":
            observe(_lookup_form(row, "canonical_name"), SRC_CLASS,
                    (KIND_ENTITY, KIND_ACTOR))

    for row in activity_rows:
        element_type = (row.get("element_type") or "").strip().lower()
        if element_type == "swimlane":
            observe(_lookup_form(row, "swimlane"), SRC_ACTIVITY,
                    (KIND_ENTITY, KIND_ACTOR))
        elif element_type == "action":
            observe(_lookup_form(row, "object"), SRC_ACTIVITY,
                    (KIND_ENTITY, KIND_ATTRIBUTE))

    for row in requirement_rows:
        for column in ("actor", "object"):
            if column in row:
                observe(_lookup_form(row, column), SRC_REQUIREMENTS,
                        (KIND_ENTITY, KIND_ACTOR, KIND_ATTRIBUTE))

    instances: list[Instance] = []
    for identity in sorted(observed):
        forms = observed[identity]
        sources = {source for source_set in forms.values() for source in source_set}
        if len(sources) < 2:
            # The rule is about cross-source agreement; a concept seen in one
            # source only cannot disagree with itself.
            continue
        label = labels.get(identity, identity)
        distinct = sorted(forms)
        if identity.startswith("unresolved:"):
            gaps.add(label, SRC_CLASS, "CM-05")

        # Two spellings of the same concept are only an inconsistency when they
        # are genuinely different *names*. Case and identifier style are not:
        # "PaymentGateway", "payment_gateway" and "payment gateway" are one
        # name written three ways, and every source already resolved them to
        # the same ontology concept. Collapsing on canonical_key keeps the rule
        # on actual naming disagreement rather than on formatting, which is
        # what "not resolved to the same canonical entity" means.
        distinct_names = sorted({canonical_key(form) for form in distinct})
        if len(distinct_names) == 1:
            instances.append(
                Instance("CM-05", label, STATUS_PASS,
                         f"'{label}' is named consistently across the "
                         f"{len(sources)} sources that use it "
                         f"(as {', '.join(repr(d) for d in distinct)}).")
            )
        else:
            instances.append(
                Instance("CM-05", label, STATUS_FAIL,
                         f"'{label}' is written {len(distinct_names)} different ways "
                         f"across sources: {', '.join(repr(d) for d in distinct)}.")
            )
    return instances


# --- orchestration -------------------------------------------------------


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def run_consistency(
    run_id: str,
    class_csv: str | Path,
    activity_csv: str | Path,
    requirements_csv: str | Path,
    out_dir: str | Path | None = None,
    cfg: Stage1Config | None = None,
) -> dict[str, Any]:
    """Compute metric 8 and write the instances CSV, the JSON and the sidecar.

    Args:
        run_id: Opaque label for the run.
        class_csv: Stage 1 output of the class-elements CSV.
        activity_csv: Stage 1 output of the activity-elements CSV.
        requirements_csv: Stage 1 output of the requirements CSV.
        out_dir: Directory for the outputs. Defaults to the Stage 1 artifact
            directory. Must resolve inside the repository.
        cfg: Effective config; loaded from ``config.yaml`` when None.

    Returns:
        The JSON payload that was written, plus the output paths.

    Raises:
        MissingColumnError: If a required ``__normalized`` column is absent.
        ConsistencyError: On any other input problem.
        Stage1ConfigError: If an output path escapes the repository.
    """
    if not run_id or not str(run_id).strip():
        raise ConsistencyError("run_id must be a non-empty label.")
    effective = cfg or load_config()
    onto = load_ontology(effective.ontology_path)

    class_path = Path(class_csv)
    activity_path = Path(activity_csv)
    requirements_path = Path(requirements_csv)

    class_fields, class_rows = _read_csv(class_path, "class-elements")
    activity_fields, activity_rows = _read_csv(activity_path, "activity-elements")
    req_fields, requirement_rows = _read_csv(requirements_path, "requirements")

    selected = set(effective.consistency.rules)

    # Prerequisite check. CM-01 compares swimlanes against class-side names, so
    # it needs the normalized forms of both. Stage 1's activity-inv/class-inv
    # presets do not currently produce them; this module does not modify
    # normalize, so it stops and names exactly what is missing.
    if "CM-01" in selected:
        missing: list[str] = []
        if "swimlane__normalized" not in activity_fields:
            missing.append(f"{_display_path(activity_path)}: swimlane__normalized")
        if "owner_class__normalized" not in class_fields:
            missing.append(f"{_display_path(class_path)}: owner_class__normalized")
        if missing:
            raise MissingColumnError(
                "CM-01 requires normalized columns that are not present: "
                + "; ".join(missing)
                + ". Stage 1's activity-inv and class-inv presets do not normalize "
                "'swimlane' or 'owner_class' yet. Extend normalize to emit them, or "
                "deselect CM-01 via stage1.consistency.rules in config.yaml."
            )

    _require_columns(req_fields, ["statement__normalized", "statement__state_mentions"],
                     requirements_path, "requirements")

    gaps = _GapLog()
    instances: list[Instance] = []
    if "CM-01" in selected:
        instances.extend(_cm01(activity_rows, onto, gaps))
    if "CM-02" in selected:
        instances.extend(_cm02(activity_rows, onto, gaps))
    if "CM-03" in selected:
        instances.extend(_cm03(class_rows, requirement_rows, onto, gaps))
    if "CM-04" in selected:
        instances.extend(_cm04(requirement_rows, onto, gaps))
    if "CM-05" in selected:
        instances.extend(
            _cm05(class_rows, activity_rows, requirement_rows, onto, gaps)
        )

    # Stable row order: by rule id, then instance label. Independent of the
    # order the rules happened to run in.
    instances.sort(key=lambda i: (i.rule_id, i.instance.lower(), i.detail))

    per_rule: dict[str, dict[str, int]] = {}
    for rule_id in sorted(selected):
        rule_instances = [i for i in instances if i.rule_id == rule_id]
        per_rule[rule_id] = {
            "total": len(rule_instances),
            "failed": sum(1 for i in rule_instances if i.failed),
        }

    total = len(instances)
    failed = sum(1 for i in instances if i.failed)
    consistency = None if total == 0 else 1 - (failed / total)

    ontology_sha = onto.sha256()
    out_directory = _resolve_out_dir(out_dir)
    out_directory.mkdir(parents=True, exist_ok=True)

    instances_path = out_directory / f"{run_id}__consistency_instances.csv"
    _write_instances(instances_path, run_id, instances, ontology_sha)

    gaps_path: Path | None = None
    if effective.consistency.emit_ontology_gaps:
        gaps_path = out_directory / f"{run_id}__ontology_gaps.csv"
        _write_gaps(gaps_path, gaps.rows())

    payload: dict[str, Any] = {
        "run_id": str(run_id),
        "consistency": consistency,
        "no_instances": total == 0,
        "total_instances": total,
        "total_failed": failed,
        "per_rule": per_rule,
    }
    json_path = out_directory / f"{run_id}__consistency.json"
    json_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    _write_meta(
        json_path,
        effective,
        run_id,
        ontology_sha,
        {
            "class_elements": _display_path(class_path),
            "activity_elements": _display_path(activity_path),
            "requirements": _display_path(requirements_path),
        },
        total,
    )

    payload["out_path"] = _display_path(json_path)
    payload["instances_path"] = _display_path(instances_path)
    payload["gaps_path"] = _display_path(gaps_path) if gaps_path else None
    return payload


def _resolve_out_dir(out_dir: str | Path | None) -> Path:
    """Resolve the output directory, confined to the repository."""
    from .config import ARTIFACT_DIR

    target = Path(out_dir) if out_dir is not None else ARTIFACT_DIR
    # resolve_output_path enforces the repo boundary on a file; apply it to a
    # sentinel inside the directory and take the parent back.
    probe = resolve_output_path(Path(target) / ".consistency_probe", None)
    return probe.parent


def _write_instances(
    path: Path, run_id: str, instances: Sequence[Instance], ontology_sha: str
) -> None:
    """Write the per-instance CSV with ``\\n`` endings, as normalize does."""
    fieldnames = [
        "run_id",
        "rule_id",
        "instance",
        "status",
        "detail",
        "ontology_sha256",
        "tool_version",
    ]
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for item in instances:
            writer.writerow(
                {
                    "run_id": run_id,
                    "rule_id": item.rule_id,
                    "instance": item.instance,
                    "status": item.status,
                    "detail": item.detail,
                    "ontology_sha256": ontology_sha,
                    "tool_version": CONSISTENCY_VERSION,
                }
            )


def _write_gaps(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    """Write the ontology-gaps CSV. Always written, even when empty."""
    fieldnames = ["term", "source_file", "rule_id", "count"]
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_meta(
    out_path: Path,
    cfg: Stage1Config,
    run_id: str,
    ontology_sha: str,
    inputs: dict[str, str],
    instance_count: int,
) -> Path:
    """Write the ``.meta.json`` sidecar, following the normalize convention."""
    meta_path = out_path.with_name(out_path.name + ".meta.json")
    meta = {
        "stage1_version": STAGE1_VERSION,
        "consistency_version": CONSISTENCY_VERSION,
        "ontology_sha256": ontology_sha,
        "ontology_path": cfg.as_dict()["ontology_path"],
        "config": cfg.consistency.as_dict(),
        "run_id": run_id,
        "inputs": dict(sorted(inputs.items())),
        "instance_count": instance_count,
        "rules": dict(sorted(RULES.items())),
    }
    meta_path.write_text(
        json.dumps(meta, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return meta_path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m pipeline.stage1.consistency",
        description=(
            "Stage 1 - metric 8 (Consistency), rules CM-01..CM-05. Reads the "
            "Stage 1 output of the class, activity and requirements CSVs and "
            "scores one instance at a time. There is deliberately no CM-06."
        ),
    )
    parser.add_argument("--run-id", required=True, help="Opaque label for this run.")
    parser.add_argument(
        "--class-csv", required=True, help="Stage 1 output of the class-elements CSV."
    )
    parser.add_argument(
        "--activity-csv", required=True, help="Stage 1 output of the activity-elements CSV."
    )
    parser.add_argument(
        "--requirements-csv", required=True, help="Stage 1 output of the requirements CSV."
    )
    parser.add_argument(
        "--out-dir",
        help=(
            "Directory for the outputs. Defaults to pipeline/stage1/artifact/. "
            "Must be inside the repository."
        ),
    )
    parser.add_argument("--config", help="Path to a config.yaml holding the stage1 section.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point. Returns the process exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        cfg = load_config(args.config)
    except Stage1ConfigError as exc:
        print(f"consistency config error: {exc}", file=sys.stderr)
        return EXIT_USAGE

    try:
        payload = run_consistency(
            args.run_id,
            args.class_csv,
            args.activity_csv,
            args.requirements_csv,
            args.out_dir,
            cfg,
        )
    except (ConsistencyError, Stage1ConfigError) as exc:
        print(f"consistency error: {exc}", file=sys.stderr)
        return EXIT_USAGE

    score = payload["consistency"]
    shown = "null (no instances)" if score is None else f"{score:.4f}"
    print(
        f"consistency {CONSISTENCY_VERSION}: {payload['total_instances']} instances, "
        f"{payload['total_failed']} failed, consistency={shown} -> {payload['out_path']}"
    )
    for rule_id in sorted(payload["per_rule"]):
        counts = payload["per_rule"][rule_id]
        print(f"  {rule_id}: {counts['total'] - counts['failed']}/{counts['total']} pass")
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
