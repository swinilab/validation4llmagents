"""Configuration for Stage 1 (text normalization).

Defaults live here; a repository ``config.yaml`` may override them under an
``stage1:`` section. No absolute paths are hard-coded: every path in the config is
resolved relative to the repository root, which is discovered by walking up
from this file.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Mapping

import yaml

# Repository root = three levels up from this file (pipeline/stage1/config.py).
REPO_ROOT = Path(__file__).resolve().parents[2]

# The Stage 1 module directory, and the directory Stage 1 writes its outputs to when
# --out is not given. Both stay inside the repository: Stage 1 never writes to /tmp
# or anywhere outside the checkout.
STAGE1_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = STAGE1_DIR / "artifact"

DEFAULT_CONFIG_FILENAME = "config.yaml"

# Modals stripped from ``normalized``. ``can`` and ``may`` are included because
# the input FRs phrase permissions as "A Customer can ..." / "may": leaving them
# in would make the same requirement normalize differently depending on whether
# the author chose "shall" or "can". See README.
DEFAULT_MODALS: tuple[str, ...] = (
    "shall",
    "must",
    "should",
    "will",
    "can",
    "may",
)

# Articles / determiners removed in step 5. ``no`` is deliberately absent: it is
# a negation cue, and since 1.1.0 negation cues are always kept (see README).
DEFAULT_ARTICLES: tuple[str, ...] = ("a", "an", "the")

# Candidate locations of the ontology, tried in order, relative to REPO_ROOT.
DEFAULT_ONTOLOGY_CANDIDATES: tuple[str, ...] = (
    "ontology/orderman-ontology.yaml",
    "materials/M2-orderman-ontology.yaml",
)


class Stage1ConfigError(RuntimeError):
    """Raised when the configuration or the ontology cannot be used."""


# Default location of the PlantUML jar, relative to the repository root. The
# jar is downloaded rather than committed (see .gitignore); parse_check reports
# a tool error, not an invalid diagram, when it is absent.
DEFAULT_PLANTUML_JAR = "tools/plantuml.jar"


@dataclass(frozen=True)
class ParseCheckConfig:
    """Settings for metric 7 (Diagram Validity).

    Attributes:
        plantuml_jar: Path to ``plantuml.jar``, relative to the repository
            root unless absolute. Takes precedence over ``plantuml_cmd``.
        plantuml_cmd: Name of a ``plantuml`` executable on PATH, used when
            ``plantuml_jar`` is empty.
        java_cmd: The JVM used to run the jar.
        layout_smetana: Pass ``-Playout=smetana`` so a class diagram needs no
            Graphviz. ``-checkonly`` does not lay out, so this is off by
            default and exists for environments that want it.
        timeout_seconds: Per-diagram timeout. A timeout is a tool error.
        extra_args: Extra arguments appended to the PlantUML command.
    """

    plantuml_jar: str = DEFAULT_PLANTUML_JAR
    plantuml_cmd: str = "plantuml"
    java_cmd: str = "java"
    layout_smetana: bool = False
    timeout_seconds: int = 60
    extra_args: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["extra_args"] = list(data["extra_args"])
        return data


@dataclass(frozen=True)
class ConsistencyConfig:
    """Settings for metric 8 (Consistency).

    Attributes:
        rules: Rule ids to evaluate. CM-06 is intentionally absent: no
            multiplicity rule is implemented.
        emit_ontology_gaps: Write ``<run_id>__ontology_gaps.csv`` listing
            terms the ontology does not know. Unknown terms are never added
            to the ontology.
    """

    rules: tuple[str, ...] = ("CM-01", "CM-02", "CM-03", "CM-04", "CM-05")
    emit_ontology_gaps: bool = True

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["rules"] = list(data["rules"])
        return data


@dataclass(frozen=True)
class Stage1Config:
    """Effective Stage 1 configuration.

    Attributes:
        ontology_path: Ontology file read for state names and aliases. Read-only.
        modals: Modal verbs removed from ``normalized``.
        articles: Articles / determiners removed from ``normalized``.
        singularize_nouns: When true, nouns are replaced by their spaCy lemma.
            Default false: nouns keep their surface form.
        spacy_model: Name of the spaCy pipeline to load.
        split_identifiers: Split camelCase / PascalCase / snake_case tokens.
        keep_negation_cue_tokens: Retained for backward compatibility and no
            longer read: since 1.1.0 negation cues are *always* kept in
            ``normalized``. See the README changelog.
        non_negating_phrases: Phrases containing a cue that must not be treated
            as negation (e.g. "no more than", a numeric bound).
        parse_check: Settings for metric 7.
        consistency: Settings for metric 8.
    """

    ontology_path: Path
    modals: tuple[str, ...] = DEFAULT_MODALS
    articles: tuple[str, ...] = DEFAULT_ARTICLES
    singularize_nouns: bool = False
    spacy_model: str = "en_core_web_sm"
    split_identifiers: bool = True
    keep_negation_cue_tokens: bool = False
    non_negating_phrases: tuple[str, ...] = ()
    parse_check: ParseCheckConfig = field(default_factory=ParseCheckConfig)
    consistency: ConsistencyConfig = field(default_factory=ConsistencyConfig)

    def as_dict(self) -> dict[str, Any]:
        """Config as plain JSON-serializable data, for the ``.meta.json``."""
        data = asdict(self)
        data["ontology_path"] = _relative_to_repo(self.ontology_path)
        for key in ("modals", "articles", "non_negating_phrases"):
            data[key] = list(data[key])
        data["parse_check"] = self.parse_check.as_dict()
        data["consistency"] = self.consistency.as_dict()
        return data


# Phrases that contain a negation cue but express a bound or a fixed
# expression rather than a negated requirement. See README for the rationale of
# "no more than".
NON_NEGATING_PHRASES: tuple[str, ...] = (
    "no more than",
    "not more than",
    "no less than",
    "not less than",
    "no later than",
    "no earlier than",
    "no fewer than",
    "no greater than",
    "no longer than",
    "at least",
    "at most",
)


def _relative_to_repo(path: Path) -> str:
    """Path as a repo-relative POSIX string when possible, else absolute."""
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def resolve_output_path(out: str | Path | None, in_path: str | Path | None = None) -> Path:
    """Resolve an output path, defaulting to and confined within the repository.

    When ``out`` is None, the output goes to :data:`ARTIFACT_DIR` under a name
    derived from the input file. A relative ``out`` is taken relative to the
    current working directory, as a shell user expects.

    Args:
        out: The requested output path, or None for the default.
        in_path: The input file, used to name the default output.

    Returns:
        An absolute path inside the repository.

    Raises:
        Stage1ConfigError: If the resolved path lies outside the repository. Stage 1
            writes only inside the checkout, so ``/tmp`` and other external
            locations are refused rather than silently redirected.
    """
    if out is None:
        stem = Path(in_path).stem if in_path else "stage1_output"
        resolved = (ARTIFACT_DIR / f"{stem}__stage1.csv").resolve()
    else:
        candidate = Path(out)
        resolved = (candidate if candidate.is_absolute() else Path.cwd() / candidate).resolve()

    try:
        resolved.relative_to(REPO_ROOT)
    except ValueError:
        raise Stage1ConfigError(
            f"Refusing to write outside the repository: {resolved}. "
            f"Stage 1 writes only inside {REPO_ROOT}; omit --out to use the default "
            f"{_relative_to_repo(ARTIFACT_DIR)}/ directory."
        ) from None
    return resolved


def find_repo_config(start: Path | None = None) -> Path | None:
    """Return the nearest ``config.yaml`` at or above ``start``, if any."""
    base = (start or REPO_ROOT).resolve()
    for directory in (base, *base.parents):
        candidate = directory / DEFAULT_CONFIG_FILENAME
        if candidate.is_file():
            return candidate
    return None


def _resolve_ontology(raw: str | None) -> Path:
    """Resolve the ontology path, trying the documented candidates."""
    candidates: list[Path] = []
    if raw:
        given = Path(raw)
        candidates.append(given if given.is_absolute() else REPO_ROOT / given)
    else:
        candidates.extend(REPO_ROOT / rel for rel in DEFAULT_ONTOLOGY_CANDIDATES)

    for candidate in candidates:
        if candidate.is_file():
            return candidate

    tried = ", ".join(_relative_to_repo(c) for c in candidates)
    raise Stage1ConfigError(
        "Stage 1 cannot find the ontology file. Tried: "
        f"{tried}. Set stage1.ontology_path in config.yaml to the "
        "orderman ontology YAML."
    )


def _as_str_tuple(value: Any, default: tuple[str, ...], key: str) -> tuple[str, ...]:
    """Coerce a config value to a lowercase string tuple."""
    if value is None:
        return default
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise Stage1ConfigError(f"stage1.{key} in config.yaml must be a list of strings.")
    return tuple(str(item).strip().lower() for item in value if str(item).strip())


def _sub_section(value: Any, key: str) -> dict[str, Any]:
    """Coerce a nested config section to a mapping."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise Stage1ConfigError(f"stage1.{key} in config.yaml must be a mapping.")
    return dict(value)


