from __future__ import annotations

import json
import os
import queue
import re
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import requests
from interfaces.base import GenerationResult, IGenerationAgent, Status

GENERATION_PROGRESS_INTERVAL_SECONDS = 5.0

# ChatDev's OpenAI provider falls back to this when a node sets no temperature
# (runtime/node/agent/providers/openai_provider.py in the chatdev package).
CHATDEV_DEFAULT_TEMPERATURE = 0.7

try:
    import chatdev.sdk
    import yaml
    from chatdev import run_workflow
    from chatdev.config import AgentConfig
    HAS_CHATDEV = True
    CHATDEV_IMPORT_ERROR = None
except ImportError as exc:
    HAS_CHATDEV = False
    CHATDEV_IMPORT_ERROR = exc


def _agent_model_overrides(yaml_file: str | Path, model: str) -> dict[str, Any]:
    """Override the model name on every agent node of the workflow YAML.

    Only `model` is set, so temperature and the other params stay at the
    workflow's / ChatDev's defaults.
    """
    path = chatdev.sdk._resolve_yaml_path(yaml_file)
    graph = yaml.safe_load(path.read_text(encoding="utf-8")).get("graph", {})
    return {
        node["id"]: AgentConfig(model=model)
        for node in graph.get("nodes", [])
        if node.get("type") == "agent"
    }


