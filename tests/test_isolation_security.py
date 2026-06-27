"""Security / isolation regression tests (hardening pass).

These lock in the fixes for three audit findings that defeated the oracle's core
"un-cheatable" claim. If a future change re-opens any of them, these fail.

  C1 -- in-process oracle tampering: a candidate that monkeypatches the oracle's
        comparators to mark its own homework. Killed by subprocess isolation.
  H1 -- input mutation: a candidate that mutates its shared input array, corrupting
        the reference comparison and later candidates. Killed by defensive copies.
  C2 -- distribution-conditioned hacks (a candidate correct only on the fixed input
        sizes the oracle tests): killed by the generative withheld_factory. Covered
        per-target in test_target_*; here we assert the evaluator path rejects one.

Isolation spawns subprocesses, so these tests are slower than pure-logic tests.
"""
from __future__ import annotations

import textwrap

import numpy as np

from tripwire.evaluator import make_openevolve_evaluator
from tripwire.isolation import CandidateError, IsolatedCandidate
from tripwire.oracle import layered_oracle
from tripwire.targets.sum_reduction import make_target


def _write(tmp_path, name, src):
    p = tmp_path / name
    p.write_text(textwrap.dedent(src))
    return str(p)


# ---------------------------------------------------------------------------
# C1 -- the monkeypatch / "marked its own homework" exploit must score 0.0.
# ---------------------------------------------------------------------------
def test_C1_oracle_monkeypatch_exploit_is_blocked(tmp_path):
    """A candidate that patches tripwire.oracle's comparators AND returns garbage
    must score 0.0 -- because under isolation it runs in a subprocess that cannot
    reach the parent's oracle. This is the verbatim Sakana exploit.

    NOTE: we deliberately do NOT include an `isolate=False` control that runs the
    same exploit in-process -- doing so would permanently monkeypatch THIS test
    process's oracle modules and contaminate every later test. The in-process path's
    vulnerability is exactly why `isolate=True` is the default (see evaluator docs)."""
    evil = _write(
        tmp_path,
        "evil.py",
        """
        import tripwire.oracle, tripwire.measure
        import tripwire.targets.sum_reduction as srm
        tripwire.oracle.exact_equal = lambda a, b: True
        tripwire.oracle.close_equal = lambda a, b, **k: True
        tripwire.oracle.speedup = lambda *a, **k: 999999.0
        tripwire.measure.close_equal = lambda a, b, **k: True
        srm.close_equal = lambda a, b, **k: True
        def solve(arr):
            return 0.5  # blatantly wrong
        """,
    )
    evaluate = make_openevolve_evaluator(make_target())  # isolate=True (default)
    result = evaluate(evil)
    assert result["combined_score"] == 0.0, "C1 REOPENED: monkeypatch exploit earned reward"
    assert result["correct"] == 0.0


def test_isolated_correct_candidate_still_scores_positive(tmp_path):
    good = _write(
        tmp_path,
        "good.py",
        """
        import numpy as np
        def solve(arr):
            return float(np.asarray(arr, dtype=np.float64).sum())
        """,
    )
    evaluate = make_openevolve_evaluator(make_target())
    result = evaluate(good)
    assert result["correct"] == 1.0, result["reason"]
    assert result["combined_score"] > 1.0


def test_isolated_wrong_candidate_scores_zero(tmp_path):
    wrong = _write(tmp_path, "wrong.py", "def solve(arr):\n    return 0.5\n")
    evaluate = make_openevolve_evaluator(make_target())
    assert evaluate(wrong)["combined_score"] == 0.0


# ---------------------------------------------------------------------------
# Isolation mechanics: crashes, hangs, missing entrypoints become clean failures.
# ---------------------------------------------------------------------------
def test_isolation_handles_missing_entrypoint(tmp_path):
    p = _write(tmp_path, "noentry.py", "x = 1\n")
    with IsolatedCandidate(p, ["solve"]) as iso:
        assert iso.load_error == "no entrypoint"


def test_isolation_handles_syntax_error(tmp_path):
    # A genuine syntax error (missing colon) -> exec_module raises SyntaxError.
    p = _write(tmp_path, "broken.py", "def solve(arr)\n    return 1\n")
    with IsolatedCandidate(p, ["solve"]) as iso:
        assert iso.load_error is not None and "load failed" in iso.load_error


def test_isolation_handles_candidate_that_raises(tmp_path):
    p = _write(tmp_path, "raiser.py", "def solve(arr):\n    raise ValueError('boom')\n")
    with IsolatedCandidate(p, ["solve"]) as iso:
        assert iso.load_error is None  # loads fine
        try:
            iso.output_fn((1,))
            raise AssertionError("expected CandidateError")
        except CandidateError as e:
            assert "raised" in str(e)


def test_isolation_timeout_on_hang(tmp_path):
    p = _write(
        tmp_path,
        "hang.py",
        """
        def solve(arr):
            while True:
                pass
        """,
    )
    with IsolatedCandidate(p, ["solve"], timeout=1.0) as iso:
        try:
            iso.output_fn((1,))
            raise AssertionError("expected timeout")
        except CandidateError as e:
            assert "timeout" in str(e)


def test_isolated_candidate_cannot_corrupt_parent_state(tmp_path):
    """A candidate that mutates global/parent state only affects its own subprocess;
    the parent's oracle modules are untouched after evaluation."""
    import tripwire.oracle as O

    before = O.close_equal
    evil = _write(
        tmp_path,
        "patcher.py",
        """
        import tripwire.oracle
        tripwire.oracle.close_equal = lambda *a, **k: True
        def solve(arr):
            return 0.5
        """,
    )
    make_openevolve_evaluator(make_target())(evil)
    assert O.close_equal is before, "parent oracle was mutated by candidate (isolation breached)"


# ---------------------------------------------------------------------------
# H1 -- input mutation cannot corrupt the reference or later candidates.
# ---------------------------------------------------------------------------
def test_H1_input_mutation_does_not_corrupt_later_candidates():
    """In-process oracle path: a candidate that mutates its input array must not
    poison the shared Target inputs for a subsequent honest candidate."""
    t = make_target()
    ref = t.reference

    def poisoner(arr):
        r = ref(arr)
        arr[0] = np.nan  # mutate the (supposedly shared) input in place
        return r

    def honest(arr):
        return float(np.sum(arr))

    layered_oracle(t, poisoner)
    v = layered_oracle(t, honest)
    assert v.accepted, f"H1 REOPENED: honest candidate corrupted by prior mutation ({v.reason})"


def test_H1_mutating_candidate_cannot_fake_correctness():
    """A candidate that mutates its input to match the reference's view must not pass:
    reference and candidate each receive independent copies."""
    t = make_target()

    def cheat(arr):
        arr *= 0  # zero the input; return 0 -- only 'correct' if ref saw the zeroed input
        return 0.0

    v = layered_oracle(t, cheat)
    assert not v.accepted
