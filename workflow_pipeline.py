"""workflow.py — Minimal pipeline orchestration logic.

Executes:
  1. Generation: calls generation agent with specified prompt template
  2. Grading: runs the selected grading modules (requirements, models, VMX)
  3. Report: writes consolidated execution report
"""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path
from typing import Any

from interfaces.base import GenerationResult, Status, ValidationResult
from workflow_factory import GRADER_NAMES, PipelineComponents

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def _read_prompt(cfg: dict[str, Any], prompt_override: str | None = None) -> str:
    workdir = Path(cfg.get("workdir", "."))
    rel_path = prompt_override or cfg.get("agent", {}).get("prompt_template", "materials/M1-prompt.md")
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
    print(f"  Reasoning   : {result.metadata.get('reasoning', '')}")
    print(f"  Agent       : {result.metadata.get('agent', 'ChatDev')}")
    print(f"  SRS Package : {result.code}")
    return result


def _standalone_generation(target: str) -> GenerationResult:
    """Rebuild a GenerationResult from an existing run directory.

    `target` may be the run dir (`generated/RUN_x`, holding the generator's
    `sdk_*/code_workspace`) or a workspace itself. Either way the pipeline's
    own output goes to the run dir, as it does after `--phase gen`.
    """
    path = Path(target)
    workspaces = sorted(path.glob("sdk_*/code_workspace"),
                        key=lambda p: p.stat().st_mtime)
    if workspaces:
        return GenerationResult(status=Status.PASS, model="standalone",
                                code=str(workspaces[-1]), output_dir=path)
    if path.name == "code_workspace" and path.parent.name.startswith("sdk_"):
        return GenerationResult(status=Status.PASS, model="standalone",
                                code=str(path), output_dir=path.parent.parent)
    return GenerationResult(status=Status.PASS, model="standalone",
                            code=target, output_dir=path)


def run_grading(
    components: PipelineComponents,
    generation: GenerationResult,
    run_id: str,
    grade: list[str] | None = None,
    on_pending: str = "provisional",
) -> list[ValidationResult]:
    """Run the selected grading modules (all of them by default).

    Each module writes into the run directory. They always run in the canonical
    order, and one that crashes is reported as failed without costing the
    results of the others.
    """
    selected = [name for name in GRADER_NAMES if not grade or name in grade]
    results: list[ValidationResult] = []
    for name in selected:
        print(f"\n==================================================")
        print(f"  GRADING: {name}")
        print(f"==================================================")
        try:
            result = components.graders[name].validate(
                generation, run_id=run_id, on_pending=on_pending)
        except Exception as error:  # noqa: BLE001 - a crash must not hide the other modules
            traceback.print_exc()
            result = ValidationResult(
                stage=2, name=f"{name} grading", passed=False,
                message=f"crashed: {type(error).__name__}: {error}",
                details={"grading_kind": name, "error": repr(error)})
        icon = "✅" if result.passed else "❌"
        print(f"  {icon} {result.name}: {result.message}")
        grading_dir = (result.details or {}).get("grading_dir")
        if grading_dir:
            print(f"    Results → {grading_dir}")
        results.append(result)
    return results


def run_pipeline(
    components: PipelineComponents,
    phase: str = "all",
    run_id: str = "RUN01",
    prompt_file: str | None = None,
    grade: list[str] | None = None,
    on_pending: str = "provisional",
) -> None:
    cfg = components.config
    generation: GenerationResult | None = None
    validation_results: list[ValidationResult] = []

    # 1. Generation Phase
    if phase in ("gen", "all"):
        prompt = _read_prompt(cfg, prompt_file)
        generation = run_generation(components, prompt, run_id=run_id)

    # 2. Grading Phase
    if phase in ("grade", "all"):
        if generation is None:
            # Standalone grading mode: use code path from config
            eval_cfg = cfg.get("evaluation", cfg.get("validation", {}))
            target_path = eval_cfg.get("generated") or eval_cfg.get("code", "generated")
            generation = _standalone_generation(target_path)
        if generation.status != Status.PASS:
            print(f"\n⚠️ Skipping grading phase: generation did not succeed (status: {generation.status}).")
            validation_results = [
                ValidationResult(
                    stage=2,
                    name="Grading",
                    passed=False,
                    message=f"Skipped due to generation failure ({generation.status})",
                    details={"generation_metadata": generation.metadata},
                )
            ]
        else:
            validation_results = run_grading(
                components, generation, run_id, grade, on_pending)

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
    json_path = getattr(components.report_writer, "json_path", None)
    if json_path:
        print(f"    Raw report → {json_path}")