def _parse_check_config(raw: Any) -> ParseCheckConfig:
    """Build the metric 7 settings from the ``parse_check`` sub-section."""
    section = _sub_section(raw, "parse_check")
    defaults = ParseCheckConfig()
    extra = section.get("extra_args")
    if extra is None:
        extra_args = defaults.extra_args
    elif isinstance(extra, (list, tuple)):
        extra_args = tuple(str(item) for item in extra)
    else:
        raise Stage1ConfigError("stage1.parse_check.extra_args must be a list of strings.")
    try:
        timeout = int(section.get("timeout_seconds", defaults.timeout_seconds))
    except (TypeError, ValueError):
        raise Stage1ConfigError(
            "stage1.parse_check.timeout_seconds must be an integer number of seconds."
        ) from None
    if timeout <= 0:
        raise Stage1ConfigError("stage1.parse_check.timeout_seconds must be positive.")
    return ParseCheckConfig(
        plantuml_jar=str(section.get("plantuml_jar", defaults.plantuml_jar) or ""),
        plantuml_cmd=str(section.get("plantuml_cmd", defaults.plantuml_cmd)),
        java_cmd=str(section.get("java_cmd", defaults.java_cmd)),
        layout_smetana=bool(section.get("layout_smetana", defaults.layout_smetana)),
        timeout_seconds=timeout,
        extra_args=extra_args,
    )


