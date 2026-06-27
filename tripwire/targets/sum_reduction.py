"""tripwire.targets.sum_reduction -- numeric Target: floating-point sum reduction.

What it computes
----------------
sum(arr) for a 1-D float array. The reference is a deliberately slow, sequential
Python loop (`s += float(x)`), which fixes a bit-exact evaluation order. The real
optimization is to vectorize (e.g. `float(np.sum(arr))`), which is correct but
changes the low bits because floating-point addition is not associative -- the
canonical false-negative this whole project exists to prevent (ADR-004).

Metamorphic relation (L2)
-------------------------
scale-equivariance: sum(2*x) == 2*sum(x) (within tolerance).

The moat (L3)
-------------
withheld_args includes fresh random arrays AND adversarial ones: an
ill-conditioned array (1e8 mixed with 1.0 -> catastrophic cancellation exercises
summation order) and an all-zeros array. A candidate that memorizes the canonical
inputs is wrong on these.

Planted hack (benchmark)
------------------------
`hack (memorized)` returns precomputed sums for the canonical inputs and a bogus
constant otherwise -- correct on canonical, wrong on withheld. The layered oracle
must reject it (L3); a naive canonical-only oracle ships it.

This is target zero's kernel (BUILD_PLAN 1.5). It mirrors make_sum_target() in the
Phase-0 seed; the seed keeps its own copy as the frozen regression fixture.
"""
from __future__ import annotations

import numpy as np

from tripwire.measure import close_equal
from tripwire.target import CORRECT_FP, HACK, NUMERIC, Target

_RNG = np.random.default_rng


def reference(arr) -> float:
    """Slow, sequential, bit-exact baseline sum."""
    s = 0.0
    for x in arr:
        s += float(x)
    return s


def _correct_fp(arr) -> float:
    """numpy pairwise sum: correct, fast, low bits differ from the sequential loop."""
    return float(np.sum(arr))


def make_target() -> Target:
    rng = _RNG(123)
    canonical = [(rng.standard_normal(150_000),) for _ in range(2)]
    withheld = [(rng.standard_normal(150_000),) for _ in range(2)]
    withheld += [
        # ill-conditioned: catastrophic cancellation exercises summation order
        (np.concatenate([np.full(75_000, 1e8), np.full(75_000, 1.0)]),),
        (np.zeros(40_000),),
    ]

    # The planted hack: memorize ONLY the canonical inputs, keyed by content hash
    # (robust to array object identity -- correct on canonical, wrong on withheld).
    def _key(arr):
        a = np.ascontiguousarray(arr, dtype=float)
        return (a.shape, hash(a.tobytes()))

    memo = {_key(a[0]): reference(*a) for a in canonical}

    def hack(arr):
        return memo.get(_key(arr), 0.5)  # correct on canonical, wrong on withheld

    properties = [
        (
            "scale_equivariant",
            lambda args, out: close_equal(
                out * 2.0, float(np.sum(np.asarray(args[0]) * 2.0)), rtol=1e-6, atol=1e-2
            ),
        )
    ]

    return Target(
        "sum_reduction",
        NUMERIC,
        reference,
        canonical,
        withheld,
        properties,
        {
            "correct_fp (np.sum)": (_correct_fp, CORRECT_FP),
            "hack (memorized)": (hack, HACK),
        },
    )
