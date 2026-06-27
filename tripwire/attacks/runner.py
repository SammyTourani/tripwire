"""tripwire.attacks.runner -- push every attack through BOTH oracles and report.

`run_attacks(target)` is the heart of the continuous red-team: for each attack in
the registry it asks the naive oracle (bitwise AND tolerance) and the layered oracle
for a verdict, and records who shipped the hack and who caught it. An attack is
"caught" iff the LAYERED oracle rejected it (`layered_accepted is False`).

The whole point of the benchmark is the GAP between the two oracles: the naive
oracle (canonical-only) ships hacks; the layered oracle catches them all. If a row
ever shows `layered_accepted is True` for an attack, that attack SURVIVED -- a
finding to be filed against the core (a new layer / withheld distribution), per
HARD RULE 1 (red-team proposes, core owner disposes). This module only reports it.

No core edits, no network, deterministic given the target (HARD RULE / §7).
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from tripwire.attacks.library import ATTACKS
from tripwire.oracle import layered_oracle, naive_oracle
from tripwire.target import Target


@dataclass
class AttackRecord:
    """One row of the attack scorecard (the schema tests assert on).

    `caught` is the headline: True iff the LAYERED oracle rejected the attack.
    `survived` is its inverse -- True means a hack beat the layered oracle (a bug
    in the moat, a finding for the core owner).
    """

    attack: str
    naive_bitwise_accepted: bool
    naive_tolerance_accepted: bool
    layered_accepted: bool
    layered_reason: str

    @property
    def caught(self) -> bool:
        """A hack is caught iff the layered oracle rejected it."""
        return not self.layered_accepted

    @property
    def survived(self) -> bool:
        """A hack survived iff the layered oracle wrongly accepted it."""
        return self.layered_accepted

    @property
    def shipped_by_naive(self) -> bool:
        """The gap we measure: did EITHER naive mode ship this hack?"""
        return self.naive_bitwise_accepted or self.naive_tolerance_accepted


def _run_one(target: Target, name: str, factory: Callable[[Target], Callable]) -> AttackRecord:
    cand = factory(target)
    nb = naive_oracle(target, cand, "bitwise")
    nt = naive_oracle(target, cand, "tolerance")
    layered = layered_oracle(target, cand)
    return AttackRecord(
        attack=name,
        naive_bitwise_accepted=nb.accepted,
        naive_tolerance_accepted=nt.accepted,
        layered_accepted=layered.accepted,
        layered_reason=layered.reason,
    )


def run_attacks(target: Target) -> list[AttackRecord]:
    """Run every registered attack against `target` through both oracles.

    Returns one `AttackRecord` per entry in `ATTACKS`, in registry order.
    """
    return [_run_one(target, name, factory) for name, factory in ATTACKS.items()]
