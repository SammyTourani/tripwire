"""experiment.llm -- a tiny, dependency-free OpenAI-compatible chat client.

Used by the judge and the candidate generator. Reads OPENAI_API_KEY / OPENAI_BASE_URL
from the env (same contract as `tripwire optimize`; point OPENAI_BASE_URL at OpenRouter,
Groq, etc.). Stdlib only -- no new dependencies."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


class LLMError(RuntimeError):
    pass


def chat(messages, *, model, temperature=None, max_tokens=2048, timeout=120) -> str:
    api_key = os.environ.get("OPENAI_API_KEY")
    base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    if not api_key:
        raise LLMError("OPENAI_API_KEY is not set")
    payload: dict = {"model": model, "messages": messages, "max_tokens": max_tokens}
    if temperature is not None:
        payload["temperature"] = temperature
    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")[:300]
        raise LLMError(f"HTTP {e.code}: {body}") from e
    except Exception as e:  # noqa: BLE001 -- network/JSON failures surface as LLMError
        raise LLMError(f"{type(e).__name__}: {e}") from e
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise LLMError(f"unexpected response shape: {str(data)[:200]}") from e
