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
#
# Both comparators are adversarial-by-design oracle primitives (CLAUDE.md §5,
# HARD RULE 2): assume the value on either side is a candidate trying to slip past
# the comparison. Two cross-cutting guarantees they share:
#
#   * TOTAL -- neither ever raises. The oracle wraps them in try/except, but a
#     comparator that can raise is a latent bug, so every path returns a bool and
#     any unexpected type falls back to a safe ``type(a) is type(b) and a == b``.
#   * NaN is EQUAL to NaN (position-wise for arrays). A correct reference that
#     legitimately produces NaN (an all-NULL aggregate, a reduction over data with
#     NaN) must not be rejected just because ``nan != nan`` in IEEE-754 -- that is
#     exactly the false-negative axis this project exists to kill (ADR-004). A NaN
#     is still UNEQUAL to any finite number. +Inf == +Inf and -Inf == -Inf, but
#     +Inf != -Inf, in both comparators.
#
# They differ on the leaf rule: `exact_equal` is TYPE-STRICT (structural targets,
# where exact is sound and free -- ADR-004), `close_equal` applies a tolerance to
# numeric leaves (numeric targets, where reordered FP arithmetic changes low bits).
# ---------------------------------------------------------------------------

# Container types we recurse through so the leaf rule applies element-wise.
_SEQ_TYPES = (list, tuple)


def _is_real_number(x) -> bool:
    """True for a non-bool Python/numpy real scalar. bool is excluded on purpose:
    for type-strict structural compares ``True`` is NOT ``1`` (Defect 1), and for
    numeric compares a bool leaf is treated structurally, not as 0.0/1.0."""
    if isinstance(x, bool) or isinstance(x, np.bool_):
        return False
    return isinstance(x, (int, float, np.integer, np.floating))


def _both_nan(a, b) -> bool:
    """True iff both `a` and `b` are NaN scalars. Used to make NaN==NaN hold at the
    leaf level. Guarded so non-float inputs (e.g. strings) never reach math.isnan."""
    try:
        return (
            _is_real_number(a)
            and _is_real_number(b)
            and math.isnan(float(a))
            and math.isnan(float(b))
        )
    except (TypeError, ValueError):
        return False


def _scalar_close(a, b, rtol: float, atol: float) -> bool:
    """Tolerance compare for two real scalars, with NaN==NaN and signed-Inf rules
    handled exactly the way ``np.allclose(equal_nan=True)`` does -- reused so the
    scalar path and the array path agree."""
    fa, fb = float(a), float(b)
    if math.isnan(fa) or math.isnan(fb):
        return math.isnan(fa) and math.isnan(fb)  # NaN==NaN, NaN!=number
    if math.isinf(fa) or math.isinf(fb):
        return fa == fb  # +inf==+inf, -inf==-inf, but +inf!=-inf and inf!=finite
    return abs(fa - fb) <= (atol + rtol * abs(fb))


def _arrays_exact_equal(a: np.ndarray, b: np.ndarray) -> bool:
    """Type-strict array equality for `exact_equal`.

    Requires matching dtype KIND (an int array is not equal to an equal-valued
    float array -- 'exact' means type-exact), then compares values with
    ``np.array_equal`` while treating NaN positions as equal. ``np.array_equal``
    does not broadcast, so an array is never silently 'equal' to a scalar."""
    if a.dtype.kind != b.dtype.kind:
        return False
    if a.shape != b.shape:
        return False
    # equal_nan only works for inexact (float/complex) kinds; for everything else
    # (ints, bytes, str, bool, object) a plain array_equal is already exact.
    if a.dtype.kind in ("f", "c"):
        return bool(np.array_equal(a, b, equal_nan=True))
    return bool(np.array_equal(a, b))


def _arrays_close(a: np.ndarray, b: np.ndarray, rtol: float, atol: float) -> bool:
    """Tolerance array equality for `close_equal`. Requires MATCHING SHAPES (no
    broadcast -- a scalar/short vector must not be 'close' to a longer one, Defect 3)
    and treats NaN positions as equal (``equal_nan=True``, Defect 2)."""
    if a.shape != b.shape:
        return False
    return bool(np.allclose(a, b, rtol=rtol, atol=atol, equal_nan=True))


def _safe_eq(a, b) -> bool:
    """The TOTAL fallback used by both comparators on any unexpected type: equal
    only if the types match exactly AND ``==`` says so, swallowing any exception a
    weird ``__eq__`` might raise (and coercing a truthy/array-like result to bool)."""
    if type(a) is not type(b):
        return False
    try:
        return bool(a == b)
    except Exception:
        return a is b


