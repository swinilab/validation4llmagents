from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from interfaces.base import GenerationResult, IGenerationAgent, Status

try:
    import chatdev.sdk
    from chatdev import run_workflow
    HAS_CHATDEV = True
except ImportError:
    HAS_CHATDEV = False


class ChatDevGenerationAgent(IGenerationAgent):
    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config.get("agent", {})

    def generate(self, prompt: str, run_id: str | None = None) -> GenerationResult:
        generated_dir = Path(self._config.get("generated_dir", "generated"))
        workdir = Path(self._config.get("workdir", "."))
        model = self._config.get("model", "qwen2.5-coder:7b")
        api_base = self._config.get("api_base", "http://localhost:11434/v1")
        api_key = self._config.get("api_key", "ollama")
        workflow_rel = self._config.get("workflow", "agents/chatdev.yaml")
        timeout_seconds = self._config.get("timeout", 1800)
        timeout = float(timeout_seconds) if timeout_seconds is not None else None

        dir_name = run_id if run_id else f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        run_output_dir = generated_dir / dir_name
        run_output_dir.mkdir(parents=True, exist_ok=True)

        # 1. Preferred: Run via ChatDev SDK if installed
        if HAS_CHATDEV:
            chatdev.sdk.OUTPUT_ROOT = generated_dir
            yaml_path = workdir / workflow_rel

            try:
                result = run_workflow(
                    yaml_file=yaml_path,
                    task_prompt=prompt,
                    variables={
                        "BASE_URL": api_base,
                        "API_KEY": api_key,
                        "MODEL_NAME": model,
                    },
                )
                code_path = str(result.output_dir / "code_workspace") if result.output_dir else str(run_output_dir)
                return GenerationResult(
                    status=Status.PASS if result.success else Status.FAIL,
                    model=model,
                    code=code_path,
                    output_dir=Path(code_path),
                )
            except Exception as exc:
                print(f"ChatDev execution encountered an error: {exc}. Falling back to direct Ollama generation.")

        # 2. Fallback: Direct OpenAI-compatible generation via local Ollama
        print(f"Executing generation via local Ollama API ({api_base}, model={model})...")
        endpoint = f"{api_base.rstrip('/')}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        stream_enabled = bool(self._config.get("stream", True))

        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are an expert requirements engineer and software architect.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": float(self._config.get("temperature", 0.2)),
            "stream": stream_enabled,
        }

        try:
            if stream_enabled:
                resp = requests.post(endpoint, json=payload, headers=headers, timeout=timeout, stream=True)
                if resp.status_code != 200:
                    print(f"Ollama API returned error HTTP {resp.status_code}: {resp.text}")
                    return GenerationResult(
                        status=Status.FAIL,
                        model=model,
                        code=str(run_output_dir),
                        output_dir=run_output_dir,
                        metadata={"error": f"HTTP {resp.status_code}: {resp.text}"},
                    )

                content_chunks: list[str] = []
                print("\n--- Live Generation Output ---")
                for line in resp.iter_lines():
                    if not line:
                        continue
                    line_str = line.decode("utf-8")
                    if line_str.startswith("data: "):
                        line_str = line_str[6:].strip()
                    if line_str == "[DONE]":
                        break
                    try:
                        chunk_json = json.loads(line_str)
                        choices = chunk_json.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            token = delta.get("content", "")
                            if token:
                                sys.stdout.write(token)
                                sys.stdout.flush()
                                content_chunks.append(token)
                    except json.JSONDecodeError:
                        continue
                print("\n--- End of Generation ---\n")
                content = "".join(content_chunks)
                usage = {}
            else:
                resp = requests.post(endpoint, json=payload, headers=headers, timeout=timeout)
                if resp.status_code != 200:
                    print(f"Ollama API returned error HTTP {resp.status_code}: {resp.text}")
                    return GenerationResult(
                        status=Status.FAIL,
                        model=model,
                        code=str(run_output_dir),
                        output_dir=run_output_dir,
                        metadata={"error": f"HTTP {resp.status_code}: {resp.text}"},
                    )

                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})

            # Save full generation output
            (run_output_dir / "generation_raw.md").write_text(content, encoding="utf-8")

            # Extract distinct files mentioned in prompt (srs.md, class.puml, activity.puml, requirements.json)
            self._extract_files(content, run_output_dir)

            return GenerationResult(
                status=Status.PASS,
                model=model,
                code=str(run_output_dir),
                output_dir=run_output_dir,
                metadata={"usage": usage},
            )

        except requests.exceptions.ConnectionError as exc:
            msg = f"Cannot connect to Ollama at {api_base}. Ensure Ollama is running (`ollama serve`)."
            print(f"Generation error: {msg}")
            return GenerationResult(
                status=Status.ERROR,
                model=model,
                code=str(run_output_dir),
                output_dir=run_output_dir,
                metadata={"error": msg},
            )
        except Exception as exc:
            print(f"Unexpected generation error: {exc}")
            return GenerationResult(
                status=Status.ERROR,
                model=model,
                code=str(run_output_dir),
                output_dir=run_output_dir,
                metadata={"error": str(exc)},
            )

    @staticmethod
    def _extract_files(content: str, out_dir: Path) -> None:
        """Extract tagged code blocks or markdown sections into target files."""
        # Extract PlantUML diagrams
        class_match = re.search(r"@startuml\s+classdiagram.*?@enduml", content, re.DOTALL)
        if class_match:
            (out_dir / "class.puml").write_text(class_match.group(0), encoding="utf-8")

        activity_match = re.search(r"@startuml\s+activity.*?@enduml", content, re.DOTALL)
        if activity_match:
            (out_dir / "activity.puml").write_text(activity_match.group(0), encoding="utf-8")

        # Extract JSON requirement listing
        json_match = re.search(r"```json\s*(\[\s*\{.*?\}\s*\])\s*```", content, re.DOTALL)
        if json_match:
            (out_dir / "requirements.json").write_text(json_match.group(1), encoding="utf-8")
        else:
            # Fallback direct array match
            json_arr = re.search(r"(\[\s*\{\s*\"id\".*?\}\s*\])", content, re.DOTALL)
            if json_arr:
                (out_dir / "requirements.json").write_text(json_arr.group(1), encoding="utf-8")

        # Always save srs.md
        (out_dir / "srs.md").write_text(content, encoding="utf-8")