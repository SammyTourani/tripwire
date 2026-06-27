"""Test for the tokenizer target (tripwire.targets.tokenizer).

Per the authoring guide: every target ships a test proving (a) its CORRECT
candidate is accepted by the layered oracle, and (b) its planted HACK is rejected
(while a naive oracle would ship it -- the thesis). This is the structural
(exact-comparison) mirror of test_target_sum_reduction.py.
"""
from __future__ import annotations

from tripwire.oracle import layered_oracle, naive_oracle
from tripwire.target import CORRECT, HACK, STRUCTURAL
from tripwire.targets.tokenizer import make_target


def test_target_is_valid_structural():
    """make_target() constructs (self-validates) and is a structural target."""
    t = make_target()
    assert t.name == "tokenizer"
    assert t.kind == STRUCTURAL
    assert len(t.canonical_args) > 0 and len(t.withheld_args) > 0
    # the moat must include the required adversarial edges
    withheld_texts = [args[0] for args in t.withheld_args]
    assert "" in withheld_texts  # empty string
    assert any(not text.isascii() for text in withheld_texts)  # unicode
    assert any(len(text.split()) >= 5000 for text in withheld_texts)  # very large


def test_correct_candidate_accepted():
    t = make_target()
    fn, truth = t.candidates["correct (re.findall)"]
    assert truth == CORRECT
    v = layered_oracle(t, fn)
    assert v.accepted, v.reason


def test_planted_hack_is_rejected_by_layered_oracle():
    t = make_target()
    fn, truth = t.candidates["hack (memorized)"]
    assert truth == HACK
    v = layered_oracle(t, fn)
    assert v.accepted is False, "planted hack must be caught by the layered oracle"


def test_planted_hack_would_be_shipped_by_naive_oracle():
    """The thesis in miniature: the naive canonical-only oracle ships the hack."""
    t = make_target()
    fn, _ = t.candidates["hack (memorized)"]
    assert naive_oracle(t, fn, "bitwise").accepted


def test_hack_is_correct_on_canonical_but_wrong_on_withheld():
    """Sanity-check the hack behaves as designed (overfit to canonical inputs)."""
    t = make_target()
    fn, _ = t.candidates["hack (memorized)"]
    # correct on every canonical input
    for args in t.canonical_args:
        assert fn(*args) == t.reference(*args)
    # wrong on at least one withheld input (that's what L3 catches)
    wrong = any(fn(*args) != t.reference(*args) for args in t.withheld_args)
    assert wrong, "hack should be wrong on withheld inputs (that's what L3 catches)"


def test_correct_candidate_matches_reference_everywhere():
    """The CORRECT candidate must be output-identical to the reference, including
    on the adversarial withheld edges (empty / unicode / large / repeats)."""
    t = make_target()
    fn, _ = t.candidates["correct (re.findall)"]
    for args in t.canonical_args + t.withheld_args:
        assert fn(*args) == t.reference(*args)
