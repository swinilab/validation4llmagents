"""Loaders for `VMXGrading/rules.yaml` and the shared `gold:` section.

Both fail loudly on a missing key and on an unknown key: defaults live in the
YAML and nowhere else.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

# Roles a column can play in a completeness condition.
ROLES = ("source", "structural", "behavioral")

_RULES_KEYS = {"submission_files", "columns", "separator", "completeness",
               "domain_sections"}
_FILE_KEYS = {"requirements", "vmx", "structural", "behavioral"}
_COLUMN_KEYS = {"id", "source", "structural", "behavioral"}


class ConfigError(RuntimeError):
    """A configuration file is missing a key, or carries one we do not know."""


def _mapping(data: Any, source: str) -> dict:
    if not isinstance(data, dict):
        raise ConfigError(f"{source}: expected a mapping")
    return data


def _exact_keys(section: dict, expected: set[str], source: str) -> None:
    missing = sorted(expected - set(section))
    if missing:
        raise ConfigError(f"{source}: missing key(s): {missing}")
    unknown = sorted(set(section) - expected)
    if unknown:
        raise ConfigError(f"{source}: unknown key(s): {unknown}")


def load_rules(path: str | Path) -> dict:
    """Read `VMXGrading/rules.yaml`."""
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"rules file not found: {path}")
    rules = _mapping(yaml.safe_load(path.read_text(encoding="utf-8")), str(path))
    _exact_keys(rules, _RULES_KEYS, str(path))
    _exact_keys(_mapping(rules["submission_files"], f"{path}:submission_files"),
                _FILE_KEYS, f"{path}:submission_files")
    _exact_keys(_mapping(rules["columns"], f"{path}:columns"),
                _COLUMN_KEYS, f"{path}:columns")

    if not rules["separator"] or not isinstance(rules["separator"], str):
        raise ConfigError(f"{path}: separator must be a non-empty string")
    for prefix, roles in _mapping(rules["completeness"],
                                  f"{path}:completeness").items():
        unknown = sorted(set(roles) - set(ROLES))
        if unknown:
            raise ConfigError(
                f"{path}: completeness.{prefix} names unknown role(s) {unknown}; "
                f"expected a subset of {list(ROLES)}")
    if not rules["domain_sections"]:
        raise ConfigError(f"{path}: domain_sections must not be empty")
    return rules


def load_domain_path(path: str | Path) -> Path:
    """Resolve `gold.domain` of the shared `gold:` section of config.yaml.

    A relative path is taken from the directory of the config file. Keys other
    modules own are left alone.
    """
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"config file not found: {path}")
    raw = _mapping(yaml.safe_load(path.read_text(encoding="utf-8")), str(path))
    section = _mapping(raw.get("gold"), f"{path}:gold")
    if "domain" not in section:
        raise ConfigError(f"{path}: gold is missing required key: domain")
    target = Path(section["domain"])
    target = target if target.is_absolute() else path.parent / target
    if not target.is_file():
        raise ConfigError(f"{path}: gold.domain file not found: {target}")
    return target
