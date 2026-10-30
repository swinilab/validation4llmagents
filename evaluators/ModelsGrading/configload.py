"""Loaders for `config.yaml` and `ModelsGrading/rules.yaml` (spec §9).

No magic numbers: every threshold, cutoff and vocabulary that can affect a
reported number is read from a file (§9.1). Both loaders fail loudly on a
missing key and on an unknown key -- defaults live in the YAML and nowhere else.

The only literals permitted here are the key names themselves and the structural
gold counts used in assertions (§9.1), which live in `GOLD_INVENTORY`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

# Structural constants with no effect on results (§9.1): the expected gold
# inventory, asserted per kind in S1 (§5.7).
GOLD_INVENTORY: dict[str, dict[str, int]] = {
    "structural": {"class": 6, "attribute": 22, "enum": 4, "literal": 13,
                   "relationship": 5},
    "behavioral": {"action": 9, "object_node": 10, "swimlane": 9,
                   "transition": 11},
}

DIAGRAMS = ("structural", "behavioral")

# Keys this section reads from the project-level config.yaml. Most are shared
# with the other grading modules; `sweep_models` / `threshold_models`,
# `syntax_gate` and `kappa_pool` are ours (§9.2).
_CONFIG_KEYS = {
    "embedding_model", "embedding_revision", "pooling", "normalize_embeddings",
    "manual_default", "judge_model", "judge_api_base", "judge_api_key",
    "judge_temperature", "judge_max_attempts",
    "kappa_sample_size", "kappa_accept", "random_seed",
    "threshold_models", "sweep_models", "syntax_gate", "kappa_pool",
}

# Config values that must never be written to a run's manifest.
SECRET_KEYS = {"judge_api_key"}

# Keys this section reads from the shared `gold:` mapping of config.yaml.
_GOLD_KEYS = {"structural", "behavioral", "domain"}

# `dedup_threshold` is deliberately not read by this section (§5.3, §9.2): its
# absence must be deliberate rather than forgotten, so supplying it aborts.
_CONFIG_FORBIDDEN = {"dedup_threshold"}

_RULES_KEYS = {
    "status_sets", "payment_methods", "roles", "roles_case_sensitive",
    "type_table", "type_unlisted", "rel_type_map", "drop_arrows",
    "guard_aliases", "normalization",
}

_NORMALIZATION_KEYS = {
    "strip_stereotypes", "strip_visibility", "collapse_separators", "lowercase",
}

_TYPE_TABLE_KEYS = {"accept", "warn", "fail"}

_SYNTAX_GATE_VALUES = {"strict", "plantuml"}
_KAPPA_POOL_VALUES = {"per_section", "pooled"}


class ConfigError(RuntimeError):
    """A configuration file is missing a key, or carries one we do not know."""


def _require_mapping(data: Any, source: str) -> dict:
    if not isinstance(data, dict):
        raise ConfigError(f"{source}: expected a mapping at the top level")
    return data


def _plantuml_settings(raw: dict, path: Path) -> dict:
    """How to run PlantUML, read from the shared `pipeline.parse_check` section.

    Used only by `syntax_gate: plantuml`. A relative jar path is taken from the
    directory of the config file, like the `gold:` paths.
    """
    section = (raw.get("pipeline") or {}).get("parse_check") or {}
    jar = section.get("plantuml_jar")
    if jar and not Path(jar).is_absolute():
        jar = str(path.parent / jar)
    return {"jar": jar, "java_cmd": section.get("java_cmd"),
            "timeout_seconds": section.get("timeout_seconds")}


def load_config(path: str | Path) -> dict:
    """Read the grading keys out of the project-level `config.yaml` (§9.2).

    The file is shared with the generation pipeline, so unrelated top-level
    sections are left alone; only the grading keys are extracted, and an
    unknown key *inside the grading set* is an error.
    """
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"config file not found: {path}")
    raw = _require_mapping(yaml.safe_load(path.read_text(encoding="utf-8")), str(path))

    present = _CONFIG_FORBIDDEN & set(raw)
    if present:
        raise ConfigError(
            f"{path}: key(s) {sorted(present)} must not be supplied to the models "
            "section: it performs exact-label collapsing, not cosine dedup "
            "(spec §5.3, §9.2)")

    missing = sorted(_CONFIG_KEYS - set(raw))
    if missing:
        raise ConfigError(f"{path}: missing required key(s): {missing}")

    config = {key: raw[key] for key in _CONFIG_KEYS}
    config["plantuml"] = _plantuml_settings(raw, path)

    sweep = config["sweep_models"]
    if not isinstance(sweep, list) or not sweep:
        raise ConfigError(f"{path}: sweep_models must be a non-empty list")
    if not all(isinstance(t, (int, float)) for t in sweep):
        raise ConfigError(f"{path}: sweep_models must contain numbers only")
    if config["threshold_models"] not in sweep:
        raise ConfigError(
            f"{path}: threshold_models {config['threshold_models']} must appear in "
            f"sweep_models {sweep}, so the primary threshold is part of the sweep")
    attempts = config["judge_max_attempts"]
    if isinstance(attempts, bool) or not isinstance(attempts, int) or attempts < 1:
        raise ConfigError(
            f"{path}: judge_max_attempts must be an integer >= 1; got {attempts!r}")
    base = config["judge_api_base"]
    if not isinstance(base, str) or not base.strip():
        raise ConfigError(
            f"{path}: judge_api_base must be a non-empty URL; got {base!r}")
    if config["syntax_gate"] not in _SYNTAX_GATE_VALUES:
        raise ConfigError(
            f"{path}: syntax_gate must be one of {sorted(_SYNTAX_GATE_VALUES)}; "
            f"got {config['syntax_gate']!r}")
    if config["syntax_gate"] == "plantuml":
        unset = sorted(k for k, v in config["plantuml"].items() if not v)
        if unset:
            raise ConfigError(
                f"{path}: syntax_gate 'plantuml' needs pipeline.parse_check "
                f"settings {unset} (plantuml_jar, java_cmd, timeout_seconds)")
    if config["kappa_pool"] not in _KAPPA_POOL_VALUES:
        raise ConfigError(
            f"{path}: kappa_pool must be one of {sorted(_KAPPA_POOL_VALUES)}; "
            f"got {config['kappa_pool']!r}")
    if config["kappa_pool"] == "pooled":
        # Pooling needs the Requirements section's unmatched elements and its
        # human labels; this section cannot read them yet. Recording "pooled"
        # next to a κ computed on this section alone would misreport the setting.
        raise ConfigError(
            f"{path}: kappa_pool 'pooled' is not supported yet: it needs the "
            "Requirements section's rubric labels. Use 'per_section'.")
    return config


def public_config(config: dict) -> dict:
    """The config without its secrets, safe to record in a manifest."""
    return {k: v for k, v in config.items() if k not in SECRET_KEYS}


def load_gold_paths(path: str | Path) -> dict[str, Path]:
    """Resolve the shared `gold:` section of `config.yaml`.

    Every grading module finds its gold standard and domain input here, so a
    path is changed in one place. Relative paths are taken from the directory
    of the config file. Keys other modules own are left alone.
    """
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"config file not found: {path}")
    raw = _require_mapping(yaml.safe_load(path.read_text(encoding="utf-8")), str(path))
    section = _require_mapping(raw.get("gold"), f"{path}:gold")

    missing = sorted(_GOLD_KEYS - set(section))
    if missing:
        raise ConfigError(f"{path}: gold is missing required key(s): {missing}")

    resolved: dict[str, Path] = {}
    for key in sorted(_GOLD_KEYS):
        target = Path(section[key])
        target = target if target.is_absolute() else path.parent / target
        if not target.is_file():
            raise ConfigError(f"{path}: gold.{key} file not found: {target}")
        resolved[key] = target
    return resolved


def load_rules(path: str | Path) -> dict:
    """Read `ModelsGrading/rules.yaml` (§9.3)."""
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"rules file not found: {path}")
    rules = _require_mapping(yaml.safe_load(path.read_text(encoding="utf-8")), str(path))

    missing = sorted(_RULES_KEYS - set(rules))
    if missing:
        raise ConfigError(f"{path}: missing required key(s): {missing}")
    unknown = sorted(set(rules) - _RULES_KEYS)
    if unknown:
        raise ConfigError(f"{path}: unknown key(s): {unknown}")

    normalization = _require_mapping(rules["normalization"], f"{path}:normalization")
    missing = sorted(_NORMALIZATION_KEYS - set(normalization))
    if missing:
        raise ConfigError(f"{path}: normalization missing key(s): {missing}")
    unknown = sorted(set(normalization) - _NORMALIZATION_KEYS)
    if unknown:
        raise ConfigError(f"{path}: normalization has unknown key(s): {unknown}")
    if normalization["lowercase"]:
        # §9.3: listed so the choice is explicit and auditable, but `true`
        # breaks the case-sensitive role check in §7.4.5.
        raise ConfigError(
            f"{path}: normalization.lowercase must stay false; roles are "
            "compared case-sensitively (spec §7.4.5, §9.3)")

    for gold_type, row in _require_mapping(rules["type_table"], f"{path}:type_table").items():
        row = _require_mapping(row, f"{path}:type_table.{gold_type}")
        missing = sorted(_TYPE_TABLE_KEYS - set(row))
        if missing:
            raise ConfigError(
                f"{path}: type_table.{gold_type} missing key(s): {missing}")
        unknown = sorted(set(row) - _TYPE_TABLE_KEYS)
        if unknown:
            raise ConfigError(
                f"{path}: type_table.{gold_type} has unknown key(s): {unknown}")

    if rules["type_unlisted"] != "manual":
        raise ConfigError(
            f"{path}: type_unlisted must be 'manual': an unlisted type goes to the "
            f"ledger (spec §9.3); got {rules['type_unlisted']!r}")
    if not rules["roles_case_sensitive"]:
        raise ConfigError(
            f"{path}: roles_case_sensitive must stay true (spec §7.4.5)")

    return rules


def all_statuses(rules: dict) -> set[str]:
    """The object-node status whitelist, flattened (§7.4.4)."""
    return {s for members in rules["status_sets"].values() for s in members}
