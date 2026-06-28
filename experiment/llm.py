"""experiment.llm -- a tiny, dependency-free OpenAI-compatible chat client.

Used by the judge and the candidate generator. Reads OPENAI_API_KEY / OPENAI_BASE_URL
from the env (same contract as `tripwire optimize`; point OPENAI_BASE_URL at OpenRouter,
Groq, etc.). Stdlib only -- no new dependencies."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

# Transient statuses worth retrying. Free-tier providers (OpenRouter etc.) hand out
# 429s constantly, so without retry a multi-model run mostly collects nothing.
_RETRYABLE = frozenset({408, 425, 429, 500, 502, 503, 504})


class LLMError(RuntimeError):
    pass


def _retry_delay(retry_after, backoff, attempt) -> float:
    """Honour a numeric Retry-After header when present, else exponential backoff.
    Capped so one stuck call can't stall a run for minutes."""
    if retry_after:
        try:
            return min(float(retry_after), 30.0)
        except ValueError:
            pass
    return min(backoff * (2 ** attempt), 30.0)


def chat(
    messages,
    *,
    model,
    temperature=None,
    max_tokens=2048,
    timeout=120,
    max_retries=3,
    backoff=2.0,
) -> str:
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
    data = None
    for attempt in range(max_retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode())
            break
        # HTTPError is a subclass of URLError -- it MUST be caught first.
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "ignore")[:300]
            if e.code in _RETRYABLE and attempt < max_retries:
                time.sleep(_retry_delay(e.headers.get("Retry-After"), backoff, attempt))
                continue
            raise LLMError(f"HTTP {e.code}: {body}") from e
        except urllib.error.URLError as e:  # transient network failure -- retry
            if attempt < max_retries:
                time.sleep(_retry_delay(None, backoff, attempt))
                continue
            raise LLMError(f"{type(e).__name__}: {e}") from e
        except Exception as e:  # noqa: BLE001 -- e.g. a malformed body; don't retry
            raise LLMError(f"{type(e).__name__}: {e}") from e
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise LLMError(f"unexpected response shape: {str(data)[:200]}") from e
