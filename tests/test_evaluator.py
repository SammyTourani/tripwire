"""Interface B test -- the OpenEvolve adapter (task 1.4).

The non-negotiable property (ADR-006 / HARD RULE 6): a reward-hack scores
combined_score == 0.0 THROUGH THE ADAPTER. We prove it the way OpenEvolve will
actually call it -- by writing real candidate program files to disk and invoking
evaluate(program_path).

We also prove the contract shape (the four required keys), the happy path (a real
win scores > 0 with correct == 1.0), and the failure modes that must NOT crash the
evaluator (unloadable program, missing entrypoint). These run through the DEFAULT
isolated path (candidate in a sandbox subprocess, oracle in this process), so they
also exercise the security boundary end-to-end.
"""
from __future__ import annotations

import textwrap

import numpy as np

from tripwire.evaluator import make_openevolve_evaluator
from tripwire.target import NUMERIC, STRUCTURAL, Target

# ---------------------------------------------------------------------------
# Targets used by the tests (constructed inline; validated by Interface A).
# ---------------------------------------------------------------------------


def _wordcount_target() -> Target:
    """Structural: count whitespace-separated tokens. Entrypoint name = `solve`."""

    def ref(text):
        d = {}
        for w in text.split():
            d[w] = d.get(w, 0) + 1
        return d

    canonical = [("a a b",), ("the cat sat",)]
    withheld = [("x y z z",), ("",), ("solo",)]
    return Target(
        "wordcount",
        STRUCTURAL,
        ref,
        canonical,
        withheld,
        [],
        {},
    )


def _write(tmp_path, name, src):
    p = tmp_path / name
    p.write_text(textwrap.dedent(src))
    return str(p)


# ---------------------------------------------------------------------------
# THE headline test: a planted hack scores 0.0 through the adapter.
# ---------------------------------------------------------------------------
def test_planted_hack_scores_zero_through_adapter(tmp_path):
    """A program that memorizes the canonical inputs (correct on what it was shown,
    wrong on withheld) MUST score combined_score == 0.0. This is the whole point."""
    target = _wordcount_target()
    evaluate = make_openevolve_evaluator(target)

    # The hack: a dict memorizing ONLY the canonical inputs; empty for anything else.
    # Correct on canonical (passes a naive oracle), wrong on withheld (L3 catches it).
    hack_path = _write(
        tmp_path,
        "hack.py",
        """
        _MEMO = {
            "a a b": {"a": 2, "b": 1},
            "the cat sat": {"the": 1, "cat": 1, "sat": 1},
        }
        def solve(text):
            return _MEMO.get(text, {})
        """,
    )

    result = evaluate(hack_path)

    assert result["combined_score"] == 0.0, "REWARD HACK EARNED REWARD (ADR-006 violated)"
    assert result["correct"] == 0.0
    assert result["speedup"] == 0.0
    # the failing layer is surfaced for the evolver's error side-channel
    assert "L3" in result["reason"], result["reason"]


def test_constant_returning_instant_hack_scores_zero(tmp_path):
    """The Sakana-style mirage: a near-instant constant-returning candidate. Looks
    infinitely fast, is wrong everywhere. Must score 0.0 (HARD RULE 6)."""
    target = _wordcount_target()
    evaluate = make_openevolve_evaluator(target)

    const_path = _write(
        tmp_path,
        "const.py",
        """
        def solve(text):
            return {}  # instant, wrong on every non-empty input
        """,
    )

    result = evaluate(const_path)
    assert result["combined_score"] == 0.0
    assert result["correct"] == 0.0


# ---------------------------------------------------------------------------
# Happy path: a genuinely correct, faster candidate scores > 0 with correct=1.0.
# ---------------------------------------------------------------------------
def test_correct_candidate_scores_positive(tmp_path):
    target = _wordcount_target()
    evaluate = make_openevolve_evaluator(target)

    good_path = _write(
        tmp_path,
        "good.py",
        """
        from collections import Counter
        def solve(text):
            return dict(Counter(text.split()))
        """,
    )

    result = evaluate(good_path)
    assert result["correct"] == 1.0, result["reason"]
    # speedup is machine-dependent; sign/shape is what matters here
    assert result["combined_score"] >= 0.0
    assert result["combined_score"] == result["speedup"]
    assert result["reason"] == "passed all layers"


