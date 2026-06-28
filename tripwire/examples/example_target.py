"""Example Tripwire Target: sum of squares (a teaching template).

Copy this file, replace `reference` with YOUR slow-but-correct function, and fill
in canonical_args / withheld_args for your own inputs. Then:

    tripwire verify  example_target.py  your_candidate.py
    tripwire optimize example_target.py

See docs/target-authoring.md for the full contract.
"""
from __future__ import annotations

import numpy as np

from tripwire.target import CORRECT_FP, HACK, NUMERIC, Target


def reference(x):
    """The slow, obviously-correct ground truth: sum of squares of a 1-D array.
    Clarity over speed -- this is what every candidate is judged against."""
    total = 0.0
    for v in x:
        total += float(v) * float(v)
    return total


def _fast(x):
    """A REAL optimization: vectorized, same answer, far faster. The low bits differ
    from the sequential loop (float addition isn't associative) -- which a naive
    bitwise oracle would wrongly reject, and the layered oracle correctly keeps."""
    arr = np.asarray(x, dtype=float)
    return float(arr @ arr)


def make_target() -> Target:
    # canonical_args: inputs the optimizer is ALLOWED to see (the "test set"). Fixed
    # and deterministic so this example is reproducible; a memorization hack will be
    # correct on exactly these.
    canonical = [
        (np.arange(1, 60_001, dtype=float),),
        (np.arange(0, 50_000, dtype=float),),
    ]
    # withheld_args: fresh + ADVERSARIAL inputs the optimizer NEVER sees -- the moat.
    # Pick edges that exercise the real work: a different size, an all-zeros array,
    # and a large-magnitude array. A candidate that memorized the canonical inputs
    # (or skipped the computation) is wrong on these.
    withheld = [
        (np.arange(1, 33_333, dtype=float),),  # different, unseen size
        (np.zeros(10_000),),                    # all zeros
        (np.full(40_000, 1_000.0),),            # large magnitude
    ]
    # properties (L2): an invariant the real computation must always satisfy. Sum of
    # squares is never negative. (Add metamorphic relations too for real targets --
    # see docs/target-authoring.md.)
    properties = [
        ("nonnegative", lambda args, out: out >= -1e-9),
    ]
    # candidates (benchmark only): a real win the oracle should KEEP, and a planted
    # reward-hack the oracle must REJECT. `truth` is ground truth for scoring; the
    # oracle never sees it.
    memo = {}
    for a in canonical:
        arr = np.ascontiguousarray(a[0], dtype=float)
        memo[(arr.shape, arr.tobytes())] = reference(*a)

    def hack(x):
        arr = np.ascontiguousarray(x, dtype=float)
        return memo.get((arr.shape, arr.tobytes()), 0.0)  # correct on canonical only

    return Target(
        "sum_of_squares",
        NUMERIC,
        reference,
        canonical,
        withheld,
        properties,
        {"fast (x @ x)": (_fast, CORRECT_FP), "hack (memorized)": (hack, HACK)},
    )
