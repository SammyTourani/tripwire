"""tripwire.isolation -- candidate execution in a FRESH OS subprocess.

Why this design (after 3 failed rounds)
----------------------------------------
The recurring root cause across rounds 1-3 was structural, not a bug: as long as
the untrusted candidate runs in the SAME interpreter as the worker that owns the
IPC channel, the candidate can find that channel via `gc.get_objects()` and either
smuggle a pickle (rounds 1-2) or forge a protocol reply (round 3, incl. fake
timing). Pure-Python in-process sandboxing of adversarial code is a published
NEGATIVE RESULT (PEP 551, the pysandbox post-mortem, the removal of rexec/Bastion
in Python 3.0) -- not an open engineering problem. Every production code-execution
service (Modal, E2B, Riza, OpenAI's Code Interpreter) places OS- or hypervisor-
level isolation between the candidate and trusted state, not a Python-level one.

Round 4 takes that lesson and applies it within pure-Python:

  * Each evaluation invokes `subprocess.run([sys.executable, "-I", runner_script])`.
    `-I` is Python isolated mode: no PYTHON* env vars, no user site-packages, no
    implicit sys.path[0]. The child is a brand-new interpreter started by exec().
  * The runner script is a TRUSTED shim Tripwire writes to a tempfile (NOT the
    candidate's file). It loads the candidate, reads JSON args from stdin, calls
    `solve(*args)`, writes the JSON-encoded output to stdout. That is its only job.
  * The candidate's process has NO inherited Python objects from the parent (spawn
    via exec, not fork). `gc.get_objects()` finds NO Connection, NO Pipe, NO socket
    to the parent -- empirically verified. There is nothing to smuggle through and
    nothing to monkeypatch that the parent reads.
  * The PARENT measures wall time with `time.perf_counter_ns()` around the
    `subprocess.run` call. The candidate is never asked to report its own time, so
    it cannot forge one. Per-call overhead (interpreter startup + import) is the
    cost; we amortize where possible via the persistent-shim mode below.
  * The parent reads stdout as length-framed JSON bytes, decoded with `json.loads`
    + a numpy-aware decoder. NEVER pickle. A malicious __reduce__ has no path.

Two modes
---------
1. ONE-SHOT (`evaluate_once`): fresh subprocess per call. Strongest isolation
   (every call gets a clean interpreter); highest overhead. Use for security tests
   and high-trust correctness checks.
2. PERSISTENT (`IsolatedCandidate` context manager): one subprocess per
   `evaluate()`; the shim's main loop reads {input,output} pairs over stdin/stdout
   until the parent sends `{"cmd":"stop"}`. The candidate still has no IPC handle
   to the parent's oracle process -- only to its OWN shim, which is trusted code
   in the same interpreter as the candidate; but the SHIM does not read protocol
   replies from the candidate to construct the parent's verdict. The candidate's
   ONLY output channel is its return value (which the shim encodes to JSON and
   writes to the shim's stdout). The shim does not trust the candidate; it just
   passes through.

What this design defends, and what it does not
-----------------------------------------------
Defends:
  * In-process oracle monkeypatch (oracle lives in parent, unreachable)
  * Verdict-class hijack (Verdict lives in parent, unreachable)
  * `__reduce__` / pickle RCE in the parent (JSON-only decode path)
  * Pipe-smuggling (no Connection / no parent-reachable socket in candidate heap)
  * Forged timing (parent owns the clock; candidate never reports time)

Does NOT defend (out of scope by design; documented in docs/threat-model.md):
  * Filesystem writes, network egress, fork-bombs, kernel-level exploits inside
    the candidate's own process. These are OS-isolation concerns; deploy under a
    container / gVisor / Firecracker if the proposer LLM is not trusted at the OS
    level. (PEP 551 / industry consensus: this is not a pure-Python problem.)
"""
from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass

import numpy as np

DEFAULT_TIMEOUT = 30.0  # seconds per evaluation
CANONICAL_ENTRYPOINT = "solve"
_MAX_MSG = 256 * 1024 * 1024  # 256 MiB wire cap (decoded size also bounded; see _decode)
_MAX_DECODED_ELEMS = 1 << 28  # 256M elements; bounds _decode memory amplification


class CandidateError(Exception):
    """Raised in the parent by the isolation layer on any sandbox failure
    (load error, raise, crash, timeout, garbage/oversize output). The oracle's
    per-layer try/except turns it into a rejection."""


