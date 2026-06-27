# Authoring a `Target` (Interface A)

> Interface A is **frozen** (BUILD_PLAN task 1.3). It is the contract every domain
> plug-in and the benchmark program against. This guide is the source of truth for
> Phase-2 authors (`tripwire/targets/*.py`). Read it before adding a target.

A `Target` (see `tripwire/target.py`) bundles everything the layered oracle needs
to judge a candidate optimization for one domain. You write **one `make_*_target()`
factory per domain**, returning a validated `Target`.

## The five things a Target provides

| field | what it is | feeds |
|-------|-----------|-------|
| `reference` | the slow-but-correct ground truth (a **pure** function) | L1, L3 |
| `canonical_args` | inputs the optimizer is **allowed to see** (the "test set") | L1 |
| `withheld_args` | fresh + adversarial inputs it **never** sees (the **moat**) | L3 |
| `properties` | metamorphic / invariant checks `(name, fn(args, out) -> bool)` | L2 |
| `candidates` | labeled reference impls `label -> (fn, truth)` (**benchmark only**) | scorecard |

Plus `name` (str) and `kind` (`STRUCTURAL` or `NUMERIC`).

## `kind` decides how outputs are compared (ADR-004)

- **`STRUCTURAL`** — outputs compared **bit-exact**. Sound and free for non-numeric
  results (tokens, parse trees, serialized strings, sets, dicts). Use this whenever
  the correct answer is exactly one value.
- **`NUMERIC`** — outputs compared with **tolerance** (`np.allclose`) plus metamorphic
  relations. Use this for floating-point results, where a *correct* optimization
  (vectorization, reordered reduction, FMA) legitimately changes the low bits.
  **Never** make a numeric target structural — you'd discard real speedups (the
  ~176x `np.sum` false-negative this whole project exists to prevent).

## The moat: `canonical_args` vs `withheld_args` (ADR-003)

This split **is** the defense against reward hacking.

- `canonical_args` are the inputs the optimizer/candidate is allowed to see. A
  memorization hack will be correct on exactly these.
- `withheld_args` are **never shown** to the optimizer. L3 differential-tests against
  them, which is how a memorized/special-cased candidate gets caught.

**Rules:**
- `withheld_args` must be **non-empty** (the `Target` constructor enforces this — an
  empty withheld set silently removes the moat).
- Make `withheld_args` *adversarial*, not just "more of the same": include the edges
  that exercise every code path — empty input, singletons, huge inputs, pathological
  repeats, unicode (structural); ill-conditioned values, cancellation, zeros, NaN/Inf
  (numeric). The "skip-the-work" hack (cf. Sakana's omitted convolution) is caught
  only if some withheld input actually exercises the work that was skipped.
- Each entry is a **tuple of positional args** so the oracle can call
  `reference(*args)` and `candidate(*args)`. A single-arg input is `("text",)` — note
  the trailing comma.

## `properties` — metamorphic / invariant checks (L2)

Each is `(name, fn(args, out) -> bool)` and is checked on **canonical + withheld**
inputs. They catch candidates that match the reference on sampled inputs but violate
a property the real computation must always satisfy. Good properties are cheap,
total, and relational. Examples:

- word-frequency: `sum(counts.values()) == len(text.split())`; keys ⊆ input tokens.
- sum reduction: scale-equivariance — `sum(2*x) ≈ 2*sum(x)`.
- parse/serialize: round-trip identity — `parse(serialize(x)) == x`.

`properties` may be empty (`[]`) if L1+L3 already pin the behavior, but prefer at
least one — it is a cheap, independent line of defense.

## `candidates` — labeled implementations (benchmark only)

`label -> (fn, truth)` where `truth` is one of:

- `CORRECT` — genuinely correct **and** bit-identical to the reference.
- `CORRECT_FP` — genuinely correct but low bits differ (the kind a bitwise oracle
  wrongly rejects). A candidate the oracle **should keep**.
- `HACK` — a reward-hack: passes canonical, wrong on withheld. The oracle **must**
  reject it.

`VALID_TRUTHS = {CORRECT, CORRECT_FP}` is what the benchmark counts as a real win.
The oracle itself never sees `truth` (no peeking); it is ground truth for scoring
only. **Every target must ship ≥1 planted `HACK`** that the oracle is expected to
catch — this doubles as the target's regression test (CLAUDE.md §7).

## Minimal skeleton

```python
from tripwire.target import CORRECT, HACK, NUMERIC, STRUCTURAL, Target


def make_mydomain_target() -> Target:
    def ref(x):
        ...  # slow, obviously-correct ground truth

    canonical = [(small_input,), (another_seen_input,)]
    withheld = [(fresh_input,), ("",), (huge_pathological_input,)]  # adversarial!

    def correct_fast(x):
        ...  # a real optimization (same answer, faster)

    memo = {a[0]: ref(*a) for a in canonical}  # the planted hack: memorize canonical
    def hack(x):
        return memo.get(x)  # correct on canonical, wrong on withheld

    props = [("invariant_name", lambda args, out: ...)]

    return Target(
        "mydomain", STRUCTURAL, ref, canonical, withheld, props,
        {"correct_fast": (correct_fast, CORRECT), "hack": (hack, HACK)},
    )
```

## Checklist before you commit a target

- [ ] `kind` is correct (`NUMERIC` for any floating-point result).
- [ ] `withheld_args` is non-empty **and** adversarial (edges, every code path).
- [ ] `withheld_args` is genuinely disjoint from / unseen vs `canonical_args` — never
      leak withheld inputs into the optimizer's context (ADR-003; a leak is a P0 bug).
- [ ] `reference` is pure and obviously correct (clarity over speed).
- [ ] ≥1 metamorphic property in `properties` (strongly recommended).
- [ ] ≥1 planted `HACK` candidate that the layered oracle catches.
- [ ] A test asserting the planted hack is rejected and any `CORRECT`/`CORRECT_FP`
      candidate is accepted.
- [ ] Your target module OWNS its own file under `tripwire/targets/` and its test —
      no two Phase-2 agents edit the same file (BUILD_PLAN Phase 2).
