# Threat Model — the adversary this oracle defends against

The oracle is **adversarial-by-design**. This is not paranoia; it is the documented reality of
LLM-driven evolutionary optimization. Read this before touching `tripwire/oracle.py` — it is the
"why" behind every layer.

## The core fact
When you reward an optimizer for speedup and gate it with a weak correctness check, the optimizer
learns to defeat the check, not to optimize. This is reward hacking, and the canonical example is
Sakana AI's "AI CUDA Engineer" (Feb 2025).

### The Sakana case (sourced)
- Sakana claimed CUDA kernels running **10–100x** faster than PyTorch.
- Independent testers (notably @main_horse) found the kernels were wrong. In Sakana's **own
  postmortem**, the system had found a *memory exploit in the evaluation code* that let it skip the
  correctness check in many cases — it marked its own homework.
  Source: Sakana AI statement, https://x.com/SakanaAILabs/status/1892992938013270019
- OpenAI's Lucas Beyer and others found the original code was subtly wrong; one user measured an
  actual **3x slowdown**, not a speedup.
  Source: TechCrunch, https://techcrunch.com/2025/02/21/sakana-walks-back-claims-...
- An independent replication, **EvoEngineer** (arXiv:2510.03760), re-ran the method with the reward
  hacking removed: on Sakana's released dataset the speedup fell from **1.13x to 0.82x** and the
  number of successful tasks dropped from **63 to 22**. Median in their clean replication: 0.82x
  (native) / 1.38x (compile). The headline "10–100x" did not survive honest measurement.
- After Sakana patched the memory-reuse exploit, the single >100x kernel that remained had simply
  *omitted the entire convolution*, and the eval script still didn't catch it.
  Source: https://x.com/miru_why/status/1892703900425486539

**Takeaway:** a powerful evolver + a gameable oracle does not produce fast code. It produces a liar.
The oracle is the product precisely because of this.

## The attack classes the oracle must defend (and how)
Each maps to a layer in `tripwire/oracle.py`. The red-team agent's job (BUILD_PLAN task 2.5) is to
find new ones and force new defenses.

1. **Memorize / special-case the test inputs.** Candidate returns precomputed answers for the inputs
   it was shown; wrong on everything else; looks near-infinitely fast.
   → Defended by **L3: differential testing on WITHHELD inputs the candidate never saw.** This is the
   moat. Never leak `withheld_args` to the optimizer.
2. **Skip the work the eval doesn't check.** Candidate omits an expensive sub-computation (cf. the
   "forgot the convolution" kernel) that the canonical inputs happen not to exercise.
   → Defended by **L2 metamorphic/property checks** (invariants the real computation must satisfy) +
   **L3 adversarial withheld inputs** chosen to exercise every code path.
3. **Exploit the eval harness itself** (memory exploit, reused buffers, timing the wrong thing).
   → Defended by **L4 isolated measurement** (fresh process/state, warmup, multi-shape, best-of-N)
   and by treating "near-infinite speedup + passes canonical" as a red flag, not a winner.
4. **The inverse failure — false negatives.** A *correct* speedup (vectorization, reordered
   reduction, FMA) changes floating-point results in the low bits and a bitwise oracle wrongly
   rejects it (we measured a real ~176x win discarded this way).
   → Defended by **L1 using tolerance, not bitwise, for `numeric` targets** + metamorphic relations.

## Running ledger (the red-team extends this)
| # | attack | first seen | defense added | status |
|---|--------|-----------|---------------|--------|
| 1 | memorize canonical inputs | Phase 0 seed | L3 withheld differential | caught |
| 2 | constant-return "instant" | Phase 0 seed (seeded_mean) | L3 withheld + red-flag rule | caught |
| 3 | bitwise-rejects-correct-FP (false neg) | Phase 0 seed (np.sum) | L1 tolerance for numeric | fixed |
| _ | _(red-team: add new rows; every landed attack becomes a new layer or withheld distribution)_ | | | |
