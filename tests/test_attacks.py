"""Tests for the red-team attack suite (tripwire.attacks + bench.attack_suite).

The thesis, from the attacker's side: every attack class in the library is CAUGHT
by the layered oracle (it ships 0 hacks), while a naive canonical-only oracle is
fooled by at least one of them. A genuinely-correct control candidate must still be
ACCEPTED, so the suite is not trivially "catching everything" by rejecting all.

All targets here are SELF-CONTAINED (defined in tripwire.attacks.library); these
tests never depend on another agent's tripwire/targets/* file.
"""
from __future__ import annotations

import pytest

from tripwire.attacks import (
    ATTACKS,
    AttackRecord,
    correct_control,
    make_numeric_target,
    make_structural_target,
    memorizer,
    run_attacks,
)
from tripwire.oracle import layered_oracle, naive_oracle
from tripwire.target import NUMERIC, Target

# Both self-contained targets, exercising exact (structural) and tolerance (numeric).
TARGET_FACTORIES = [make_numeric_target, make_structural_target]
RECORD_FIELDS = {
    "attack",
    "naive_bitwise_accepted",
    "naive_tolerance_accepted",
    "layered_accepted",
    "layered_reason",
}


@pytest.fixture(params=TARGET_FACTORIES, ids=lambda f: f().name)
def target(request) -> Target:
    return request.param()


# ---------------------------------------------------------------------------
# Headline: the layered oracle catches every attack class (ships 0 hacks).
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("attack_name", list(ATTACKS))
def test_layered_oracle_catches_every_attack(target: Target, attack_name: str) -> None:
    factory = ATTACKS[attack_name]
    cand = factory(target)
    verdict = layered_oracle(target, cand)
    assert verdict.accepted is False, (
        f"attack {attack_name!r} SURVIVED the layered oracle on {target.name} "
        f"(reason={verdict.reason!r}) -- the moat has a hole; file against the core"
    )
    assert verdict.reason  # a rejection always names the failing layer


def test_layered_ships_zero_hacks_across_targets(target: Target) -> None:
    records = run_attacks(target)
    survivors = [r.attack for r in records if r.survived]
    assert survivors == [], f"these attacks beat the layered oracle: {survivors}"
    assert all(r.caught for r in records)


# ---------------------------------------------------------------------------
# The gap: a naive canonical-only oracle is fooled by at least one attack.
# ---------------------------------------------------------------------------
def test_naive_oracle_ships_at_least_one_attack(target: Target) -> None:
    records = run_attacks(target)
    shipped = [r.attack for r in records if r.shipped_by_naive]
    assert shipped, (
        "no attack fooled the naive oracle -- the gap the benchmark measures "
        "would be invisible"
    )


def test_memorizer_is_shipped_by_naive_oracle(target: Target) -> None:
    """The memorizer passes canonical, so the naive (canonical-only) oracle ships
    it -- the documented false-positive (threat-model class 1)."""
    cand = memorizer(target)
    assert naive_oracle(target, cand, "tolerance").accepted is True
    assert naive_oracle(target, cand, "bitwise").accepted is True


# ---------------------------------------------------------------------------
# The moat in isolation: with no metamorphic property to short-circuit, a
# memorizer that passes canonical can ONLY be caught by L3 (the withheld
# differential). Proves the moat itself works, not just an earlier layer.
# ---------------------------------------------------------------------------
def test_moat_alone_catches_memorizer_via_L3() -> None:
    base = make_numeric_target()
    no_props = Target(  # same data, properties stripped -> L3 is the only defense
        "noprop_numeric",
        NUMERIC,
        base.reference,
        base.canonical_args,
        base.withheld_args,
    )
    cand = memorizer(no_props)
    verdict = layered_oracle(no_props, cand)
    assert verdict.accepted is False
    assert verdict.reason == "L3 withheld-input differential mismatch"
    # ...and the naive oracle still ships it (the gap).
    assert naive_oracle(no_props, cand, "tolerance").accepted is True


# ---------------------------------------------------------------------------
# Schema: run_attacks returns one well-formed record per registered attack.
# ---------------------------------------------------------------------------
def test_run_attacks_schema(target: Target) -> None:
    records = run_attacks(target)
    assert len(records) == len(ATTACKS)
    assert [r.attack for r in records] == list(ATTACKS)
    for r in records:
        assert isinstance(r, AttackRecord)
        assert set(vars(r)) == RECORD_FIELDS
        assert isinstance(r.naive_bitwise_accepted, bool)
        assert isinstance(r.naive_tolerance_accepted, bool)
        assert isinstance(r.layered_accepted, bool)
        assert isinstance(r.layered_reason, str) and r.layered_reason
        # derived flags are internally consistent
        assert r.caught is (not r.layered_accepted)
        assert r.survived is r.layered_accepted
        assert r.shipped_by_naive is (
            r.naive_bitwise_accepted or r.naive_tolerance_accepted
        )


# ---------------------------------------------------------------------------
# Control (false-negative axis): a genuinely-correct candidate is ACCEPTED, so
# the suite isn't trivially rejecting everything.
# ---------------------------------------------------------------------------
def test_correct_control_is_accepted(target: Target) -> None:
    verdict = layered_oracle(target, correct_control(target))
    assert verdict.accepted is True, verdict.reason
    assert verdict.reason == "passed all layers"


def test_control_is_not_in_the_attack_registry() -> None:
    """correct_control is a control, never an attack we expect to be rejected."""
    assert "correct_control" not in ATTACKS
    assert "correct" not in ATTACKS


# ---------------------------------------------------------------------------
# The runnable suite returns 0 (all attacks caught) end-to-end.
# ---------------------------------------------------------------------------
def test_attack_suite_main_exits_zero() -> None:
    from bench.attack_suite import main

    assert main() == 0
