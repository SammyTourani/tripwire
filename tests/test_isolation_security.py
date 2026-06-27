"""Security / isolation regression tests (hardening pass).

These lock in fixes for audit findings that defeated the oracle's "un-cheatable"
claim. If a future change re-opens any, these fail.

  C1   -- in-process oracle tampering ("marked its own homework"). Killed by running
          the FULL evaluation in a subprocess that returns only primitives.
  RCE1 -- pickle __reduce__ RCE: a first hardening attempt shipped candidate OUTPUT
          objects to the parent, letting a malicious __reduce__ run in the parent.
          Killed by never deserializing candidate-controlled data (primitives only).
  RCE2 -- in-parent import for the speedup step (RCE + cross-candidate poisoning).
          Killed by measuring speedup inside the child too.
  H1   -- input mutation corrupting the reference / later candidates. Killed by
          per-call deep copies (incl. the L4 timing path).
  C2   -- distribution-conditioned hacks (covered per-target in test_target_*).

Isolation spawns subprocesses, so these tests are slower than pure-logic tests.
"""
from __future__ import annotations

import os
import textwrap

import numpy as np

from tripwire.evaluator import make_openevolve_evaluator
from tripwire.isolation import evaluate_isolated
from tripwire.oracle import layered_oracle
from tripwire.targets.sum_reduction import make_target

_SUM_FACTORY = ("tripwire.targets.sum_reduction", "make_target")


def _write(tmp_path, name, src):
    p = tmp_path / name
    p.write_text(textwrap.dedent(src))
    return str(p)


