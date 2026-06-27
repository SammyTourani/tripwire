"""Test for the serde target (tripwire.targets.serde).

Per the authoring guide: every target ships a test proving (a) its CORRECT
candidate is accepted by the layered oracle, and (b) its planted HACK is rejected
by the layered oracle while a naive oracle would ship it -- the thesis in
miniature (CLAUDE.md §2). Plus a direct check of the headline metamorphic
relation (round-trip identity) on fresh documents.
"""
from __future__ import annotations

from tripwire.oracle import layered_oracle, naive_oracle
from tripwire.target import CORRECT, HACK, STRUCTURAL
from tripwire.targets.serde import correct, make_target, parse, serialize


def test_target_constructs_and_is_structural():
    t = make_target()
    assert t.name == "serde"
    assert t.kind == STRUCTURAL
    assert len(t.canonical_args) > 0 and len(t.withheld_args) > 0


def test_correct_candidate_accepted_by_layered_oracle():
    t = make_target()
    fn, truth = t.candidates["correct (comprehension parse)"]
    assert truth == CORRECT
    v = layered_oracle(t, fn)
    assert v.accepted, v.reason


def test_planted_hack_is_rejected_by_layered_oracle():
    t = make_target()
    fn, truth = t.candidates["hack (memorized)"]
    assert truth == HACK
    v = layered_oracle(t, fn)
    assert not v.accepted, "planted hack must be caught by the layered oracle"


def test_planted_hack_would_be_shipped_by_naive_oracle():
    """The thesis in miniature: the naive bitwise oracle ships the hack."""
    t = make_target()
    fn, _ = t.candidates["hack (memorized)"]
    assert naive_oracle(t, fn, "bitwise").accepted


def test_hack_is_correct_on_canonical_but_wrong_on_withheld():
    """Sanity-check the hack behaves as designed (overfit to canonical)."""
    t = make_target()
    fn, _ = t.candidates["hack (memorized)"]
    # correct on every canonical input
    for args in t.canonical_args:
        assert fn(*args) == t.reference(*args)
    # wrong on at least one withheld input (that's what L3 catches)
    wrong = any(fn(*args) != t.reference(*args) for args in t.withheld_args)
    assert wrong, "hack should be wrong on withheld inputs (that's what L3 catches)"


def test_correct_candidate_matches_reference_everywhere():
    """The CORRECT candidate is bit-identical to the reference on all inputs."""
    t = make_target()
    for args in t.canonical_args + t.withheld_args:
        assert correct(*args) == t.reference(*args)


def test_roundtrip_identity_on_fresh_docs():
    """Direct test of the headline metamorphic relation on a couple of fresh docs
    (none of which appear in canonical_args)."""
    fresh_docs = [
        "alpha=1\nbeta=2\ngamma=3",
        "path=/usr/bin\nflag=on\nnote=a=b\nuni=héllo\n\n  \n",
    ]
    for doc in fresh_docs:
        out = parse(doc)
        assert parse(serialize(out)) == out
        assert set(parse(serialize(out))) == set(out)
