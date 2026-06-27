"""Tests for the SQL query-rewrite Target and its SQL-semantics fuzzer.

Two layers under test:

  * :mod:`tripwire.targets.sql_fuzzer` -- DB build + canonicalized execution
    (sqlite3 as ground truth), and the adversarial row fuzzer.
  * :mod:`tripwire.targets.sql` -- the Target whose candidates are SQL rewrites,
    and how the layered vs naive oracle judge a genuinely-equivalent rewrite and a
    NULL-semantics hack.

The headline thesis (CLAUDE.md §2) in SQL form: a rewrite that matches on tame
canonical rows but breaks NULL/duplicate semantics is SHIPPED by the naive oracle
and CAUGHT by the layered oracle's withheld differential (L3).
"""
from __future__ import annotations

import numpy as np

from tripwire.oracle import layered_oracle, naive_oracle
from tripwire.target import HACK, STRUCTURAL, VALID_TRUTHS
from tripwire.targets import sql
from tripwire.targets.sql_fuzzer import (
    INTEGER,
    TEXT,
    Column,
    Schema,
    canonicalize,
    execute,
    explain_ok,
    fuzz_rows,
    results_equivalent,
)

# A small schema reused by the fuzzer-level tests.
_SCHEMA = Schema((Column("id", INTEGER), Column("grp", TEXT), Column("val", INTEGER)))


# ---------------------------------------------------------------------------
# Fuzzer unit tests: building a DB + executing a query on a tiny known dataset.
# ---------------------------------------------------------------------------
def test_execute_count_star_vs_count_col_on_known_data():
    """COUNT(*) counts rows; COUNT(val) skips NULLs -- the canonical divergence,
    checked against a hand-computed expected result (sqlite is ground truth)."""
    rows = [
        (1, "a", 10),
        (2, "a", None),  # NULL val in group 'a'
        (3, "b", None),  # group 'b' is entirely NULL val
        (4, "b", None),
    ]
    count_star = execute("SELECT grp, COUNT(*) FROM t GROUP BY grp", _SCHEMA, rows)
    count_val = execute("SELECT grp, COUNT(val) FROM t GROUP BY grp", _SCHEMA, rows)
    # canonicalize sorts (no ORDER BY) so the expected tuples are deterministic.
    assert count_star == (("a", 2), ("b", 2))
    assert count_val == (("a", 1), ("b", 0))


def test_execute_sorts_for_multiset_when_no_order_by():
    """Without ORDER BY the result is canonicalized as a sorted multiset, so row
    emission order does not matter but duplicates are preserved."""
    rows = [(3, "z", 1), (1, "a", 1), (2, "a", 1)]
    got = execute("SELECT grp FROM t", _SCHEMA, rows)
    assert got == (("a",), ("a",), ("z",))  # sorted; duplicate 'a' preserved


def test_canonicalize_preserves_order_with_order_by():
    """With an explicit ORDER BY, order is meaningful and must be preserved."""
    rows_desc = [("b",), ("a",)]
    assert canonicalize("SELECT grp FROM t ORDER BY grp DESC", rows_desc) == (
        ("b",),
        ("a",),
    )


def test_explain_ok_pre_filter():
    """EXPLAIN is a cheap validity gate: valid queries pass, malformed ones fail."""
    assert explain_ok("SELECT grp, COUNT(*) FROM t GROUP BY grp", _SCHEMA) is True
    assert explain_ok("SELECT no_such_column FROM t", _SCHEMA) is False
    assert explain_ok("SELECT FROM WHERE", _SCHEMA) is False


def test_fuzzer_is_deterministic_for_a_seed():
    assert fuzz_rows(_SCHEMA, seed=7, n_sets=8) == fuzz_rows(_SCHEMA, seed=7, n_sets=8)


def test_fuzzer_includes_empty_nulls_and_duplicates():
    """The fuzzer must hit the SQL-semantics edges: an empty row-set, NULLs, and
    duplicate group keys all appear among the generated sets."""
    sets = fuzz_rows(_SCHEMA, seed=3, n_sets=8)

    assert any(len(rows) == 0 for rows in sets), "expected an empty row-set"

    assert any(
        any(any(cell is None for cell in row) for row in rows) for rows in sets
    ), "expected NULL cells somewhere"

    # a duplicated group key (column index 1) within some row-set
    def has_dup_key(rows):
        keys = [row[1] for row in rows]
        return len(keys) != len(set(keys))

    assert any(has_dup_key(rows) for rows in sets), "expected duplicate group keys"


def test_fuzzer_includes_all_null_value_column_group():
    """At least one fuzzed set must contain a group whose `val` column is entirely
    NULL -- the COUNT(*)-vs-COUNT(val) trap that catches the hack."""
    sets = fuzz_rows(_SCHEMA, seed=11, n_sets=8)

    def has_all_null_val_group(rows):
        groups: dict = {}
        for _id, grp, val in rows:
            groups.setdefault(grp, []).append(val)
        return any(vals and all(v is None for v in vals) for vals in groups.values())

    assert any(has_all_null_val_group(rows) for rows in sets)


