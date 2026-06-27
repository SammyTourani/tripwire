"""Tests for measurement hardening (Phase 2 task 2.6, tripwire.measure).

Two things must hold:
  1. The FROZEN public surface (measure_time, speedup, exact_equal, close_equal) is
     unchanged in behavior -- the oracle/seed/targets depend on it.
  2. The hardened API (measure_stats / speedup_stats) reports variance and makes the
     "phantom improvement from random noise" (PIE) failure impossible: two runs of
     the SAME function must NOT be reported as a trustworthy speedup.

Timing magnitudes are never asserted (machine-dependent); we assert structure,
stability flags, and the noise-vs-real decision -- all of which are deterministic
in expectation.
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
def test_identical_function_is_not_a_trustworthy_speedup():
    """THE key property: same fn vs itself must never be a trustworthy 'win'."""
    ss = speedup_stats(_slow, _slow, [(30000,)])
    assert isinstance(ss, SpeedupStats)
    # point estimate hovers around 1x; the conservative lower bound must NOT clear 1.
    assert ss.lower_bound <= 1.0, f"phantom win: lower_bound={ss.lower_bound}"
    assert ss.trustworthy is False


def test_crashing_candidate_is_untrustworthy():
    ss = speedup_stats(_slow, _boom, [(20000,)])
    assert ss.cand.raised is True
    assert ss.trustworthy is False


def test_constant_instant_candidate_is_untrustworthy_red_flag():
    """A ~instant candidate (HARD RULE 6 red flag): inf speedup, NOT trustworthy."""
    ss = speedup_stats(_slow, lambda n: 0, [(20000,)])
    # lambda is near-instant -> either inf speedup or an unstable candidate; never trustworthy.
    assert ss.trustworthy is False


def test_genuine_resolved_speedup_is_trustworthy():
    """A real ~4x win where BOTH sides are well above timing resolution should be
    reported as trustworthy (lower bound clears 1.0)."""
    ss = speedup_stats(_slow, _slow_quarter, [(200000,)])
    assert ss.speedup > 1.0
    # We don't pin the exact multiplier, but a 4x-less-work candidate with both
    # sides well-resolved must clear the conservative bound.
    assert ss.lower_bound > 1.0
    assert ss.trustworthy is True


def test_lower_bound_never_exceeds_point_estimate():
    ss = speedup_stats(_slow, _slow_quarter, [(100000,)])
    assert ss.lower_bound <= ss.speedup + 1e-9
