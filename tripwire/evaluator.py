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

from tripwire.isolation import DEFAULT_TIMEOUT, IsolatedCandidate
from tripwire.measure import speedup
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
    """Import the evolved program IN-PROCESS and return its entrypoint, or None if it
    cannot be loaded or exposes no entrypoint. Used only for the trusted/timing path;
    the security-critical correctness check runs in isolation (see make_..._evaluator).
    A program that raises at import time must NOT crash the evaluator."""
    spec = importlib.util.spec_from_file_location("candidate", program_path)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, CANONICAL_ENTRYPOINT, None) or getattr(mod, target.name, None)


def make_openevolve_evaluator(
    target: Target, *, isolate: bool = True, timeout: float = DEFAULT_TIMEOUT
) -> Callable[[str], dict]:
    """Build the OpenEvolve evaluator for `target`.

    Returns a callable `evaluate(program_path) -> dict` with keys:
      combined_score : the metric OpenEvolve maximizes. == oracle-verified speedup
                       on success, 0.0 on ANY correctness failure (ADR-006).
      correct        : 1.0 iff every oracle layer (L1-L3) passed, else 0.0.
      speedup        : measured speedup (== combined_score on success), 0.0 otherwise.
      reason         : human-readable verdict / failing layer.

    SECURITY (isolate=True, the default): the candidate is loaded and CALLED in a
    fresh subprocess (tripwire.isolation), and the layered oracle compares its
    outputs against the reference in THIS clean process. The candidate therefore
    never executes in the evaluator's interpreter during the correctness check, so it
    cannot monkeypatch the oracle's comparators to mark its own homework (audit C1),
    nor corrupt shared inputs (H1). Only AFTER correctness passes all layers is the
    candidate run in-process to MEASURE speedup -- by then it is already proven
    correct, so the worst a tampering candidate can do is inflate its own (already
    earned) speed number, never earn reward for wrong code.

    isolate=False runs the candidate in-process throughout (the original trusted
    path) -- use only for trusted code / tests, never for untrusted evolved programs.

    The returned callable is exposed both as `evaluate` (OpenEvolve naming) and via
    the `.evaluator` attribute (CLAUDE.md Interface B wording).
    """
    entrypoints = [CANONICAL_ENTRYPOINT, target.name]

    def _evaluate_isolated(program_path: str) -> dict:
        # Correctness is judged against the candidate's OUTPUTS, computed in a
        # subprocess the oracle is not reachable from.
        with IsolatedCandidate(program_path, entrypoints, timeout=timeout) as iso:
            if iso.load_error is not None:
                return _zero(iso.load_error)
            verdict = layered_oracle(target, None, output_fn=iso.output_fn)
        if not verdict.accepted:
            return _zero(verdict.reason)
        # Correctness passed in isolation. Measure speedup with an in-process load
        # (safe now: a wrong candidate already got 0.0; this only times a proven one).
        try:
            cand = _load_candidate(program_path, target)
        except Exception as e:
            return _zero(f"load failed: {type(e).__name__}")
        if not callable(cand):
            return _zero("no entrypoint")
        sp = speedup(target.reference, cand, target.canonical_args + target.withheld_args)
        sp = 0.0 if math.isinf(sp) else sp
        return {"combined_score": sp, "correct": 1.0, "speedup": sp, "reason": verdict.reason}

    def _evaluate_inprocess(program_path: str) -> dict:
        try:
            cand = _load_candidate(program_path, target)
        except Exception as e:
            return _zero(f"load failed: {type(e).__name__}")
        if cand is None:
            return _zero("no entrypoint")
        if not callable(cand):
            return _zero("entrypoint not callable")
        verdict = layered_oracle(target, cand)
        if not verdict.accepted:
            return _zero(verdict.reason)
        sp = 0.0 if math.isinf(verdict.speedup) else verdict.speedup
        return {"combined_score": sp, "correct": 1.0, "speedup": sp, "reason": verdict.reason}

    evaluate = _evaluate_isolated if isolate else _evaluate_inprocess
    # Expose under both names (see docstring).
    evaluate.evaluator = evaluate  # type: ignore[attr-defined]
    return evaluate