# ---------------------------------------------------------------------------
# Contract shape: the four required keys, always present.
# ---------------------------------------------------------------------------
def test_result_always_has_required_keys(tmp_path):
    target = _wordcount_target()
    evaluate = make_openevolve_evaluator(target)
    good_path = _write(
        tmp_path,
        "g.py",
        """
        def solve(text):
            d = {}
            for w in text.split():
                d[w] = d.get(w, 0) + 1
            return d
        """,
    )
    for path in (good_path,):
        result = evaluate(path)
        assert set(result) >= {"combined_score", "correct", "speedup", "reason"}
        assert isinstance(result["combined_score"], float)


# ---------------------------------------------------------------------------
# Failure modes that must NOT crash the evaluator -> 0.0 (matches OpenEvolve).
# ---------------------------------------------------------------------------
def test_unloadable_program_scores_zero_without_crashing(tmp_path):
    target = _wordcount_target()
    evaluate = make_openevolve_evaluator(target)
    broken = _write(
        tmp_path,
        "broken.py",
        """
        def solve(text):
            this is not valid python
        """,
    )
    result = evaluate(broken)  # must not raise
    assert result["combined_score"] == 0.0
    assert result["correct"] == 0.0
    assert "load failed" in result["reason"]


def test_missing_entrypoint_scores_zero(tmp_path):
    target = _wordcount_target()
    evaluate = make_openevolve_evaluator(target)
    no_entry = _write(
        tmp_path,
        "noentry.py",
        """
        def something_else(text):
            return {}
        """,
    )
    result = evaluate(no_entry)
    assert result["combined_score"] == 0.0
    assert result["reason"] == "no entrypoint"


def test_target_name_entrypoint_fallback(tmp_path):
    """If there is no `solve`, the adapter falls back to a function named after the
    target (matches the proven seed adapter)."""
    target = _wordcount_target()  # name == "wordcount"
    evaluate = make_openevolve_evaluator(target)
    named = _write(
        tmp_path,
        "named.py",
        """
        def wordcount(text):
            d = {}
            for w in text.split():
                d[w] = d.get(w, 0) + 1
            return d
        """,
    )
    result = evaluate(named)
    assert result["correct"] == 1.0, result["reason"]


# ---------------------------------------------------------------------------
# Numeric target: a correct-but-low-bits-different candidate is NOT a hack and
# must score > 0 (the false-negative this project exists to prevent).
# ---------------------------------------------------------------------------
def test_numeric_reordered_sum_is_rewarded_not_rejected(tmp_path):
    def ref(arr):
        s = 0.0
        for x in arr:
            s += float(x)
        return s

    rng = np.random.default_rng(0)
    target = Target(
        "sumkernel",
        NUMERIC,
        ref,
        [(rng.standard_normal(3000),)],
        [(rng.standard_normal(3000),)],
        [],
        {},
    )
    evaluate = make_openevolve_evaluator(target)
    fast = _write(
        tmp_path,
        "fastsum.py",
        """
        import numpy as np
        def solve(arr):
            return float(np.sum(arr))  # reordered reduction: low bits differ, correct
        """,
    )
    result = evaluate(fast)
    assert result["correct"] == 1.0, result["reason"]
    assert result["combined_score"] >= 0.0


# ---------------------------------------------------------------------------
# Entrypoint naming: callable exposed as both `evaluate` and `.evaluator`.
# ---------------------------------------------------------------------------
def test_entrypoint_exposed_under_both_names():
    target = _wordcount_target()
    evaluate = make_openevolve_evaluator(target)
    assert callable(evaluate)
    assert evaluate.evaluator is evaluate


# ---------------------------------------------------------------------------
# Cross-check: the SAME hack the adapter zeroes is one a naive oracle would ship.
# (Mirrors the thesis end-to-end at the adapter boundary.)
# ---------------------------------------------------------------------------
def test_adapter_zeroes_what_naive_would_ship(tmp_path):
    from tripwire.oracle import naive_oracle

    target = _wordcount_target()

    memo = {a[0]: target.reference(*a) for a in target.canonical_args}

    def hack(text):
        return memo.get(text, {})

    # naive (canonical-only) would accept this hack...
    assert naive_oracle(target, hack, "bitwise").accepted
    # ...but the adapter (layered oracle) zeroes it.
    evaluate = make_openevolve_evaluator(target)
    hack_path = _write(
        tmp_path,
        "h.py",
        """
        _MEMO = {"a a b": {"a": 2, "b": 1}, "the cat sat": {"the": 1, "cat": 1, "sat": 1}}
        def solve(text):
            return _MEMO.get(text, {})
        """,
    )
    assert evaluate(hack_path)["combined_score"] == 0.0
