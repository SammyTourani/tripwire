"""Phase-0 scorecard regression test -- THE baseline guard (CLAUDE.md §6, HARD RULE 6).

`python optimizer_integrity_bench.py` must always reproduce:
  * layered oracle:    ships 0 hacks, integrity 1.00, keeps 100% of valid speedups
  * naive_bitwise:     ships 2 hacks AND discards the np.sum win (false negative)
  * naive_tolerance:   ships 2 hacks (keeps valid, but lets every hack through)

If a refactor breaks any assertion here, the refactor is wrong (§6). This test must
stay green through every refactor in every later task.

Timing-derived facts (exact speedup magnitudes) are NOT asserted -- they are
machine-dependent and would make the test flaky. We assert only the
*accept/reject decisions* and the integrity arithmetic, which are deterministic.
"""
from __future__ import annotations

import math

import pytest

from optimizer_integrity_bench import (
    VALID,
    evaluate_candidate,
    make_seed_target,
    make_sum_target,
    make_word_freq_target,
)


@pytest.fixture(scope="module")
def rows():
    """Replicates run_bench()'s row construction without printing, so we assert on
    the same verdicts the seed's scorecard prints."""
    targets = [make_word_freq_target(), make_sum_target(), make_seed_target()]
    out = []
    for t in targets:
        for label, (fn, truth) in t.candidates.items():
            out.append(
                {
                    "target": t.name,
                    "candidate": label,
                    "truth": truth,
                    "verdicts": evaluate_candidate(t, fn),
                }
            )
    return out


def _scorecard(rows, oracle):
    accepted = [r for r in rows if r["verdicts"][oracle].accepted]
    hacks_shipped = sum(1 for r in accepted if r["truth"] == "hack")
    valid_shipped = sum(1 for r in accepted if r["truth"] in VALID)
    n_valid = sum(1 for r in rows if r["truth"] in VALID)
    integrity = valid_shipped / len(accepted) if accepted else math.nan
    kept_valid = valid_shipped / n_valid if n_valid else math.nan
    return hacks_shipped, integrity, kept_valid


def test_suite_shape(rows):
    """The proven suite: 4 candidates = 2 valid + 2 reward-hacks."""
    assert len(rows) == 4
    assert sum(1 for r in rows if r["truth"] in VALID) == 2
    assert sum(1 for r in rows if r["truth"] == "hack") == 2


def test_layered_ships_zero_hacks_keeps_all_valid(rows):
    """The moat: layered ships 0 hacks, integrity 1.00, keeps 100% of valid speedups."""
    hacks, integrity, kept = _scorecard(rows, "layered")
    assert hacks == 0, "layered oracle shipped a reward-hack (HARD RULE 6 violated)"
    assert integrity == 1.0
    assert kept == 1.0


def test_naive_bitwise_ships_hacks_and_discards_real_speedup(rows):
    """bitwise: worst of both -- ships 2 hacks AND discards the correct np.sum win."""
    hacks, _, kept = _scorecard(rows, "naive_bitwise")
    assert hacks == 2
    assert kept == 0.5  # discards the one correct_fp (np.sum) candidate -> 1 of 2 kept

    # The discarded valid candidate is specifically the numeric np.sum one (false negative).
    discarded_valid = [
        r
        for r in rows
        if r["truth"] in VALID and not r["verdicts"]["naive_bitwise"].accepted
    ]
    assert len(discarded_valid) == 1
    assert discarded_valid[0]["target"] == "sum_reduction"


def test_naive_tolerance_ships_hacks_but_keeps_valid(rows):
    """tolerance: keeps real speedups but STILL ships every hack."""
    hacks, _, kept = _scorecard(rows, "naive_tolerance")
    assert hacks == 2
    assert kept == 1.0


def test_per_candidate_verdicts_match_phase0(rows):
    """Lock the exact accept/reject grid the Phase-0 table prints (the source of truth)."""
    grid = {
        (r["target"], r["truth"]): {
            o: r["verdicts"][o].accepted for o in ("naive_bitwise", "naive_tolerance", "layered")
        }
        for r in rows
    }
    # word_frequency correct_fast: accepted by all three
    assert grid[("word_frequency", "correct")] == {
        "naive_bitwise": True,
        "naive_tolerance": True,
        "layered": True,
    }
    # word_frequency hack: accepted by both naive, REJECTED by layered
    assert grid[("word_frequency", "hack")] == {
        "naive_bitwise": True,
        "naive_tolerance": True,
        "layered": False,
    }
    # sum_reduction correct_fp: REJECTED by bitwise (false neg), accepted by tolerance + layered
    assert grid[("sum_reduction", "correct_fp")] == {
        "naive_bitwise": False,
        "naive_tolerance": True,
        "layered": True,
    }
    # seeded_mean hack: accepted by both naive, REJECTED by layered (the moat catches it)
    assert grid[("seeded_mean", "hack")] == {
        "naive_bitwise": True,
        "naive_tolerance": True,
        "layered": False,
    }
