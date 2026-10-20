"""Stage 1 - text normalization, stage 1 of the SRS-evaluation matching cascade.

Stage 1 produces one canonical form of a string for downstream matching and
checks diagram validity. It never decides whether two items match.

See README.md for the normalization rules and the changelog, and COMMAND.md for
copy-pasteable commands.
"""

from .config import (
    ARTIFACT_DIR,
    ParseCheckConfig,
    Stage1Config,
    Stage1ConfigError,
    load_config,
)
from .normalize import (
    STAGE1_VERSION,
    NEGATION_CUES,
    NON_NEGATING_PHRASES,
    SCOPE_MAIN,
    SCOPE_NONE,
    SCOPE_SUBORDINATE,
    Normalized,
    normalize,
    normalize_label,
)
from .cli import SOURCES, run_stage1

# parse_check is runnable with ``python -m``. Importing it
# eagerly here would load each one twice - once as a package attribute, once as
# ``__main__`` - which Python warns about and which would give the module two
# distinct sets of module-level constants. They are resolved on first use
# instead (PEP 562), so package imports stay lightweight.
_LAZY_EXPORTS: dict[str, str] = {
    "PARSE_CHECK_VERSION": "parse_check",
    "ParseCheckError": "parse_check",
    "PlantUmlNotAvailable": "parse_check",
    "STRUCTURAL_RULES": "parse_check",
    "inventory_allowed": "parse_check",
    "run_parse_check": "parse_check",
}


def __getattr__(name: str):
    """Resolve the lazily-exported analysis symbols on first access."""
    module_name = _LAZY_EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    module = import_module(f".{module_name}", __name__)
    value = getattr(module, name)
    globals()[name] = value  # cache, so __getattr__ runs once per symbol
    return value


def __dir__() -> list[str]:
    return sorted({*globals(), *_LAZY_EXPORTS})

__all__ = [
    "ARTIFACT_DIR",
    "PARSE_CHECK_VERSION",
    "STRUCTURAL_RULES",
    "STAGE1_VERSION",
    "ParseCheckConfig",
    "ParseCheckError",
    "PlantUmlNotAvailable",
    "Stage1Config",
    "Stage1ConfigError",
    "inventory_allowed",
    "run_parse_check",
    "NEGATION_CUES",
    "NON_NEGATING_PHRASES",
    "Normalized",
    "SCOPE_MAIN",
    "SCOPE_NONE",
    "SCOPE_SUBORDINATE",
    "SOURCES",
    "load_config",
    "normalize",
    "normalize_label",
    "run_stage1",
]