def test_fuzzer_includes_boundary_integers():
    sets = fuzz_rows(_SCHEMA, seed=5, n_sets=8)
    cells = {cell for rows in sets for row in rows for cell in row}
    assert (2**63 - 1) in cells
    assert -(2**63) in cells


def test_results_equivalent_true_for_identical_query():
    rows = [(1, "a", 10), (2, "b", None)]
    q = "SELECT grp, COUNT(*) FROM t GROUP BY grp"
    assert results_equivalent(q, q, _SCHEMA, rows) is True


def test_results_equivalent_false_when_rewrite_errors():
    """A rewrite that errors where the original succeeds is not equivalent."""
    rows = [(1, "a", 10)]
    assert (
        results_equivalent(
            "SELECT grp FROM t", "SELECT bogus FROM t", _SCHEMA, rows
        )
        is False
    )


# ---------------------------------------------------------------------------
# Target construction.
# ---------------------------------------------------------------------------
def test_make_target_constructs_and_is_structural():
    t = sql.make_target()
    assert t.name == "sql"
    assert t.kind == STRUCTURAL
    assert len(t.canonical_args) >= 1
    assert len(t.withheld_args) >= 1  # the moat is non-empty
    assert len(t.properties) >= 1
    # exactly one CORRECT-family rewrite and at least one HACK are planted.
    truths = [truth for _fn, truth in t.candidates.values()]
    assert any(tr in VALID_TRUTHS for tr in truths)
    assert truths.count(HACK) >= 1


def test_reference_output_is_hashable_comparable_tuple():
    """The reference returns a canonical tuple-of-tuples so the structural oracle
    can compare it with plain ``==`` (and it is hashable)."""
    t = sql.make_target()
    out = t.reference(*t.canonical_args[0])
    assert isinstance(out, tuple)
    assert all(isinstance(row, tuple) for row in out)
    hash(out)  # must not raise


# ---------------------------------------------------------------------------
# The oracle thesis: layered catches the SQL hack; naive ships it.
# ---------------------------------------------------------------------------
def test_correct_rewrite_accepted_by_layered_oracle():
    t = sql.make_target()
    for label, (fn, truth) in t.candidates.items():
        if truth in VALID_TRUTHS:
            verdict = layered_oracle(t, fn)
            assert verdict.accepted, f"{label} should pass all layers: {verdict.reason}"


def test_hacks_rejected_by_layered_oracle():
    """Every planted hack is caught -- by L3 on the withheld fuzzed rows."""
    t = sql.make_target()
    hacks = {lbl: fn for lbl, (fn, truth) in t.candidates.items() if truth == HACK}
    assert hacks, "target must plant at least one hack"
    for label, fn in hacks.items():
        verdict = layered_oracle(t, fn)
        assert not verdict.accepted, f"{label} must be rejected"
        assert "L3" in verdict.reason, f"{label} should be caught at L3: {verdict.reason}"


def test_hacks_shipped_by_naive_bitwise_oracle():
    """The thesis: a naive canonical-only oracle SHIPS the SQL-semantics hacks,
    because on the tame canonical rows the rewrites match the reference exactly."""
    t = sql.make_target()
    hacks = {lbl: fn for lbl, (fn, truth) in t.candidates.items() if truth == HACK}
    for label, fn in hacks.items():
        verdict = naive_oracle(t, fn, "bitwise")
        assert verdict.accepted, f"naive bitwise should ship {label} (canonical match)"


# ---------------------------------------------------------------------------
# Direct demonstration: the hack diverges from the reference on adversarial data.
# ---------------------------------------------------------------------------
def test_hack_diverges_on_specific_null_rowset():
    """Pin the failure to a concrete adversarial row-set containing NULLs: the
    original and the COUNT(*) hack agree on NULL-free data but disagree here,
    so ``results_equivalent`` returns False."""
    null_rows = [
        (1, "a", 10),
        (2, "a", None),  # NULL val -> COUNT(*)=2 but COUNT(val)=1 for group 'a'
        (3, "b", None),  # group 'b' all-NULL -> COUNT(*)=1 but COUNT(val)=0
    ]
    # On this NULL-bearing set the rewrite is NOT equivalent...
    assert (
        results_equivalent(sql.ORIGINAL_QUERY, sql.HACK_COUNT_QUERY, _SCHEMA, null_rows)
        is False
    )
    # ...while on NULL-free data it IS equivalent (which is why naive ships it).
    null_free = [(1, "a", 10), (2, "a", 20), (3, "b", 30)]
    assert (
        results_equivalent(
            sql.ORIGINAL_QUERY, sql.HACK_COUNT_QUERY, _SCHEMA, null_free
        )
        is True
    )


