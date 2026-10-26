"""Graph IR shared by both parsers (spec §4.1, §5, §11).

A `Declaration` is one source construct that would yield at least one element
under §5: a class body, an attribute line, an enum body, a literal, a
relationship edge, an activity, an object node, a swimlane directive, an edge.
Syntax Validity (§4.1) is the ratio of accepted to total declarations, so the
parser must record every declaration it recognises *and* every one it rejects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

PARSER_VERSION = "1.0.0"

# Reported in the manifest (§11) and the paper appendix (§9.4). The gate is not
# reproducible without knowing what the parser can and cannot read.
SUPPORTED_CONSTRUCTS = [
    # structural
    "class", "abstract class", "interface", "enum", "attribute", "method",
    "association", "aggregation", "composition", "generalization",
    "realization", "dependency", "hide", "skinparam", "title", "note",
    # behavioral
    "start", "stop", "end", "activity", "object node", "swimlane",
    "if/elseif/else/endif", "while/endwhile", "repeat/repeat while",
    "fork/fork again/end fork", "split/split again/end split",
    "detach", "kill", "label/goto", "partition", "group", "style",
    "arrow label", "backward", "break",
]

UNSUPPORTED_CONSTRUCTS = [
    "state diagram syntax",
    "sequence diagram syntax",
    "component/deployment diagram syntax",
    "json/yaml/wbs/mindmap diagrams",
    "preprocessor directives (!define, !include, !if)",
    "sprite/inline image declarations",
    "swimlane alias with colour-only redefinition",
]


@dataclass
class Declaration:
    """One source construct, accepted or rejected."""

    line: int
    source: str
    kind: str
    accepted: bool


@dataclass
class Rejection:
    """A declaration the parser could not read (§4.4)."""

    line: int
    source: str
    code: str

    def to_json(self) -> dict[str, Any]:
        return {"line": self.line, "source": self.source, "code": self.code}


@dataclass
class Violation:
    """A format violation: recorded, never fatal (§5.6)."""

    code: str
    detail: str
    element_id: str | None = None
    line: int | None = None

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"code": self.code, "detail": self.detail}
        if self.element_id is not None:
            out["element_id"] = self.element_id
        if self.line is not None:
            out["line"] = self.line
        return out


@dataclass
class Element:
    """A graded element (§5.1, §5.2).

    `label_raw` is verbatim and used by the rule layer; `label_norm` is used for
    embedding only (§5.4). Extra structured fields the rule layer needs live in
    `fields`.
    """

    element_id: str
    kind: str
    label_raw: str
    label_norm: str
    line: int | None = None
    fields: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "element_id": self.element_id,
            "kind": self.kind,
            "label_raw": self.label_raw,
            "label_norm": self.label_norm,
        }
        if self.line is not None:
            out["line"] = self.line
        out.update(self.fields)
        return out


@dataclass
class ParseResult:
    """Everything one diagram's parse produced."""

    elements: list[Element] = field(default_factory=list)
    declarations: list[Declaration] = field(default_factory=list)
    rejections: list[Rejection] = field(default_factory=list)
    violations: list[Violation] = field(default_factory=list)
    dropped: list[dict[str, Any]] = field(default_factory=list)
    parse_error: str | None = None
    # Control-flow IR: needed by the transition walk (§5.5) and the control
    # checklist (§8), but control nodes never enter a denominator (§5.2).
    graph: dict[str, Any] = field(default_factory=dict)

    @property
    def total_declarations(self) -> int:
        return len(self.declarations)

    @property
    def accepted_declarations(self) -> int:
        return sum(1 for d in self.declarations if d.accepted)

    def validity(self) -> float:
        """Syntax Validity (§4.1).

        A file that cannot be tokenized at all is 0.0 with `total_declarations`
        recorded as 0 and `parse_error` set (§4.1).

        A diagram that tokenizes but declares nothing is a different case: §13
        requires it to pass the gate at validity 1.0 and then score Recall 0 and
        Precision 0 -- *measured, and nothing matched* -- rather than `n/a`.
        An empty ratio is vacuously perfect: nothing was rejected.
        """
        if self.parse_error is not None:
            return 0.0
        if self.total_declarations == 0:
            return 1.0
        return self.accepted_declarations / self.total_declarations

    def syntax_json(self) -> dict[str, Any]:
        """The per-diagram block of `00_syntax.json` (§4.4)."""
        return {
            "validity": round(self.validity(), 4),
            "accepted": self.accepted_declarations,
            "total": 0 if self.parse_error is not None else self.total_declarations,
            "parse_error": self.parse_error,
            "rejections": [r.to_json() for r in self.rejections],
        }
