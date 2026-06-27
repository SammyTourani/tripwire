"""tripwire.isolation -- run untrusted candidate code in a FRESH subprocess.

Audit findings C1 (in-process oracle tampering) and H1 (cross-candidate input
mutation) both stem from one root cause: the evaluator imported and CALLED the
candidate in the SAME interpreter as the oracle. A candidate's module-level code
could then monkeypatch `tripwire.oracle`'s comparison functions (`exact_equal` /
`close_equal` / `speedup`) and make a blatantly-wrong implementation score
`correct=1.0, combined_score=huge` -- the verbatim Sakana "marked its own
homework" exploit this whole project exists to prevent.

The fix: execute the candidate in a CHILD PROCESS started with the 'spawn' method
(a brand-new interpreter, so it inherits none of the parent's already-imported,
potentially-monkeypatched modules). The child loads the candidate ONCE, then serves
the parent's input batches: for each arg-tuple it CALLS the candidate and returns
the OUTPUT. All correctness comparison happens back in the clean PARENT process,
against a reference the candidate's code never touched. Therefore:
  * a candidate cannot reach (let alone patch) the oracle that judges it,
  * a candidate that mutates its inputs only mutates throwaway copies in the child,
  * a candidate that hangs is killed by a per-call timeout,
  * a candidate that crashes/segfaults takes down only the child; the parent records
    a failure (-> the oracle rejects it, score 0.0).

`IsolatedCandidate` is a context manager exposing an `output_fn(args) -> output`
that `layered_oracle(..., output_fn=...)` calls in place of the in-process
candidate. Each call round-trips one input to the persistent child and back.

This module is imported only by tripwire/evaluator.py (Interface B). The pure,
in-process oracle (tripwire/oracle.py) is unchanged and still usable directly for
trusted candidates and tests; isolation is the hardened path for untrusted code.
"""
from __future__ import annotations

import multiprocessing as mp

# A fresh interpreter for the candidate. 'spawn' does NOT fork the parent's memory,
# so the child cannot see (or undo) any parent-side state -- the oracle is unreachable.
_CTX = mp.get_context("spawn")

DEFAULT_TIMEOUT = 30.0  # seconds per candidate call; exceeding it = failure


class CandidateError(Exception):
    """Raised in the PARENT by IsolatedCandidate.output_fn when the isolated child
    fails on an input (load error, raise, crash, timeout). The oracle's per-layer
    try/except turns this into a rejection -- exactly as if the candidate had raised
    in-process. The message is a short reason ('timeout', 'raised ValueError', ...)."""


def _worker(program_path, entrypoint_names, conn):
    """Runs IN THE CHILD. Loads the candidate once, then loops: receive an arg-tuple,
    send back ('ok', output) or ('err', reason). The candidate may monkeypatch
    anything in here -- it's a throwaway interpreter with no oracle in it."""
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location("candidate", program_path)
        if spec is None or spec.loader is None:
            conn.send(("fatal", "load failed: no spec"))
            return
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        except Exception as e:
            conn.send(("fatal", f"load failed: {type(e).__name__}"))
            return

        fn = None
        for name in entrypoint_names:
            fn = getattr(mod, name, None)
            if fn is not None:
                break
        if fn is None:
            conn.send(("fatal", "no entrypoint"))
            return
        if not callable(fn):
            conn.send(("fatal", "entrypoint not callable"))
            return

        conn.send(("ready", None))
        while True:
            msg = conn.recv()
            if msg == "__stop__":
                return
            args = msg
            try:
                conn.send(("ok", fn(*args)))
            except Exception as e:
                conn.send(("err", f"raised {type(e).__name__}"))
    except Exception as e:  # last-resort; never hang the parent
        try:
            conn.send(("fatal", f"child error: {type(e).__name__}"))
        except Exception:
            pass
    finally:
        conn.close()


class IsolatedCandidate:
    """Context manager that loads `program_path` in a fresh subprocess and exposes
    `output_fn(args) -> output`. Pass `.output_fn` to `layered_oracle(..., output_fn=)`.

    On enter: starts the child and waits for it to load the candidate. If loading
    fails (no entrypoint, syntax error), `load_error` is set and `output_fn` will
    raise CandidateError on first use (the oracle then rejects -> score 0.0).
    """

    def __init__(self, program_path, entrypoint_names, timeout=DEFAULT_TIMEOUT):
        self.program_path = program_path
        self.entrypoint_names = list(entrypoint_names)
        self.timeout = timeout
        self._proc = None
        self._conn = None
        self.load_error: str | None = None
        self._dead = False

    def __enter__(self):
        parent_conn, child_conn = _CTX.Pipe(duplex=True)
        self._conn = parent_conn
        self._proc = _CTX.Process(
            target=_worker,
            args=(self.program_path, self.entrypoint_names, child_conn),
            daemon=True,
        )
        self._proc.start()
        child_conn.close()
        # Wait for the child to finish loading the candidate's module.
        if parent_conn.poll(self.timeout):
            try:
                tag, info = parent_conn.recv()
            except EOFError:
                self.load_error, self._dead = "crashed", True
                return self
            if tag == "ready":
                pass
            else:  # 'fatal' (load failed / no entrypoint / not callable)
                self.load_error, self._dead = info, True
        else:
            self.load_error, self._dead = "load timeout", True
        return self

    def output_fn(self, args):
        """Send one arg-tuple to the isolated child, return its output. Raises
        CandidateError on any failure (load error, raise, crash, timeout)."""
        if self.load_error is not None:
            raise CandidateError(self.load_error)
        if self._dead or self._conn is None:
            raise CandidateError("crashed")
        try:
            self._conn.send(tuple(args))
        except Exception:
            self._dead = True
            raise CandidateError("crashed") from None
        if not self._conn.poll(self.timeout):
            self._dead = True
            raise CandidateError("timeout")
        try:
            tag, payload = self._conn.recv()
        except EOFError:
            self._dead = True
            raise CandidateError("crashed") from None
        if tag == "ok":
            return payload
        self._dead = tag == "fatal"  # err is per-call; fatal kills the worker
        raise CandidateError(payload if isinstance(payload, str) else "raised")

    def __exit__(self, *exc):
        try:
            if self._conn is not None and not self._dead:
                try:
                    self._conn.send("__stop__")
                except Exception:
                    pass
            if self._conn is not None:
                self._conn.close()
        finally:
            if self._proc is not None:
                self._proc.join(timeout=1.0)
                if self._proc.is_alive():
                    self._proc.terminate()
                    self._proc.join(timeout=1.0)
        return False
