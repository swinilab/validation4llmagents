"""PlantUML -> Graph IR parsers (spec §4, §5)."""

from .structural import parse_structural
from .behavioral import parse_behavioral
from .collapse import collapse_by_label, collapse_violations
from .ir import (
    Declaration,
    Element,
    Rejection,
    Violation,
    ParseResult,
    PARSER_VERSION,
    SUPPORTED_CONSTRUCTS,
    UNSUPPORTED_CONSTRUCTS,
)

__all__ = [
    "parse_structural",
    "collapse_by_label",
    "collapse_violations",
    "parse_behavioral",
    "Declaration",
    "Element",
    "Rejection",
    "Violation",
    "ParseResult",
    "PARSER_VERSION",
    "SUPPORTED_CONSTRUCTS",
    "UNSUPPORTED_CONSTRUCTS",
]
