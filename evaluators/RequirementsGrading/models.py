"""models.py — Data structures for RequirementsGrading pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


@dataclass
class Unit:
    unit_id: str
    parent_id: str
    kind: Literal["ac", "nfr"]
    text_raw: str
    text_norm: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "parent_id": self.parent_id,
            "kind": self.kind,
            "text_raw": self.text_raw,
            "text_norm": self.text_norm,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Unit:
        return cls(
            unit_id=data["unit_id"],
            parent_id=data["parent_id"],
            kind=data["kind"],
            text_raw=data["text_raw"],
            text_norm=data["text_norm"],
        )


@dataclass
class FormatViolation:
    unit_id: str
    code: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "code": self.code,
            "detail": self.detail,
        }


@dataclass
class Candidate:
    gold_id: str
    gen_id: str
    cosine: float
    excluded: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "gold_id": self.gold_id,
            "gen_id": self.gen_id,
            "cosine": round(float(self.cosine), 4),
            "excluded": self.excluded,
        }


@dataclass
class AxisResult:
    gold_id: str
    gen_id: str
    verdict: Literal["PASS", "FAIL", "MANUAL"]
    failed_axis: str | None
    detail: str | None
    source: Literal["rule", "ledger", "default"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "gold_id": self.gold_id,
            "gen_id": self.gen_id,
            "verdict": self.verdict,
            "failed_axis": self.failed_axis,
            "detail": self.detail,
            "source": self.source,
        }
