"""bench.attack_suite -- runnable red-team scorecard (BUILD_PLAN 2.5).

Runs the attack library (tripwire.attacks) against one or more Targets through BOTH
the naive oracle and the layered oracle, and prints a readable scorecard plus the
headline: the layered oracle catches ALL known attack classes (ships 0 hacks) while
the naive oracle is fooled by at least one.

Targets exercised:
  * a self-contained NUMERIC target  (tolerance comparison; owned here)
  * a self-contained STRUCTURAL target (exact comparison; owned here)
  * tripwire.targets.sum_reduction.make_target, IF importable -- tried behind a
    try/except so a missing/partial sibling module (another agent owns it) can
    never break this suite (CLAUDE.md parallel-work rule).

Exit code: 0 iff every attack was CAUGHT by the layered oracle on every target. If
any attack SURVIVES, the suite prints a loud finding and exits non-zero -- that
surviving attack is a finding for the core owner (a new layer / withheld
distribution), per HARD RULE 1: red-team proposes, core owner disposes. This suite
never edits the core.

Run:  .venv/bin/python -m bench.attack_suite
"""
from __future__ import annotations

import sys

from tripwire.attacks.library import ATTACKS, make_numeric_target, make_structural_target
from tripwire.attacks.runner import AttackRecord, run_attacks
from tripwire.target import Target

# The attack taxonomy, mirroring the "running ledger" in docs/threat-model.md. This
# is the ledger the red-team extends; each row maps an attack to its threat class and
# the layer expected to catch it (defense-in-depth: an earlier layer catching it is a
# strictly-better fail-fast, so this is the *latest* layer that must catch it).
LEDGER = {
    "memorize": ("memorize / special-case canonical inputs", "L3 withheld differential"),
    "constant": ("constant-return 'instant' (red-flag speedup)", "L1 / L3 withheld"),
    "skip_work": ("skip the work the eval doesn't check", "L2 property / L3 withheld"),
}


def _yn(b: bool) -> str:
    return "yes" if b else "no "


def _print_target_scorecard(target: Target, records: list[AttackRecord]) -> None:
    print(f"\n=== target: {target.name}  (kind={target.kind}) ===")
    print(
        f"  {'attack':<11}{'naive_bit':<11}{'naive_tol':<11}"
        f"{'layered':<10}{'status':<10}reason"
    )
    print(f"  {'-' * 72}")
    for r in records:
        status = "CAUGHT" if r.caught else "SURVIVED!"
        print(
            f"  {r.attack:<11}{_yn(r.naive_bitwise_accepted):<11}"
            f"{_yn(r.naive_tolerance_accepted):<11}{_yn(r.layered_accepted):<10}"
            f"{status:<10}{r.layered_reason}"
        )


def _print_ledger() -> None:
    print("\n--- attack-class ledger (mirrors docs/threat-model.md) ---")
    print(f"  {'attack':<11}{'threat-model class':<48}{'defended by'}")
    print(f"  {'-' * 90}")
    for name, (desc, defense) in LEDGER.items():
        print(f"  {name:<11}{desc:<48}{defense}")


def build_targets() -> list[Target]:
    """The targets the suite attacks. Self-contained ones first (never fail); the
    sibling sum_reduction target is appended only if it imports cleanly."""
    targets: list[Target] = [make_numeric_target(), make_structural_target()]
    try:  # opportunistic: another agent owns this file; never depend on it.
        from tripwire.targets.sum_reduction import make_target as _make_sum

        targets.append(_make_sum())
    except Exception as e:  # noqa: BLE001 -- any import/build failure is non-fatal here
        print(f"(note: tripwire.targets.sum_reduction unavailable, skipping: {e})")
    return targets


def main() -> int:
    print("Tripwire RED-TEAM attack suite (BUILD_PLAN 2.5)")
    print(f"attacks under test: {', '.join(ATTACKS)}")
    _print_ledger()

    n_attacks_total = 0
    n_caught_total = 0
    n_shipped_by_naive = 0
    survivors: list[tuple[str, str]] = []  # (target, attack)

    for target in build_targets():
        records = run_attacks(target)
        _print_target_scorecard(target, records)
        for r in records:
            n_attacks_total += 1
            if r.caught:
                n_caught_total += 1
            else:
                survivors.append((target.name, r.attack))
            if r.shipped_by_naive:
                n_shipped_by_naive += 1

    print("\n" + "=" * 74)
    print(
        f"SUMMARY: layered caught {n_caught_total}/{n_attacks_total} attacks; "
        f"naive shipped {n_shipped_by_naive}"
    )
    if survivors:
        print("\n!!! SURVIVING ATTACKS (findings for the core owner) !!!")
        for tname, aname in survivors:
            print(f"  - {aname} survived on target {tname}")
        print("File these as new oracle layers / withheld distributions (HARD RULE 1).")
        return 1

    print("layered oracle caught ALL attacks (0 hacks shipped). The moat holds.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
