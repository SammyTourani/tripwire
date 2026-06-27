"""tripwire.isolation -- run untrusted candidate code in a sandbox subprocess that
emits ONLY its raw outputs, serialized with a NON-pickle (JSON) codec.

Audit history (three rounds; learn from it)
--------------------------------------------
* The original evaluator ran the candidate in-process with the oracle -> a candidate
  could monkeypatch the comparators and "mark its own homework" (Sakana exploit).
* Round 1 ran the candidate in a subprocess but shipped its OUTPUT OBJECTS back over
  an mp.Pipe -> the PARENT unpickled attacker data (a malicious __reduce__ ran in the
  parent). It also imported the candidate in-parent to time it.
* Round 2 ran the FULL oracle in the child and returned "only primitives" -> but the
  untrusted candidate shared that child's interpreter, so it could (a) grab the live
  pipe Connection via gc and send an arbitrary pickle to the parent, and (b) rebind
  `tripwire.oracle.Verdict` so every internal `Verdict(False, ...)` became accepted.

The invariant those rounds violated
------------------------------------
Untrusted candidate code must NEVER share an interpreter with (1) the verdict logic
or (2) any handle that can send pickled objects to the parent. Process isolation
alone is not enough if the verdict logic or the IPC handle is co-resident.

This design (round 3)
---------------------
The CHILD is a DUMB WORKER: it loads the candidate and, for each input the parent
sends, CALLS the candidate and writes back its output ENCODED AS JSON BYTES. The
child runs NO oracle logic -- there is no Verdict to hijack and no verdict to fake;
the child only produces outputs.

The PARENT (trusted) runs the entire `layered_oracle`; its candidate-calling goes
through `output_fn`, which sends one input and reads back the JSON-decoded output.
The parent reads LENGTH-PREFIXED RAW BYTES and decodes them with `json.loads` -- it
NEVER calls pickle on anything from the child. Therefore:
  * a malicious object cannot survive the JSON boundary (no __reduce__ path),
  * even if the candidate grabs the child's socket and writes arbitrary bytes, the
    worst it can do is produce JSON the parent treats as a (wrong) output -> rejected,
  * the candidate never touches the oracle, comparators, or Verdict (all in parent),
  * inputs cross parent->child as JSON too, so the child reconstructs them locally.

A numpy-aware codec handles our domains (numbers, strings, bools, None, lists, dicts,
tuples, and ndarrays as {"__ndarray__": ..., "dtype": ...}). Anything a candidate
returns that is not JSON-encodable by this codec is reported as a failure (rejected),
never as a passing verdict.

Crashes / hangs / fork-bombs: a per-call timeout bounds the parent's read; on timeout
or EOF the candidate is rejected and the child's whole PROCESS GROUP is killed
(so detached grandchildren can't outlive it).
"""
from __future__ import annotations

import json
import multiprocessing as mp
import os
import signal
import struct

import numpy as np

# Fresh interpreter per candidate. 'spawn' => the child starts clean.
_CTX = mp.get_context("spawn")

DEFAULT_TIMEOUT = 30.0  # seconds per candidate call
CANONICAL_ENTRYPOINT = "solve"
_MAX_MSG = 256 * 1024 * 1024  # 256 MiB hard cap on a single decoded message


# ---------------------------------------------------------------------------
# JSON codec (numpy-aware). NO pickle anywhere on this path.
# ---------------------------------------------------------------------------
def _encode(obj):
    """Convert an output into JSON-safe primitives. ndarrays -> tagged dict. Raises
    TypeError on anything unsupported (caller treats that as a candidate failure)."""
    if isinstance(obj, np.ndarray):
        return {"__ndarray__": obj.tolist(), "dtype": str(obj.dtype), "shape": list(obj.shape)}
    if isinstance(obj, np.generic):  # numpy scalar
        return obj.item()
    if isinstance(obj, (str, bool, int, float)) or obj is None:
        return obj
    if isinstance(obj, (list, tuple)):
        return {"__seq__": type(obj).__name__, "items": [_encode(x) for x in obj]}
    if isinstance(obj, dict):
        return {"__dict__": [[_encode(k), _encode(v)] for k, v in obj.items()]}
    raise TypeError(f"unencodable output type: {type(obj).__name__}")


def _decode(obj):
    """Inverse of _encode. Operates only on JSON primitives (parsed by json.loads),
    so there is no code-execution path here -- the worst malformed input yields a
    wrong/!=-reference value, never code execution."""
    if isinstance(obj, dict):
        if "__ndarray__" in obj:
            arr = np.array(obj["__ndarray__"], dtype=obj.get("dtype"))
            shape = obj.get("shape")
            if shape is not None:
                arr = arr.reshape(shape)
            return arr
        if "__seq__" in obj:
            items = [_decode(x) for x in obj["items"]]
            return tuple(items) if obj["__seq__"] == "tuple" else items
        if "__dict__" in obj:
            return {_decode(k): _decode(v) for k, v in obj["__dict__"]}
        return obj  # plain JSON object
    if isinstance(obj, list):
        return [_decode(x) for x in obj]
    return obj


