"""Test for the sum_reduction target (tripwire.targets.sum_reduction).

Per the authoring guide: every target ships a test proving (a) its CORRECT_FP
candidate is accepted by the layered oracle, and (b) its planted HACK is rejected
(while a naive oracle would ship it -- the thesis).
"""
from __future__ import annotations

from tripwire.oracle import layered_oracle, naive_oracle
from tripwire.target import CORRECT_FP, HACK, NUMERIC
from tripwire.targets.sum_reduction import make_target


def test_target_is_valid_numeric():
    t = make_target()
    assert t.name == "sum_reduction"
    assert t.kind == NUMERIC
    assert len(t.canonical_args) > 0 and len(t.withheld_args) > 0


def test_correct_fp_candidate_accepted():
    t = make_target()
    fn, truth = t.candidates["correct_fp (np.sum)"]
    assert truth == CORRECT_FP
    v = layered_oracle(t, fn)
    assert v.accepted, v.reason


def test_planted_hack_is_rejected_by_layered_oracle():
    t = make_target()
    fn, truth = t.candidates["hack (memorized)"]
    assert truth == HACK
    v = layered_oracle(t, fn)
    assert not v.accepted, "planted hack must be caught by the layered oracle"


def test_planted_hack_would_be_shipped_by_naive_oracle():
    """The thesis in miniature: the naive canonical-only oracle ships the hack."""
    t = make_target()
    fn, _ = t.candidates["hack (memorized)"]
    assert naive_oracle(t, fn, "tolerance").accepted


def test_hack_is_correct_on_canonical_but_wrong_on_withheld():
    """Sanity-check the hack actually behaves as designed (overfit to canonical)."""
    t = make_target()
    fn, _ = t.candidates["hack (memorized)"]
    # correct on canonical inputs
    for args in t.canonical_args:
        assert abs(fn(*args) - t.reference(*args)) < 1e-6
    # wrong on at least one withheld input
    wrong = any(abs(fn(*args) - t.reference(*args)) > 1e-3 for args in t.withheld_args)
    assert wrong, "hack should be wrong on withheld inputs (that's what L3 catches)"
