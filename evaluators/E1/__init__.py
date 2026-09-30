"""E1 - text normalization, stage 1 of the SRS-evaluation matching cascade.

E1 produces one canonical form of a string for E2 (ontology frame match) and E3
(embedding cosine). It never decides whether two items match.

See README.md for the normalization rules and the changelog, and COMMAND.md for
copy-pasteable commands.
"""

from .config import ARTIFACT_DIR, E1Config, E1ConfigError, load_config
from .normalize import (
    E1_VERSION,
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
from .cli import SOURCES, run_e1

__all__ = [
    "ARTIFACT_DIR",
    "E1_VERSION",
    "E1Config",
    "E1ConfigError",
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
    "run_e1",
]
