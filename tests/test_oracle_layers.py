"""Unit tests for tripwire.oracle -- each layer rejects for the RIGHT reason.

The scorecard test (test_scorecard.py) guards the end-to-end behavior. These tests
guard the *internal layer ordering* (HARD RULE 3 / ADR-002): a refactor that, say,
skipped L3 could still pass an aggregate count by luck -- these catch that by
asserting which layer fires and that earlier layers short-circuit later ones.

Targets are constructed inline (duck-typed on the frozen-in-1.3 Target shape) with
tiny inputs so the suite runs fast.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from tripwire.oracle import Verdict, layered_oracle, naive_oracle


@dataclass
class _T:
    """Minimal stand-in matching the fields the oracle reads (Interface A is frozen
    in task 1.3; this avoids importing it before then)."""

    name: str
    kind: str
    reference: Callable
    canonical_args: list
    withheld_args: list
    properties: list = field(default_factory=list)


# --- a trivial structural target: identity over short strings ---------------
def _ident(s):
    return s.split()


def _struct_target(**over):
    base = dict(
        name="ident",
        kind="structural",
        reference=_ident,
        canonical_args=[("a b c",), ("x",)],
        withheld_args=[("d e",), ("",)],
        properties=[],
    )
    base.update(over)
    return _T(**base)


# ---------------------------------------------------------------------------
# Verdict invariant (ADR-006): rejected => speedup is NaN, never a number.
# ---------------------------------------------------------------------------
def test_rejected_verdict_has_nan_speedup():
    import math

    t = _struct_target()
    v = layered_oracle(t, lambda s: ["wrong"])
    assert not v.accepted
    assert math.isnan(v.speedup), "a rejected candidate must NOT carry a speedup (ADR-006)"


# ---------------------------------------------------------------------------
# L1 -- canonical correctness
# ---------------------------------------------------------------------------
def test_L1_rejects_wrong_on_canonical():
    t = _struct_target()
    v = layered_oracle(t, lambda s: ["always", "wrong"])
    assert not v.accepted
    assert v.reason.startswith("L1"), v.reason


def test_L1_catches_exception_as_rejection():
    t = _struct_target()

    def boom(s):
        raise RuntimeError("boom")

    v = layered_oracle(t, boom)
    assert not v.accepted
    assert v.reason.startswith("L1 raised"), v.reason


# ---------------------------------------------------------------------------
# L2 -- metamorphic / property checks (fires AFTER L1 passes)
# ---------------------------------------------------------------------------
def test_L2_rejects_property_violation():
    # candidate equals reference on the literal canonical+withheld inputs (passes L1+L3),
    # but violates a property on some of those inputs.
    seen = {("a b c",): ["a", "b", "c"], ("x",): ["x"], ("d e",): ["d", "e"], ("",): []}

    def cand(s):
        return seen[(s,)]

    # property that the candidate's output is always length >= 99 (false here) -> L2 must fire
    t = _struct_target(properties=[("len_ge_99", lambda args, out: len(out) >= 99)])
    v = layered_oracle(t, cand)
    assert not v.accepted
    assert v.reason.startswith("L2 property 'len_ge_99'"), v.reason


def test_L2_runs_over_canonical_and_withheld():
    # property holds on canonical but FAILS on a withheld input -> proves L2 checks withheld too.
    def cand(s):
        return _ident(s)

    def prop(args, out):
        # passes for non-empty, fails for the withheld empty-string input ("",)
        return len(out) > 0

    t = _struct_target(properties=[("nonempty", prop)])
    v = layered_oracle(t, cand)
    assert not v.accepted
    assert "nonempty" in v.reason


# ---------------------------------------------------------------------------
# L3 -- differential on WITHHELD inputs (the moat). The memorization hack.
# ---------------------------------------------------------------------------
def test_L3_catches_memorization_hack():
    # classic hack: correct on canonical (memorized), wrong on withheld.
    memo = {("a b c",): ["a", "b", "c"], ("x",): ["x"]}

    def hack(s):
        return memo.get((s,), [])  # wrong (empty) on withheld 'd e'

    t = _struct_target()
    v = layered_oracle(t, hack)
    assert not v.accepted
    assert v.reason.startswith("L3"), v.reason


def test_L3_naive_oracle_would_SHIP_the_same_hack():
    """Contrast: the naive oracle (canonical-only) accepts the very hack L3 rejects.
    This is the core thesis in miniature."""
    memo = {("a b c",): ["a", "b", "c"], ("x",): ["x"]}

    def hack(s):
        return memo.get((s,), [])

    t = _struct_target()
    assert naive_oracle(t, hack, "bitwise").accepted  # naive ships it...
    assert not layered_oracle(t, hack).accepted  # ...layered catches it (the moat)


# ---------------------------------------------------------------------------
# Layer ORDER: an earlier failing layer must short-circuit later ones.
# ---------------------------------------------------------------------------
def test_layer_order_L1_before_L3():
    # wrong on BOTH canonical and withheld -> must report L1 (the earliest), not L3.
    t = _struct_target()
    v = layered_oracle(t, lambda s: ["nope"])
    assert v.reason.startswith("L1"), f"expected earliest layer to fire, got: {v.reason}"


# ---------------------------------------------------------------------------
# Numeric vs structural comparison selection (ADR-004).
# ---------------------------------------------------------------------------
def test_numeric_target_uses_tolerance_not_bitwise():
    # a correct-but-low-bits-different numeric candidate must PASS (tolerance),
    # whereas a bitwise comparison would reject it.
    def ref(arr):
        s = 0.0
        for x in arr:
            s += float(x)
        return s

    def reordered(arr):  # different summation order -> differs in low bits, still correct
        return float(np.sum(arr))

    rng = np.random.default_rng(0)
    t = _T(
        name="sum",
        kind="numeric",
        reference=ref,
        canonical_args=[(rng.standard_normal(5000),)],
        withheld_args=[(rng.standard_normal(5000),)],
        properties=[],
    )
    v = layered_oracle(t, reordered)
    assert v.accepted, f"numeric tolerance should accept a correct reordered sum: {v.reason}"


def test_structural_target_uses_exact_equality():
    # structural: an off-by-one structural difference must be rejected by L1 exact compare.
    t = _struct_target()

    def almost(s):
        out = _ident(s)
        return out + ["EXTRA"] if out else out  # structurally wrong on non-empty inputs

    v = layered_oracle(t, almost)
    assert not v.accepted
    assert v.reason.startswith("L1"), v.reason


def test_verdict_is_dataclass_with_expected_fields():
    v = Verdict(True, "ok", 2.0)
    assert v.accepted is True and v.reason == "ok" and v.speedup == 2.0
    # default speedup is NaN
    import math

    assert math.isnan(Verdict(False, "x").speedup)