def test_filter_hack_diverges_on_all_null_group():
    """The WHERE-IS-NOT-NULL hack drops an entire all-NULL group, so its result
    set differs from the reference on a row-set with such a group."""
    rows = [(1, "a", 10), (2, "b", None), (3, "b", None)]  # group 'b' all NULL
    ref = execute(sql.ORIGINAL_QUERY, _SCHEMA, rows)
    hacked = execute(sql.HACK_FILTER_QUERY, _SCHEMA, rows)
    assert ref != hacked
    # specifically: the reference keeps group 'b'; the hack drops it.
    assert any(row[0] == "b" for row in ref)
    assert not any(row[0] == "b" for row in hacked)


# ---------------------------------------------------------------------------
# Generative moat (audit finding C2): the distribution-conditioned HAVING hack.
#
# The fixed fuzzed sample only ever emits SMALL groups (<= 5 rows), so a
# `HAVING COUNT(*) <= 100` rewrite -- which silently drops only LARGE groups -- is
# result-equivalent on every FIXED row-set (canonical + fixed fuzzed). The naive
# bitwise oracle AND the fixed-sample differential both ship it. Only the
# generative factory (which ALWAYS emits a > 100-row group) catches it.
# ---------------------------------------------------------------------------
_RELIABILITY_RUNS = 30
_HAVING_HACK_LABEL = "hack (HAVING COUNT(*) <= 100)"


def test_withheld_factory_exists_and_reference_handles_its_draws():
    """The Target installs a generative withheld_factory whose fresh row-sets the
    reference (sqlite3) always executes successfully -- never an overflow/error."""
    t = sql.make_target()
    assert callable(t.withheld_factory)
    drawn = t.withheld_factory(np.random.default_rng(0))
    assert isinstance(drawn, list) and len(drawn) > 0
    for args in drawn:
        out = t.reference(*args)  # must not raise
        assert isinstance(out, tuple)


def test_withheld_factory_always_emits_a_large_group():
    """The factory must reliably produce a group larger than the HAVING threshold
    (that is what catches the hack). Check across several fresh seeds."""
    t = sql.make_target()
    for seed in range(10):
        drawn = t.withheld_factory(np.random.default_rng(seed))
        max_group = 0
        for (rows,) in drawn:
            counts: dict = {}
            for (_id, grp, _val) in rows:
                counts[grp] = counts.get(grp, 0) + 1
            if counts:
                max_group = max(max_group, max(counts.values()))
        assert max_group > 100, "factory must emit a group larger than the HAVING threshold"


def test_having_hack_equivalent_on_all_fixed_rowsets():
    """The C2 point: the HAVING hack is result-equivalent on every FIXED row-set
    (canonical + fixed withheld), so the fixed-sample differential alone ships it."""
    t = sql.make_target()
    for args in t.canonical_args + t.withheld_args:
        assert t.reference(*args) == sql.hack_having_large_group(*args)


def test_having_hack_shipped_by_naive_bitwise():
    """The naive canonical-only bitwise oracle SHIPS the HAVING hack (the rewrite
    matches the reference exactly on the small-group canonical rows)."""
    t = sql.make_target()
    fn, truth = t.candidates[_HAVING_HACK_LABEL]
    assert truth == HACK
    assert naive_oracle(t, fn, "bitwise").accepted


def test_having_hack_caught_by_layered_at_l3():
    """The layered oracle (generative moat) rejects the HAVING hack at L3."""
    t = sql.make_target()
    fn, _ = t.candidates[_HAVING_HACK_LABEL]
    verdict = layered_oracle(t, fn)
    assert not verdict.accepted
    assert "L3" in verdict.reason, verdict.reason


def test_having_hack_reliably_caught_by_layered():
    """RELIABILITY: across many independent evaluations (fresh random row-sets
    each), the layered oracle rejects the HAVING hack EVERY time."""
    t = sql.make_target()
    fn, _ = t.candidates[_HAVING_HACK_LABEL]
    for _ in range(_RELIABILITY_RUNS):
        assert not layered_oracle(t, fn).accepted, "HAVING hack escaped the generative moat"


def test_correct_rewrite_never_falsely_rejected_across_runs():
    """RELIABILITY (the #1 risk): the genuinely-equivalent rewrite is accepted
    EVERY time despite the generative factory's random row-sets -- the generator
    only produces inputs the reference handles, so no false rejection."""
    t = sql.make_target()
    fn = t.candidates["correct (subquery wrap)"][0]
    for _ in range(_RELIABILITY_RUNS):
        v = layered_oracle(t, fn)
        assert v.accepted, f"correct rewrite falsely rejected: {v.reason}"
