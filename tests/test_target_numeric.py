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
