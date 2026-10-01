"""Stage 1 - text normalization, stage 1 of the SRS-evaluation matching cascade.

Stage 1 produces one canonical form of a string for Stage 2 (ontology frame match) and Stage 3
(embedding cosine). It never decides whether two items match.

See README.md for the normalization rules and the changelog, and COMMAND.md for
copy-pasteable commands.
"""

from .config import (
    ARTIFACT_DIR,
    ConsistencyConfig,
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
    StateVocabulary,
    load_state_vocabulary,
    normalize,
    normalize_label,
)
from .cli import SOURCES, run_stage1
from .ontology import Concept, Ontology, canonical_key, load_ontology

# parse_check and consistency are runnable with ``python -m``. Importing them
# eagerly here would load each one twice - once as a package attribute, once as
# ``__main__`` - which Python warns about and which would give the module two
# distinct sets of module-level constants. They are resolved on first use
# instead (PEP 562), so ``from pipeline.stage1 import run_consistency`` still
# works.
_LAZY_EXPORTS: dict[str, str] = {
    "CONSISTENCY_VERSION": "consistency",
    "ConsistencyError": "consistency",
    "MissingColumnError": "consistency",
    "RULES": "consistency",
    "run_consistency": "consistency",
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
    "CONSISTENCY_VERSION",
    "PARSE_CHECK_VERSION",
    "RULES",
    "STRUCTURAL_RULES",
    "STAGE1_VERSION",
    "Concept",
    "ConsistencyConfig",
    "ConsistencyError",
    "MissingColumnError",
    "Ontology",
    "ParseCheckConfig",
    "ParseCheckError",
    "PlantUmlNotAvailable",
    "Stage1Config",
    "Stage1ConfigError",
    "canonical_key",
    "inventory_allowed",
    "load_ontology",
    "run_consistency",
    "run_parse_check",
    "NEGATION_CUES",
    "NON_NEGATING_PHRASES",
    "Normalized",
    "SCOPE_MAIN",
    "SCOPE_NONE",
    "SCOPE_SUBORDINATE",
    "SOURCES",
    "StateVocabulary",
    "load_config",
    "load_state_vocabulary",
    "normalize",
    "normalize_label",
    "run_stage1",
]
