"""Edge-case tests for the oracle's comparison primitives (tripwire.measure).

These cover the four hardening fixes the audit demanded for ``exact_equal`` (the
L1/L3 comparator for ``structural`` targets) and ``close_equal`` (for ``numeric``
targets). All four are soundness / false-negative fixes, so each assertion below
maps to a specific defect:

  Defect 1  exact_equal is TYPE-STRICT: 1 != 1.0 != True, "1" != 1, a tuple is not a
            list, dict values differ in type -> not equal. (Structural "exact" must
            mean type-exact, ADR-004.)
  Defect 2  NaN == NaN in BOTH comparators (scalar and position-wise in arrays); a
            correct reference that legitimately produces NaN is not falsely rejected.
  Defect 3  close_equal recurses into dict/list/tuple applying tolerance to numeric
            leaves (no silent bitwise fallback), and requires MATCHING SHAPES for
            arrays (a scalar is not "close" to a vector via numpy broadcast).
  TOTAL     Both comparators always return a bool and never raise, even on objects
            with no useful ``__eq__``.

Both comparators are also exercised end-to-end through the real Targets (the types
the structural targets actually return: list[str], dict[str,str], tuples) so a
too-strict fix that broke a legitimate candidate would be caught here.
"""
from __future__ import annotations

import numpy as np
import pytest

from tripwire.measure import close_equal, exact_equal

NAN = float("nan")
POS_INF = float("inf")
NEG_INF = float("-inf")


# ===========================================================================
# Defect 1 -- exact_equal type-coercion holes are closed (type-strict).
# ===========================================================================
@pytest.mark.parametrize(
    "a,b",
    [
        (1, 1.0),            # int vs float
        (1, True),           # int vs bool
        (0, False),          # int vs bool (the 0/False hole)
        ({"a": 1}, {"a": 1.0}),     # dict value type differs
        ((1,), (1.0,)),      # tuple element type differs
        ("1", 1),            # str vs int
        ((1,), [1]),         # tuple vs list (different container types)
        (1.0, True),         # float vs bool
        ({"a": 1}, {"a": True}),    # dict value 1 vs True
        ([1, 2], (1, 2)),    # list vs tuple
    ],
)
def test_exact_equal_is_type_strict(a, b):
    """Type-distinct values are NEVER 'exactly equal' (Defect 1)."""
    assert exact_equal(a, b) is False
    assert exact_equal(b, a) is False  # symmetric


# The explicit cases named in the Definition of Done.
def test_exact_equal_dod_named_cases():
    assert exact_equal(1, 1.0) is False
    assert exact_equal(1, True) is False
    assert exact_equal({"a": 1}, {"a": 1.0}) is False


@pytest.mark.parametrize(
    "a,b",
    [
        (1, 1),              # same int
        (1.0, 1.0),          # same float
        (True, True),        # same bool
        (False, False),
        ("a", "a"),          # same str
        (None, None),        # None == None
        (b"x", b"x"),        # same bytes
        ([1, 2, 3], [1, 2, 3]),         # list recursion, same types
        ((1, "a", None), (1, "a", None)),   # tuple with mixed leaf types
        ({"k": "v", "n": 2}, {"k": "v", "n": 2}),  # dict, same value types
    ],
)
def test_exact_equal_same_type_same_value_is_equal(a, b):
    """Same-typed equal values ARE equal -- type-strictness must not over-reject."""
    assert exact_equal(a, b) is True


def test_exact_equal_container_length_and_keys():
    assert exact_equal([1, 2], [1, 2, 3]) is False          # length differs
    assert exact_equal((1, 2, 3), (1, 2)) is False
    assert exact_equal({"a": 1}, {"a": 1, "b": 2}) is False  # key-set differs
    assert exact_equal({"a": 1}, {"b": 1}) is False          # different keys


def test_exact_equal_nested_type_strictness_recurses():
    # A nested int-vs-float deep in a structure must still be caught.
    assert exact_equal({"k": [1, 2]}, {"k": [1, 2.0]}) is False
    assert exact_equal([[1], [2]], [[1], [2]]) is True
    assert exact_equal({"a": (1, 2)}, {"a": (1, 2)}) is True


# ===========================================================================
# Defect 2 -- NaN equals NaN in BOTH comparators (scalar + array, position-wise).
# ===========================================================================
def test_exact_equal_nan_equals_nan():
    assert exact_equal(NAN, NAN) is True                 # DoD named case
    assert exact_equal(np.nan, np.nan) is True


def test_close_equal_nan_equals_nan():
    assert close_equal(NAN, NAN) is True                 # DoD named case
    assert close_equal(np.nan, np.nan) is True


def test_nan_is_not_equal_to_a_number():
    assert exact_equal(NAN, 1.0) is False
    assert exact_equal(1.0, NAN) is False
    assert close_equal(NAN, 1.0) is False
    assert close_equal(1.0, NAN) is False