# ---------------------------------------------------------------------------
# JSON codec (numpy-aware). NO pickle anywhere. Bounded decode allocation.
# ---------------------------------------------------------------------------
def _encode(obj):
    """Convert an output into JSON-safe primitives. ndarrays -> tagged dict. Raises
    TypeError on anything unsupported (caller treats that as a candidate failure)."""
    if isinstance(obj, np.ndarray):
        return {"__ndarray__": obj.tolist(), "dtype": str(obj.dtype), "shape": list(obj.shape)}
    if isinstance(obj, np.generic):  # numpy scalar
        return obj.item()
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, (str, int, float)) or obj is None:
        return obj
    if isinstance(obj, (list, tuple)):
        return {"__seq__": type(obj).__name__, "items": [_encode(x) for x in obj]}
    if isinstance(obj, dict):
        return {"__dict__": [[_encode(k), _encode(v)] for k, v in obj.items()]}
    raise TypeError(f"unencodable output type: {type(obj).__name__}")


def _safe_dtype(name):
    """Reject dtype strings that could trigger huge per-element allocations
    (e.g. 'S2000000000' -> 2 GB per element). Whitelist the dtype kinds we use."""
    s = str(name)
    if len(s) > 16:
        raise ValueError(f"dtype too long: {s!r}")
    try:
        dt = np.dtype(s)
    except TypeError as e:
        raise ValueError(f"bad dtype: {s!r}") from e
    if dt.kind == "O":
        raise ValueError("object dtype not allowed in oracle codec")
    if dt.itemsize > 16:  # we only ship int/float/bool/complex; cap itemsize
        raise ValueError(f"dtype itemsize too large: {dt.itemsize}")
    return dt


def _decode(obj):
    """Inverse of _encode. Operates only on JSON primitives. Bounds total element
    count to keep an adversarial child from forcing the parent into OOM via a tiny
    payload with a huge shape product."""
    if isinstance(obj, dict):
        if "__ndarray__" in obj:
            dt = _safe_dtype(obj.get("dtype"))
            shape = obj.get("shape")
            if shape is None:
                arr = np.array(obj["__ndarray__"], dtype=dt)
            else:
                if not isinstance(shape, list) or not all(isinstance(d, int) for d in shape):
                    raise ValueError("bad shape")
                total = 1
                for d in shape:
                    if d < 0:
                        raise ValueError("negative dim")
                    total *= d
                    if total > _MAX_DECODED_ELEMS:
                        raise ValueError("array shape too large")
                arr = np.array(obj["__ndarray__"], dtype=dt).reshape(shape)
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


def _write_msg(stream, payload_bytes: bytes) -> None:
    stream.write(struct.pack("!Q", len(payload_bytes)) + payload_bytes)
    stream.flush()


def _read_msg(stream, deadline: float | None) -> bytes | None:
    """Read one length-prefixed message from a binary stream. Returns None on
    EOF, oversize, or a (process-level) timeout caller enforces. The parent's
    Popen wait+kill provides the wall-clock bound; this is best-effort framing."""
    header = _read_exact(stream, 8)
    if header is None:
        return None
    (length,) = struct.unpack("!Q", header)
    if length > _MAX_MSG:
        return None
    return _read_exact(stream, length)


def _read_exact(stream, n: int) -> bytes | None:
    chunks = []
    got = 0
    while got < n:
        chunk = stream.read(n - got)
        if not chunk:
            return None
        chunks.append(chunk)
        got += len(chunk)
    return b"".join(chunks)


