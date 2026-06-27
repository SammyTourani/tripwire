"""tripwire.oracle -- the layered, adversarial-by-design correctness oracle.

THE CROWN JEWEL (CLAUDE.md §4). Everything else is plumbing around this. The
oracle assumes every candidate is trying to cheat it (threat-model.md) and is
right on BOTH failure axes:

  * it does NOT discard correct floating-point speedups (false negatives), and
  * it does NOT ship memorization / skip-the-work reward-hacks (false positives).

Layer order is FIXED (HARD RULE 3 / ADR-002); do not collapse the stack:

  L1  canonical correctness   -- exact for `structural`, tolerance for `numeric`
  L2  metamorphic / property  -- invariants the real computation must satisfy
  L3  differential on WITHHELD + adversarial inputs the candidate never saw (the moat)
  L4  isolated speedup measurement

Any correctness layer failing -> reject, no speedup reported. Speed is only
measured after L1-L3 pass.

This module is duck-typed on the Target contract (Interface A, frozen in task
1.3): it reads `.kind`, `.reference`, `.canonical_args`, `.withheld_args`, and
`.properties`. It imports Target only for type annotations -- target.py has no
dependency on oracle.py, so there is no import cycle. There is NO
evolutionary-search / population / archive code here (HARD RULE 1).
"""
from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from tripwire.measure import close_equal, exact_equal, speedup
from tripwire.target import Target

# Hardening: how many FRESH adversarial input-sets to draw from a target's
# withheld_factory (if present) on each evaluation. Each draw uses a different
# random seed, so L3 is a moving target -- a candidate cannot overfit to it, and an
# OpenEvolve loop cannot select for passing one fixed sample (audit finding C2/C3).
_GENERATIVE_DRAWS = 4


@dataclass
class Verdict:
    """The oracle's decision. `speedup` is NaN unless every correctness layer
    passed (ADR-006: a rejected candidate is never credited with speed)."""

    accepted: bool
    reason: str
    speedup: float = float("nan")


def _fresh_args(args):
    """Return a deep copy of an arg-tuple so a candidate that MUTATES its input in
    place (e.g. `arr[0] = nan`) cannot corrupt the reference's view, the shared
    Target state, or the scoring of any later candidate (audit finding H1).
    numpy arrays are copied via copy.deepcopy (which calls ndarray.__deepcopy__)."""
    return copy.deepcopy(tuple(args))


def _generative_withheld(t: Target) -> list:
    """Draw fresh adversarial inputs from the target's withheld_factory, if it has
    one, using several distinct random seeds. Empty if the target defines no
    factory (then L3 relies on the fixed `withheld_args` alone, as before)."""
    factory = getattr(t, "withheld_factory", None)
    if factory is None:
        return []
    drawn: list = []
    # Seeds are nondeterministic across evaluations on purpose (entropy from the
    # OS), so the candidate/loop never sees the same withheld inputs twice.
    seeds = np.random.SeedSequence().spawn(_GENERATIVE_DRAWS)
    for s in seeds:
        rng = np.random.default_rng(s)
        try:
            drawn.extend(factory(rng))
        except Exception:
            # A misbehaving factory must never crash the oracle; just skip its draw.
            continue
    return drawn


# ---------------------------------------------------------------------------
# Oracles
# ---------------------------------------------------------------------------
def naive_oracle(t: Target, cand: Callable, mode: str) -> Verdict:
    """Output-match on CANONICAL inputs only. mode = 'bitwise' | 'tolerance'.
    This is what current AI optimizers do -- and why they ship hacks / discard
    real speedups. Kept here as the baseline the layered oracle is measured against."""
    cmp = exact_equal if mode == "bitwise" else close_equal
    for args in t.canonical_args:
        try:
            # reference and candidate each get an independent copy (H1): a candidate
            # that mutates its input cannot corrupt the reference's computation.
            expected = t.reference(*_fresh_args(args))
            got = cand(*_fresh_args(args))
            if not cmp(expected, got):
                return Verdict(False, f"canonical mismatch ({mode})")
        except Exception as e:
            return Verdict(False, f"raised {type(e).__name__}")
    return Verdict(True, "passed canonical", speedup(t.reference, cand, t.canonical_args))


def layered_oracle(t: Target, cand: Callable, *, output_fn: Callable | None = None) -> Verdict:
    """The product. Exact-where-sound -> metamorphic -> differential on WITHHELD
    adversarial inputs -> isolated speedup. Assumes the candidate is trying to cheat.

    L3 checks the fixed `withheld_args` AND fresh adversarial inputs drawn from the
    target's `withheld_factory` (if any) under new random seeds each call, so the
    moat defends distribution-conditioned wrongness, not just exact memorization.
    Inputs are deep-copied per call so an input-mutating candidate cannot corrupt
    the reference or later candidates (H1).

    `output_fn`, if given, is `output_fn(args_tuple) -> output` and is used INSTEAD
    of calling `cand(*args)` directly. The hardened evaluator (Interface B) passes an
    output_fn that runs the candidate in an ISOLATED SUBPROCESS, so the candidate can
    never reach or monkeypatch this oracle (audit finding C1). It must raise to signal
    a candidate failure (the oracle treats that as a rejection, like a live raise).
    When None, the candidate is called in-process (the original trusted path)."""
    cmp = exact_equal if t.kind == "structural" else close_equal
    call = output_fn if output_fn is not None else (lambda args: cand(*_fresh_args(args)))
    # L1 -- canonical correctness
    for args in t.canonical_args:
        try:
            expected = t.reference(*_fresh_args(args))
            got = call(args)
            if not cmp(expected, got):
                return Verdict(False, "L1 canonical mismatch")
        except Exception as e:
            return Verdict(False, f"L1 raised {type(e).__name__}")
    # L2 -- metamorphic / property checks
    for pname, pfn in t.properties:
        for args in t.canonical_args + t.withheld_args:
            try:
                if not pfn(args, call(args)):
                    return Verdict(False, f"L2 property '{pname}' violated")
            except Exception as e:
                return Verdict(False, f"L2 raised {type(e).__name__}")
    # L3 -- differential testing on withheld + adversarial inputs (the moat).
    # Fixed adversarial edges PLUS fresh generative draws (the candidate never saw
    # either; the generative draws also vary every evaluation).
    for args in t.withheld_args + _generative_withheld(t):
        try:
            expected = t.reference(*_fresh_args(args))
            got = call(args)
            if not cmp(expected, got):
                return Verdict(False, "L3 withheld-input differential mismatch")
        except Exception as e:
            return Verdict(False, f"L3 raised {type(e).__name__}")
    # L4 -- isolated speedup across many shapes
    return Verdict(
        True, "passed all layers", speedup(t.reference, cand, t.canonical_args + t.withheld_args)
    )
