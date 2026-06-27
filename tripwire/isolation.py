"""tripwire.isolation -- evaluate untrusted candidate code in a FRESH subprocess,
returning ONLY primitive, trusted values across the process boundary.

Why this exists (audit history)
--------------------------------
The original evaluator imported and CALLED the candidate in the SAME interpreter as
the oracle, so a candidate could monkeypatch the oracle's comparators and "mark its
own homework" (the Sakana exploit). The first hardening attempt ran the candidate in
a subprocess but shipped the candidate's OUTPUT objects back to the parent over an
mp.Pipe -- which made the PARENT unpickle attacker-controlled data, an arbitrary
code-execution hole (a malicious `__reduce__` runs in the trusted parent). It also
still imported the candidate in-parent to time it.

The sound design (this module)
-------------------------------
The CHILD process does the ENTIRE evaluation and returns only THREE PRIMITIVES:
`(accepted: bool, reason: str, speedup: float)`. The parent unpickles nothing the
candidate controls -- only those primitives -- so there is no deserialization RCE,
and the candidate never executes in the parent at all.

Inside the child, the trusted machinery is captured into LOCAL variables BEFORE the
candidate module is imported, so the candidate's module-level code cannot monkeypatch
what the child uses to judge it:
  * the reference function and comparators are imported and bound to locals first,
  * then the candidate is loaded,
  * then the oracle logic runs using those captured locals.
A candidate that patches `tripwire.oracle.close_equal` in the child patches a name
the child's evaluation no longer reads; and the child is a throwaway interpreter
discarded immediately after, so any damage is contained.

Crashes / hangs / fork-bombs take down only the child; the parent observes EOF or a
timeout and reports a clean failure (-> rejected, score 0.0).

Used only by tripwire/evaluator.py (Interface B). The in-process oracle
(tripwire/oracle.py) is unchanged and still used directly for trusted code + tests.
"""
from __future__ import annotations

import multiprocessing as mp
from dataclasses import dataclass

# Fresh interpreter per candidate. 'spawn' does not fork parent memory, so the child
# starts from a clean import state the parent cannot have pre-poisoned.
_CTX = mp.get_context("spawn")

DEFAULT_TIMEOUT = 30.0  # seconds for the whole child evaluation; exceeding it = fail

# Entrypoint names a candidate may expose (kept in sync with the evaluator).
CANONICAL_ENTRYPOINT = "solve"


@dataclass
class IsolatedVerdict:
    """The trusted, primitives-only result the parent receives from the child.
    `speedup` is finite only when accepted; NaN/inf are normalized by the parent."""

    accepted: bool
    reason: str
    speedup: float


def _child_evaluate(program_path, target_factory_ref, entrypoint_names, conn):
    """Runs IN THE CHILD. Performs the FULL layered-oracle evaluation and sends back
    only (accepted, reason, speedup) as primitives. See module docstring for why the
    trusted functions are captured into locals before the candidate is imported.

    `target_factory_ref` is a ('module', 'attr') pair naming a zero-arg factory that
    rebuilds the Target fresh in this process (Targets contain callables/closures and
    are reconstructed here rather than pickled across)."""
    try:
        import importlib

        # --- capture TRUSTED machinery into locals BEFORE loading the candidate ---
        oracle_mod = importlib.import_module("tripwire.oracle")
        layered = oracle_mod.layered_oracle  # uses measure.* bound at its import time

        mod_name, attr = target_factory_ref
        target = getattr(importlib.import_module(mod_name), attr)()

        # --- now load the (untrusted) candidate ---
        import importlib.util

        spec = importlib.util.spec_from_file_location("candidate", program_path)
        if spec is None or spec.loader is None:
            conn.send((False, "load failed: no spec", 0.0))
            return
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        except Exception as e:
            conn.send((False, f"load failed: {type(e).__name__}", 0.0))
            return

        fn = None
        for name in entrypoint_names:
            fn = getattr(mod, name, None)
            if fn is not None:
                break
        if fn is None:
            conn.send((False, "no entrypoint", 0.0))
            return
        if not callable(fn):
            conn.send((False, "entrypoint not callable", 0.0))
            return

        # --- full oracle evaluation in the child; only primitives leave ---
        verdict = layered(target, fn)
        sp = float(verdict.speedup)
        # normalize non-finite to a safe primitive (parent re-checks anyway)
        if sp != sp or sp in (float("inf"), float("-inf")):
            sp = float("inf") if sp == float("inf") else (0.0 if sp != sp else sp)
        conn.send((bool(verdict.accepted), str(verdict.reason), sp))
    except Exception as e:  # last-resort: never hang the parent
        try:
            conn.send((False, f"child error: {type(e).__name__}", 0.0))
        except Exception:
            pass
    finally:
        conn.close()


def evaluate_isolated(
    program_path: str,
    target_factory_ref: tuple[str, str],
    entrypoint_names=None,
    timeout: float = DEFAULT_TIMEOUT,
) -> IsolatedVerdict:
    """Evaluate `program_path` against the Target produced by `target_factory_ref`
    (a ('module','factory_attr') pair) entirely inside a fresh subprocess. Returns an
    IsolatedVerdict built from PRIMITIVES only. Never raises; all failure modes
    (load error, crash, segfault, fork-bomb death, timeout) map to accepted=False."""
    if entrypoint_names is None:
        entrypoint_names = [CANONICAL_ENTRYPOINT]
    parent_conn, child_conn = _CTX.Pipe(duplex=False)
    proc = _CTX.Process(
        target=_child_evaluate,
        args=(program_path, tuple(target_factory_ref), list(entrypoint_names), child_conn),
        daemon=True,
    )
    proc.start()
    child_conn.close()  # parent only reads

    result = None
    if parent_conn.poll(timeout):
        try:
            payload = parent_conn.recv()
        except EOFError:
            payload = None  # child died without sending (segfault / killed)
        # Defensively validate the shape/types -- the child is trusted code, but be
        # strict so a corrupted message can never become a nonzero score.
        if (
            isinstance(payload, tuple)
            and len(payload) == 3
            and isinstance(payload[0], bool)
            and isinstance(payload[1], str)
            and isinstance(payload[2], (int, float))
        ):
            result = payload
    else:
        result = ("__timeout__",)  # sentinel

    parent_conn.close()
    proc.join(timeout=1.0)
    if proc.is_alive():
        proc.terminate()
        proc.join(timeout=1.0)

    if result is None:
        return IsolatedVerdict(False, "crashed", 0.0)
    if result == ("__timeout__",):
        return IsolatedVerdict(False, "timeout", 0.0)

    accepted, reason, sp = result
    sp = float(sp)
    if not accepted:
        sp = 0.0
    return IsolatedVerdict(accepted=accepted, reason=reason, speedup=sp)