def exact_equal(a, b) -> bool:
    """Type-strict, NaN-aware, TOTAL exact comparison. SOUND ONLY for `structural`
    targets (ADR-004), where 'exact' must mean *type-exact*.

    Type-strictness (Defect 1): values of different types are NEVER equal. In
    particular ``1`` (int) != ``1.0`` (float) != ``True`` (bool), ``"1"`` != ``1``,
    a tuple is not a list with the same contents, and a dict whose values differ in
    type (``{"a": 1}`` vs ``{"a": 1.0}``) is not equal. This stops a candidate that
    returns ``{"count": True}`` from masquerading as the reference's ``{"count": 1}``.

    NaN (Defect 2): ``nan`` equals ``nan`` (scalar and position-wise in arrays), but
    a NaN is never equal to a finite number.

    Recursion: list/tuple/dict are compared element-wise so type-strictness applies
    to every leaf; differing length or key-set => not equal.

    Numpy arrays are compared with matching dtype-kind + shape (an int array is not
    equal to an equal-valued float array), so no silent scalar/array broadcast.

    TOTAL: never raises; any unexpected type falls back to ``type(a) is type(b) and
    a == b``.
    """
    # --- numpy arrays: type-strict (matching dtype-kind), no broadcast ---
    if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
        if not (isinstance(a, np.ndarray) and isinstance(b, np.ndarray)):
            return False  # an array is never 'exactly' a bare scalar/list
        return _arrays_exact_equal(a, b)

    # --- type-strictness gate for everything else: different types => not equal.
    # (bool vs int and int vs float are distinct because ``type`` distinguishes
    # them, even though bool subclasses int.)
    if type(a) is not type(b):
        return False

    # --- dict: same keys, recurse on values (types now known equal) ---
    if isinstance(a, dict):
        if a.keys() != b.keys():
            return False
        return all(exact_equal(a[k], b[k]) for k in a)

    # --- list / tuple: same length, recurse element-wise ---
    if isinstance(a, _SEQ_TYPES):
        if len(a) != len(b):
            return False
        return all(exact_equal(x, y) for x, y in zip(a, b, strict=False))

    # --- real scalars of the SAME type: handle NaN==NaN, else exact ``==`` ---
    if _is_real_number(a):  # b has the same type here
        if _both_nan(a, b):
            return True
        try:
            return bool(a == b)
        except Exception:
            return a is b

    # --- any other same-typed leaf (str, bytes, bool, None, custom): safe ``==`` ---
    return _safe_eq(a, b)


def close_equal(a, b, rtol: float = 1e-6, atol: float = 1e-9) -> bool:
    """Tolerance, NaN-aware, structure-aware, TOTAL comparison for `numeric` targets
    (ADR-004): correct speedups (vectorization, reordered reduction, FMA) change low
    bits, so numeric correctness is tolerance, never bitwise.

    Numeric leaves are compared with ``rtol``/``atol`` (defaults unchanged). NaN
    equals NaN and +Inf/-Inf follow the usual signed rules (Defect 2).

    Structured outputs (Defect 3): dict/list/tuple are recursed so the tolerance
    applies to numeric leaves while non-numeric leaves (strings, bools, keys) use
    type-strict exact comparison. So ``{"x": 1.0}`` is close to ``{"x": 1.0+1e-9}``
    -- the bitwise false-negative for non-array numeric output is gone.

    Arrays require MATCHING SHAPES -- no numpy broadcast (Defect 3): a constant
    scalar is NOT 'close' to a vector reference (``close_equal(np.zeros(200), 0.0)``
    is False), so a skip-the-work candidate can't match a vector by broadcasting.

    TOTAL: never raises; any unexpected type falls back to ``type(a) is type(b) and
    a == b``.
    """
    return _close_equal(a, b, rtol, atol)


def _close_equal(a, b, rtol: float, atol: float) -> bool:
    """Recursive worker for `close_equal` (keeps the public signature clean)."""
    # --- numpy arrays: tolerance, matching shapes, equal_nan (no broadcast) ---
    if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
        try:
            arr_a = a if isinstance(a, np.ndarray) else np.asarray(a, dtype=float)
            arr_b = b if isinstance(b, np.ndarray) else np.asarray(b, dtype=float)
            # numeric arrays compare by tolerance; non-numeric (str/object) exactly.
            if arr_a.dtype.kind in ("f", "c", "i", "u") and arr_b.dtype.kind in (
                "f",
                "c",
                "i",
                "u",
            ):
                return _arrays_close(arr_a, arr_b, rtol, atol)
            return _arrays_exact_equal(arr_a, arr_b)
        except Exception:
            return _safe_eq(a, b)

    # --- dict: same keys, recurse on values ---
    if isinstance(a, dict) and isinstance(b, dict):
        if a.keys() != b.keys():
            return False
        return all(_close_equal(a[k], b[k], rtol, atol) for k in a)
    if isinstance(a, dict) != isinstance(b, dict):
        return False  # one dict, one not

    # --- list / tuple: same concrete type + length, recurse element-wise ---
    if isinstance(a, _SEQ_TYPES) or isinstance(b, _SEQ_TYPES):
        if type(a) is not type(b) or len(a) != len(b):
            return False
        return all(_close_equal(x, y, rtol, atol) for x, y in zip(a, b, strict=False))

    # --- two real scalars: tolerance with NaN/Inf semantics ---
    if _is_real_number(a) and _is_real_number(b):
        try:
            return _scalar_close(a, b, rtol, atol)
        except Exception:
            return _safe_eq(a, b)

    # --- a real number vs a non-number (e.g. None, str): not close ---
    if _is_real_number(a) != _is_real_number(b):
        return False

    # --- any other leaf (str, bytes, bool, None, custom): type-strict safe ``==`` ---
    return _safe_eq(a, b)
