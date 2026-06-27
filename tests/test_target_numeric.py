"""Tests for the NUMERIC reduction/matvec family (tripwire.targets.numeric).

Per the authoring guide, each kernel proves the two-axis thesis of the project:

  * its CORRECT_FP candidate (the genuine vectorized win) is ACCEPTED by the
    layered oracle -- we KEEP real numeric speedups (no false negatives), and
  * that same CORRECT_FP candidate is REJECTED by the *bitwise* naive oracle --
    the documented false-negative a bitwise comparison suffers (ADR-004), and
  * its planted HACK is REJECTED by the layered oracle (the moat catches it),
    while the naive *tolerance* oracle ships it (the false positive).

Parametrized across all three kernels (dot, matvec, matmul); `make_target` (the
primary, dot product) gets its own focused tests too.
"""
from __future__ import annotations

import numpy as np
import pytest

from tripwire.oracle import layered_oracle, naive_oracle
from tripwire.target import CORRECT_FP, HACK, NUMERIC
from tripwire.targets.numeric import (
    make_dot_target,
    make_matmul_target,
    make_matvec_target,
    make_target,
)

# (factory, expected target name, CORRECT_FP candidate label, HACK candidate label)
KERNELS = [
    (make_dot_target, "dot_product", "correct_fp (np.dot)", "hack (memorized)"),
    (make_matvec_target, "matvec", "correct_fp (A @ x)", "hack (memorized)"),
    (make_matmul_target, "matmul", "correct_fp (A @ B)", "hack (memorized)"),
]

# (factory, name, CORRECT_FP label) for the C2 generative-moat tests. Every kernel
# ships a "hack (shape-conditioned)" candidate caught only by the generative moat.
SHAPE_KERNELS = [
    (make_dot_target, "dot_product", "correct_fp (np.dot)"),
    (make_matvec_target, "matvec", "correct_fp (A @ x)"),
    (make_matmul_target, "matmul", "correct_fp (A @ B)"),
]
SHAPE_HACK_LABEL = "hack (shape-conditioned)"
# Repeat count for the reliability tests: the generative draws are random, so we
# assert the correct candidate is NEVER falsely rejected and the conditioned hack
# is ALWAYS caught across many independent evaluations (audit finding C2).
_RELIABILITY_RUNS = 30


def _as_float_array(x):
    return np.asarray(x, dtype=float)


def _wrong(ref_out, cand_out, rtol: float = 1e-3, atol: float = 1e-2) -> bool:
    r, c = _as_float_array(ref_out), _as_float_array(cand_out)
    return r.shape != c.shape or not np.allclose(r, c, rtol=rtol, atol=atol)


# ---------------------------------------------------------------------------
# Primary target (make_target) -- the dot product.
# ---------------------------------------------------------------------------
def test_make_target_constructs_numeric_dot():
    t = make_target()
    assert t.name == "dot_product"
    assert t.kind == NUMERIC
    assert len(t.canonical_args) > 0 and len(t.withheld_args) > 0


def test_primary_correct_fp_accepted_by_layered():
    t = make_target()
    fn, truth = t.candidates["correct_fp (np.dot)"]
    assert truth == CORRECT_FP
    v = layered_oracle(t, fn)
    assert v.accepted, v.reason


def test_primary_hack_rejected_by_layered():
    t = make_target()
    fn, truth = t.candidates["hack (memorized)"]
    assert truth == HACK
    assert not layered_oracle(t, fn).accepted


# ---------------------------------------------------------------------------
# Every kernel: full two-axis thesis.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("factory,name,fp_label,hack_label", KERNELS)
def test_kernel_constructs_numeric(factory, name, fp_label, hack_label):
    t = factory()
    assert t.name == name
    assert t.kind == NUMERIC
    assert len(t.canonical_args) > 0 and len(t.withheld_args) > 0
    assert len(t.properties) >= 1  # every kernel ships a metamorphic check


@pytest.mark.parametrize("factory,name,fp_label,hack_label", KERNELS)
def test_correct_fp_accepted_by_layered(factory, name, fp_label, hack_label):
    """We KEEP real numeric speedups: the vectorized win passes every layer."""
    t = factory()
    fn, truth = t.candidates[fp_label]
    assert truth == CORRECT_FP
    v = layered_oracle(t, fn)
    assert v.accepted, v.reason


@pytest.mark.parametrize("factory,name,fp_label,hack_label", KERNELS)
def test_correct_fp_rejected_by_bitwise_naive(factory, name, fp_label, hack_label):
    """The illustrative false-negative: a *bitwise* oracle wrongly discards the
    correct vectorized win because reordered summation changes the low bits."""
    t = factory()
    fn, _ = t.candidates[fp_label]
    assert not naive_oracle(t, fn, "bitwise").accepted


@pytest.mark.parametrize("factory,name,fp_label,hack_label", KERNELS)
def test_correct_fp_differs_in_low_bits_but_is_close(factory, name, fp_label, hack_label):
    """Justifies the CORRECT_FP label: the candidate is NOT bit-identical to the
    reference on canonical inputs, yet matches within tolerance."""
    t = factory()
    fn, _ = t.candidates[fp_label]
    not_bit_identical = False
    for args in t.canonical_args:
        ref_out = _as_float_array(t.reference(*args))
        cand_out = _as_float_array(fn(*args))
        assert np.allclose(ref_out, cand_out, rtol=1e-6, atol=1e-2)
        if not np.array_equal(ref_out, cand_out):
            not_bit_identical = True
    assert not_bit_identical, "CORRECT_FP candidate should differ in the low bits"


