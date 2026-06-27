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

from tripwire.isolation import DEFAULT_TIMEOUT, evaluate_isolated
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
    """Import the evolved program IN-PROCESS and return its entrypoint, or None.
    Used only by the isolate=False trusted path; the hardened default never imports
    the candidate in this process at all."""
    spec = importlib.util.spec_from_file_location("candidate", program_path)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, CANONICAL_ENTRYPOINT, None) or getattr(mod, target.name, None)


def make_openevolve_evaluator(
    target: Target,
    *,
    isolate: bool = True,
    timeout: float = DEFAULT_TIMEOUT,
    target_factory_ref: tuple[str, str] | None = None,
) -> Callable[[str], dict]:
    """Build the OpenEvolve evaluator for `target`.

    Returns a callable `evaluate(program_path) -> dict` with keys:
      combined_score : the metric OpenEvolve maximizes. == oracle-verified speedup
                       on success, 0.0 on ANY correctness failure (ADR-006).
      correct        : 1.0 iff every oracle layer (L1-L3) passed, else 0.0.
      speedup        : measured speedup (== combined_score on success), 0.0 otherwise.
      reason         : human-readable verdict / failing layer.

    SECURITY (isolate=True, the default): the ENTIRE evaluation -- loading the
    candidate, running the layered oracle, and measuring speedup -- happens in a
    fresh 'spawn' subprocess. The subprocess returns ONLY primitives
    (accepted, reason, speedup); the parent deserializes nothing the candidate
    controls. Therefore the candidate never executes in the evaluator's process and
    cannot (a) monkeypatch the oracle, (b) run code in the parent via a malicious
    pickle `__reduce__`, or (c) corrupt inputs/state for later candidates. Inside the
    child, the oracle's comparators/speedup are captured as default args before the
    candidate loads, so even in-child monkeypatching cannot fake a verdict.

    To run in the subprocess, the child must REBUILD the Target from a zero-arg
    factory named by `target_factory_ref=('module', 'attr')`. If not provided, it is
    inferred from `target` when possible (e.g. tripwire.targets.<name>.make_target);
    pass it explicitly for custom targets.

    isolate=False runs the candidate in-process (the original trusted path) -- use
    only for trusted code / tests, never for untrusted evolved programs.

    The returned callable is exposed both as `evaluate` (OpenEvolve naming) and via
    the `.evaluator` attribute (CLAUDE.md Interface B wording).
    """
    entrypoints = [CANONICAL_ENTRYPOINT, target.name]
    factory_ref = target_factory_ref or _infer_factory_ref(target)

    def _evaluate_isolated(program_path: str) -> dict:
        if factory_ref is None:
            return _zero(
                "isolation requires target_factory_ref=('module','factory') for this target"
            )
        v = evaluate_isolated(program_path, factory_ref, entrypoints, timeout=timeout)
        if not v.accepted:
            return _zero(v.reason)
        sp = 0.0 if (math.isinf(v.speedup) or math.isnan(v.speedup)) else v.speedup
        return {"combined_score": sp, "correct": 1.0, "speedup": sp, "reason": v.reason}

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
    evaluate.evaluator = evaluate  # type: ignore[attr-defined]
    return evaluate


def _infer_factory_ref(target: Target) -> tuple[str, str] | None:
    """Best-effort: a target named 'foo' usually lives at tripwire.targets.foo with a
    `make_target` factory. Returns ('tripwire.targets.<base>', 'make_target') if that
    module imports and its make_target() reproduces a Target of the same name, else
    None (caller must then pass target_factory_ref explicitly)."""
    base = target.name.split(":")[0]  # e.g. 'numeric:dot' -> 'numeric'
    mod_name = f"tripwire.targets.{base}"
    try:
        mod = importlib.import_module(mod_name)
    except Exception:
        return None
    factory = getattr(mod, "make_target", None)
    if factory is None:
        return None
    try:
        if factory().name == target.name:
            return (mod_name, "make_target")
    except Exception:
        return None
    return None
