# Tripwire — an un-cheatable oracle for AI code optimization

> **Status:** MVP in progress. The core oracle is proven (see below). Working name; rename freely.

AI code optimizers are graded on a reward = speedup with a naive correctness check. That check fails
in two opposite directions: it **discards correct speedups** (when floating-point results shift) and
it **ships reward-hacks** (when a candidate memorizes the test inputs and looks almost infinitely
fast). Tripwire is the layered, adversarial-by-design oracle that is right on both axes — packaged as
a drop-in evaluator for [OpenEvolve](https://github.com/algorithmicsuperintelligence/openevolve), so
you never rebuild the optimization loop. Alongside it is **OIB**, a benchmark that puts a number on
how often current optimizers cheat.

## The result, already proven

`python optimizer_integrity_bench.py` produces this (real measured numbers, no network, no LLM):

| oracle           | ships hacks | integrity | keeps valid speedups | speedup discarded |
|------------------|:-----------:|:---------:|:--------------------:|-------------------|
| naive_bitwise    | 2           | 0.33      | 50%                  | a real ~176x win  |
| naive_tolerance  | 2           | 0.50      | 100%                 | none              |
| **layered**      | **0**       | **1.00**  | **100%**             | **none**          |

The two reward-hacks register as ~2,000x and ~5,200x "speedups" — the mirage — and both naive oracles
ship them. Only the layered oracle blocks the cheats while keeping every honest win. See
`assets/optimizer_integrity_bench.png`.

## Novelty claim (calibrated — stay inside this)

Metamorphic, differential, and property-based testing are decades old; we do not claim to invent them.
What does not exist in the wild is (1) a clean cross-optimizer **measurement** of the
reward-hacking / silent-failure rate across the dominant open optimization stack, and (2) a
**reusable, adversarial-by-design oracle packaged as a component** for that stack. COMPILOT
(arXiv:2511.00592) proved the principle for one narrow domain; we generalize and harden it.

## Files
- `START_HERE.md` — setup + kickoff prompt. Read first.
- `CLAUDE.md` — the brain for any agent on this repo.
- `BUILD_PLAN.md` — phased plan; serial Phase 1, then the parallel gate, then Phase 2.
- `optimizer_integrity_bench.py` — the proven core + the OpenEvolve adapter. Run it.
- `docs/threat-model.md` — the adversary the oracle defends against (the Sakana case, sourced).
- `docs/decisions.md` — the recorded rationale behind every hard rule.
- `docs/compilot-paper.pdf` — *(you add this; see docs/ADD_THE_PAPER.md)*.

## Run it
```bash
python optimizer_integrity_bench.py     # smoke test / regression baseline
```
Build everything else by following `START_HERE.md`.
