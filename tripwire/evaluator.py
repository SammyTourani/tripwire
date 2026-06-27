"""tripwire.evaluator -- Interface B: the FROZEN OpenEvolve evaluator contract.

The second of the two load-bearing contracts (CLAUDE.md §4). This is the drop-in
that makes an OpenEvolve run trustworthy: it wraps the layered oracle so the
evolver is scored on REAL, oracle-verified speedup and can never be rewarded for
fast-but-wrong code.

THE CENTRAL INVARIANT (ADR-006): any correctness-layer failure ZEROES
`combined_score`. A reward-hack must never earn reward, so the evolver gets zero
gradient toward cheating. This is the property that makes the loop trustworthy.

Matches the real OpenEvolve evaluator API (verified against the live repo per
ADR-007 -- algorithmicsuperintelligence/openevolve v0.2.27, the confirmed-latest
release / PyPI version; see docs/openevolve-example-evaluator.py and
docs/ADD_THE_PAPER.md for provenance):
  * entrypoint signature `evaluate(program_path) -> dict`,
  * loads the candidate via importlib.util.spec_from_file_location,
  * returns metrics including `combined_score` (the metric OpenEvolve optimizes),
  * a program that fails to load / has no entrypoint / fails the oracle scores 0.0.

OpenEvolve accepts a plain `dict` return (it auto-wraps via
EvaluationResult.from_dict), so we return a plain dict and keep this module
dependency-light (no `openevolve` import, no network) -- the artifact side-channel
(EvaluationResult.artifacts) can be added later WITHOUT changing this frozen
contract, since it is purely additive.

There is NO evolutionary-loop / population / archive code here (HARD RULE 1);
OpenEvolve owns those (ADR-001).
"""
from __future__ import annotations

import importlib.util
import math
from collections.abc import Callable

from tripwire.oracle import layered_oracle
from tripwire.target import Target

# The candidate program must expose its optimized implementation under one of
# these names. `solve` is the canonical entrypoint; we fall back to a function
# named after the target (matches the proven seed adapter).
CANONICAL_ENTRYPOINT = "solve"


def _zero(reason: str) -> dict:
    """A rejection result. combined_score is 0.0 and speedup is 0.0 -- a rejected
    candidate is NEVER credited with speed (ADR-006)."""
    return {"combined_score": 0.0, "correct": 0.0, "speedup": 0.0, "reason": reason}


def _load_candidate(program_path: str, target: Target) -> Callable | None:
    """Import the evolved program and return its entrypoint, or None if it cannot
    be loaded or exposes no entrypoint. A program that raises at import time
    (syntax error, bad top-level code) must NOT crash the evaluator -- it scores
    0.0 like any other failure (matches the real OpenEvolve example)."""
    spec = importlib.util.spec_from_file_location("candidate", program_path)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, CANONICAL_ENTRYPOINT, None) or getattr(mod, target.name, None)


def make_openevolve_evaluator(target: Target) -> Callable[[str], dict]:
    """Build the OpenEvolve evaluator for `target`.

    Returns a callable `evaluate(program_path) -> dict` with keys:
      combined_score : the metric OpenEvolve maximizes. == oracle-verified speedup
                       on success, 0.0 on ANY correctness failure (ADR-006).
      correct        : 1.0 iff every oracle layer (L1-L3) passed, else 0.0.
      speedup        : measured speedup (== combined_score on success), 0.0 otherwise.
      reason         : human-readable verdict / failing layer.

    The returned callable is exposed both as `evaluate` (the OpenEvolve naming
    convention) and via the `.evaluator` attribute (CLAUDE.md Interface B wording
    and the proven seed). Both refer to the same function.
    """

    def evaluate(program_path: str) -> dict:
        # --- load the evolved program (failure to load => 0.0, never a crash) ---
        try:
            cand = _load_candidate(program_path, target)
        except Exception as e:
            return _zero(f"load failed: {type(e).__name__}")
        if cand is None:
            return _zero("no entrypoint")
        if not callable(cand):
            return _zero("entrypoint not callable")

        # --- run the layered oracle: correctness BEFORE speed (ADR-006) ---
        verdict = layered_oracle(target, cand)
        if not verdict.accepted:
            # reward hacking / wrong -> no reward, period. The failing layer is
            # surfaced in `reason` so the evolver's error side-channel can learn.
            return _zero(verdict.reason)

        # --- correctness passed all layers: credit the verified speedup ---
        # A near-infinite "speedup" is a red flag, not a winner (HARD RULE 6). The
        # oracle/measure layer treats an ~instant candidate as inf; we clamp inf to
        # 0.0 so a memorization mirage that somehow reaches here earns no reward
        # rather than an unbounded one.
        sp = 0.0 if math.isinf(verdict.speedup) else verdict.speedup
        return {"combined_score": sp, "correct": 1.0, "speedup": sp, "reason": verdict.reason}

    # Expose under both names (see docstring). `evaluator` is the Interface-B /
    # seed name; `evaluate` is the OpenEvolve convention.
    evaluate.evaluator = evaluate  # type: ignore[attr-defined]
    return evaluate
