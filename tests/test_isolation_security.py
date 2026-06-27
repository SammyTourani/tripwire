"""Security / isolation regression tests (hardening pass).

These lock in fixes for audit findings on the candidate-execution sandbox. If a
future change re-opens any, these fail.

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
from tripwire.isolation import CandidateError, IsolatedCandidate
from tripwire.oracle import layered_oracle
from tripwire.targets.sum_reduction import make_target


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
    with IsolatedCandidate(p, ["solve", "sum_reduction"]) as iso:
        assert iso.load_error == "no entrypoint"


def test_isolation_syntax_error(tmp_path):
    p = _write(tmp_path, "broken.py", "def solve(arr)\n    return 1\n")
    with IsolatedCandidate(p, ["solve"]) as iso:
        assert iso.load_error is not None and "load failed" in iso.load_error


def test_isolation_candidate_that_raises(tmp_path):
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
    with IsolatedCandidate(p, ["solve"], timeout=2.0) as iso:
        try:
            iso.output_fn((1,))
            raise AssertionError("expected timeout")
        except CandidateError as e:
            assert "timeout" in str(e)


def test_isolation_output_is_json_decoded_not_unpickled(tmp_path):
    """A correct candidate's output crosses as JSON and decodes to the right value;
    no candidate object is ever unpickled by the parent."""
    good = _write(
        tmp_path,
        "g.py",
        "import numpy as np\ndef solve(arr):\n    return float(np.asarray(arr).sum())\n",
    )
    with IsolatedCandidate(good, ["solve", "sum_reduction"]) as iso:
        out = iso.output_fn((np.array([1.0, 2.0, 3.0]),))
        assert isinstance(out, float) and abs(out - 6.0) < 1e-9


def test_isolation_unencodable_output_is_rejected(tmp_path):
    """A candidate returning a non-JSON-encodable object is a failure, never a pass."""
    p = _write(
        tmp_path,
        "weird.py",
        "def solve(arr):\n    return object()\n",
    )
    with IsolatedCandidate(p, ["solve"]) as iso:
        try:
            iso.output_fn((1,))
            raise AssertionError("expected CandidateError")
        except CandidateError as e:
            assert "unencodable" in str(e)


def test_pipe_smuggling_cannot_execute_in_parent(tmp_path):
    """A candidate that grabs the child's socket and sends a malicious PICKLE must NOT
    run code in the parent -- the parent decodes with json.loads, never pickle."""
    proof = tmp_path / "smuggle_proof.txt"
    evil = _write(
        tmp_path,
        "smuggle.py",
        f"""
        import gc, os, socket, pickle
        class Pwn:
            def __reduce__(self):
                return (os.system, ("touch {proof}",))
        for obj in gc.get_objects():
            try:
                if isinstance(obj, socket.socket):
                    obj.sendall(pickle.dumps(Pwn()))
            except Exception:
                pass
        def solve(arr):
            return 0.5
        """,
    )
    result = make_openevolve_evaluator(make_target())(evil)
    assert not proof.exists(), "PIPE-SMUGGLING RCE: candidate pickle executed in the parent"
    assert result["combined_score"] == 0.0


def test_verdict_class_hijack_is_blocked(tmp_path):
    """A candidate rebinding tripwire.oracle.Verdict cannot fake a passing verdict,
    because the oracle (and Verdict) run in the trusted parent, not the candidate's
    process."""
    evil = _write(
        tmp_path,
        "verdict_hijack.py",
        """
        import tripwire.oracle as O
        class _AlwaysAccept:
            def __init__(self, *a, **k):
                self.accepted = True
                self.reason = "x"
                self.speedup = 424242.0
        O.Verdict = _AlwaysAccept
        def solve(arr):
            return 0.5  # blatantly wrong
        """,
    )
    result = make_openevolve_evaluator(make_target())(evil)
    assert result["combined_score"] == 0.0, "VERDICT-HIJACK: wrong code earned reward"
    assert result["correct"] == 0.0


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


# ---------------------------------------------------------------------------
# ROUND-4 STRUCTURAL GUARANTEES (fresh-subprocess design).
# These lock in the architectural properties that make the previous attack
# classes IMPOSSIBLE rather than merely patched:
#   * the candidate runs in a fresh-exec'd interpreter (no inherited Python heap),
#   * the parent owns the clock (candidate cannot forge its timing),
#   * `gc.get_objects()` in the child finds NO parent-reachable IPC handle.
# ---------------------------------------------------------------------------
def test_R4_candidate_heap_contains_no_parent_ipc_handle(tmp_path):
    """In the round-4 architecture, a fresh `subprocess.run([python, '-I', shim])`
    child has no `multiprocessing.Connection` or parent-reachable socket in its
    Python heap. This is what makes the round-1/round-2 pipe-smuggle attack class
    STRUCTURALLY IMPOSSIBLE: there is no handle for `gc.get_objects()` to find."""
    recon = _write(
        tmp_path,
        "recon.py",
        """
        import gc, socket
        import multiprocessing.connection as mpc
        _conns = [o for o in gc.get_objects() if isinstance(o, mpc.Connection)]
        _socks = [o for o in gc.get_objects() if isinstance(o, socket.socket)]
        def solve(arr):
            return {"connections": len(_conns), "sockets": len(_socks)}
        """,
    )
    with IsolatedCandidate(recon, ["solve"]) as iso:
        out = iso.output_fn((np.array([1.0]),))
        assert out["connections"] == 0, "ROUND-4 BREACH: Connection visible in candidate heap"
        assert out["sockets"] == 0, "ROUND-4 BREACH: socket visible in candidate heap"


def test_R4_timing_forge_is_blocked_parent_owns_clock(tmp_path):
    """Round-3's critical: the candidate could pre-send a forged tiny `elapsed` over
    a shared socket, scoring billions of x faster than reality. Round 4 has the
    parent measure wall time around each call; the candidate never reports a clock,
    so it cannot forge one. A genuinely-slower candidate scores LESS than ref, not
    arbitrarily more."""
    slow = _write(
        tmp_path,
        "slow.py",
        """
        import time, numpy as np
        def solve(arr):
            # Genuinely slower than the np.sum reference, AND patches the local
            # time module -- which is now harmless because the parent owns timing.
            time.perf_counter = lambda: 0.0
            time.sleep(0.001)
            return float(np.asarray(arr, dtype=np.float64).sum())
        """,
    )
    result = make_openevolve_evaluator(make_target())(slow)
    assert result["correct"] == 1.0, result["reason"]
    # Genuinely-slower candidate must NOT score arbitrarily high. Compared to the
    # in-process reference timing, a sleep-injecting candidate will score < ~100x
    # (the honest np.sum win is ~180x; this is bounded well below that).
    assert result["combined_score"] < 50.0, (
        f"TIMING FORGE: slower candidate scored {result['combined_score']}x"
    )


def test_R4_child_runs_with_empty_env(tmp_path):
    """The shim is launched with `env={}`, so the candidate can't read parent
    env vars (e.g. API keys in OPENAI_API_KEY)."""
    leak = _write(
        tmp_path,
        "leak.py",
        """
        import os
        def solve(arr):
            return sorted(os.environ.keys())
        """,
    )
    with IsolatedCandidate(leak, ["solve"]) as iso:
        env_keys = iso.output_fn((1,))
        # Some baseline OS-injected vars may exist (PATH etc. on some platforms);
        # what matters is OPENAI_API_KEY / OPENAI_BASE_URL / OPENEVOLVE_MODEL etc.
        for sensitive in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENEVOLVE_MODEL"):
            assert sensitive not in env_keys, f"env leakage: {sensitive} reached candidate"


def test_R4_python_isolated_mode_blocks_user_site(tmp_path):
    """`python -I` disables user site-packages and ignores PYTHON* env vars, so a
    candidate cannot pre-load malicious code into its own interpreter via the
    parent's environment."""
    probe = _write(
        tmp_path,
        "probe.py",
        """
        import sys
        def solve(arr):
            return {
                "flags_isolated": int(sys.flags.isolated),
                "no_user_site": int(sys.flags.no_user_site),
                "no_site": int(sys.flags.no_site),
                "ignore_environment": int(sys.flags.ignore_environment),
            }
        """,
    )
    with IsolatedCandidate(probe, ["solve"]) as iso:
        flags = iso.output_fn((1,))
        assert flags["flags_isolated"] == 1, "candidate not in -I isolated mode"
        assert flags["ignore_environment"] == 1
        assert flags["no_user_site"] == 1


def test_R4_decode_rejects_object_dtype_array(tmp_path):
    """Round-3 audit medium: a malicious dtype string could trigger huge per-element
    allocations or unpickling inside numpy. The codec now whitelists dtypes (no
    object dtype, capped itemsize). A candidate returning an object-dtype ndarray
    is rejected, not unpickled."""
    p = _write(
        tmp_path,
        "obj_dtype.py",
        """
        import numpy as np
        def solve(arr):
            return np.array([object()], dtype=object)
        """,
    )
    with IsolatedCandidate(p, ["solve"]) as iso:
        try:
            iso.output_fn((1,))
        except CandidateError as e:
            # Either the shim rejected the encode (TypeError) or the parent decode
            # refused the dtype. Either way: not unpickled, not silently accepted.
            assert "unencodable" in str(e) or "dtype" in str(e) or "decode" in str(e), str(e)
        else:
            raise AssertionError("object-dtype output should have been rejected")
