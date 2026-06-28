"""Model-free tests for the reward-hacking experiment harness (no API calls).

The linchpin is the referee: if it mislabels any planted candidate (especially the
subtle distribution-conditioned hacks), the whole moat-vs-judge comparison is invalid."""
from __future__ import annotations

import pytest

from experiment import generate, ground_truth, judge
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
