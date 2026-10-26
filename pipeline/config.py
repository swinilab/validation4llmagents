"""Configuration for the normalization and analysis pipeline.

Defaults live here; a repository ``config.yaml`` may override them under a
``pipeline:`` section (or legacy ``stage1:`` section). No absolute paths are
hard-coded: every path in the config is resolved relative to the repository
root, which is discovered by walking up from this file.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping

import yaml

# Repository root = two levels up from this file (pipeline/config.py).
REPO_ROOT = Path(__file__).resolve().parents[1]

# The pipeline module directory, and the directory pipeline writes its outputs to when
# --out is not given. Both stay inside the repository: pipeline never writes to /tmp
# or anywhere outside the checkout.
PIPELINE_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = PIPELINE_DIR / "artifact"
STAGE1_DIR = PIPELINE_DIR  # Backward compatibility alias

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


class ConfigError(RuntimeError):
    """Raised when the pipeline configuration cannot be used."""


Stage1ConfigError = ConfigError  # Backward compatibility alias


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
class PipelineConfig:
    """Effective pipeline configuration.

    Attributes:
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
    """

    modals: tuple[str, ...] = DEFAULT_MODALS
    articles: tuple[str, ...] = DEFAULT_ARTICLES
    singularize_nouns: bool = False
    spacy_model: str = "en_core_web_sm"
    split_identifiers: bool = True
    keep_negation_cue_tokens: bool = False
    non_negating_phrases: tuple[str, ...] = ()
    parse_check: ParseCheckConfig = field(default_factory=ParseCheckConfig)

    def as_dict(self) -> dict[str, Any]:
        """Config as plain JSON-serializable data, for the ``.meta.json``."""
        data = asdict(self)
        for key in ("modals", "articles", "non_negating_phrases"):
            data[key] = list(data[key])
        data["parse_check"] = self.parse_check.as_dict()
        return data


Stage1Config = PipelineConfig  # Backward compatibility alias


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
        ConfigError: If the resolved path lies outside the repository. The pipeline
            writes only inside the checkout, so ``/tmp`` and other external
            locations are refused rather than silently redirected.
    """
    if out is None:
        stem = Path(in_path).stem if in_path else "pipeline_output"
        resolved = (ARTIFACT_DIR / f"{stem}__normalized.csv").resolve()
    else:
        candidate = Path(out)
        resolved = (candidate if candidate.is_absolute() else Path.cwd() / candidate).resolve()

    try:
        resolved.relative_to(REPO_ROOT)
    except ValueError:
        raise ConfigError(
            f"Refusing to write outside the repository: {resolved}. "
            f"Pipeline writes only inside {REPO_ROOT}; omit --out to use the default "
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


def _as_str_tuple(value: Any, default: tuple[str, ...], key: str) -> tuple[str, ...]:
    """Coerce a config value to a lowercase string tuple."""
    if value is None:
        return default
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise ConfigError(f"pipeline.{key} in config.yaml must be a list of strings.")
    return tuple(str(item).strip().lower() for item in value if str(item).strip())


def _sub_section(value: Any, key: str) -> dict[str, Any]:
    """Coerce a nested config section to a mapping."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"pipeline.{key} in config.yaml must be a mapping.")
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
        raise ConfigError("pipeline.parse_check.extra_args must be a list of strings.")
    try:
        timeout = int(section.get("timeout_seconds", defaults.timeout_seconds))
    except (TypeError, ValueError):
        raise ConfigError(
            "pipeline.parse_check.timeout_seconds must be an integer number of seconds."
        ) from None
    if timeout <= 0:
        raise ConfigError("pipeline.parse_check.timeout_seconds must be positive.")
    return ParseCheckConfig(
        plantuml_jar=str(section.get("plantuml_jar", defaults.plantuml_jar) or ""),
        plantuml_cmd=str(section.get("plantuml_cmd", defaults.plantuml_cmd)),
        java_cmd=str(section.get("java_cmd", defaults.java_cmd)),
        layout_smetana=bool(section.get("layout_smetana", defaults.layout_smetana)),
        timeout_seconds=timeout,
        extra_args=extra_args,
    )


def load_config(
    config_path: Path | str | None = None,
    overrides: Mapping[str, Any] | None = None,
) -> PipelineConfig:
    """Build the effective config from ``config.yaml`` plus ``overrides``.

    Args:
        config_path: Explicit config file. When None, the nearest
            ``config.yaml`` at or above the repository root is used if present.
        overrides: Values applied on top of the file's ``pipeline`` section.

    Returns:
        The effective, frozen :class:`PipelineConfig`.

    Raises:
        ConfigError: If the file is unreadable or a value has the wrong type.
    """
    section: dict[str, Any] = {}
    path = Path(config_path) if config_path else find_repo_config()
    if path is not None:
        if not path.is_file():
            raise ConfigError(f"Config file not found: {path}")
        try:
            loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:  # pragma: no cover - malformed config
            raise ConfigError(f"Cannot parse {path}: {exc}") from exc
        if not isinstance(loaded, dict):
            raise ConfigError(f"{path} must contain a YAML mapping at the top level.")
        raw_section = loaded.get("pipeline")
        if raw_section is None:
            raw_section = loaded.get("stage1") or {}
        if not isinstance(raw_section, dict):
            raise ConfigError(f"The pipeline section of {path} must be a mapping.")
        section = dict(raw_section)

    if overrides:
        section.update(overrides)

    return PipelineConfig(
        parse_check=_parse_check_config(section.get("parse_check")),
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