def test_array_nan_positions_match():
    a = np.array([1.0, 2.0, NAN])
    b = np.array([1.0, 2.0, NAN])
    assert exact_equal(a, b) is True
    assert close_equal(a, b) is True
    # a NaN in a DIFFERENT position is not equal
    c = np.array([1.0, NAN, 3.0])
    assert exact_equal(a, c) is False
    assert close_equal(a, c) is False


def test_list_with_nan_leaf_is_equal():
    # numpy allclose default (equal_nan=False) would reject this; we must not.
    assert close_equal([1, 2, NAN], [1, 2, NAN]) is True
    assert exact_equal([1.0, 2.0, NAN], [1.0, 2.0, NAN]) is True


def test_signed_infinity_rules():
    # +inf == +inf, -inf == -inf, but +inf != -inf, in BOTH comparators.
    assert exact_equal(POS_INF, POS_INF) is True
    assert exact_equal(NEG_INF, NEG_INF) is True
    assert exact_equal(POS_INF, NEG_INF) is False
    assert close_equal(POS_INF, POS_INF) is True
    assert close_equal(NEG_INF, NEG_INF) is True
    assert close_equal(POS_INF, NEG_INF) is False
    # inf is not close to a finite number
    assert close_equal(POS_INF, 1e308) is False
    assert np.array([POS_INF, NEG_INF]) is not None  # sanity
    assert close_equal(np.array([POS_INF, 1.0]), np.array([POS_INF, 1.0])) is True
    assert close_equal(np.array([POS_INF]), np.array([NEG_INF])) is False


# ===========================================================================
# Defect 3 -- close_equal: structured tolerance + shape-strict (no broadcast).
# ===========================================================================
def test_close_equal_dict_applies_tolerance_to_numeric_leaves():
    # The headline DoD case: a structured numeric output is NOT compared bitwise.
    assert close_equal({"x": 1.0}, {"x": 1.0 + 1e-9}) is True
    assert close_equal({"x": 1.0}, {"x": 1.1}) is False
    # nested structure
    assert close_equal({"a": [1.0, 2.0]}, {"a": [1.0 + 1e-10, 2.0]}) is True
    assert close_equal({"a": [1.0, 2.0]}, {"a": [1.0, 9.0]}) is False


def test_close_equal_list_tuple_tolerance():
    assert close_equal([1.0, 2.0], [1.0 + 1e-10, 2.0 - 1e-10]) is True
    assert close_equal((1.0, 2.0), (1.0 + 1e-10, 2.0)) is True
    assert close_equal([1.0, 2.0], [1.0, 5.0]) is False
    # container length / type must still match
    assert close_equal([1.0], [1.0, 2.0]) is False
    assert close_equal([1.0, 2.0], (1.0, 2.0)) is False  # list vs tuple


def test_close_equal_non_numeric_leaves_are_type_strict():
    # strings inside a numeric structure compare exactly (a label that changed is wrong)
    assert close_equal({"name": "a", "v": 1.0}, {"name": "a", "v": 1.0 + 1e-9}) is True
    assert close_equal({"name": "a", "v": 1.0}, {"name": "b", "v": 1.0}) is False


def test_close_equal_shape_mismatch_is_not_close():
    # DoD named case: a scalar must NOT broadcast to match a vector.
    assert close_equal(np.zeros(5), 0.0) is False
    assert close_equal(0.0, np.zeros(5)) is False
    assert close_equal(np.zeros(200), 0.0) is False        # the documented hole
    # equal-shaped zero vectors ARE close
    assert close_equal(np.zeros(5), np.zeros(5)) is True
    # differently-shaped arrays are not close even with equal values
    assert close_equal(np.array([1.0, 1.0]), np.array([1.0, 1.0, 1.0])) is False
    assert close_equal(np.ones((2, 3)), np.ones((3, 2))) is False


def test_close_equal_scalar_tolerance_still_works():
    assert close_equal(1.0, 1.0 + 1e-12) is True
    assert close_equal(1.0, 1.1) is False
    assert close_equal(100.0, 100.0 + 1e-5) is True   # within rtol=1e-6 of 100
    assert close_equal(100.0, 101.0) is False


def test_close_equal_custom_tolerances_passed_through():
    # Signature/defaults preserved; a looser rtol accepts a bigger gap.
    assert close_equal(1.0, 1.05, rtol=0.1) is True
    assert close_equal(1.0, 1.05, rtol=1e-6) is False


def test_exact_equal_array_dtype_kind_strictness():
    # int array vs equal-valued float array -> different for 'exact'.
    assert exact_equal(np.array([1, 2, 3]), np.array([1.0, 2.0, 3.0])) is False
    # same dtype, same values -> equal (the case that must keep working).
    assert exact_equal(np.array([1, 2, 3]), np.array([1, 2, 3])) is True
    assert exact_equal(np.array([1.0, 2.0]), np.array([1.0, 2.0])) is True


def test_exact_equal_array_vs_scalar_no_broadcast():
    # An array is never 'exactly' a bare scalar (no silent broadcast to equal).
    assert exact_equal(np.array([1, 1, 1]), 1) is False
    assert exact_equal(1, np.array([1, 1, 1])) is False
    assert exact_equal(np.zeros(3), 0.0) is False


