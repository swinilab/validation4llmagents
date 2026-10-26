"""Pipeline - text normalization and diagram verification for SRS evaluation.

The pipeline produces canonical forms of strings for downstream evaluation and
checks diagram validity.

See README.md for the normalization rules and the changelog, and COMMAND.md for
copy-pasteable commands.
"""

from .config import (
    ARTIFACT_DIR,
    ConfigError,
    ParseCheckConfig,
    PipelineConfig,
    Stage1Config,
    Stage1ConfigError,
    load_config,
)
from .normalize import (
    PIPELINE_VERSION,
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
from .cli import (
    SOURCES,
    InputError,
    Stage1InputError,
    run_pipeline_cli,
    run_stage1,
)

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
    "PIPELINE_VERSION",
    "STAGE1_VERSION",
    "ParseCheckConfig",
    "ParseCheckError",
    "PlantUmlNotAvailable",
    "PipelineConfig",
    "ConfigError",
    "Stage1Config",
    "Stage1ConfigError",
    "InputError",
    "Stage1InputError",
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
    "run_pipeline_cli",
    "run_stage1",
]
