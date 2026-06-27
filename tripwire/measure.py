"""tripwire.measure -- shared measurement and comparison primitives.

This module is the single source of truth for:
  * reward-hacking-resistant timing (warmup + best-of-N per shape, summed across
    multiple shapes), and
  * the comparison primitives the oracle's L1/L3 layers use (exact vs tolerance).

It is deliberately dependency-light (numpy only) and contains NO oracle logic,
NO Target type, and NO evolutionary-loop code (HARD RULE 1). The oracle lives in
tripwire/oracle.py (task 1.2); the Target contract is frozen in 1.3; the
OpenEvolve adapter in 1.4.

MEASUREMENT HARDENING (Phase 2 task 2.6)
----------------------------------------
Goal: speedup numbers nobody can challenge. The "phantom improvement from random
noise" failure (a candidate that looks faster only because of timing jitter) must
be impossible. The hardened path adds, on top of warmup + best-of-N:
  * warmup discipline + GC quiesce per timing batch,
  * repeat-until-stable: keep sampling until the timing's relative spread is below
    a threshold (or a cap is hit), so reported numbers are reproducible,
  * variance reporting: every measurement carries best/median/mean/std and a
    relative-std, and every speedup carries a conservative lower bound derived from
    the two timing distributions.

The original public surface (measure_time, speedup, exact_equal, close_equal) is
FROZEN -- same signatures, same behavior -- because the oracle, the seed, and every
Phase-2 target import it. The hardened API (measure_stats, speedup_stats, and the
MeasurementStats / SpeedupStats dataclasses) is purely ADDITIVE.
"""
from __future__ import annotations

