"""Schema test for Interface A (Target) -- locks the FROZEN contract (task 1.3).

Interface A is load-bearing: every Phase-2 domain plug-in and the benchmark
program against this exact shape. These tests fail loudly if a refactor:
  * renames/removes a field or changes its order/default,
  * weakens a validation invariant (esp. ADR-003: withheld_args must be non-empty),
  * changes the frozen vocabularies (KINDS / TRUTHS / VALID_TRUTHS).

If you are intentionally evolving the contract, it must be ADDITIVE (new optional
field with a safe default) and these tests updated deliberately -- not loosened to
make a breaking change pass.
"""
from __future__ import annotations

import dataclasses

import pytest

from tripwire.target import (
    CORRECT,
    CORRECT_FP,
    HACK,
    KINDS,
    NUMERIC,
    STRUCTURAL,
    TRUTHS,
    VALID_TRUTHS,
    Target,
)


def _ok(**over):
    """A minimal valid Target; override individual fields to test one invariant."""
    base = dict(
        name="t",
        kind=STRUCTURAL,
        reference=lambda s: s,
        canonical_args=[("a",)],
        withheld_args=[("b",)],
    )
    base.update(over)
    return Target(**base)


# ---------------------------------------------------------------------------
# Frozen vocabularies
# ---------------------------------------------------------------------------
def test_kinds_vocabulary_frozen():
    assert KINDS == frozenset({"structural", "numeric"})
    assert STRUCTURAL == "structural"
    assert NUMERIC == "numeric"


def test_truth_vocabulary_frozen():
    assert TRUTHS == frozenset({"correct", "correct_fp", "hack"})
    assert (CORRECT, CORRECT_FP, HACK) == ("correct", "correct_fp", "hack")


def test_valid_truths_are_the_non_hack_labels():
    # bench integrity depends on this: a 'valid' candidate is one the oracle SHOULD keep.
    assert VALID_TRUTHS == frozenset({"correct", "correct_fp"})
    assert HACK not in VALID_TRUTHS


# ---------------------------------------------------------------------------
# Frozen field set, order, types, and defaults
# ---------------------------------------------------------------------------
def test_field_names_and_order_frozen():
    names = [f.name for f in dataclasses.fields(Target)]
    assert names == [
        "name",
        "kind",
        "reference",
        "canonical_args",
        "withheld_args",
        "properties",
        "candidates",
        # ADDITIVE (hardening): optional generative moat. Appended LAST so the
        # original 7-field positional construction is unchanged. New optional fields
        # may be appended here, but the first 7 names/order are FROZEN.
        "withheld_factory",
    ], "Interface A field set/order changed -- the first 7 are FROZEN (1.3)"


def test_optional_fields_have_safe_defaults():
    t = _ok()
    assert t.properties == []
    assert t.candidates == {}
    assert t.withheld_factory is None  # optional generative moat; off by default
    # defaults must be independent instances (no shared mutable default state)
    t2 = _ok()
    t.properties.append(("x", lambda a, o: True))
    assert t2.properties == [], "properties default is shared mutable state (bug)"


def test_positional_construction_matches_seed_usage():
    # the seed constructs Target positionally; lock that order keeps working.
    t = Target("n", NUMERIC, lambda x: x, [(1,)], [(2,)], [], {})
    assert t.name == "n" and t.kind == NUMERIC


# ---------------------------------------------------------------------------
# Validation: kind
# ---------------------------------------------------------------------------
def test_rejects_unknown_kind():
    with pytest.raises(ValueError, match="kind"):
        _ok(kind="quantum")


# ---------------------------------------------------------------------------
# Validation: reference
# ---------------------------------------------------------------------------
def test_rejects_non_callable_reference():
    with pytest.raises(TypeError, match="reference"):
        _ok(reference=42)


# ---------------------------------------------------------------------------
# Validation: canonical / withheld  (ADR-003 -- the moat)
# ---------------------------------------------------------------------------
def test_rejects_empty_withheld_args_the_moat():
    # THE most important invariant: no withheld inputs => no moat (ADR-003).
    with pytest.raises(ValueError, match="withheld_args"):
        _ok(withheld_args=[])


def test_rejects_empty_canonical_args():
    with pytest.raises(ValueError, match="canonical_args"):
        _ok(canonical_args=[])


def test_rejects_non_list_args():
    with pytest.raises(ValueError, match="canonical_args"):
        _ok(canonical_args="a b c")  # str is iterable but not the contract


def test_rejects_arg_entry_that_is_not_a_tuple():
    # each entry must be a tuple/list so reference(*args) works.
    with pytest.raises(TypeError, match=r"canonical_args\[0\]"):
        _ok(canonical_args=["a"])  # 'a' is not a tuple of positional args


# ---------------------------------------------------------------------------
# Validation: properties
# ---------------------------------------------------------------------------
def test_rejects_malformed_property_pair():
    with pytest.raises(TypeError, match="properties"):
        _ok(properties=[lambda a, o: True])  # not a (name, fn) pair


def test_rejects_property_with_non_callable_fn():
    with pytest.raises(TypeError, match="fn must be callable"):
        _ok(properties=[("bad", 123)])


def test_accepts_empty_properties():
    # seeded_mean ships with no properties; must stay legal.
    assert _ok(properties=[]).properties == []


# ---------------------------------------------------------------------------
# Validation: candidates
# ---------------------------------------------------------------------------
def test_rejects_unknown_truth_label():
    with pytest.raises(ValueError, match="truth"):
        _ok(candidates={"c": (lambda x: x, "definitely_correct")})


def test_rejects_malformed_candidate_spec():
    with pytest.raises(TypeError, match="candidates"):
        _ok(candidates={"c": (lambda x: x,)})  # missing truth


def test_accepts_each_valid_truth_label():
    for truth in TRUTHS:
        t = _ok(candidates={"c": (lambda x: x, truth)})
        assert t.candidates["c"][1] == truth


# ---------------------------------------------------------------------------
# The real seed targets must satisfy the frozen contract (regression).
# ---------------------------------------------------------------------------
def test_seed_targets_satisfy_the_contract():
    from optimizer_integrity_bench import (
        make_seed_target,
        make_sum_target,
        make_word_freq_target,
    )

    for make in (make_word_freq_target, make_sum_target, make_seed_target):
        t = make()  # construction itself runs __post_init__ validation
        assert t.kind in KINDS
        assert len(t.canonical_args) > 0 and len(t.withheld_args) > 0
        for _label, (_fn, truth) in t.candidates.items():
            assert truth in TRUTHS
