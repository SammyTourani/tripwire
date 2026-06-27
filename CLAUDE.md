# CLAUDE.md — Tripwire / Optimizer Integrity Bench

> Working name: **Tripwire** (the oracle) + **OIB** (the public benchmark). Rename freely.
> This file is the source of truth for any agent working on this repo. Read it fully before writing code.

## 0. Required reading (in this order, before Phase 1)
1. This file, in full.
2. `BUILD_PLAN.md` — the phased plan and the parallel gate.
3. `docs/compilot-paper.pdf` — the anchor paper (arXiv:2511.00592). Appendix A = reference system
   prompt for target zero; RQ7 = why correctness is delegated, never generated; RQ10 = why the
   analysis/CoT step exists. *(If the PDF is absent, see `docs/ADD_THE_PAPER.md`.)*
4. `docs/threat-model.md` — the reward-hacking adversary the oracle defends against (sourced). This
   is the "why" behind the layered design.
5. `docs/decisions.md` — the recorded rationale (ADRs) behind every hard rule.
6. `docs/openevolve-example-evaluator.py` — a REAL OpenEvolve evaluator. Match this interface; do not
   invent one. *(If absent, see `docs/ADD_THE_PAPER.md` step 2.)*

For anything about OpenEvolve's current API, the Anthropic API, or library versions: verify against
live docs. Your training cutoff predates the versions this repo runs on (see ADR-007).

---

## 1. What this is (one paragraph)

The agentic code-optimization loop is **commoditized** — OpenEvolve (6k+ stars) already gives you
the LLM-proposes → evaluate → keep-best → iterate loop, production-grade, off the shelf. The thing
nobody has built is the part that makes that loop *trustworthy*: a **layered, adversarial-by-design
correctness oracle**. We are building (a) that oracle, shipped as a drop-in OpenEvolve evaluator, and
(b) a public benchmark that measures how often current AI optimizers ship reward-hacked or
silently-wrong "optimizations."

## 2. The problem, stated precisely (do not drift from this)

AI optimizers are graded on a reward = speedup, with a naive correctness check (output-match or a
tolerance band on a fixed set of test inputs). That naive check fails in **two opposite directions**,
and both are already proven empirically in `optimizer_integrity_bench.py`:

- **False negatives (discarded real wins):** a correct, faster candidate (vectorization, reordered
  reduction, FMA) changes floating-point results in the low bits. A *bitwise* oracle rejects it. We
  measured a real **176x** `np.sum` speedup getting thrown away this way.
- **False positives (shipped reward-hacks):** a candidate that memorizes / special-cases the test
  inputs is correct on those inputs and wrong everywhere else, and it looks almost infinitely fast.
  We measured **2,040x** and **5,231x** "speedups" that are pure mirages — both pass bitwise AND
  tolerance oracles. This is the documented Sakana CUDA-Engineer failure.

**Only a layered oracle is right on both axes.** That is the entire product.

## 3. Calibrated novelty claim (use this exact framing; do NOT overclaim)

Metamorphic testing, differential testing, and property-based testing are decades old — we do **not**
claim to invent them. What does not exist in the wild, per extensive search, is:
1. a clean, cross-optimizer **measurement** of the reward-hacking / silent-correctness-failure rate
   across the dominant open optimization stack, and
2. a **reusable, adversarial-by-design oracle packaged as a component** for that stack (OpenEvolve).

COMPILOT (arXiv:2511.00592) proved the principle — delegate correctness to something rigorous — for
one narrow domain (polyhedral loop nests, Tiramisu backend). We generalize and harden it into the
missing piece every optimizer needs. README and any blog copy must stay inside this claim.

## 4. Architecture & the TWO FROZEN INTERFACES

Everything hangs off two contracts. **Freeze these in Phase 1 before any parallel work begins.**
Changing them later forces a re-sync across every domain plug-in, so get them right once.

### Interface A — `Target` (the plug-in contract for a domain)
A Target bundles a reference implementation, the inputs the optimizer is allowed to see, the inputs it
is NOT (the moat), metamorphic relations, and (for the benchmark) a set of labeled candidate
implementations. Current shape (see `optimizer_integrity_bench.py`):