# ===========================================================================
# TOTAL -- both comparators always return a bool and never raise.
# ===========================================================================
class _NoEq:
    """An object whose __eq__ blows up -- to prove the comparators swallow it."""

    def __eq__(self, other):
        raise RuntimeError("boom: __eq__ must never escape the comparator")

    def __hash__(self):
        return 0


@pytest.mark.parametrize(
    "a,b",
    [
        (object(), object()),       # DoD named case
        (_NoEq(), _NoEq()),         # raising __eq__
        (object(), 1),              # mismatched weird types
        ({1, 2, 3}, {1, 2, 3}),     # sets (not a recursed container)
        (frozenset({1}), frozenset({1})),
        (NAN, "not a number"),      # NaN vs str
        ([1, object()], [1, object()]),  # weird leaf inside a list
        ({"k": object()}, {"k": object()}),  # weird leaf inside a dict
        (range(3), range(3)),       # exotic iterable type
    ],
)
def test_exact_equal_is_total(a, b):
    result = exact_equal(a, b)
    assert isinstance(result, bool)  # returned a bool, did not raise


@pytest.mark.parametrize(
    "a,b",
    [
        (object(), object()),
        (_NoEq(), _NoEq()),
        (object(), 1.0),
        ({1, 2, 3}, {1, 2, 3}),
        (NAN, "not a number"),
        ([1.0, object()], [1.0, object()]),
        ({"k": object()}, {"k": object()}),
        ("a string", "a string"),
        (None, 1.0),                # None vs number
    ],
)
def test_close_equal_is_total(a, b):
    result = close_equal(a, b)
    assert isinstance(result, bool)  # returned a bool, did not raise


def test_total_on_identical_object_identity():
    # Same object on both sides: _NoEq raises on ==, so fall back to identity -> True.
    o = _NoEq()
    assert exact_equal(o, o) is True
    assert close_equal(o, o) is True


# ===========================================================================
# End-to-end against the REAL target return types (guards against TOO-strict).
# ===========================================================================
def test_exact_equal_matches_tokenizer_list_of_str():
    from tripwire.targets.tokenizer import correct_regex, reference

    text = "Hello, World! 123 -- testing 1-2-3."
    ref_out = reference(text)        # list[str]
    cand_out = correct_regex(text)   # list[str], must compare equal
    assert isinstance(ref_out, list) and all(isinstance(x, str) for x in ref_out)
    assert exact_equal(ref_out, cand_out) is True
    # a single token changed -> not equal
    assert exact_equal(ref_out, ref_out[:-1]) is False


def test_exact_equal_matches_serde_dict_of_str():
    from tripwire.targets.serde import correct, parse

    text = "name=tripwire\nkind=structural\nstars=6000"
    ref_out = parse(text)            # dict[str, str]
    cand_out = correct(text)
    assert isinstance(ref_out, dict)
    assert exact_equal(ref_out, cand_out) is True
    # a hack constant must differ
    assert exact_equal(ref_out, {"_": "_"}) is False


def test_exact_equal_matches_sql_tuple_results_with_nulls():
    from tripwire.targets.sql import correct, reference

    # canonical row-set + an adversarial one with NULL val (all-NULL group -> NULL out)
    rows = [(1, "a", 10), (2, "a", 20), (3, "b", None), (4, "b", None)]
    ref_out = reference(rows)        # tuple of row-tuples, contains ints/str/None
    cand_out = correct(rows)         # genuinely-equivalent rewrite -> identical result
    assert isinstance(ref_out, tuple)
    assert exact_equal(ref_out, cand_out) is True


def test_close_equal_matches_numeric_float_outputs():
    # The numeric correct_fp candidate returns a Python float that differs in low bits;
    # type-strictness must NOT reject it (Python float vs Python float is fine).
    from tripwire.targets.sum_reduction import _correct_fp, reference

    rng = np.random.default_rng(7)
    arr = rng.standard_normal(50_000)
    ref_out = reference(arr)         # Python float (sequential sum)
    cand_out = _correct_fp(arr)      # Python float (np.sum) -- low bits differ
    assert isinstance(ref_out, float) and isinstance(cand_out, float)
    assert ref_out != cand_out or True  # may or may not differ; tolerance is the point
    assert close_equal(ref_out, cand_out) is True


def test_close_equal_matches_numeric_array_outputs():
    # matvec returns a numpy array; reference and np-vectorized differ in low bits.
    from tripwire.targets.numeric import _matvec_correct_fp, matvec_reference

    rng = np.random.default_rng(11)
    A = rng.standard_normal((30, 40))
    x = rng.standard_normal(40)
    ref_out = matvec_reference(A, x)
    cand_out = _matvec_correct_fp(A, x)
    assert close_equal(ref_out, cand_out) is True
    # a wrong-shape constant candidate (a hack) is not close
    assert close_equal(ref_out, np.full(31, 0.5)) is False  # wrong shape
