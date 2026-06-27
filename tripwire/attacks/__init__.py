"""tripwire.attacks -- the RED-TEAM (BUILD_PLAN 2.5): candidates that TRY to beat
the oracle.

The oracle is only as strong as the attacks it survives (threat-model.md). This
package is the *automated, continuous* adversary: a library of attack factories
(one per threat-model attack class) plus a runner that pushes every attack through
BOTH the naive oracle and the layered oracle and reports which the layered oracle
CATCHES vs (if any) lets SURVIVE.

Red-team proposes, the core owner disposes (HARD RULE 1 / BUILD_PLAN 2.5): nothing
in here edits the frozen core (`oracle.py`, `measure.py`, `target.py`). A surviving
attack is a finding to be filed against the core as a new layer or withheld-input
distribution -- never a silent patch from this side.

Public surface:
  * ATTACKS                  -- name -> attack-factory registry (the threat taxonomy)
  * run_attacks(target)      -- run every attack through both oracles -> [AttackRecord]
  * AttackRecord             -- per-attack result row (the scorecard schema)
  * memorizer / constant_return / skip_work -- the individual factories
  * make_structural_target / make_numeric_target -- self-contained attack targets
"""
from __future__ import annotations

from tripwire.attacks.library import (
    ATTACKS,
    constant_return,
    correct_control,
    make_numeric_target,
    make_structural_target,
    memorizer,
    skip_work,
)
from tripwire.attacks.runner import AttackRecord, run_attacks

__all__ = [
    "ATTACKS",
    "AttackRecord",
    "constant_return",
    "correct_control",
    "make_numeric_target",
    "make_structural_target",
    "memorizer",
    "run_attacks",
    "skip_work",
]