```python
@dataclass
class Target:
    name: str
    kind: str                 # 'structural' | 'numeric'  (controls exact vs tolerance comparison)
    reference: Callable
    canonical_args: list      # inputs the optimizer SEES        (the "test set")
    withheld_args: list       # fresh + adversarial; NEVER shown (the differential set)
    properties: list          # [(name, fn(args, out) -> bool)]  metamorphic / invariants
    candidates: dict          # label -> (fn, truth)  truth in {correct, correct_fp, hack}  (benchmark only)
```

### Interface B — the OpenEvolve evaluator contract
A function `evaluator(program_path: str) -> dict` returning at minimum
`{combined_score, correct, speedup, reason}`. **Correctness failure ZEROES `combined_score`.** A
reward-hack must never be able to earn reward. Reference impl: `make_openevolve_evaluator(target)`.

### Component map
- `tripwire/oracle.py`       — the layered oracle (lift from the seed file). The crown jewel.
- `tripwire/measure.py`      — reward-hacking-resistant timing (warmup, best-of-N, multi-shape).
- `tripwire/targets/`        — one file per domain Target (parallelizable in Phase 2).
- `tripwire/evaluator.py`    — OpenEvolve adapter (Interface B).
- `bench/run.py`             — runs the benchmark, emits the scorecard + a JSONL event log.
- `viz/`                     — Phase 3 React replay of the JSONL log.
- `optimizer_integrity_bench.py` — the proven seed. Keep it runnable as a regression/smoke test.

## 5. HARD RULES (violations are bugs)

1. **Do not rebuild the loop, the population, or the archive.** OpenEvolve owns those. We build the
   evaluator only. If you find yourself writing evolutionary-search code, stop.
2. **The oracle is adversarial-by-design.** Assume every candidate is trying to cheat the oracle
   (because OpenEvolve-style evolution is exactly what reward-hacked Sakana — see
   `docs/threat-model.md` for the sourced case and the attack classes you must defend). Design every
   layer to be attacked.
3. **Layer order is fixed:** (L1) canonical correctness — *exact* for `structural`, *tolerance* for
   `numeric`; (L2) metamorphic/property checks; (L3) differential test on **withheld + adversarial**
   inputs the candidate never saw; (L4) isolated speedup measurement. Any correctness layer failing →
   reject, no speedup reported.
4. **Withhold inputs.** The evolver/candidate is never given `withheld_args`. The whole moat is that
   it can't overfit to inputs it can't see. Never leak them into the optimizer's context.
5. **Numeric correctness is never bitwise.** Use tolerance + metamorphic, because correct speedups
   change low bits. Bitwise comparison is only sound for `structural` targets.
6. **A constant-returning / instant candidate is a red flag, not a winner.** Near-infinite speedup +
   passing canonical = almost certainly a memorization hack. The withheld differential must catch it.

## 6. Proven baseline (regression target — keep these passing)

`python optimizer_integrity_bench.py` must always reproduce: layered oracle ships **0 hacks**,
integrity **1.00**, keeps **100%** of valid speedups; naive_bitwise ships 2 hacks AND discards the
np.sum win; naive_tolerance ships 2 hacks. If a refactor breaks this, the refactor is wrong.

## 7. Conventions

- Python 3.11+, `numpy`. Keep dependencies minimal. `ruff` + `pytest`.
- Pure functions where possible; the oracle must be deterministic given its inputs.
- Every Target ships with a `README` snippet: what it computes, its metamorphic relations, and at
  least one planted hack that the oracle is expected to catch (this doubles as a test).
- No network in the oracle/measure/targets layers (so they run in CI and in this sandbox). Network is
  only for the OpenEvolve run, which lives behind `tripwire/evaluator.py` + a runner script.

## 8. How to run
- Smoke/regression: `python optimizer_integrity_bench.py`
- Benchmark: `python -m bench.run` (emits scorecard + `runs/*.jsonl`)
- OpenEvolve loop (needs network + LLM key): see `BUILD_PLAN.md` Phase 1, task 1.5 (target zero).
