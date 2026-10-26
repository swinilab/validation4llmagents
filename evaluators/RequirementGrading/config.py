"""config.py — Configuration loaders for RequirementGrading."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import yaml


REQUIRED_CONFIG_KEYS = {
    "embedding_model",
    "embedding_revision",
    "pooling",
    "normalize_embeddings",
    "threshold",
    "sweep",
    "dedup_threshold",
    "allow_cross_kind",
    "manual_default",
    "judge_model",
    "judge_temperature",
    "kappa_sample_size",
    "kappa_accept",
    "random_seed",
    "gold_path",
    "expected_gold_units",
}

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
    judge_temperature: float
    kappa_sample_size: int
    kappa_accept: float
    random_seed: int
    gold_path: str
    expected_gold_units: int | None
    raw_dict: dict[str, Any]

    @classmethod
    def load(cls, config_path: Path | str = "config.yaml") -> GradingConfig:
        p = Path(config_path)
        if not p.is_file():
            raise FileNotFoundError(f"Config file not found: {p}")
        with p.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        # If data has requirement_grading section, extract it; otherwise treat root as grading config
        grading_data = data.get("requirement_grading", data)

        missing = REQUIRED_CONFIG_KEYS - grading_data.keys()
        if missing:
            raise KeyError(f"Missing required config keys in {p}: {sorted(missing)}")

        unknown = grading_data.keys() - REQUIRED_CONFIG_KEYS
        # If grading_data is the whole root, ignore other top-level sections like workdir, agent, pipeline, etc.
        if "requirement_grading" in data and unknown:
            raise KeyError(f"Unknown config keys in requirement_grading section: {sorted(unknown)}")

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
            judge_temperature=float(grading_data["judge_temperature"]),
            kappa_sample_size=int(grading_data["kappa_sample_size"]),
            kappa_accept=float(grading_data["kappa_accept"]),
            random_seed=int(grading_data["random_seed"]),
            gold_path=str(grading_data["gold_path"]),
            expected_gold_units=int(grading_data["expected_gold_units"]) if grading_data["expected_gold_units"] is not None else None,
            raw_dict=grading_data,
        )


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
        if not p.is_file():
            raise FileNotFoundError(f"Rules file not found: {p}")
        with p.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        missing = REQUIRED_RULES_KEYS - data.keys()
        if missing:
            raise KeyError(f"Missing required rules keys in {p}: {sorted(missing)}")

        unknown = data.keys() - REQUIRED_RULES_KEYS
        if unknown:
            raise KeyError(f"Unknown rules keys in {p}: {sorted(unknown)}")

        # §8.3: lowercase must stay false; loader must reject true
        norm = data["normalization"]
        if norm.get("lowercase", False) is True:
            raise ValueError("normalization.lowercase must be false; roles are case-sensitive.")

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
