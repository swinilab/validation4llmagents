"""workflow.py — Minimal pipeline orchestration logic.

Executes:
  1. Generation: calls generation agent with specified prompt template
  2. Evaluation: runs Stage 1 diagram validity, flattening, and quality checks
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

    prompt_text = full_path.read_text(encoding="utf-8").strip()

    inputs_rel_path = cfg.get("agent", {}).get("prompt_inputs")
    if inputs_rel_path:
        inputs_path = (workdir / inputs_rel_path).resolve()
        if inputs_path.is_file():
            try:
                inputs_data = json.loads(inputs_path.read_text(encoding="utf-8"))
                
                # Format FR_INPUT
                if "{{FR_INPUT}}" in prompt_text and "FR_INPUT" in inputs_data:
                    fr_lines = []
                    for req_id, req_data in inputs_data["FR_INPUT"].items():
                        fr_lines.append(f"- **{req_id}**: {req_data.get('statement', '')}")
                    prompt_text = prompt_text.replace("{{FR_INPUT}}", "\n".join(fr_lines))
                
                # Format NFR_INPUT
                if "{{NFR_INPUT}}" in prompt_text and "NFR_INPUT" in inputs_data:
                    nfr_lines = []
                    for req_id, req_data in inputs_data["NFR_INPUT"].items():
                        nfr_lines.append(f"- **{req_id}**: {req_data.get('statement', '')}")
                    prompt_text = prompt_text.replace("{{NFR_INPUT}}", "\n".join(nfr_lines))

            except Exception as e:
                print(f"⚠️ Warning: Failed to parse or inject prompt inputs from {inputs_path}: {e}", file=sys.stderr)

    return prompt_text


def run_generation(components: PipelineComponents, prompt: str, run_id: str) -> GenerationResult:
    print(f"\n==================================================")
    print(f"  PHASE 1: GENERATION")
    print(f"==================================================")
    result = components.generation_agent.generate(prompt, run_id=run_id)
    if result.status == Status.PASS:
        print(f"  ✅ Generation completed successfully")
    else:
        print(f"  ⚠️ Generation status: {result.status}")
    print(f"  LLM         : {result.model}")
    print(f"  Reasoning   : ")
    print(f"  Agent       : ChatDev")
    print(f"  SRS Package : {result.code}")
    return result


def run_validation(
    components: PipelineComponents,
    generation: GenerationResult,
    run_id: str,
) -> list[ValidationResult]:
    print(f"\n==================================================")
    print(f"  PHASE 2: EVALUATION (Stage 1 SRS & Diagram Checks)")
    print(f"==================================================")
    result = components.stage1_validator.validate(generation, run_id=run_id)

    status_icon = "✅" if result.passed else "❌"
    status_text = "passed" if result.passed else "failed"
    print(f"  {status_icon} {result.name}: {status_text}")

    d = result.details
    if d:
        # 1. Completeness
        vmx = d.get("vmx")
        print(f"    1. COMPLETENESS:")
        if vmx and not vmx.get("missing"):
            cov_rate = vmx.get("coverage_rate", 0.0) * 100
            cov_comp = vmx.get("coverage_complete", 0)
            cov_rows = vmx.get("rows", 0)
            print(f"       - VMX Requirement Coverage : {cov_rate:.1f}% ({cov_comp}/{cov_rows} complete)")
        else:
            print(f"       - VMX Requirement Coverage : ❌ Missing VMX.csv (0.0%)")

        # 2. Correctness
        valid_d = d.get("valid_diagrams", 0)
        total_d = d.get("total_diagrams", 0)
        cl_score = d.get("class_score", 0.0)
        cl_corr = d.get("class_correct", 0)
        cl_tot = d.get("class_total", 0)
        ac_score = d.get("act_score", 0.0)
        ac_corr = d.get("act_correct", 0)
        ac_tot = d.get("act_total", 0)

        print(f"    2. CORRECTNESS:")
        print(f"       - Structural Model Syntax   : score={cl_score} ({cl_corr}/{cl_tot} elements)")
        print(f"       - Behavioral Model Syntax   : score={ac_score} ({ac_corr}/{ac_tot} elements)")
        if vmx and not vmx.get("missing"):
            int_rate = vmx.get("integrity_rate", 0.0) * 100
            int_fnd = vmx.get("integrity_found", 0)
            int_tot = vmx.get("integrity_total", 0)
            print(f"       - VMX Referential Integrity : {int_rate:.1f}% ({int_fnd}/{int_tot} references valid)")
        else:
            print(f"       - VMX Referential Integrity : ❌ Missing VMX.csv (0.0%)")

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

    # 2. Evaluation Phase
    if phase in ("val", "all"):
        if generation is None:
            # Standalone evaluation mode: use code path from config
            eval_cfg = cfg.get("evaluation", cfg.get("validation", {}))
            target_path = eval_cfg.get("generated") or eval_cfg.get("code", "generated")
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
