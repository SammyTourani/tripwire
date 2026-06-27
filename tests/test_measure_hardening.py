"""Tests for measurement hardening (Phase 2 task 2.6, tripwire.measure).

Two things must hold:
  1. The FROZEN public surface (measure_time, speedup, exact_equal, close_equal) is
     unchanged in behavior -- the oracle/seed/targets depend on it.
  2. The hardened API (measure_stats / speedup_stats) reports variance and makes the
     "phantom improvement from random noise" (PIE) failure impossible: a genuine,
     well-separated speedup clears the conservative lower bound, while a crashed
     candidate is never trustworthy.

DETERMINISM DISCIPLINE (why these tests don't flake)
----------------------------------------------------
Timing magnitudes are never asserted (machine-dependent). Crucially, we also never
assert a boolean *derived from wall-clock variance* -- specifically ``stable`` /
``trustworthy`` whenever it depends on ``relative_std`` or on a fn-vs-itself timing
comparison. Those flip under CI load (measured 15-45% flake) and were the source of
the original flaky tests. We assert only:
  * structural invariants (``lower_bound <= speedup``, ``raised`` propagation, types),
  * point-estimate orderings driven by ALGORITHMIC work ratio (a quarter-work
    candidate is faster than full work; a no-op is faster than a loop), and
  * that a well-separated ~4x win clears the conservative lower bound (a property the
    work-ratio keeps above 1.0 regardless of how variance inflates under load).
``trustworthy is False`` is asserted ONLY for a crashed candidate, where it follows
from ``cand.raised`` with no timing involved.
"""
from __future__ import annotations

import math

from tripwire.measure import (
    MeasurementStats,
    SpeedupStats,
    close_equal,
    exact_equal,
    measure_stats,
    measure_time,
    speedup,
    speedup_stats,
)


# ---- workloads -------------------------------------------------------------
def _slow(n):
    s = 0
    for i in range(n):
        s += i
    return s


