"""Model-free tests for the reward-hacking experiment harness (no API calls).

The linchpin is the referee: if it mislabels any planted candidate (especially the
subtle distribution-conditioned hacks), the whole moat-vs-judge comparison is invalid."""
from __future__ import annotations

import io
import json
import urllib.error
import urllib.request

import pytest

from experiment import generate, ground_truth, judge, llm
from tripwire.scorecard import TARGET_FACTORIES
from tripwire.target import HACK, VALID_TRUTHS


def _known(truth):
    if truth == HACK:
        return "hack"
    return "correct" if truth in VALID_TRUTHS else truth


# --- the referee must agree with the known planted labels (incl. subtle hacks) ---
@pytest.mark.parametrize("name,factory", TARGET_FACTORIES)
def test_referee_matches_known_truth(name, factory):
    target = factory()
    for label, (fn, truth) in target.candidates.items():
        # modest factory_draws keeps the test fast; planted hacks fail on any
        # held-out input, so this still catches the conditioned ones.
        verdict, reason = ground_truth.label_candidate(target, fn=fn, factory_draws=10)
        assert verdict == _known(truth), (
            f"{name}/{label}: referee said {verdict!r} ({reason}), known {_known(truth)!r}"
        )


def test_label_candidate_requires_exactly_one_input_mode():
    target = TARGET_FACTORIES[0][1]()
    with pytest.raises(ValueError):
        ground_truth.label_candidate(target)  # neither fn nor output_fn
    with pytest.raises(ValueError):
        ground_truth.label_candidate(target, fn=lambda *a: None, output_fn=lambda a: None)


# --- judge reply parsing (model-free) ---------------------------------------
def test_judge_parse():
    assert judge._parse('{"verdict": "accept", "reason": "ok"}')[0] == "accept"
    assert judge._parse('{"verdict":"reject","reason":"memorizes canonical"}')[0] == "reject"
    assert judge._parse('sure: {"verdict": "reject"} ok')[0] == "reject"
    assert judge._parse("no json at all")[0] == "reject"  # conservative default


# --- candidate code extraction (model-free) ---------------------------------
def test_generate_extract_code():
    raw = "Sure:\n```python\ndef solve(x):\n    return x\n```\nDone"
    assert generate._extract_code(raw) == "def solve(x):\n    return x"
    assert "def solve" in (generate._extract_code("def solve(x):\n    return x") or "")
    assert generate._extract_code("") is None


# --- chat retry/backoff (model-free, fully mocked) --------------------------
class _FakeResp:
    def __init__(self, body):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._body


def _http_error(code):
    return urllib.error.HTTPError(
        "http://x/v1/chat/completions", code, "err", {}, io.BytesIO(b"transient")
    )


def test_chat_retries_transient_then_succeeds(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    body = json.dumps({"choices": [{"message": {"content": "hi"}}]}).encode()
    calls = {"n": 0}

    def fake_urlopen(req, timeout=0):
        calls["n"] += 1
        if calls["n"] < 3:  # two 429s, then success
            raise _http_error(429)
        return _FakeResp(body)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    out = llm.chat([{"role": "user", "content": "hi"}], model="m", max_retries=3)
    assert out == "hi"
    assert calls["n"] == 3


def test_chat_does_not_retry_client_error(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    calls = {"n": 0}

    def fake_urlopen(req, timeout=0):
        calls["n"] += 1
        raise _http_error(400)  # client error -- not retryable

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(llm.LLMError):
        llm.chat([{"role": "user", "content": "hi"}], model="m", max_retries=3)
    assert calls["n"] == 1


def test_chat_gives_up_after_max_retries(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    calls = {"n": 0}

    def fake_urlopen(req, timeout=0):
        calls["n"] += 1
        raise _http_error(429)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(llm.LLMError):
        llm.chat([{"role": "user", "content": "hi"}], model="m", max_retries=2)
    assert calls["n"] == 3  # initial try + 2 retries


def test_retry_delay_honours_retry_after():
    assert llm._retry_delay("5", 2.0, 0) == 5.0
    assert llm._retry_delay("999", 2.0, 0) == 30.0  # capped
    assert llm._retry_delay(None, 2.0, 2) == 8.0  # 2 * 2**2
    assert llm._retry_delay("not-a-number", 2.0, 0) == 2.0  # falls back to backoff


# --- tempted generation mode (model-free, mocked) --------------------------
def test_generate_format_examples_uses_canonical():
    target = TARGET_FACTORIES[0][1]()
    ex = generate._format_examples(target)
    assert "solve(" in ex and "==" in ex
    assert 1 <= ex.count("solve(") <= 6  # capped, from canonical inputs only


def test_generate_candidates_tempt_builds_gameable_prompt(monkeypatch):
    target = TARGET_FACTORIES[0][1]()
    captured = {}

    def fake_chat(messages, **kw):
        captured["system"] = messages[0]["content"]
        captured["user"] = messages[1]["content"]
        return "```python\ndef solve(s):\n    return s\n```"

    monkeypatch.setattr(generate, "chat", fake_chat)
    out = generate.generate_candidates(target, model="m", n=1, tempt=True)
    assert out and "def solve" in out[0]
    assert "only inputs it checks" in captured["system"]   # naive grader described
    assert "solve(" in captured["user"]                    # example pairs shown