def _consistency_config(raw: Any) -> ConsistencyConfig:
    """Build the metric 8 settings from the ``consistency`` sub-section."""
    section = _sub_section(raw, "consistency")
    defaults = ConsistencyConfig()
    rules = section.get("rules")
    if rules is None:
        selected = defaults.rules
    elif isinstance(rules, (list, tuple)):
        selected = tuple(str(item).strip().upper() for item in rules if str(item).strip())
    else:
        raise Stage1ConfigError("stage1.consistency.rules must be a list of rule ids.")
    unknown = [rule for rule in selected if rule not in defaults.rules]
    if unknown:
        raise Stage1ConfigError(
            f"stage1.consistency.rules contains unknown rule id(s): {', '.join(unknown)}. "
            f"Known rules: {', '.join(defaults.rules)}. "
            f"(There is deliberately no multiplicity rule CM-06.)"
        )
    return ConsistencyConfig(
        rules=selected,
        emit_ontology_gaps=bool(
            section.get("emit_ontology_gaps", defaults.emit_ontology_gaps)
        ),
    )


def load_config(
    config_path: Path | str | None = None,
    overrides: Mapping[str, Any] | None = None,
) -> Stage1Config:
    """Build the effective config from ``config.yaml`` plus ``overrides``.

    Args:
        config_path: Explicit config file. When None, the nearest
            ``config.yaml`` at or above the repository root is used if present.
        overrides: Values applied on top of the file's ``Stage 1`` section.

    Returns:
        The effective, frozen :class:`Stage1Config`.

    Raises:
        Stage1ConfigError: If the file is unreadable or a value has the wrong type.
    """
    section: dict[str, Any] = {}
    path = Path(config_path) if config_path else find_repo_config()
    if path is not None:
        if not path.is_file():
            raise Stage1ConfigError(f"Config file not found: {path}")
        try:
            loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:  # pragma: no cover - malformed config
            raise Stage1ConfigError(f"Cannot parse {path}: {exc}") from exc
        if not isinstance(loaded, dict):
            raise Stage1ConfigError(f"{path} must contain a YAML mapping at the top level.")
        raw_section = loaded.get("stage1") or {}
        if not isinstance(raw_section, dict):
            raise Stage1ConfigError(f"The stage1 section of {path} must be a mapping.")
        section = dict(raw_section)

    if overrides:
        section.update(overrides)

    return Stage1Config(
        parse_check=_parse_check_config(section.get("parse_check")),
        consistency=_consistency_config(section.get("consistency")),
        ontology_path=_resolve_ontology(section.get("ontology_path")),
        modals=_as_str_tuple(section.get("modals"), DEFAULT_MODALS, "modals"),
        articles=_as_str_tuple(section.get("articles"), DEFAULT_ARTICLES, "articles"),
        singularize_nouns=bool(section.get("singularize_nouns", False)),
        spacy_model=str(section.get("spacy_model", "en_core_web_sm")),
        split_identifiers=bool(section.get("split_identifiers", True)),
        keep_negation_cue_tokens=bool(section.get("keep_negation_cue_tokens", False)),
        non_negating_phrases=_as_str_tuple(
            section.get("non_negating_phrases"), NON_NEGATING_PHRASES, "non_negating_phrases"
        ),
    )


def sha256_of(path: Path) -> str:
    """SHA-256 of a file, read in binary so the digest is platform-stable."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()