import gc
import math
import statistics
import time
from collections.abc import Callable
from dataclasses import dataclass, field

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

    FROZEN public surface (do not change signature/behavior).
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
    (a red flag, not a winner -- see HARD RULE 6 / threat-model attack class 3).

    FROZEN public surface (do not change signature/behavior).
    """
    t_ref = measure_time(ref_fn, arg_sets, repeats)
    t_cand = measure_time(cand_fn, arg_sets, repeats)
    if t_cand <= 0:
        return math.inf
    return t_ref / t_cand


# ---------------------------------------------------------------------------
# Hardened measurement (task 2.6) -- ADDITIVE. Variance-aware, repeat-until-stable.
# ---------------------------------------------------------------------------
# Defaults chosen to be CI-friendly (fast) while still rejecting noise. Callers
# that want tighter bounds raise max_batches / lower target_rel_std.
_DEFAULT_WARMUP = 2
_DEFAULT_BATCH = 5            # samples (each a best-of-shape pass) per batch
_DEFAULT_MAX_BATCHES = 6      # cap on repeat-until-stable
_DEFAULT_TARGET_REL_STD = 0.05  # stop once relative std of samples <= 5%


@dataclass(frozen=True)
class MeasurementStats:
    """Timing distribution for `fn` over `arg_sets` (seconds). `best` is the
    summed best-of-shape time -- the metric speedup() uses -- while median/mean/std
    describe run-to-run stability. `relative_std` = std/mean (0 if mean is 0)."""

    best: float
    median: float
    mean: float
    std: float
    samples: list[float] = field(default_factory=list)
    raised: bool = False

    @property
    def relative_std(self) -> float:
        return (self.std / self.mean) if self.mean > 0 else 0.0

    @property
    def stable(self) -> bool:
        """True if the samples are tight enough to trust (low jitter)."""
        return (not self.raised) and self.relative_std <= _DEFAULT_TARGET_REL_STD


@dataclass(frozen=True)
class SpeedupStats:
    """A speedup measurement you can defend: the point estimate plus a conservative
    LOWER bound that accounts for timing jitter in BOTH ref and candidate. If
    `lower_bound > 1` the speedup survives noise; if it straddles 1 the "win" may
    be phantom (the PIE failure 2.6 exists to prevent)."""

    speedup: float
    lower_bound: float
    ref: MeasurementStats
    cand: MeasurementStats

    @property
    def trustworthy(self) -> bool:
        """A real, defensible speedup: both sides measured stably, candidate didn't
        crash, and even the conservative lower bound clears 1.0x."""
        return self.ref.stable and self.cand.stable and self.lower_bound > 1.0


def _sum_best_over_shapes(fn: Callable, arg_sets) -> float:
    """One sample: best-of-1 per shape, summed across shapes (a single pass)."""
    total = 0.0
    for args in arg_sets:
        total += _time_once(fn, args)
    return total


def measure_stats(
    fn: Callable,
    arg_sets,
    *,
    warmup: int = _DEFAULT_WARMUP,
    batch: int = _DEFAULT_BATCH,
    max_batches: int = _DEFAULT_MAX_BATCHES,
    target_rel_std: float = _DEFAULT_TARGET_REL_STD,
) -> MeasurementStats:
    """Variance-aware timing with repeat-until-stable.

    Warms up `warmup` times (also a smoke test -> if `fn` raises, returns a `raised`
    stats object). Then collects timing samples in batches, stopping early once the
    relative std drops to `target_rel_std` (or after `max_batches`). GC is disabled
    during the timed region to cut jitter, then restored.
    """
    # warmup / smoke test
    for _ in range(max(1, warmup)):
        for args in arg_sets:
            try:
                fn(*args)
            except Exception:
                return MeasurementStats(
                    best=math.inf, median=math.inf, mean=math.inf, std=0.0, raised=True
                )

    samples: list[float] = []
    gc_was_enabled = gc.isenabled()
    gc.disable()
    try:
        for _ in range(max(1, max_batches)):
            for _ in range(max(1, batch)):
                samples.append(_sum_best_over_shapes(fn, arg_sets))
            mean = statistics.fmean(samples)
            std = statistics.pstdev(samples) if len(samples) > 1 else 0.0
            rel = (std / mean) if mean > 0 else 0.0
            if rel <= target_rel_std:
                break
    finally:
        if gc_was_enabled:
            gc.enable()

    best = min(samples)
    median = statistics.median(samples)
    mean = statistics.fmean(samples)
    std = statistics.pstdev(samples) if len(samples) > 1 else 0.0
    return MeasurementStats(best=best, median=median, mean=mean, std=std, samples=samples)


def speedup_stats(
    ref_fn: Callable, cand_fn: Callable, arg_sets, *, sigma: float = 2.0, **kw
) -> SpeedupStats:
    """Speedup with a defensible variance bound.

    point estimate = ref.best / cand.best (matches speedup()'s best-of metric).

    Conservative LOWER bound at ~95% (sigma=2): the slowest credible reference over
    the fastest credible candidate,
        lower = (ref.mean - sigma*ref.std) / (cand.mean + sigma*cand.std).
    Using a 2-sigma envelope on BOTH sides means timing jitter cannot manufacture a
    win: two runs of the SAME function produce a lower bound that straddles 1.0
    (so `trustworthy` is False), which is exactly the PIE "phantom improvement from
    random noise" failure this guards against. A genuine large speedup clears it
    comfortably. A candidate that crashed, or is ~instant (cand.best <= 0 -> a red
    flag per HARD RULE 6), yields inf speedup but an untrustworthy bound.
    """
    ref = measure_stats(ref_fn, arg_sets, **kw)
    cand = measure_stats(cand_fn, arg_sets, **kw)

    if cand.raised or ref.raised:
        return SpeedupStats(speedup=math.inf if cand.raised else 0.0,
                            lower_bound=0.0, ref=ref, cand=cand)
    if cand.best <= 0:
        # near-infinite "speedup" -- HARD RULE 6: a red flag, not a winner.
        return SpeedupStats(speedup=math.inf, lower_bound=0.0, ref=ref, cand=cand)

    point = ref.best / cand.best
    ref_low = max(ref.mean - sigma * ref.std, 0.0)
    cand_high = cand.mean + sigma * cand.std
    lower = (ref_low / cand_high) if cand_high > 0 else 0.0
    return SpeedupStats(speedup=point, lower_bound=lower, ref=ref, cand=cand)


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