def _send(sock, payload_bytes: bytes) -> None:
    sock.sendall(struct.pack("!Q", len(payload_bytes)) + payload_bytes)


def _recv(sock, timeout: float) -> bytes | None:
    """Read one length-prefixed message with a wall-clock bound. Returns None on
    timeout / EOF / oversize. Reads RAW BYTES only; decoding is the caller's job
    (and is JSON, never pickle)."""
    sock.settimeout(timeout)
    try:
        header = _recv_exact(sock, 8, timeout)
        if header is None:
            return None
        (length,) = struct.unpack("!Q", header)
        if length > _MAX_MSG:
            return None
        return _recv_exact(sock, length, timeout)
    except (TimeoutError, OSError):
        return None


def _recv_exact(sock, n: int, timeout: float) -> bytes | None:
    import time as _time

    chunks = []
    got = 0
    deadline = _time.monotonic() + timeout
    while got < n:
        remaining = deadline - _time.monotonic()
        if remaining <= 0:
            return None
        sock.settimeout(remaining)
        try:
            chunk = sock.recv(min(n - got, 1 << 20))
        except (TimeoutError, OSError):
            return None
        if not chunk:
            return None  # EOF
        chunks.append(chunk)
        got += len(chunk)
    return b"".join(chunks)


# ---------------------------------------------------------------------------
# Child worker: load candidate, then loop {recv JSON input -> call -> send JSON out}.
# Runs NO oracle logic. The candidate may do whatever it wants here; it cannot reach
# the parent's oracle, and its only output channel is JSON bytes.
# ---------------------------------------------------------------------------
def _worker(program_path, entrypoint_names, sock):
    # Become our own process-group / session leader so the parent can reap the WHOLE
    # group (incl. any forks the candidate detaches) with killpg on timeout/exit.
    try:
        os.setsid()
    except OSError:
        pass
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location("candidate", program_path)
        if spec is None or spec.loader is None:
            _send(sock, json.dumps({"status": "fatal", "reason": "load failed: no spec"}).encode())
            return
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        except Exception as e:
            _send(sock, json.dumps(
                {"status": "fatal", "reason": f"load failed: {type(e).__name__}"}).encode())
            return
        fn = None
        for name in entrypoint_names:
            fn = getattr(mod, name, None)
            if fn is not None:
                break
        if fn is None or not callable(fn):
            reason = "no entrypoint" if fn is None else "entrypoint not callable"
            _send(sock, json.dumps({"status": "fatal", "reason": reason}).encode())
            return
        _send(sock, json.dumps({"status": "ready"}).encode())

        while True:
            raw = _recv(sock, timeout=3600)  # child waits for parent; parent bounds total time
            if raw is None:
                return
            msg = json.loads(raw)
            cmd = msg.get("cmd")
            if cmd == "stop":
                return
            if cmd == "time":
                # Time the candidate INSIDE the child (best-of-repeats per input set),
                # returning only the elapsed seconds (a float). Keeps timing honest
                # (no IPC overhead) and the candidate out of the parent.
                import time as _t

                arg_sets = [tuple(_decode(a) for a in s) for s in msg["arg_sets"]]
                repeats = int(msg.get("repeats", 5))
                try:
                    for a in arg_sets:  # warmup
                        fn(*a)
                    total = 0.0
                    for a in arg_sets:
                        best = float("inf")
                        for _ in range(repeats):
                            t0 = _t.perf_counter()
                            fn(*a)
                            best = min(best, _t.perf_counter() - t0)
                        total += best
                    _send(sock, json.dumps({"status": "ok", "elapsed": float(total)}).encode())
                except Exception as e:
                    _send(sock, json.dumps(
                        {"status": "err", "reason": f"raised {type(e).__name__}"}).encode())
                continue
            args = tuple(_decode(a) for a in msg["args"])
            try:
                out = fn(*args)
                encoded = _encode(out)  # may raise TypeError -> reported as err
                _send(sock, json.dumps({"status": "ok", "output": encoded}).encode())
            except TypeError as e:
                _send(sock, json.dumps(
                    {"status": "err", "reason": f"unencodable: {type(e).__name__}"}).encode())
            except Exception as e:
                _send(sock, json.dumps(
                    {"status": "err", "reason": f"raised {type(e).__name__}"}).encode())
    except Exception:
        # last-resort: stay silent; the parent will see EOF/timeout and reject.
        pass
    finally:
        try:
            sock.close()
        except Exception:
            pass


class CandidateError(Exception):
    """Raised in the PARENT by IsolatedCandidate.output_fn on any sandbox failure
    (load error, raise, crash, timeout, unencodable/garbage output). The oracle's
    per-layer try/except turns it into a rejection."""


