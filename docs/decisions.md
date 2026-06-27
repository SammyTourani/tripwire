# Decision Log (ADRs)

Short records of *why*, not just what. When an agent is tempted to "simplify" by dropping a layer,
leaking withheld inputs, or rebuilding the loop, the relevant ADR is the answer. Agents respect
recorded rationale; bare rules get rationalized away.

Format: Context → Decision → Consequence.

---

### ADR-001 — Build on OpenEvolve, do not write our own optimization loop
**Context:** The LLM-proposes → evaluate → keep-best → iterate loop is commoditized. OpenEvolve
(~6k★, `pip install openevolve`) already provides it production-grade: prompt sampler, LLM ensemble,
evaluator pool, program database, island populations, error-feedback side-channel.
**Decision:** We build the evaluator only. We never implement evolutionary search, populations, or
the archive.
**Consequence:** ~70% of the system is off-the-shelf. Our entire surface area — and our entire moat —
is `tripwire/oracle.py` + `tripwire/evaluator.py`. If you're writing search code, you're off-plan.

### ADR-002 — Layered oracle, not a single mechanism
**Context:** Two failure modes pull in opposite directions: bitwise comparison discards correct
floating-point speedups (false negatives); naive output-match ships memorization hacks (false
positives). Each "clever single oracle" we considered fails one or the other — formal-proof-only
boxes you into narrow decidable domains; seed-determinism-only is bitwise (rejects real speedups) AND
gameable (a hack memorizes the seeds).
**Decision:** A stack — L1 canonical correctness (exact for structural, tolerance for numeric) → L2
metamorphic/property → L3 differential on withheld+adversarial inputs → L4 isolated measurement.
**Consequence:** Proven on the Phase-0 scorecard: layered ships 0 hacks AND keeps 100% of real
speedups; neither naive oracle does both. Do not collapse the stack to one layer.

### ADR-003 — Withheld inputs are non-negotiable
**Context:** The dominant attack is overfitting to the inputs the optimizer can see.
**Decision:** Every Target defines `withheld_args` (fresh + adversarial) that are NEVER shown to the
optimizer or the candidate. L3 tests against them.
**Consequence:** This is the moat. Leaking withheld inputs into the optimizer's context silently
destroys the entire guarantee. Treat such a leak as a P0 bug.

### ADR-004 — Numeric correctness is tolerance + metamorphic, never bitwise
**Context:** Correct optimizations (vectorization, reordered reduction, FMA) change low bits because
floating-point addition is not associative.
**Decision:** `numeric` targets use tolerance comparison plus metamorphic relations (scale/permutation
invariance, identities). Bitwise is reserved for `structural` targets, where it is sound and free.
**Consequence:** We keep real numeric speedups (the ~176x np.sum win) that a bitwise oracle throws
away — without admitting hacks, because L2+L3 still catch them.

### ADR-005 — Structural domains first; SQL is high-value but its own project
**Context:** Vertical value × oracle cleanliness. Non-numeric/structural code (tokenizers, parsers,
serializers) gives an exact oracle for free — the clean proof. SQL is high-value B2B but its hard
correctness failures (NULL/three-valued logic, ordering, duplicates, aggregate edges) live exactly
where prod data won't expose them.
**Decision:** Ship structural targets first. SQL requires a real SQL-semantics fuzzer for its
withheld layer (EXPLAIN pre-filter → result-equivalence on fuzzed adversarial rows), scoped as its
own multi-step effort — not "diff against prod data."
**Consequence:** Fast, credible early wins; SQL added deliberately, not underestimated.

### ADR-006 — Correctness failure zeroes the reward
**Context:** If a fast-but-wrong candidate earns any reward, the evolver climbs toward cheating.
**Decision:** The OpenEvolve evaluator returns `combined_score = 0.0` on any correctness-layer
failure. Speed is only scored after correctness passes all layers.
**Consequence:** Reward hacking yields zero gradient toward itself. This is the property that makes
the loop trustworthy.

### ADR-007 — Verify external/API facts against live docs
**Context:** Agent training cutoffs predate the OpenEvolve / Anthropic API versions we actually run
on. Self-knowledge of one's own knowledge boundary is, fittingly, the lesson of this whole project.
**Decision:** For OpenEvolve's current API, the Anthropic API, or library versions, the agent reads
live docs rather than trusting training.
**Consequence:** Fewer wasted cycles on a hallucinated interface; the evaluator matches reality.