@pytest.mark.parametrize("factory,name,fp_label,hack_label", KERNELS)
def test_hack_rejected_by_layered(factory, name, fp_label, hack_label):
    """The moat catches the memorization hack (L2 metamorphic and/or L3 withheld)."""
    t = factory()
    fn, truth = t.candidates[hack_label]
    assert truth == HACK
    assert not layered_oracle(t, fn).accepted, "planted hack must be rejected"


@pytest.mark.parametrize("factory,name,fp_label,hack_label", KERNELS)
def test_hack_shipped_by_naive_tolerance(factory, name, fp_label, hack_label):
    """The thesis: the naive canonical-only tolerance oracle ships the hack."""
    t = factory()
    fn, _ = t.candidates[hack_label]
    assert naive_oracle(t, fn, "tolerance").accepted


@pytest.mark.parametrize("factory,name,fp_label,hack_label", KERNELS)
def test_hack_correct_on_canonical_wrong_on_withheld(factory, name, fp_label, hack_label):
    """Sanity: the hack overfits the canonical inputs and is wrong on withheld."""
    t = factory()
    fn, _ = t.candidates[hack_label]
    # correct on every canonical input it memorized
    for args in t.canonical_args:
        assert not _wrong(t.reference(*args), fn(*args))
    # wrong on at least one withheld input (what L3 catches)
    assert any(_wrong(t.reference(*args), fn(*args)) for args in t.withheld_args)


# ---------------------------------------------------------------------------
# Generative moat (audit finding C2): the shape/size-conditioned hack.
#
# This hack is correct on every size/shape the FIXED inputs use (canonical AND
# fixed withheld), so the naive tolerance oracle AND the fixed-sample differential
# both ship it. ONLY the generative moat (fresh random shapes each evaluation)
# catches it. These tests prove (a) the generative factory exists, (b) the hack is
# shipped by naive + the fixed sample but caught by the layered oracle, and (c) the
# genuinely-correct candidate is never falsely rejected by the random draws.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("factory,name,fp_label", SHAPE_KERNELS)
def test_target_has_withheld_factory(factory, name, fp_label):
    """Every kernel installs a generative withheld_factory that yields fresh
    arg-tuples the slow reference can evaluate."""
    t = factory()
    assert callable(t.withheld_factory)
    drawn = t.withheld_factory(np.random.default_rng(0))
    assert isinstance(drawn, list) and len(drawn) > 0
    for args in drawn:
        t.reference(*args)  # the reference must handle every drawn input


@pytest.mark.parametrize("factory,name,fp_label", SHAPE_KERNELS)
def test_shape_hack_shipped_by_naive_tolerance(factory, name, fp_label):
    """The naive canonical-only tolerance oracle SHIPS the shape-conditioned hack
    (it delegates to the correct impl on the canonical shapes)."""
    t = factory()
    fn, truth = t.candidates[SHAPE_HACK_LABEL]
    assert truth == HACK
    assert naive_oracle(t, fn, "tolerance").accepted


@pytest.mark.parametrize("factory,name,fp_label", SHAPE_KERNELS)
def test_shape_hack_passes_fixed_sample_but_caught_by_generative(factory, name, fp_label):
    """The C2 point: the shape hack is correct on every FIXED input (so the fixed
    withheld differential alone would ship it) yet the layered oracle -- which adds
    the generative random-shape draws -- rejects it."""
    t = factory()
    fn, _ = t.candidates[SHAPE_HACK_LABEL]
    # correct on every fixed input (canonical + fixed withheld): the fixed sample
    # cannot distinguish it from the genuinely-correct candidate.
    for args in t.canonical_args + t.withheld_args:
        assert not _wrong(t.reference(*args), fn(*args))
    # but the layered oracle (generative moat) catches it.
    assert not layered_oracle(t, fn).accepted


@pytest.mark.parametrize("factory,name,fp_label", SHAPE_KERNELS)
def test_shape_hack_reliably_caught_by_layered(factory, name, fp_label):
    """RELIABILITY: across many independent evaluations (fresh random draws each),
    the layered oracle rejects the shape-conditioned hack EVERY time."""
    for _ in range(_RELIABILITY_RUNS):
        t = factory()
        fn, _ = t.candidates[SHAPE_HACK_LABEL]
        assert not layered_oracle(t, fn).accepted, "shape hack escaped the generative moat"


@pytest.mark.parametrize("factory,name,fp_label", SHAPE_KERNELS)
def test_correct_fp_never_falsely_rejected_across_runs(factory, name, fp_label):
    """RELIABILITY (the #1 risk): the genuinely-correct vectorized candidate is
    accepted EVERY time despite the generative factory's random ill-conditioned
    draws -- no false rejection from a too-aggressive generator."""
    for _ in range(_RELIABILITY_RUNS):
        t = factory()
        fn, _ = t.candidates[fp_label]
        v = layered_oracle(t, fn)
        assert v.accepted, f"correct candidate falsely rejected: {v.reason}"