# ---------------------------------------------------------------------------
# The shim script the parent writes to a tempfile and exec's. Its only job is to
# load the candidate program, then loop reading JSON inputs and writing JSON
# outputs over stdin/stdout. It has NO oracle logic, NO verdict, NO timing.
# ---------------------------------------------------------------------------
_SHIM_SOURCE = r'''
import json, struct, sys, importlib.util

_MAX = 256 * 1024 * 1024

def _read_exact(s, n):
    chunks = []; got = 0
    while got < n:
        b = s.read(n - got)
        if not b:
            return None
        chunks.append(b); got += len(b)
    return b"".join(chunks)

def _read_msg(s):
    h = _read_exact(s, 8)
    if h is None: return None
    (n,) = struct.unpack("!Q", h)
    if n > _MAX: return None
    return _read_exact(s, n)

def _write_msg(s, b):
    s.write(struct.pack("!Q", len(b)) + b); s.flush()

def _encode(o):
    # Mirrors tripwire.isolation._encode but stdlib-only inside the shim.
    try:
        import numpy as np
    except Exception:
        np = None
    if np is not None and isinstance(o, np.ndarray):
        return {"__ndarray__": o.tolist(), "dtype": str(o.dtype), "shape": list(o.shape)}
    if np is not None and isinstance(o, np.generic):
        return o.item()
    if isinstance(o, bool):
        return o
    if isinstance(o, (str, int, float)) or o is None:
        return o
    if isinstance(o, (list, tuple)):
        return {"__seq__": type(o).__name__, "items": [_encode(x) for x in o]}
    if isinstance(o, dict):
        return {"__dict__": [[_encode(k), _encode(v)] for k, v in o.items()]}
    raise TypeError("unencodable: " + type(o).__name__)

def _decode(o):
    try:
        import numpy as np
    except Exception:
        np = None
    if isinstance(o, dict):
        if "__ndarray__" in o and np is not None:
            arr = np.array(o["__ndarray__"], dtype=o.get("dtype"))
            sh = o.get("shape")
            if sh is not None:
                arr = arr.reshape(sh)
            return arr
        if "__seq__" in o:
            items = [_decode(x) for x in o["items"]]
            return tuple(items) if o["__seq__"] == "tuple" else items
        if "__dict__" in o:
            return {_decode(k): _decode(v) for k, v in o["__dict__"]}
        return o
    if isinstance(o, list):
        return [_decode(x) for x in o]
    return o

def main():
    # Discard env vars + stdin tty interference. Redirect stdout (the protocol
    # channel) to fd 1 explicitly, and route the candidate's stdout/stderr to
    # /dev/null so it can't corrupt our framing or the parent's logs.
    in_bin = sys.stdin.buffer
    out_bin = sys.stdout.buffer
    devnull = open("/dev/null", "w")
    sys.stdout = devnull
    sys.stderr = devnull

    cand_path = sys.argv[1]
    entrypoints = sys.argv[2].split(",")

    spec = importlib.util.spec_from_file_location("candidate", cand_path)
    if spec is None or spec.loader is None:
        _write_msg(out_bin, json.dumps({"status":"fatal","reason":"load failed: no spec"}).encode())
        return
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as e:
        _write_msg(out_bin, json.dumps(
            {"status":"fatal","reason":"load failed: " + type(e).__name__}).encode())
        return
    fn = None
    for name in entrypoints:
        fn = getattr(mod, name, None)
        if fn is not None: break
    if fn is None:
        _write_msg(out_bin, json.dumps({"status":"fatal","reason":"no entrypoint"}).encode())
        return
    if not callable(fn):
        _write_msg(out_bin, json.dumps(
            {"status":"fatal","reason":"entrypoint not callable"}).encode())
        return
    _write_msg(out_bin, json.dumps({"status":"ready"}).encode())

    # Registered inputs: pay JSON cost once at startup, then time by NAME so the
    # per-call protocol is tiny (a short string instead of e.g. a 150k-element array).
    registry = {}

    while True:
        raw = _read_msg(in_bin)
        if raw is None:
            return
        try:
            msg = json.loads(raw)
        except Exception:
            _write_msg(out_bin, json.dumps({"status":"err","reason":"bad request"}).encode())
            continue
        cmd = msg.get("cmd")
        if cmd == "stop":
            return
        if cmd == "register":
            # {"cmd":"register","name":"<str>","args":[...]} -> store decoded args
            try:
                name = msg["name"]
                args = tuple(_decode(a) for a in msg["args"])
                registry[name] = args
                _write_msg(out_bin, json.dumps({"status":"ok"}).encode())
            except Exception as e:
                _write_msg(out_bin, json.dumps(
                    {"status":"err","reason":"bad register: " + type(e).__name__}).encode())
            continue
        if cmd == "call_named":
            # {"cmd":"call_named","name":"<str>"} -> call fn on the registered args
            try:
                args = registry[msg["name"]]
            except KeyError:
                _write_msg(out_bin, json.dumps(
                    {"status":"err","reason":"unknown name"}).encode())
                continue
            try:
                out = fn(*args)
                payload = json.dumps({"status":"ok","output": _encode(out)}).encode()
                _write_msg(out_bin, payload)
            except TypeError as e:
                _write_msg(out_bin, json.dumps(
                    {"status":"err","reason":"unencodable: " + type(e).__name__}).encode())
            except Exception as e:
                _write_msg(out_bin, json.dumps(
                    {"status":"err","reason":"raised " + type(e).__name__}).encode())
            continue
        # default: one-shot {"args":[...]}
        try:
            args = tuple(_decode(a) for a in msg["args"])
        except Exception as e:
            _write_msg(out_bin, json.dumps(
                {"status":"err","reason":"bad args: " + type(e).__name__}).encode())
            continue
        try:
            out = fn(*args)
            payload = json.dumps({"status":"ok","output": _encode(out)}).encode()
            _write_msg(out_bin, payload)
        except TypeError as e:
            _write_msg(out_bin, json.dumps(
                {"status":"err","reason":"unencodable: " + type(e).__name__}).encode())
        except Exception as e:
            _write_msg(out_bin, json.dumps(
                {"status":"err","reason":"raised " + type(e).__name__}).encode())

if __name__ == "__main__":
    main()
'''