class ChatDevGenerationAgent(IGenerationAgent):
    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config.get("agent", {})

    def generate(self, prompt: str, run_id: str | None = None) -> GenerationResult:
        generated_dir = Path(self._config.get("generated_dir", "generated"))
        workdir = Path(self._config.get("workdir", "."))
        model = self._config.get("model", "qwen2.5-coder:7b")
        api_base = self._config.get("api_base", "http://localhost:11434/v1")
        openrouter_key = os.environ.get("OPENROUTER_API_KEY")
        is_openrouter = urlparse(api_base).hostname == "openrouter.ai"
        api_key = (
            (openrouter_key if is_openrouter else None)
            or self._config.get("api_key", "ollama")
        )
        workflow_rel = self._config.get("workflow", "agents/chatdev.yaml")
        timeout_seconds = self._config.get("timeout", 1800)
        timeout = float(timeout_seconds) if timeout_seconds is not None else None

        dir_name = run_id if run_id else f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        run_output_dir = generated_dir / dir_name
        run_output_dir.mkdir(parents=True, exist_ok=True)

        if is_openrouter and not openrouter_key:
            message = "OPENROUTER_API_KEY is required when agent.api_base uses OpenRouter."
            print(f"Generation error: {message}", file=sys.stderr)
            return GenerationResult(
                status=Status.ERROR,
                model=model,
                code=str(run_output_dir),
                output_dir=run_output_dir,
                metadata={"error": message},
            )

        # 1. Preferred: Run via ChatDev SDK if installed
        if HAS_CHATDEV:
            # ChatDev writes its sdk_<workflow>_<ts>/ folder straight into the
            # RUN dir and is left untouched; pipeline results sit next to it.
            chatdev.sdk.OUTPUT_ROOT = run_output_dir
            yaml_path = workdir / workflow_rel

            try:
                # yaml_file = yaml_path
                yaml_file = "ChatDev_v1.yaml"
                result = run_workflow(
                    yaml_file=yaml_file,
                    task_prompt=prompt,
                    variables={
                        "BASE_URL": api_base,
                        "API_KEY": api_key,
                        "MODEL_NAME": model,
                    },
                    agent_configs=_agent_model_overrides(yaml_file, model),
                )
                code_path = str(result.output_dir / "code_workspace") if result.output_dir else str(run_output_dir)
                return GenerationResult(
                    status=Status.PASS if result.success else Status.FAIL,
                    model=model,
                    code=code_path,
                    output_dir=run_output_dir,
                    metadata={
                        "agent": "ChatDev",
                        "reasoning": f"temperature {CHATDEV_DEFAULT_TEMPERATURE}",
                    },
                )
            except Exception:
                print("ChatDev execution failed:", file=sys.stderr)
                traceback.print_exc()
                sys.exit(1)
        else:
            print(f"ChatDev SDK is not available: {CHATDEV_IMPORT_ERROR!r}", file=sys.stderr)
            sys.exit(1)

        # 2. Fallback: Direct OpenAI-compatible generation
        print(f"Executing generation via API ({api_base}, model={model})...")
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
                    "content": (
                        "You are an expert requirements engineer and software architect. "
                        "You MUST produce all 5 required files sequentially in your single response:\n"
                        "1. `srs.md` (the complete SRS document in Markdown)\n"
                        "2. `structural.puml` (raw PlantUML from @startuml classdiagram to @enduml)\n"
                        "3. `behavioral.puml` (raw PlantUML from @startuml activity to @enduml)\n"
                        "4. `requirements.json` (raw JSON array of requirements)\n"
                        "5. `VMX.csv` (raw CSV traceability matrix starting with header: SRS-Req-ID,Source-Input-ID,Structural-Elements,Behavorial-Elements)\n\n"
                        "CRITICAL INSTRUCTION: Do NOT stop after writing `srs.md`! You must immediately proceed to output the complete source code and content for all remaining 4 files in the exact order specified."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": float(self._config.get("temperature", 0.2)),
            "stream": stream_enabled,
        }
        max_tokens = self._config.get("max_tokens")
        if max_tokens:
            payload["max_tokens"] = int(max_tokens)

        try:
            if stream_enabled:
                events: queue.Queue[tuple[str, Any]] = queue.Queue()

                def read_stream() -> None:
                    try:
                        with requests.post(
                            endpoint,
                            json=payload,
                            headers=headers,
                            timeout=timeout,
                            stream=True,
                        ) as response:
                            if response.status_code != 200:
                                events.put(("http_error", (response.status_code, response.text)))
                                return
                            for response_line in response.iter_lines():
                                events.put(("line", response_line))
                    except Exception as exc:
                        events.put(("error", exc))
                    finally:
                        events.put(("done", None))

                worker = threading.Thread(target=read_stream, daemon=True)
                worker.start()
                content_chunks: list[str] = []
                print("\n--- Live Generation Output ---")
                finished = False
                while not finished:
                    event, event_data = events.get()

                    if event == "done":
                        finished = True
                        continue
                    if event == "error":
                        raise event_data
                    if event == "http_error":
                        status_code, response_text = event_data
                        error = f"HTTP {status_code}: {response_text}"
                        print(f"API returned error {error}")
                        return GenerationResult(
                            status=Status.FAIL,
                            model=model,
                            code=str(run_output_dir),
                            output_dir=run_output_dir,
                            metadata={"error": error},
                        )
                    if event != "line":
                        continue

                    line = event_data
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
                    provider = "API"
                    print(f"{provider} returned error HTTP {resp.status_code}: {resp.text}")
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

            # Save all 5 artifacts + raw output into artifacts/ subfolder
            artifacts_dir = run_output_dir / "artifacts"
            artifacts_dir.mkdir(parents=True, exist_ok=True)
            (artifacts_dir / "generation_raw.md").write_text(content, encoding="utf-8")

            # Extract distinct artifact files into artifacts/
            self._extract_files(content, artifacts_dir)

            return GenerationResult(
                status=Status.PASS,
                model=model,
                code=str(run_output_dir),
                output_dir=run_output_dir,
                metadata={"usage": usage},
            )

        except requests.exceptions.ConnectionError as exc:
            msg = f"Cannot connect to API at {api_base}. Ensure the model server is running."
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
        """Extract tagged code blocks or markdown sections into target artifact files."""
        # Extract PlantUML diagrams
        # 1. Primary label match (from prompt instructions)
        structural_puml: str | None = None
        behavioral_puml: str | None = None

        m_st = re.search(r"@startuml\s+(?:classdiagram|class\b|structural\b).*?@enduml", content, re.DOTALL | re.IGNORECASE)
        if m_st:
            structural_puml = m_st.group(0)

        m_bh = re.search(r"@startuml\s+(?:activity\b|behavioral\b).*?@enduml", content, re.DOTALL | re.IGNORECASE)
        if m_bh:
            behavioral_puml = m_bh.group(0)

        # 2. Resilient fallback: inspect all @startuml ... @enduml blocks if either was not found by exact label
        all_puml = re.findall(r"@startuml.*?@enduml", content, re.DOTALL)
        if not structural_puml or not behavioral_puml:
            for puml in all_puml:
                # Class / structural indicators
                if not structural_puml and re.search(r"\b(class|enum|interface)\s+\w+", puml):
                    structural_puml = puml
                # Activity / behavioral indicators
                elif not behavioral_puml and re.search(r"(\|[A-Za-z0-9_ ]+\||start\s*[\n;]|:\s*[^;]+;)", puml):
                    behavioral_puml = puml

            # Positional fallback if there are at least 2 diagrams and one is still missing
            if len(all_puml) >= 2:
                if not structural_puml:
                    structural_puml = all_puml[0]
                if not behavioral_puml:
                    behavioral_puml = all_puml[1]

        if structural_puml:
            (out_dir / "structural.puml").write_text(structural_puml, encoding="utf-8")
        if behavioral_puml:
            (out_dir / "behavioral.puml").write_text(behavioral_puml, encoding="utf-8")

        # Extract JSON requirement listing (with auto-repair for truncated JSON)
        repaired_json = ChatDevGenerationAgent._extract_and_repair_json(content)
        if repaired_json:
            (out_dir / "requirements.json").write_text(repaired_json, encoding="utf-8")

        # Extract VMX.csv (traceability matrix)
        # Look for a fenced CSV block or a table starting with the VMX header (allowing typo Behavorial or Behavioral)
        vmx_pattern = r"SRS-Req-ID\s*,\s*Source-Input-ID\s*,\s*Structural-Elements\s*,\s*Behav[a-zA-Z]+-Elements"
        vmx_fenced = re.search(
            rf"```(?:csv)?\s*({vmx_pattern}.*?)```",
            content,
            re.DOTALL | re.IGNORECASE,
        )
        if vmx_fenced:
            (out_dir / "VMX.csv").write_text(vmx_fenced.group(1).strip(), encoding="utf-8")
        else:
            # Fallback: bare CSV lines after header
            vmx_bare = re.search(
                rf"({vmx_pattern}[^\n]*\n(?:[^\n]+\n?)+)",
                content,
                re.DOTALL | re.IGNORECASE,
            )
            if vmx_bare:
                (out_dir / "VMX.csv").write_text(vmx_bare.group(1).strip(), encoding="utf-8")

        # Always save srs.md (full generation as SRS document)
        (out_dir / "srs.md").write_text(content, encoding="utf-8")

    @staticmethod
    def _extract_and_repair_json(content: str) -> str | None:
        """Extract JSON requirement array, repairing truncated closing brackets if necessary."""
        candidate = None

        # 1. Look for fenced code block (closed or unclosed/truncated)
        m = re.search(r"```(?:json)?\s*(\[\s*\{.*?)\s*```", content, re.DOTALL)
        if m:
            candidate = m.group(1).strip()
        else:
            m = re.search(r"```(?:json)?\s*(\[\s*\{.*)", content, re.DOTALL)
            if m:
                candidate = m.group(1).strip()
            else:
                m = re.search(r"(\[\s*\{\s*\"id\".*)", content, re.DOTALL)
                if m:
                    candidate = m.group(1).strip()

        if not candidate:
            return None

        # 2. Try parsing directly
        try:
            return json.dumps(json.loads(candidate), indent=2)
        except Exception:
            pass

        # 3. Try bracket closure heuristics
        closing_sequences = [
            "\n]\n}\n]",
            "\n}\n]\n}\n]",
            "\n}\n]",
            "\n]",
            "\n}\n}\n]",
        ]
        for seq in closing_sequences:
            test_str = candidate.rstrip().rstrip(",") + seq
            try:
                parsed = json.loads(test_str)
                return json.dumps(parsed, indent=2)
            except Exception:
                pass

        # 4. Backward scan to last valid object brace '}' and close array
        last_idx = len(candidate)
        while True:
            last_brace = candidate.rfind("}", 0, last_idx)
            if last_brace == -1:
                break
            for closing in ["\n]", "\n]\n}"]:
                test_str = candidate[:last_brace + 1].strip().rstrip(",") + closing
                try:
                    parsed = json.loads(test_str)
                    return json.dumps(parsed, indent=2)
                except Exception:
                    pass
            last_idx = last_brace

        return candidate