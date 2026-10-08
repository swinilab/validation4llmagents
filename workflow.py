"""workflow.py — Minimal pipeline orchestration logic.

Executes:
  1. Generation: calls generation agent with specified prompt template
  2. Validation: runs Stage 1 diagram validity, flattening, and quality checks
  3. Report: writes consolidated execution report
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from interfaces.base import GenerationResult, Status, ValidationResult
from workflow_factory import PipelineComponents

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def _read_prompt(cfg: dict[str, Any], prompt_override: str | None = None) -> str:
    workdir = Path(cfg.get("workdir", "."))
    rel_path = prompt_override or cfg.get("agent", {}).get("prompt_template", "prompts/v1.0.md")
    full_path = (workdir / rel_path).resolve()

    if not full_path.is_file():
        print(f"❌ Error: Prompt file not found at path: '{full_path}'", file=sys.stderr)
        sys.exit(1)

    return full_path.read_text(encoding="utf-8").strip()


def run_generation(components: PipelineComponents, prompt: str, run_id: str) -> GenerationResult:
    print(f"\n==================================================")
    print(f"  PHASE 1: GENERATION (ChatDev + Ollama)")
    print(f"==================================================")
    result = components.generation_agent.generate(prompt, run_id=run_id)
    if result.status == Status.PASS:
        print(f"  ✅ Generation completed successfully")
    else:
        print(f"  ⚠️ Generation status: {result.status}")
    print(f"  Model  : {result.model}")
    print(f"  Output : {result.code}")
    return result


def run_validation(
    components: PipelineComponents,
    generation: GenerationResult,
    run_id: str,
) -> list[ValidationResult]:
    print(f"\n==================================================")
    print(f"  PHASE 2: VALIDATION (Stage 1 SRS & Diagram Checks)")
    print(f"==================================================")
    result = components.stage1_validator.validate(generation, run_id=run_id)

    if result.passed:
        print(f"  ✅ {result.name}: passed ({result.message})")
    else:
        print(f"  ❌ {result.name}: failed ({result.message})")

    return [result]


def run_pipeline(
    components: PipelineComponents,
    phase: str = "all",
    run_id: str = "RUN01",
    prompt_file: str | None = None,
) -> None:
    cfg = components.config
    generation: GenerationResult | None = None
    validation_results: list[ValidationResult] = []

    # 1. Generation Phase
    if phase in ("gen", "all"):
        prompt = _read_prompt(cfg, prompt_file)
        generation = run_generation(components, prompt, run_id=run_id)

    # 2. Validation Phase
    if phase in ("val", "all"):
        if generation is None:
            # Standalone validation mode: use code path from config
            val_cfg = cfg.get("validation", {})
            target_path = val_cfg.get("generated") or val_cfg.get("code", "generated")
            generation = GenerationResult(
                status=Status.PASS,
                model="standalone",
                code=target_path,
                output_dir=Path(target_path),
            )
        if generation.status != Status.PASS:
            print(f"\n⚠️ Skipping validation phase: generation did not succeed (status: {generation.status}).")
            validation_results = [
                ValidationResult(
                    stage=1,
                    name="Stage 1 (Diagram & SRS Validity)",
                    passed=False,
                    message=f"Skipped due to generation failure ({generation.status})",
                    details={"generation_metadata": generation.metadata},
                )
            ]
        else:
            validation_results = run_validation(components, generation, run_id=run_id)

    # 3. Report Export
    print(f"\n==================================================")
    print(f"  EXPORTING REPORT")
    print(f"==================================================")
    all_passed = all(vr.passed for vr in validation_results) if validation_results else (
        generation is not None and generation.status == Status.PASS
    )

    report_path = components.report_writer.write(
        generation=generation,
        validation_results=validation_results,
        all_passed=all_passed,
        run_id=run_id,
    )

    if all_passed:
        print(f"  ✅ Complete → {report_path}")
    else:
        print(f"  ⚠️ Completed with issues → {report_path}")
