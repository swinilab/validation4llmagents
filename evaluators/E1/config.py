"""Configuration for E1 (text normalization).

Defaults live here; a repository ``config.yaml`` may override them under an
``E1:`` section. No absolute paths are hard-coded: every path in the config is
resolved relative to the repository root, which is discovered by walking up
from this file.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Mapping

import yaml

# Repository root = three levels up from this file (evaluators/E1/config.py).
REPO_ROOT = Path(__file__).resolve().parents[2]

# The E1 module directory, and the directory E1 writes its outputs to when
# --out is not given. Both stay inside the repository: E1 never writes to /tmp
# or anywhere outside the checkout.
E1_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = E1_DIR / "artifact"

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


class E1ConfigError(RuntimeError):
    """Raised when the configuration or the ontology cannot be used."""


@dataclass(frozen=True)
class E1Config:
    """Effective E1 configuration.

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
    """

    ontology_path: Path
    modals: tuple[str, ...] = DEFAULT_MODALS
    articles: tuple[str, ...] = DEFAULT_ARTICLES
    singularize_nouns: bool = False
    spacy_model: str = "en_core_web_sm"
    split_identifiers: bool = True
    keep_negation_cue_tokens: bool = False
    non_negating_phrases: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        """Config as plain JSON-serializable data, for the ``.meta.json``."""
        data = asdict(self)
        data["ontology_path"] = _relative_to_repo(self.ontology_path)
        for key in ("modals", "articles", "non_negating_phrases"):
            data[key] = list(data[key])
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
        E1ConfigError: If the resolved path lies outside the repository. E1
            writes only inside the checkout, so ``/tmp`` and other external
            locations are refused rather than silently redirected.
    """
    if out is None:
        stem = Path(in_path).stem if in_path else "e1_output"
        resolved = (ARTIFACT_DIR / f"{stem}__e1.csv").resolve()
    else:
        candidate = Path(out)
        resolved = (candidate if candidate.is_absolute() else Path.cwd() / candidate).resolve()

    try:
        resolved.relative_to(REPO_ROOT)
    except ValueError:
        raise E1ConfigError(
            f"Refusing to write outside the repository: {resolved}. "
            f"E1 writes only inside {REPO_ROOT}; omit --out to use the default "
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
    raise E1ConfigError(
        "E1 cannot find the ontology file. Tried: "
        f"{tried}. Set E1.ontology_path in config.yaml to the "
        "orderman ontology YAML."
    )


def _as_str_tuple(value: Any, default: tuple[str, ...], key: str) -> tuple[str, ...]:
    """Coerce a config value to a lowercase string tuple."""
    if value is None:
        return default
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise E1ConfigError(f"E1.{key} in config.yaml must be a list of strings.")
    return tuple(str(item).strip().lower() for item in value if str(item).strip())


def load_config(
    config_path: Path | str | None = None,
    overrides: Mapping[str, Any] | None = None,
) -> E1Config:
    """Build the effective config from ``config.yaml`` plus ``overrides``.

    Args:
        config_path: Explicit config file. When None, the nearest
            ``config.yaml`` at or above the repository root is used if present.
        overrides: Values applied on top of the file's ``E1`` section.

    Returns:
        The effective, frozen :class:`E1Config`.

    Raises:
        E1ConfigError: If the file is unreadable or a value has the wrong type.
    """
    section: dict[str, Any] = {}
    path = Path(config_path) if config_path else find_repo_config()
    if path is not None:
        if not path.is_file():
            raise E1ConfigError(f"Config file not found: {path}")
        try:
            loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:  # pragma: no cover - malformed config
            raise E1ConfigError(f"Cannot parse {path}: {exc}") from exc
        if not isinstance(loaded, dict):
            raise E1ConfigError(f"{path} must contain a YAML mapping at the top level.")
        raw_section = loaded.get("E1") or {}
        if not isinstance(raw_section, dict):
            raise E1ConfigError(f"The E1 section of {path} must be a mapping.")
        section = dict(raw_section)

    if overrides:
        section.update(overrides)

    return E1Config(
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