# ---------------------------------------------------------------------------
# C1 -- monkeypatch / "marked its own homework" exploit must score 0.0.
# ---------------------------------------------------------------------------
def test_C1_oracle_monkeypatch_exploit_is_blocked(tmp_path):
    """A candidate that patches every comparator binding site AND returns garbage
    must score 0.0. The full oracle runs in the child with comparators captured as
    default args (untamperable), and only primitives cross back."""
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
        tripwire.measure.exact_equal = lambda a, b: True
        srm.close_equal = lambda a, b, **k: True
        def solve(arr):
            return 0.5  # blatantly wrong
        """,
    )
    result = make_openevolve_evaluator(make_target())(evil)
    assert result["combined_score"] == 0.0, "C1 REOPENED: monkeypatch exploit earned reward"
    assert result["correct"] == 0.0


# ---------------------------------------------------------------------------
# RCE1 -- a malicious pickle __reduce__ in candidate output must NOT run in parent.
# ---------------------------------------------------------------------------
def test_RCE1_pickle_reduce_does_not_execute_in_parent(tmp_path):
    """The headline regression: the parent must deserialize nothing the candidate
    controls. A candidate returning an object whose __reduce__ runs os.system must
    NOT execute that code in the parent (and must score 0.0)."""
    proof = tmp_path / "rce_proof.txt"
    evil = _write(
        tmp_path,
        "pickle_evil.py",
        f"""
        import os
        class Pwn:
            def __reduce__(self):
                return (os.system, ("touch {proof}",))
        def solve(arr):
            return Pwn()
        """,
    )
    result = make_openevolve_evaluator(make_target())(evil)
    assert not proof.exists(), "RCE1 REOPENED: candidate __reduce__ executed in the parent"
    assert result["combined_score"] == 0.0


# ---------------------------------------------------------------------------
# RCE2 -- candidate module-level code must NOT execute in the parent process.
# ---------------------------------------------------------------------------
def test_RCE2_candidate_module_code_does_not_run_in_parent(tmp_path):
    """Even a CORRECT candidate's import-time code must run only in the child, never
    in the parent (the old in-parent speedup step was an RCE + poisoning vector)."""
    proof = tmp_path / "import_proof.txt"
    parent_pid = os.getpid()
    cand = _write(
        tmp_path,
        "import_marker.py",
        f"""
        import os
        with open("{proof}", "w") as f:
            f.write(str(os.getpid()))
        import numpy as np
        def solve(arr):
            return float(np.asarray(arr, dtype=np.float64).sum())
        """,
    )
    result = make_openevolve_evaluator(make_target())(cand)
    assert result["correct"] == 1.0, result["reason"]
    # If the marker exists it must record the CHILD's pid, never the parent's.
    if proof.exists():
        assert proof.read_text().strip() != str(parent_pid), (
            "RCE2 REOPENED: candidate module code executed in the PARENT process"
        )


def test_correct_plus_patcher_does_not_poison_parent_or_later_candidates(tmp_path):
    """A correct candidate that also monkeypatches must not corrupt the parent's
    oracle for the NEXT candidate (the cross-candidate poisoning vector)."""
    import tripwire.oracle as O

    before = O.close_equal
    patcher = _write(
        tmp_path,
        "patcher.py",
        """
        import tripwire.oracle, tripwire.measure
        import tripwire.targets.sum_reduction as srm
        tripwire.oracle.close_equal = lambda a, b, **k: True
        tripwire.measure.close_equal = lambda a, b, **k: True
        srm.close_equal = lambda a, b, **k: True
        import numpy as np
        def solve(arr):
            return float(np.asarray(arr, dtype=np.float64).sum())
        """,
    )
    wrong = _write(tmp_path, "wrong.py", "def solve(arr):\n    return 0.5\n")
    evaluate = make_openevolve_evaluator(make_target())
    evaluate(patcher)
    assert O.close_equal is before, "parent oracle mutated by candidate (isolation breached)"
    assert evaluate(wrong)["combined_score"] == 0.0, "later candidate poisoned"


# ---------------------------------------------------------------------------
# Isolation mechanics: happy path, crashes, hangs, missing entrypoints -> clean.
# ---------------------------------------------------------------------------
def test_isolated_correct_candidate_scores_positive(tmp_path):
    good = _write(
        tmp_path,
        "good.py",
        """
        import numpy as np
        def solve(arr):
            return float(np.asarray(arr, dtype=np.float64).sum())
        """,
    )
    result = make_openevolve_evaluator(make_target())(good)
    assert result["correct"] == 1.0, result["reason"]
    assert result["combined_score"] > 1.0


def test_isolated_wrong_candidate_scores_zero(tmp_path):
    wrong = _write(tmp_path, "wrong.py", "def solve(arr):\n    return 0.5\n")
    assert make_openevolve_evaluator(make_target())(wrong)["combined_score"] == 0.0


def test_isolation_missing_entrypoint(tmp_path):
    p = _write(tmp_path, "noentry.py", "x = 1\n")
    v = evaluate_isolated(p, _SUM_FACTORY, ["solve", "sum_reduction"])
    assert not v.accepted and v.reason == "no entrypoint"


def test_isolation_syntax_error(tmp_path):
    p = _write(tmp_path, "broken.py", "def solve(arr)\n    return 1\n")
    v = evaluate_isolated(p, _SUM_FACTORY, ["solve"])
    assert not v.accepted and "load failed" in v.reason


def test_isolation_candidate_that_raises(tmp_path):
    p = _write(tmp_path, "raiser.py", "def solve(arr):\n    raise ValueError('boom')\n")
    v = evaluate_isolated(p, _SUM_FACTORY, ["solve"])
    assert not v.accepted  # raised at L1 -> rejected


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
    v = evaluate_isolated(p, _SUM_FACTORY, ["solve"], timeout=2.0)
    assert not v.accepted and v.reason == "timeout"


def test_isolation_returns_only_primitive_speedup(tmp_path):
    """The cross-process result's speedup is always a plain float (no candidate
    object crosses the boundary)."""
    good = _write(
        tmp_path,
        "g.py",
        "import numpy as np\ndef solve(arr):\n    return float(np.asarray(arr).sum())\n",
    )
    v = evaluate_isolated(good, _SUM_FACTORY, ["solve", "sum_reduction"])
    assert isinstance(v.speedup, float)
    assert isinstance(v.accepted, bool)
    assert isinstance(v.reason, str)


# ---------------------------------------------------------------------------
# H1 -- input mutation cannot corrupt the reference or later candidates (incl L4).
# ---------------------------------------------------------------------------
def test_H1_input_mutation_does_not_corrupt_later_candidates():
    t = make_target()
    ref = t.reference

    def poisoner(arr):
        r = ref(arr)
        arr[0] = np.nan
        return r

    def honest(arr):
        return float(np.sum(arr))

    layered_oracle(t, poisoner)
    v = layered_oracle(t, honest)
    assert v.accepted, f"H1 REOPENED: honest candidate corrupted by prior mutation ({v.reason})"


def test_H1_mutating_candidate_cannot_fake_correctness():
    t = make_target()

    def cheat(arr):
        arr *= 0
        return 0.0

    assert not layered_oracle(t, cheat).accepted


def test_H1_L4_timing_path_does_not_corrupt_shared_args():
    """A candidate correct on every checked input but which MUTATES its input only
    affects copies -- the shared Target args survive L4 timing intact, so a later
    honest candidate is unaffected."""
    t = make_target()
    canonical_snapshot = [a[0].copy() for a in t.canonical_args]

    def correct_but_mutates(arr):
        out = float(np.sum(arr))
        arr[:] = np.nan  # mutate after computing the right answer
        return out

    layered_oracle(t, correct_but_mutates)  # passes correctness, runs L4 timing
    # The shared canonical args must be unchanged.
    for snap, args in zip(canonical_snapshot, t.canonical_args, strict=True):
        assert np.array_equal(snap, args[0]), "L4 timing leaked raw args to a mutating candidate"