class IsolatedCandidate:
    """Context manager: starts a sandbox worker for `program_path` and exposes
    `output_fn(args) -> output`. Pass `.output_fn` to `layered_oracle(..., output_fn=)`.

    The parent decodes worker replies with json.loads + a numpy-aware decoder -- never
    pickle -- so nothing the candidate emits can execute code in the parent."""

    def __init__(self, program_path, entrypoint_names=None, timeout=DEFAULT_TIMEOUT):
        self.program_path = program_path
        self.entrypoint_names = list(entrypoint_names or [CANONICAL_ENTRYPOINT])
        self.timeout = timeout
        self._proc = None
        self._sock = None
        self.load_error: str | None = None
        self._dead = False

    def __enter__(self):
        import socket

        # A socketpair carries LENGTH-FRAMED RAW BYTES (json), not picklable
        # Connection objects -- so even if the candidate grabs the child's socket, the
        # parent only ever json.loads() what it reads.
        p_sock, c_sock = socket.socketpair()
        self._sock = p_sock
        self._proc = _CTX.Process(
            target=_worker,
            args=(self.program_path, self.entrypoint_names, c_sock),
            daemon=False,  # we reap the process group ourselves on exit/timeout
        )
        self._proc.start()
        c_sock.close()  # parent keeps p_sock only
        # await readiness / load result
        raw = _recv(self._sock, self.timeout)
        if raw is None:
            self.load_error, self._dead = "load timeout", True
            return self
        try:
            msg = json.loads(raw)
        except Exception:
            self.load_error, self._dead = "load failed: bad handshake", True
            return self
        if msg.get("status") == "ready":
            return self
        self.load_error = msg.get("reason", "load failed")
        self._dead = True
        return self

    def output_fn(self, args):
        if self.load_error is not None:
            raise CandidateError(self.load_error)
        if self._dead or self._sock is None:
            raise CandidateError("crashed")
        try:
            payload = json.dumps({"args": [_encode(a) for a in args]}).encode()
        except TypeError as e:
            # An input we can't encode is our bug, not the candidate's; surface clearly.
            raise CandidateError(f"uninputtable: {type(e).__name__}") from None
        try:
            _send(self._sock, payload)
        except OSError:
            self._dead = True
            raise CandidateError("crashed") from None
        raw = _recv(self._sock, self.timeout)
        if raw is None:
            self._dead = True
            raise CandidateError("timeout")
        try:
            msg = json.loads(raw)
        except Exception:
            self._dead = True
            raise CandidateError("garbage output") from None
        status = msg.get("status")
        if status == "ok":
            return _decode(msg["output"])
        if status == "err":
            raise CandidateError(msg.get("reason", "error"))
        self._dead = True
        raise CandidateError(msg.get("reason", "fatal"))

    def time_fn(self, arg_sets, repeats: int = 5) -> float:
        """Total best-of-`repeats` wall time of the candidate over `arg_sets`,
        measured INSIDE the sandbox (no IPC overhead; candidate stays out of the
        parent). Raises CandidateError on failure. Used only AFTER correctness passes,
        to compute speedup against an in-parent reference timing."""
        if self._dead or self._sock is None:
            raise CandidateError("crashed")
        payload = json.dumps(
            {"cmd": "time", "arg_sets": [[_encode(a) for a in s] for s in arg_sets],
             "repeats": repeats}
        ).encode()
        try:
            _send(self._sock, payload)
        except OSError:
            self._dead = True
            raise CandidateError("crashed") from None
        raw = _recv(self._sock, self.timeout)
        if raw is None:
            self._dead = True
            raise CandidateError("timeout")
        try:
            msg = json.loads(raw)
        except Exception:
            self._dead = True
            raise CandidateError("garbage output") from None
        if msg.get("status") == "ok":
            return float(msg["elapsed"])
        raise CandidateError(msg.get("reason", "error"))

    def __exit__(self, *exc):
        try:
            if self._sock is not None and not self._dead:
                try:
                    _send(self._sock, json.dumps({"cmd": "stop"}).encode())
                except Exception:
                    pass
            if self._sock is not None:
                self._sock.close()
        finally:
            self._reap()
        return False

    def _reap(self):
        """Kill the worker AND its process group so detached grandchildren can't
        outlive it (audit finding: orphaned grandchild survives terminate())."""
        if self._proc is None:
            return
        self._proc.join(timeout=1.0)
        if self._proc.is_alive():
            self._proc.terminate()
            self._proc.join(timeout=1.0)
        if self._proc.is_alive():
            self._proc.kill()
            self._proc.join(timeout=1.0)
        # best-effort: reap the child's process group (it's its own session leader
        # only if it called setsid; we kill the pid's group to catch raw forks).
        try:
            pid = self._proc.pid
            if pid is not None:
                os.killpg(os.getpgid(pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass
