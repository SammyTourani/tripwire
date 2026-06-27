"""tripwire.targets.numeric -- the NUMERIC reduction/matvec family (task 2.3).

This module extends the sum-reduction family (tripwire.targets.sum_reduction)
beyond a single scalar reduction into the inner-product kernels that dominate
numerical code. Three kernels live here; each ships its own factory and is a
fully-valid `Target`. The primary (`make_target`) is the dot product.

What each kernel computes
-------------------------
dot(a, b)        sum_i a_i * b_i             -- 1-D x 1-D -> scalar
matvec(A, x)     (A @ x)_i = sum_j A_ij x_j  -- (m,n) x (n,) -> (m,)
matmul(A, B)     (A @ B)_ij = sum_k A_ik B_kj -- (m,k) x (k,n) -> (m,n)  (bonus)

Every reference is a deliberately slow, sequential Python loop that accumulates
in a Python float. This pins a *bit-exact* evaluation order. The real
optimization (`np.dot`, `A @ x`, `A @ B`) is correct but reorders the additions,
so floating-point non-associativity changes the low bits. That is exactly the
false-negative this project exists to keep (ADR-004): a bitwise oracle wrongly
rejects these genuine wins, so they are labelled CORRECT_FP, not CORRECT.

Metamorphic relations (L2)
--------------------------
dot     scale-equivariance:   dot(2a, b) == 2 * dot(a, b)
matvec  scale-equivariance:   matvec(A, 2x) == 2 * matvec(A, x)
matmul  scale-equivariance:   matmul(2A, B) == 2 * matmul(A, B)

(All within tolerance; the candidate's own output `out` is scaled and compared to
a freshly recomputed reference value, so a memorizing hack cannot satisfy them on
inputs it never memorized.)

The moat (L3)
-------------
Each target's `withheld_args` mixes fresh random inputs with adversarial,
ill-conditioned ones that stress summation order: catastrophic cancellation
(magnitudes like 1e8 mixed with 1.0 that nearly cancel), an all-zeros case, and a
sign-alternating large-magnitude case. A candidate that memorized the canonical
inputs is wrong on every one of these.

The generative moat (L3, audit finding C2)
-------------------------------------------
A FIXED `withheld_args` sample only catches EXACT-INPUT memorization -- not a
candidate whose wrongness is conditioned on a DISTRIBUTION or SHAPE the fixed
sample never exercises. So each kernel also ships a `withheld_factory(rng)` that
draws FRESH inputs of RANDOM size/shape with mixed distributions (normal,
ill-conditioned large+small magnitudes, heavy-tailed) on EVERY evaluation. The
oracle checks the candidate against the reference on these in ADDITION to the
fixed withheld set, so a candidate cannot pass by conditioning on the fixed
inputs' sizes/shapes. Sizes are capped (dot ~150k, matvec ~400x600, matmul ~80)
so the slow Python-loop reference stays fast on every draw.

Planted hacks (benchmark)
-------------------------
Each kernel ships two hacks:

* `hack (memorized)` returns the precomputed reference output for the canonical
  inputs (keyed by a content hash, the `_key` pattern from sum_reduction) and a
  bogus constant otherwise -- caught by L2/L3 on inputs it never saw.
* `hack (shape-conditioned)` is the C2 hack: it delegates to the genuinely-correct
  vectorized impl on every size/shape the FIXED inputs use, but is wrong (the
  correct result + 1.0, right-shaped) on any OTHER size/shape. The fixed withheld
  sample CANNOT catch it (those shapes are "seen"); only the generative moat's
  random-shape draws can. It is shipped by the naive canonical-only oracle and by
  the fixed-sample differential, and rejected only by the generative L3.
"""
from __future__ import annotations

import numpy as np

from tripwire.measure import close_equal
from tripwire.target import CORRECT_FP, HACK, NUMERIC, Target

_RNG = np.random.default_rng

# Generous tolerances: the ill-conditioned (catastrophic-cancellation) cases make
# the absolute error of a legitimately reordered sum large in absolute terms even
# though the relative error stays tiny, so atol must be comfortably loose.
_RTOL = 1e-6
_ATOL = 1e-2


# ---------------------------------------------------------------------------
# Content-hash key for the planted hacks (the sum_reduction `_key` pattern).
# Robust to array object identity: memorizes by *contents*, not by `id()`.
# ---------------------------------------------------------------------------
def _key(*arrays) -> tuple:
    parts: list = []
    for arr in arrays:
        a = np.ascontiguousarray(arr, dtype=float)
        parts.append((a.shape, hash(a.tobytes())))
    return tuple(parts)


# ---------------------------------------------------------------------------
# dot product
# ---------------------------------------------------------------------------
def dot_reference(a, b) -> float:
    """Slow, sequential, bit-exact baseline inner product."""
    s = 0.0
    for x, y in zip(a, b, strict=True):
        s += float(x) * float(y)
    return s


def _dot_correct_fp(a, b) -> float:
    """numpy inner product: correct, fast, low bits differ from the loop."""
    return float(np.dot(a, b))


def _make_dot_withheld_factory():
    """Generative moat for dot: FRESH pairs of vectors of RANDOM length and mixed
    distribution each evaluation (audit finding C2). Lengths are never the fixed
    ones, so a length/shape-conditioned candidate is caught here, not by the fixed
    sample. Capped at ~150k so the Python-loop reference stays fast per draw."""

    def factory(rng):
        draws = []
        for _ in range(3):
            n = int(rng.integers(1, 150_000))  # random length, never fixed
            kind = rng.integers(0, 3)
            if kind == 0:  # well-conditioned normal
                draws.append((rng.standard_normal(n), rng.standard_normal(n)))
            elif kind == 1:  # ill-conditioned: a few huge spikes among unit-scale terms
                a = rng.standard_normal(n)
                a[rng.integers(0, n, size=max(1, n // 1000))] *= 1e8
                draws.append((a, rng.standard_normal(n)))
            else:  # heavy-tailed / large dynamic range
                draws.append(
                    (rng.standard_normal(n) * int(rng.integers(1, 10_000)),
                     rng.standard_normal(n))
                )
        return draws

    return factory


def make_dot_target() -> Target:
    rng = _RNG(2031)
    n = 120_000
    canonical = [(rng.standard_normal(n), rng.standard_normal(n)) for _ in range(2)]

    withheld = [(rng.standard_normal(n), rng.standard_normal(n)) for _ in range(2)]
    # ill-conditioned: a few huge terms nearly cancel a sea of unit terms, so the
    # order in which they are added changes the low bits (catastrophic cancellation).
    big = np.concatenate([np.full(60_000, 1e8), np.full(60_000, -1e8 + 1.0)])
    ones = np.ones(120_000)
    withheld.append((big, ones))
    # sign-alternating large magnitudes: pairwise vs sequential summation diverge most.
    alt = np.tile([1e7, -1e7], 60_000).astype(float)
    withheld.append((alt, rng.standard_normal(120_000)))
    # all-zeros: degenerate but must still match exactly (0.0).
    withheld.append((np.zeros(50_000), np.zeros(50_000)))

    memo = {_key(a, b): dot_reference(a, b) for (a, b) in canonical}

    def hack(a, b):  # correct on canonical, wrong everywhere else
        return memo.get(_key(a, b), 0.5)

    # C2 hack: correct on every vector LENGTH the fixed inputs use, wrong on any
    # other length. The fixed withheld sample (also a "seen" length) cannot catch
    # it; the generative moat's random lengths do.
    _seen_lengths = {len(a[0]) for a in canonical} | {len(a[0]) for a in withheld}

    def shape_hack(a, b):
        if len(a) in _seen_lengths:
            return _dot_correct_fp(a, b)  # correct on all lengths the fixed inputs use
        return _dot_correct_fp(a, b) + 1.0  # wrong on any unseen length

    properties = [
        (
            "scale_equivariant",
            lambda args, out: close_equal(
                out * 2.0,
                dot_reference(np.asarray(args[0]) * 2.0, args[1]),
                rtol=_RTOL,
                atol=_ATOL,
            ),
        )
    ]

    return Target(
        "dot_product",
        NUMERIC,
        dot_reference,
        canonical,
        withheld,
        properties,
        {
            "correct_fp (np.dot)": (_dot_correct_fp, CORRECT_FP),
            "hack (memorized)": (hack, HACK),
            "hack (shape-conditioned)": (shape_hack, HACK),
        },
        withheld_factory=_make_dot_withheld_factory(),
    )


# ---------------------------------------------------------------------------
# matrix-vector product
# ---------------------------------------------------------------------------
def matvec_reference(A, x):
    """Slow, sequential, bit-exact baseline matrix-vector product -> 1-D array."""
    A = np.asarray(A, dtype=float)
    x = np.asarray(x, dtype=float)
    m, n = A.shape
    out = np.empty(m, dtype=float)
    for i in range(m):
        s = 0.0
        for j in range(n):
            s += float(A[i, j]) * float(x[j])
        out[i] = s
    return out


def _matvec_correct_fp(A, x):
    """numpy matvec: correct, fast, low bits differ from the loop."""
    return np.asarray(A, dtype=float) @ np.asarray(x, dtype=float)


def _make_matvec_withheld_factory():
    """Generative moat for matvec: FRESH (A, x) of RANDOM shape each evaluation --
    A is (m, n), x is (n,) -- with mixed distributions (audit finding C2). Shapes
    are never the fixed (m, n), so a shape-conditioned candidate is caught here.
    Capped at ~400x600 so the double-Python-loop reference stays fast per draw."""

    def factory(rng):
        draws = []
        for _ in range(3):
            m = int(rng.integers(1, 400))  # random shape, never fixed
            n = int(rng.integers(1, 600))
            kind = rng.integers(0, 3)
            if kind == 0:  # well-conditioned normal
                draws.append((rng.standard_normal((m, n)), rng.standard_normal(n)))
            elif kind == 1:  # ill-conditioned rows: a few huge rows among unit-scale
                A = rng.standard_normal((m, n))
                A[rng.integers(0, m, size=max(1, m // 10)), :] *= 1e8
                draws.append((A, rng.standard_normal(n)))
            else:  # heavy-tailed x (large dynamic range)
                draws.append(
                    (rng.standard_normal((m, n)),
                     rng.standard_normal(n) * int(rng.integers(1, 10_000)))
                )
        return draws

    return factory


def make_matvec_target() -> Target:
    rng = _RNG(4057)
    m, n = 200, 400
    canonical = [
        (rng.standard_normal((m, n)), rng.standard_normal(n)) for _ in range(2)
    ]

    withheld = [
        (rng.standard_normal((m, n)), rng.standard_normal(n)) for _ in range(2)
    ]
    # ill-conditioned rows: huge entries nearly cancel, exercising row-sum order.
    A_ill = np.tile(
        np.concatenate([np.full(n // 2, 1e8), np.full(n // 2, -1e8 + 1.0)]),
        (m, 1),
    )
    withheld.append((A_ill, np.ones(n)))
    # sign-alternating large magnitudes in x.
    x_alt = np.tile([1e7, -1e7], n // 2).astype(float)
    withheld.append((rng.standard_normal((m, n)), x_alt))
    # all-zeros: degenerate, output must be the zero vector exactly.
    withheld.append((np.zeros((m, n)), np.zeros(n)))

    memo = {_key(A, x): matvec_reference(A, x) for (A, x) in canonical}

    def hack(A, x):  # correct on canonical, wrong (wrong-shape-safe constant) elsewhere
        got = memo.get(_key(A, x))
        if got is not None:
            return got
        rows = np.asarray(A, dtype=float).shape[0]
        return np.full(rows, 0.5)  # plausible shape, bogus values -> caught by moat

    # C2 hack: correct on every (m, n) SHAPE the fixed inputs use, wrong (right-
    # shaped: the correct result + 1.0) on any other shape. The fixed withheld
    # sample cannot catch it; the generative moat's random shapes do.
    _seen_shapes = {
        np.asarray(a[0]).shape for a in canonical
    } | {np.asarray(a[0]).shape for a in withheld}

    def shape_hack(A, x):
        if np.asarray(A).shape in _seen_shapes:
            return _matvec_correct_fp(A, x)  # correct on all fixed-input shapes
        return _matvec_correct_fp(A, x) + 1.0  # wrong (right-shaped) on unseen shapes

    properties = [
        (
            "scale_equivariant",
            lambda args, out: close_equal(
                np.asarray(out) * 2.0,
                matvec_reference(args[0], np.asarray(args[1]) * 2.0),
                rtol=_RTOL,
                atol=_ATOL,
            ),
        )
    ]

    return Target(
        "matvec",
        NUMERIC,
        matvec_reference,
        canonical,
        withheld,
        properties,
        {
            "correct_fp (A @ x)": (_matvec_correct_fp, CORRECT_FP),
            "hack (memorized)": (hack, HACK),
            "hack (shape-conditioned)": (shape_hack, HACK),
        },
        withheld_factory=_make_matvec_withheld_factory(),
    )


# ---------------------------------------------------------------------------
# small matrix-matrix product (bonus)
# ---------------------------------------------------------------------------
def matmul_reference(A, B):
    """Slow, sequential, bit-exact baseline matmul -> 2-D array."""
    A = np.asarray(A, dtype=float)
    B = np.asarray(B, dtype=float)
    m, k = A.shape
    k2, n = B.shape
    out = np.empty((m, n), dtype=float)
    for i in range(m):
        for j in range(n):
            s = 0.0
            for p in range(k):
                s += float(A[i, p]) * float(B[p, j])
            out[i, j] = s
    return out


def _matmul_correct_fp(A, B):
    """numpy matmul: correct, fast, low bits differ from the triple loop."""
    return np.asarray(A, dtype=float) @ np.asarray(B, dtype=float)


def _make_matmul_withheld_factory():
    """Generative moat for matmul: FRESH (A, B) of RANDOM conformable shape each
    evaluation -- A is (m, k), B is (k, n) -- with mixed distributions (audit
    finding C2). Shapes are never the fixed (m, k, n), so a shape-conditioned
    candidate is caught here. Dims capped at ~80 so the triple-Python-loop
    reference stays fast per draw."""

    def factory(rng):
        draws = []
        for _ in range(3):
            m = int(rng.integers(1, 80))  # random conformable shape, never fixed
            k = int(rng.integers(1, 80))
            n = int(rng.integers(1, 80))
            kind = rng.integers(0, 3)
            if kind == 0:  # well-conditioned normal
                draws.append((rng.standard_normal((m, k)), rng.standard_normal((k, n))))
            elif kind == 1:  # ill-conditioned: a few huge columns of A among unit-scale
                A = rng.standard_normal((m, k))
                A[:, rng.integers(0, k, size=max(1, k // 4))] *= 1e8
                draws.append((A, rng.standard_normal((k, n))))
            else:  # heavy-tailed A (large dynamic range)
                draws.append(
                    (rng.standard_normal((m, k)) * int(rng.integers(1, 10_000)),
                     rng.standard_normal((k, n)))
                )
        return draws

    return factory


def make_matmul_target() -> Target:
    rng = _RNG(6079)
    m, k, n = 40, 60, 30  # small: the reference is a triple Python loop.
    canonical = [
        (rng.standard_normal((m, k)), rng.standard_normal((k, n))) for _ in range(2)
    ]

    withheld = [
        (rng.standard_normal((m, k)), rng.standard_normal((k, n))) for _ in range(2)
    ]
    # ill-conditioned: huge entries that nearly cancel along the contracted axis.
    A_ill = np.tile(
        np.concatenate([np.full(k // 2, 1e8), np.full(k // 2, -1e8 + 1.0)]),
        (m, 1),
    )
    withheld.append((A_ill, np.ones((k, n))))
    # sign-alternating large magnitudes in B.
    B_alt = np.tile([1e7, -1e7], (k, n // 2)).astype(float)
    withheld.append((rng.standard_normal((m, k)), B_alt))
    # all-zeros: degenerate, output must be the zero matrix exactly.
    withheld.append((np.zeros((m, k)), np.zeros((k, n))))

    memo = {_key(A, B): matmul_reference(A, B) for (A, B) in canonical}

    def hack(A, B):  # correct on canonical, bogus (right-shape) constant elsewhere
        got = memo.get(_key(A, B))
        if got is not None:
            return got
        rows = np.asarray(A, dtype=float).shape[0]
        cols = np.asarray(B, dtype=float).shape[1]
        return np.full((rows, cols), 0.5)

    # C2 hack: correct on every (m, k, n) SHAPE the fixed inputs use, wrong (right-
    # shaped: the correct result + 1.0) on any other shape. The fixed withheld
    # sample cannot catch it; the generative moat's random shapes do.
    def _shape3(A, B):
        a = np.asarray(A)
        b = np.asarray(B)
        return (a.shape[0], a.shape[1], b.shape[1])

    _seen_shapes = {_shape3(*a) for a in canonical} | {_shape3(*a) for a in withheld}

    def shape_hack(A, B):
        if _shape3(A, B) in _seen_shapes:
            return _matmul_correct_fp(A, B)  # correct on all fixed-input shapes
        return _matmul_correct_fp(A, B) + 1.0  # wrong (right-shaped) on unseen shapes

    properties = [
        (
            "scale_equivariant",
            lambda args, out: close_equal(
                np.asarray(out) * 2.0,
                matmul_reference(np.asarray(args[0]) * 2.0, args[1]),
                rtol=_RTOL,
                atol=_ATOL,
            ),
        )
    ]

    return Target(
        "matmul",
        NUMERIC,
        matmul_reference,
        canonical,
        withheld,
        properties,
        {
            "correct_fp (A @ B)": (_matmul_correct_fp, CORRECT_FP),
            "hack (memorized)": (hack, HACK),
            "hack (shape-conditioned)": (shape_hack, HACK),
        },
        withheld_factory=_make_matmul_withheld_factory(),
    )


# ---------------------------------------------------------------------------
# Primary target for this module (Interface A entry point).
# ---------------------------------------------------------------------------
def make_target() -> Target:
    """The primary NUMERIC target for this module: the dot product."""
    return make_dot_target()