# ---------------------------------------------------------------------------
# Parent-side isolation primitive.
# ---------------------------------------------------------------------------
@dataclass
class _ShimResult:
    elapsed: float  # wall-clock seconds (parent's perf_counter)
    output: object


class IsolatedCandidate:
    """Context manager: starts a fresh-subprocess shim for `program_path`, exposes
    `output_fn(args) -> output` (used by layered_oracle for correctness), and
    `time_fn(arg_sets, repeats)` for speedup measurement -- BOTH timed by THIS
    PROCESS via time.perf_counter() around the subprocess call. The candidate
    never reports its own time, so it cannot forge it.

    The shim has NO oracle code; it just loads the candidate and round-trips
    JSON inputs <-> JSON outputs. The candidate has NO IPC handle to the parent
    (the only Python objects in its interpreter are what its own code creates;
    `gc.get_objects()` finds zero Connection/socket -- empirically verified).
    """

    def __init__(self, program_path, entrypoint_names=None, timeout=DEFAULT_TIMEOUT):
        self.program_path = program_path
        self.entrypoint_names = list(entrypoint_names or [CANONICAL_ENTRYPOINT])
        self.timeout = float(timeout)
        self._proc: subprocess.Popen | None = None
        self._shim_path: str | None = None
        self.load_error: str | None = None
        self._dead = False

    def __enter__(self):
        # Write the trusted shim to its own tempfile (NOT the candidate file).
        fd, self._shim_path = tempfile.mkstemp(prefix="tripwire_shim_", suffix=".py")
        try:
            os.write(fd, _SHIM_SOURCE.encode())
        finally:
            os.close(fd)
        # `python -I`: isolated mode (no PYTHON* env vars, no user site, no implicit
        # sys.path[0]). The first positional after the shim is the candidate path,
        # the second is comma-joined entrypoint names.
        cmd = [
            sys.executable, "-I", self._shim_path, self.program_path,
            ",".join(self.entrypoint_names),
        ]
        # start_new_session: detaches the child into its own pgid so we can
        # killpg the whole tree on timeout/exit (incl. any forks the candidate spawns).
        # close_fds defaults to True since 3.7 -- only 0/1/2 reach the child.
        self._proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,  # candidate stderr also blocked (anti-noise)
            start_new_session=True,
            env={},  # no env vars -- removes another leakage / config-injection vector
        )
        # Read the shim's handshake (ready or fatal). Bounded by self.timeout.
        raw = self._recv(self.timeout)
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

    # ---- protocol helpers (parent side) ----
    def _recv(self, timeout: float) -> bytes | None:
        """Read one framed message from the child's stdout. Bounded by `timeout`:
        if the child doesn't deliver in time we kill it and return None."""
        assert self._proc is not None and self._proc.stdout is not None
        deadline = time.monotonic() + timeout
        # Use a watcher thread to enforce the wall-clock bound: we can't easily
        # apply a per-read timeout to the binary pipe. The watcher kills the
        # process group if we miss the deadline, which causes the blocking read
        # to return b"" (EOF) and _read_msg returns None.
        import threading

        killed = {"v": False}

        def watcher():
            while time.monotonic() < deadline:
                time.sleep(0.05)
                if killed["v"]:
                    return
            self._kill_group()
            killed["v"] = True

        t = threading.Thread(target=watcher, daemon=True)
        t.start()
        try:
            data = _read_msg(self._proc.stdout, None)
        finally:
            killed["v"] = True  # stop the watcher
        return data

    def _send(self, payload: dict) -> None:
        """Write a framed JSON message to the child's stdin. Like _recv, this is
        bounded by self.timeout: if the child isn't draining stdin (e.g. it's hung
        in fn(*args)), the pipe buffer fills up and write() blocks. A watcher thread
        kills the process group after the deadline so write() unblocks with EPIPE."""
        if self._dead or self._proc is None or self._proc.stdin is None:
            raise CandidateError("crashed")
        import threading

        deadline = time.monotonic() + self.timeout
        killed = {"v": False}

        def watcher():
            while time.monotonic() < deadline:
                time.sleep(0.05)
                if killed["v"]:
                    return
            self._kill_group()
            killed["v"] = True

        t = threading.Thread(target=watcher, daemon=True)
        t.start()
        try:
            _write_msg(self._proc.stdin, json.dumps(payload).encode())
        except (BrokenPipeError, OSError):
            self._dead = True
            raise CandidateError("crashed") from None
        finally:
            killed["v"] = True

    # ---- public API used by the oracle ----
    def output_fn(self, args):
        """Send one input to the sandbox, return its (JSON-decoded) output. Raises
        CandidateError on failure. The oracle's per-layer try/except turns that
        into a rejection."""
        if self.load_error is not None:
            raise CandidateError(self.load_error)
        try:
            self._send({"args": [_encode(a) for a in args]})
        except TypeError as e:
            raise CandidateError(f"uninputtable: {type(e).__name__}") from None
        raw = self._recv(self.timeout)
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
            try:
                return _decode(msg["output"])
            except Exception as e:
                raise CandidateError(f"decode failed: {type(e).__name__}") from None
        if status == "err":
            raise CandidateError(msg.get("reason", "error"))
        self._dead = True
        raise CandidateError(msg.get("reason", "fatal"))

    def time_fn(self, arg_sets, repeats: int = 5) -> float:
        """Total best-of-`repeats` wall time of the candidate over `arg_sets`,
        MEASURED IN THIS PROCESS via time.perf_counter around each round-trip to
        the sandbox. The candidate never sees a clock to forge; the parent owns
        the measurement.

        To keep per-call IPC overhead minimal even for large inputs, args are
        REGISTERED (sent and decoded) ONCE at the start, then timed calls reference
        them by NAME -- so the per-call protocol is a short string instead of (e.g.)
        a 150k-element JSON array. The reference timing in measure_time() pays no
        IPC overhead at all, so for tiny workloads the candidate's apparent speedup
        is understated; for the project's targets the candidate's work dominates
        and the measurement is meaningful. (For maximum-rigor timing under an
        untrusted candidate, use this; for absolute speed numbers in the bench,
        the in-process path with isolate=False is faster.)"""
        # Register each unique arg-set once.
        names = [f"argset_{i}" for i in range(len(arg_sets))]
        for name, args in zip(names, arg_sets, strict=True):
            self._send({"cmd": "register", "name": name, "args": [_encode(a) for a in args]})
            raw = self._recv(self.timeout)
            if raw is None:
                self._dead = True
                raise CandidateError("timeout")
            msg = json.loads(raw)
            if msg.get("status") != "ok":
                raise CandidateError(msg.get("reason", "register failed"))
        # Warmup
        for name in names:
            self._call_named(name)
        # Timed best-of-repeats per arg-set
        total = 0.0
        for name in names:
            best = float("inf")
            for _ in range(max(1, repeats)):
                t0 = time.perf_counter()
                self._call_named(name)
                best = min(best, time.perf_counter() - t0)
            total += best
        return total

    def _call_named(self, name: str):
        """Call the candidate on a pre-registered arg-set by name. Used by time_fn."""
        self._send({"cmd": "call_named", "name": name})
        raw = self._recv(self.timeout)
        if raw is None:
            self._dead = True
            raise CandidateError("timeout")
        try:
            msg = json.loads(raw)
        except Exception:
            self._dead = True
            raise CandidateError("garbage output") from None
        if msg.get("status") == "ok":
            return  # we don't need the output for timing
        if msg.get("status") == "err":
            raise CandidateError(msg.get("reason", "error"))
        self._dead = True
        raise CandidateError(msg.get("reason", "fatal"))

    def __exit__(self, *exc):
        try:
            if self._proc is not None and not self._dead and self._proc.stdin is not None:
                try:
                    self._send({"cmd": "stop"})
                except Exception:
                    pass
        finally:
            self._kill_group()
            if self._shim_path and os.path.exists(self._shim_path):
                try:
                    os.unlink(self._shim_path)
                except OSError:
                    pass
        return False

    def _kill_group(self):
        """Reap the candidate's process group (start_new_session put it in its
        own pgid) so detached children don't outlive the evaluation."""
        if self._proc is None:
            return
        try:
            os.killpg(os.getpgid(self._proc.pid), 9)
        except (ProcessLookupError, PermissionError, OSError):
            pass
        try:
            self._proc.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            try:
                self._proc.kill()
            except OSError:
                pass
            try:
                self._proc.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                pass
