"""config.py — Configuration loaders for RequirementsGrading."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import yaml


class ConfigError(RuntimeError):
    """A config or rules file is missing, incomplete or inconsistent."""


# Keys shared with the other grading modules: top level of config.yaml.
SHARED_CONFIG_KEYS = {
    "embedding_model",
    "embedding_revision",
    "pooling",
    "normalize_embeddings",
    "manual_default",
    "judge_model",
    "judge_api_base",
    "judge_api_key",
    "judge_temperature",
    "judge_max_attempts",
    "kappa_sample_size",
    "kappa_accept",
    "random_seed",
}

# Config values that must never be written to a run's manifest.
SECRET_KEYS = {"judge_api_key"}

# Keys owned by this module: the `requirement_grading:` section.
OWN_CONFIG_KEYS = {
    "threshold",
    "sweep",
    "dedup_threshold",
    "allow_cross_kind",
    "expected_gold_units",
}

REQUIRED_CONFIG_KEYS = SHARED_CONFIG_KEYS | OWN_CONFIG_KEYS

REQUIRED_RULES_KEYS = {
    "status_sets",
    "payment_methods",
    "roles",
    "roles_case_sensitive",
    "cardinality_phrases",
    "polarity",
    "numeric",
    "transition_pattern",
    "entity_nouns",
    "normalization",
}


def _read_yaml(path: Path | str, what: str) -> dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        raise ConfigError(f"{what} not found: {p}")
    try:
        with p.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except yaml.YAMLError as error:
        raise ConfigError(f"{p}: not valid YAML: {error}") from error
    if not isinstance(data, dict):
        raise ConfigError(f"{p}: expected a mapping at the top level")
    return data


@dataclass(frozen=True)
class GradingConfig:
    embedding_model: str
    embedding_revision: str | None
    pooling: str
    normalize_embeddings: bool
    threshold: float
    sweep: list[float]
    dedup_threshold: float
    allow_cross_kind: bool
    manual_default: str
    judge_model: str | None
    judge_api_base: str
    judge_temperature: float
    judge_max_attempts: int
    kappa_sample_size: int
    kappa_accept: float
    random_seed: int
    expected_gold_units: int | None
    raw_dict: dict[str, Any]

    @property
    def public_dict(self) -> dict[str, Any]:
        """The config without its secrets, safe to record in a manifest."""
        return {k: v for k, v in self.raw_dict.items() if k not in SECRET_KEYS}

    @classmethod
    def load(cls, config_path: Path | str = "config.yaml") -> GradingConfig:
        data = _read_yaml(config_path, "Config file")
        p = Path(config_path)

        section = data.get("requirement_grading")
        if not isinstance(section, dict):
            raise ConfigError(f"{p}: the requirement_grading section is missing")

        missing = OWN_CONFIG_KEYS - section.keys()
        if missing:
            raise ConfigError(
                f"Missing required keys in {p}:requirement_grading: {sorted(missing)}")
        unknown = section.keys() - OWN_CONFIG_KEYS
        if unknown:
            raise ConfigError(
                f"Unknown keys in {p}:requirement_grading: {sorted(unknown)} "
                f"(keys shared with the other grading modules live at the top level)")

        missing = SHARED_CONFIG_KEYS - data.keys()
        if missing:
            raise ConfigError(f"Missing required config keys in {p}: {sorted(missing)}")

        # Shared keys come from the top level, the module's own from its section.
        grading_data = {**{k: data[k] for k in SHARED_CONFIG_KEYS}, **section}

        attempts = grading_data["judge_max_attempts"]
        if isinstance(attempts, bool) or not isinstance(attempts, int) or attempts < 1:
            raise ConfigError(
                f"{p}: judge_max_attempts must be an integer >= 1; got {attempts!r}")
        base = grading_data["judge_api_base"]
        if not isinstance(base, str) or not base.strip():
            raise ConfigError(f"{p}: judge_api_base must be a non-empty URL; got {base!r}")

        return cls(
            embedding_model=grading_data["embedding_model"],
            embedding_revision=grading_data["embedding_revision"],
            pooling=grading_data["pooling"],
            normalize_embeddings=bool(grading_data["normalize_embeddings"]),
            threshold=float(grading_data["threshold"]),
            sweep=[float(x) for x in grading_data["sweep"]],
            dedup_threshold=float(grading_data["dedup_threshold"]),
            allow_cross_kind=bool(grading_data["allow_cross_kind"]),
            manual_default=grading_data["manual_default"],
            judge_model=grading_data["judge_model"],
            judge_api_base=base,
            judge_temperature=float(grading_data["judge_temperature"]),
            judge_max_attempts=attempts,
            kappa_sample_size=int(grading_data["kappa_sample_size"]),
            kappa_accept=float(grading_data["kappa_accept"]),
            random_seed=int(grading_data["random_seed"]),
            expected_gold_units=int(grading_data["expected_gold_units"]) if grading_data["expected_gold_units"] is not None else None,
            raw_dict=grading_data,
        )


def _gold_file(config_path: Path | str, key: str) -> Path:
    p = Path(config_path)
    data = _read_yaml(p, "Config file")
    section = data.get("gold")
    if not isinstance(section, dict) or key not in section:
        raise ConfigError(f"{p}: gold.{key} is missing")
    target = Path(section[key])
    target = target if target.is_absolute() else p.parent / target
    if not target.is_file():
        raise ConfigError(f"{p}: gold.{key} file not found: {target}")
    return target


def load_gold_path(config_path: Path | str) -> Path:
    """Resolve `gold.requirements` of the shared `gold:` section of config.yaml.

    Every grading module finds its gold standard there, so a path is changed in
    one place. A relative path is taken from the directory of the config file.
    """
    return _gold_file(config_path, "requirements")


def load_domain_path(config_path: Path | str) -> Path:
    """Resolve `gold.domain`: the input the rubric judge checks traceability against."""
    return _gold_file(config_path, "domain")


@dataclass(frozen=True)
class RulesConfig:
    status_sets: dict[str, list[str]]
    payment_methods: list[str]
    roles: list[str]
    roles_case_sensitive: bool
    cardinality_phrases: dict[str, Any]
    polarity: dict[str, list[str]]
    numeric: dict[str, list[str]]
    transition_pattern: str
    entity_nouns: list[str]
    normalization: dict[str, Any]
    raw_dict: dict[str, Any]

    @classmethod
    def load(cls, rules_path: Path | str) -> RulesConfig:
        p = Path(rules_path)
        data = _read_yaml(p, "Rules file")

        missing = REQUIRED_RULES_KEYS - data.keys()
        if missing:
            raise ConfigError(f"Missing required rules keys in {p}: {sorted(missing)}")

        unknown = data.keys() - REQUIRED_RULES_KEYS
        if unknown:
            raise ConfigError(f"Unknown rules keys in {p}: {sorted(unknown)}")

        # §8.3: lowercase must stay false; loader must reject true
        norm = data["normalization"]
        if norm.get("lowercase", False) is True:
            raise ConfigError("normalization.lowercase must be false; roles are case-sensitive.")

        return cls(
            status_sets=data["status_sets"],
            payment_methods=data["payment_methods"],
            roles=data["roles"],
            roles_case_sensitive=bool(data["roles_case_sensitive"]),
            cardinality_phrases=data["cardinality_phrases"],
            polarity=data["polarity"],
            numeric=data["numeric"],
            transition_pattern=data["transition_pattern"],
            entity_nouns=data["entity_nouns"],
            normalization=data["normalization"],
            raw_dict=data,
        )