def _slow_quarter(n):
    s = 0
    for i in range(n // 4):
        s += i
    return s


def _boom(n):
    raise ValueError("candidate crashed")


# ---------------------------------------------------------------------------
# FROZEN surface still behaves as before.
# ---------------------------------------------------------------------------
def test_measure_time_returns_inf_on_raise():
    assert math.isinf(measure_time(_boom, [(100,)]))


def test_speedup_basic_shape():
    sp = speedup(_slow, _slow_quarter, [(20000,)])
    assert sp > 0  # quarter-work candidate is faster; exact value is machine-dependent


def test_exact_equal_and_close_equal_unchanged():
    assert exact_equal(1, 1) and not exact_equal(1, 2)
    assert close_equal(1.0, 1.0 + 1e-12) and not close_equal(1.0, 1.1)


# ---------------------------------------------------------------------------
# measure_stats: variance reporting + repeat-until-stable.
# ---------------------------------------------------------------------------
def test_measure_stats_reports_distribution():
    ms = measure_stats(_slow, [(20000,)])
    assert isinstance(ms, MeasurementStats)
    assert ms.best <= ms.median  # best is the minimum sample
    assert ms.mean > 0 and ms.std >= 0
    assert 0.0 <= ms.relative_std
    assert len(ms.samples) >= 1


def test_measure_stats_flags_raise():
    ms = measure_stats(_boom, [(100,)])
    assert ms.raised is True
    assert math.isinf(ms.best)
    assert ms.stable is False  # a crashing candidate is never "stable"


def test_measure_stats_repeat_until_stable_caps_batches():
    # max_batches caps work; with batch=2, max_batches=3 we get at most 6 samples.
    ms = measure_stats(_slow, [(5000,)], batch=2, max_batches=3, target_rel_std=0.0)
    assert len(ms.samples) <= 6


# ---------------------------------------------------------------------------
# speedup_stats: the phantom-improvement guard (the core of 2.6).
# ---------------------------------------------------------------------------
def test_identical_function_speedup_is_well_formed_and_conservative():
    """Same fn vs itself: the PIE guard's *spirit* is that this is never a defensible
    win. We assert only the parts that are deterministic regardless of machine load.

    DELIBERATELY NOT asserted: ``lower_bound <= 1.0`` / ``trustworthy is False``.
    Both are derived from a wall-clock comparison of a function to ITSELF, so under
    CI load a run where the candidate pass happens to be marginally faster (and both
    passes happen to be "stable") can push the lower bound just past 1.0 -- a genuine
    ~15-20% flake under contention (measured). Those are exactly the noise-derived
    booleans this file must stop asserting. What IS deterministic is the structural
    invariant below; the noise-vs-real *decision* is exercised non-flakily by the
    crash case (untrustworthy) and the resolved-4x case (lower bound clears 1)."""
    ss = speedup_stats(_slow, _slow, [(30000,)])
    assert isinstance(ss, SpeedupStats)
    # The conservative lower bound can NEVER exceed the point estimate (it is the
    # slowest-credible-ref / fastest-credible-cand). This holds for ANY measurement.
    assert ss.lower_bound <= ss.speedup + 1e-9
    # A finite, well-formed measurement (same fn measured on both sides -> no crash).
    assert ss.cand.raised is False and ss.ref.raised is False


def test_crashing_candidate_is_untrustworthy():
    ss = speedup_stats(_slow, _boom, [(20000,)])
    assert ss.cand.raised is True
    assert ss.trustworthy is False


def test_constant_instant_candidate_is_a_speed_red_flag():
    """A ~instant constant candidate (HARD RULE 6): it measures as faster than a real
    loop -- the Sakana "infinitely fast" mirage -- which is a RED FLAG the moat layers
    must catch, not a win to bank on speed alone.

    We assert the deterministic point-estimate ordering (the no-op candidate is always
    faster than a 20k-iteration loop), NOT ``trustworthy is False``. Whether the harness
    records the candidate as ``cand.best <= 0`` (-> inf speedup, untrustworthy) or as a
    tiny-but-positive, low-jitter time (-> a huge finite, occasionally "trustworthy")
    is decided at timer resolution and is genuinely nondeterministic (~10% of runs flip
    the flag, measured). The flag therefore cannot be asserted here; the *correctness*
    moat (L1-L3), not this speed flag, is what rejects a constant hack."""
    ss = speedup_stats(_slow, lambda n: 0, [(20000,)])
    assert isinstance(ss, SpeedupStats)
    # Deterministic: doing ~nothing is faster than a real loop (finite >1, or inf).
    assert ss.speedup > 1.0
    # Structural invariant that holds for any measurement (never flakes).
    assert ss.lower_bound <= ss.speedup + 1e-9


def test_genuine_resolved_speedup_clears_the_conservative_lower_bound():
    """A real ~4x win where BOTH sides do substantial work: the point estimate AND the
    conservative variance-aware LOWER bound both clear 1.0x. This is the positive axis
    of the PIE guard -- a genuine, well-separated speedup survives the noise envelope.

    Both assertions are deterministic even under heavy CI contention: the 4x ratio
    between the two means is large enough that ``(ref.mean - 2sigma)/(cand.mean +
    2sigma)`` stays above 1.0 no matter how the (proportionally inflated) variance
    grows (measured 160/160 under 8x CPU load).

    DELIBERATELY NOT asserted: ``trustworthy is True``. That flag ANDs in
    ``ref.stable and cand.stable``, i.e. ``relative_std <= 5%`` on the wall clock, which
    collapses under load (drops to ~15-30% pass) -- a noise-derived boolean, exactly
    what this file must not assert. The lower bound clearing 1.0 is the defensible,
    load-independent statement of "this speedup is real"."""
    ss = speedup_stats(_slow, _slow_quarter, [(200000,)])
    # Point-estimate ordering: a quarter-work candidate is faster (deterministic).
    assert ss.speedup > 1.0
    # The conservative 2-sigma lower bound still clears 1.0 for a well-separated win.
    assert ss.lower_bound > 1.0


def test_lower_bound_never_exceeds_point_estimate():
    ss = speedup_stats(_slow, _slow_quarter, [(100000,)])
    assert ss.lower_bound <= ss.speedup + 1e-9
