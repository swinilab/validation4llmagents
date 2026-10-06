"""Base interfaces and data structures for generation and validation pipelines."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Protocol


class Status(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"
    ERROR = "ERROR"


@dataclass
class GenerationResult:
    """The result of code / artifact generation."""
    status: Status
    model: str
    code: str
    output_dir: Path | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationResult:
    """The result of a validation stage."""
    stage: int
    name: str
    passed: bool
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)


class IGenerationAgent(Protocol):
    def generate(self, prompt: str) -> GenerationResult: ...


class IValidator(Protocol):
    def validate(self, generation: GenerationResult) -> ValidationResult: ...


class ICompilabilityValidator(IValidator, Protocol): ...
class IFunctionalValidator(IValidator, Protocol): ...
class IStaticQualityValidator(IValidator, Protocol): ...


class IReportWriter(Protocol):
    def write(
        self,
        generation: GenerationResult | None,
        validation_results: list[ValidationResult],
        all_passed: bool,
    ) -> Path: ...
