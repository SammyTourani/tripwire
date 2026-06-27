"""tripwire.measure -- shared measurement and comparison primitives.

This module is the single source of truth for:
  * reward-hacking-resistant timing (warmup + best-of-N per shape, summed across
    multiple shapes), and
  * the comparison primitives the oracle's L1/L3 layers use (exact vs tolerance).

It is deliberately dependency-light (numpy only) and contains NO oracle logic,
NO Target type, and NO evolutionary-loop code (HARD RULE 1). The oracle lives in
tripwire/oracle.py (task 1.2); the Target contract is frozen in 1.3; the
OpenEvolve adapter in 1.4.

Phase 2 task 2.6 ("measurement hardening") OWNS this file -- CPU pinning, variance
reporting, repeat-until-stable. Keep the public surface (measure_time, speedup,
exact_equal, close_equal) stable so downstream agents can rely on it.
"""
from __future__ import annotations

import math
import time
from collections.abc import Callable

import numpy as np


# ---------------------------------------------------------------------------
# Reward-hacking-resistant measurement: warmup + best-of-repeats per shape,
# summed across multiple shapes. A hack that returns a constant looks
# "infinitely fast" -- which is exactly the Sakana 10-100x mirage we surface.
# ---------------------------------------------------------------------------
def _time_once(fn: Callable, args) -> float:
    t0 = time.perf_counter()
    fn(*args)
    return time.perf_counter() - t0


def measure_time(fn: Callable, arg_sets, repeats: int = 5) -> float:
    """Total best-of-`repeats` wall time across every shape in `arg_sets`.

    Runs each shape once first as a warmup / smoke test; if the candidate raises
    on any shape, returns math.inf so callers treat it as unusable.
    """
    for args in arg_sets:  # warmup / smoke test
        try:
            fn(*args)
        except Exception:
            return math.inf
    total = 0.0
    for args in arg_sets:
        total += min(_time_once(fn, args) for _ in range(repeats))
    return total


def speedup(ref_fn: Callable, cand_fn: Callable, arg_sets, repeats: int = 5) -> float:
    """ref_time / cand_time across `arg_sets`. inf if the candidate is ~instant
    (a red flag, not a winner -- see HARD RULE 6 / threat-model attack class 3)."""
    t_ref = measure_time(ref_fn, arg_sets, repeats)
    t_cand = measure_time(cand_fn, arg_sets, repeats)
    if t_cand <= 0:
        return math.inf
    return t_ref / t_cand


# ---------------------------------------------------------------------------
# Comparison primitives
# ---------------------------------------------------------------------------
def exact_equal(a, b) -> bool:
    """Bit-exact comparison. SOUND ONLY for `structural` targets (ADR-004)."""
    if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
        return np.array_equal(np.asarray(a), np.asarray(b))
    if isinstance(a, float) or isinstance(b, float):
        return float(a) == float(b)  # bit-exact for floats
    return a == b


def close_equal(a, b, rtol: float = 1e-6, atol: float = 1e-9) -> bool:
    """Tolerance comparison for `numeric` targets (ADR-004): correct speedups
    (vectorization, reordered reduction, FMA) change low bits."""
    try:
        return bool(
            np.allclose(
                np.asarray(a, dtype=float),
                np.asarray(b, dtype=float),
                rtol=rtol,
                atol=atol,
            )
        )
    except Exception:
        return a == b
