from __future__ import annotations

import json
import queue
import re
import sys
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from interfaces.base import GenerationResult, IGenerationAgent, Status

GENERATION_PROGRESS_INTERVAL_SECONDS = 5.0

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
                events: queue.Queue[tuple[str, Any]] = queue.Queue()
                started_at = time.monotonic()
                progress_interval = GENERATION_PROGRESS_INTERVAL_SECONDS
                progress_is_tty = sys.stderr.isatty()
                last_progress_at = started_at
                first_output_at: float | None = None
                output_chunks = 0
                recent_output_at: deque[float] = deque()

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
                print("[Generation] Waiting for Ollama response...", file=sys.stderr, flush=True)
                finished = False
                while not finished:
                    try:
                        event, event_data = events.get(timeout=min(1.0, progress_interval))
                    except queue.Empty:
                        event, event_data = "", None

                    now = time.monotonic()
                    if now - last_progress_at >= progress_interval:
                        elapsed = now - started_at
                        if first_output_at is None:
                            message = f"[Generation] Waiting for first output | elapsed {elapsed:.0f}s"
                        else:
                            while recent_output_at and now - recent_output_at[0] > 10:
                                recent_output_at.popleft()
                            chunk_rate = len(recent_output_at) / min(elapsed, 10)
                            message = (
                                f"[Generation] Generating | elapsed {elapsed:.0f}s"
                                f" | ~{chunk_rate:.1f} output chunks/s"
                            )
                        if progress_is_tty:
                            sys.stderr.write(f"\r{message}")
                            sys.stderr.flush()
                        else:
                            print(message, file=sys.stderr, flush=True)
                        last_progress_at = now
                        continue

                    if event == "done":
                        finished = True
                        continue
                    if event == "error":
                        raise event_data
                    if event == "http_error":
                        status_code, response_text = event_data
                        error = f"HTTP {status_code}: {response_text}"
                        print(f"Ollama API returned error {error}")
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
                                if first_output_at is None:
                                    first_output_at = now
                                output_chunks += 1
                                recent_output_at.append(now)
                                if progress_is_tty:
                                    sys.stderr.write("\r\x1b[2K")
                                    sys.stderr.flush()
                                sys.stdout.write(token)
                                sys.stdout.flush()
                                content_chunks.append(token)
                    except json.JSONDecodeError:
                        continue
                print("\n--- End of Generation ---\n")
                if progress_is_tty:
                    sys.stderr.write("\r\x1b[2K")
                    sys.stderr.flush()
                elapsed = time.monotonic() - started_at
                first_output = (
                    f"{first_output_at - started_at:.1f}s" if first_output_at is not None else "none"
                )
                chunk_rate = output_chunks / elapsed if elapsed else 0.0
                print(
                    f"[Generation] Finished | elapsed {elapsed:.1f}s"
                    f" | first output {first_output} | {output_chunks} output chunks"
                    f" (~{chunk_rate:.1f}/s)",
                    file=sys.stderr,
                    flush=True,
                )
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