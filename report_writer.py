"""report_writer.py — Raw report of a pipeline run.

Writes `report_<run dir name>.json` into the run directory: the generation record
and the result of every grading module that ran (requirements, models, VMX). The
JSON is the report; the text version is rendered from it by `report_to_txt.py`
and written next to it.

One run directory has one report, whatever the invocation. A call updates only
what it ran: `--grade reqs` followed by `--grade models` leaves both modules in
the report, running a module again replaces its entry, and a grade-only call does
not overwrite the generation record written by `--phase gen`. The full per-module
output (metrics, review files, logs) stays in `<run dir>/grading/<module>/`.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from interfaces.base import (
    GenerationResult,
    IReportWriter,
    ValidationResult,
)
from report_to_txt import render

SCHEMA = 1

# The generation record `_standalone_generation` fabricates when grading an
# existing run; it must never replace a real one.
STANDALONE_MODEL = "standalone"

# Config keys the grading modules use, recorded with each module's result so the
# report states the models that module was run with.
MODEL_KEYS = ("embedding_model", "embedding_revision", "judge_model")


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _posix(path: object) -> str:
    return str(path).replace("\\", "/")


def _write_atomic(path: Path, text: str) -> None:
    """Write through a temp file so an interrupted run never leaves half a report."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


class TextReportWriter(IReportWriter):
    """Keeps the raw JSON report of a run and renders its text version."""

    def __init__(self, report_dir: str = "generated/reports/",
                 config: dict | None = None) -> None:
        self._report_dir = report_dir
        # The pipeline config: each grading entry records the models it used.
        self._config = config or {}
        self.json_path: str | None = None
        self._path: str | None = None

    def write(
        self,
        generation: GenerationResult | None,
        validation_results: list[ValidationResult],
        all_passed: bool,
        run_id: str | None = None,
    ) -> str:
        """Merge this invocation into the run's report; returns the text report path."""
        # The report sits next to the generator's output (the run dir) when there is one.
        run_dir = None
        if generation and generation.output_dir and Path(generation.output_dir).is_dir():
            run_dir = Path(generation.output_dir)

        base_dir = run_dir or Path(self._report_dir)
        # A run dir gives the report a stable name, so invocations with different
        # flags (or a different --run-id) still update the same report.
        key = (run_dir.name if run_dir
               else run_id or datetime.now().strftime("%Y%m%d_%H%M%S"))
        base_dir.mkdir(parents=True, exist_ok=True)
        json_path = base_dir / f"report_{key}.json"
        txt_path = json_path.with_suffix(".txt")

        report = self._load(json_path)
        report.update(schema=SCHEMA, run_id=run_id or report.get("run_id") or key,
                      target=_posix(base_dir), updated_at=_now())
        report.setdefault("created_at", report["updated_at"])
        self._merge_generation(report, generation)
        for result in validation_results:
            kind = (result.details or {}).get("grading_kind") or "grading"
            report.setdefault("grading", {})[kind] = self._grading_entry(kind, result)

        _write_atomic(json_path, json.dumps(report, indent=2, ensure_ascii=False,
                                            default=str) + "\n")
        _write_atomic(txt_path, render(report))
        self.json_path, self._path = str(json_path), str(txt_path)
        return self._path

    @staticmethod
    def _load(path: Path) -> dict:
        if not path.is_file():
            return {}
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return report if isinstance(report, dict) else {}

    @staticmethod
    def _merge_generation(report: dict, generation: GenerationResult | None) -> None:
        if generation is None:
            return
        if generation.model == STANDALONE_MODEL and report.get("generation"):
            return
        metadata = generation.metadata or {}
        report["generation"] = {
            "status": getattr(generation.status, "value", str(generation.status)),
            "model": generation.model,
            "agent": metadata.get("agent"),
            "reasoning": metadata.get("reasoning"),
            "code": _posix(generation.code),
            "output_dir": _posix(generation.output_dir) if generation.output_dir else None,
            "recorded_at": _now(),
        }

    def _grading_entry(self, kind: str, result: ValidationResult) -> dict:
        entry = {
            "name": result.name,
            "passed": result.passed,
            "message": result.message,
            "ran_at": _now(),
            "details": result.details or {},
        }
        if kind in ("reqs", "models"):
            entry["models_used"] = {k: self._config.get(k) for k in MODEL_KEYS}
        return entry
