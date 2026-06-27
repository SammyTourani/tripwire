"""OpenEvolve evaluator file for target zero (BUILD_PLAN 1.5).

OpenEvolve discovers a top-level `evaluate(program_path) -> dict` in this file
(its canonical contract; see docs/openevolve-example-evaluator.py). We keep this
a thin, self-contained wrapper that builds the sum_reduction Target and delegates
to the FROZEN adapter in tripwire.evaluator (Interface B) -- so the live run uses
the exact same layered-oracle code path our tests cover.

We pass this as a FILE PATH (not a Python callable) on purpose: OpenEvolve's
callable-wrapper serializes a callable via inspect.getsource + __name__, which (a)
breaks on closures like make_openevolve_evaluator(target) and (b) collided with our
inner function also being named `evaluate` (causing infinite recursion). A file
with a plain top-level `evaluate` avoids both issues and matches real usage.
"""
from __future__ import annotations

from tripwire.evaluator import make_openevolve_evaluator
from tripwire.targets.sum_reduction import make_target

# Build the target + oracle-backed evaluator once at import time.
_TARGET = make_target()
_EVALUATE = make_openevolve_evaluator(_TARGET)


def evaluate(program_path: str) -> dict:
    """OpenEvolve entry point. Delegates to the frozen layered-oracle adapter:
    returns {combined_score, correct, speedup, reason}; a correctness-layer
    failure zeroes combined_score (ADR-006)."""
    return _EVALUATE(program_path)
