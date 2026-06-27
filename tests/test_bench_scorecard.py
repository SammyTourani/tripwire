"""Cross-domain benchmark regression test (bench.run).

The Phase-2 generalization of the Phase-0 scorecard guard: across EVERY domain
target, the layered oracle must ship 0 hacks and keep 100% of valid wins, while
both naive oracles fail. If a future change breaks this, the benchmark is wrong.

Asserts deterministic decisions only (accept/reject + integrity arithmetic), never
machine-dependent timing magnitudes.
"""
from __future__ import annotations

from bench.run import collect_rows
from tripwire.target import VALID_TRUTHS


def _summary(rows, oracle):
    accepted = [r for r in rows if r.verdicts[oracle][0]]
    hacks = sum(1 for r in accepted if r.truth == "hack")
    valid_shipped = sum(1 for r in accepted if r.truth in VALID_TRUTHS)
    n_valid = sum(1 for r in rows if r.truth in VALID_TRUTHS)
    kept = (valid_shipped / n_valid) if n_valid else 0.0
    return hacks, kept


def test_bench_has_multiple_domains_and_hacks():
    rows = collect_rows()
    domains = {r.domain for r in rows}
    assert len(domains) >= 3, f"Phase 2 needs >=3 domains live, got {domains}"
    assert sum(1 for r in rows if r.truth == "hack") >= 3
    assert sum(1 for r in rows if r.truth in VALID_TRUTHS) >= 3


def test_layered_ships_zero_hacks_and_keeps_all_valid_across_domains():
    rows = collect_rows()
    hacks, kept = _summary(rows, "layered")
    assert hacks == 0, "layered oracle shipped a reward-hack in some domain"
    assert kept == 1.0, "layered oracle dropped a valid win in some domain"


def test_naive_oracles_are_unsafe_across_domains():
    rows = collect_rows()
    bitwise_hacks, bitwise_kept = _summary(rows, "naive_bitwise")
    tol_hacks, tol_kept = _summary(rows, "naive_tolerance")
    # both naive oracles ship hacks...
    assert bitwise_hacks > 0
    assert tol_hacks > 0
    # ...and bitwise additionally discards real numeric (correct_fp) wins.
    assert bitwise_kept < 1.0


def test_every_layered_accepted_candidate_is_actually_valid():
    """No hack slips through the layered oracle in any domain (truth-checked)."""
    rows = collect_rows()
    for r in rows:
        if r.verdicts["layered"][0]:
            assert r.truth in VALID_TRUTHS, (
                f"{r.domain}/{r.candidate} accepted by layered but truth={r.truth}"
            )
