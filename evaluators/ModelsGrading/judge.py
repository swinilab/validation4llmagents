"""LLM judge for the rubric stage (spec §7.6).

The judge is the callable `s7_rubric.run(..., judge=...)` expects: it takes the
fixed prompt and returns the model's reply as text.

§7.6 requires a pinned snapshot in `config.judge_model`, `temperature = 0`, a
model from a different family than the model under evaluation, and the full
output logged. The model id, endpoint (`judge_api_base`), key (`judge_api_key`)
and temperature all come from `config.yaml`; this module only carries the
transport, which matches the generation agent's OpenAI-compatible convention
(`agents/gen.py`). An empty `judge_api_key` falls back to the environment.
"""

from __future__ import annotations

import os
from urllib.parse import urlparse

import requests

REQUEST_TIMEOUT_SECONDS = 180


class JudgeError(RuntimeError):
    """The judge could not be reached, or returned nothing usable."""


def make_judge(config: dict, api_base: str | None = None):
    """Build the judge callable from the pinned config (§7.6).

    Returns None when `config.judge_model` is unset, which is the honest state:
    with no judge the unmatched elements stay pending rather than being scored
    by a model the manifest cannot name.
    """
    model = config.get("judge_model")
    if not model:
        return None

    temperature = config["judge_temperature"]
    api_base = api_base or config["judge_api_base"]
    is_openrouter = urlparse(api_base).hostname == "openrouter.ai"
    variable = "OPENROUTER_API_KEY" if is_openrouter else "OPENAI_API_KEY"
    api_key = config.get("judge_api_key") or os.environ.get(variable)
    if not api_key:
        raise JudgeError(
            f"the rubric judge {model!r} needs an API key: set judge_api_key in "
            f"config.yaml or the {variable} environment variable")

    def judge(prompt: str) -> str:
        response = requests.post(
            f"{api_base.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}",
                     "Content-Type": "application/json"},
            json={
                "model": model,
                "temperature": temperature,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if response.status_code != 200:
            raise JudgeError(
                f"judge {model!r} returned HTTP {response.status_code}: "
                f"{response.text[:400]}")
        payload = response.json()
        try:
            return payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise JudgeError(
                f"judge {model!r} returned an unexpected payload: {error}") from error

    return judge
