# BUILD_PLAN.md — phased, with the parallel gate made explicit

**Principle:** serial until the interfaces freeze, then parallel. Parallelism only pays when work is
partitioned onto disjoint files. Each Phase-2 task below names the files it OWNS — never let two
parallel agents touch the same file.

---

## Phase 0 — DONE (the thesis is proven)
`optimizer_integrity_bench.py` already demonstrates, with real measured numbers, that bitwise and
tolerance oracles both fail and the layered oracle is right on both axes. This is the foundation and
the regression baseline. Do not regress it.

---

## Phase 1 — SERIAL (one Claude Code session, Opus 4.8, you steering)
Goal: a real repo with frozen interfaces and target zero running end-to-end. **No parallel agents
until 1.4 is merged.**

- **1.1 Scaffold.** Create the package layout from `CLAUDE.md` §4. Move shared timing/compare helpers
  into `tripwire/measure.py`. Keep `optimizer_integrity_bench.py` runnable as a smoke test.
- **1.2 Lift the oracle.** Move `layered_oracle` / `naive_oracle` into `tripwire/oracle.py` with tests
  that reproduce the Phase-0 scorecard exactly.
- **1.3 Freeze Interface A (`Target`).** Finalize the dataclass + a `Target` authoring guide. This is
  the contract every Phase-2 agent depends on — get it right now. Add a schema test.
- **1.4 Freeze Interface B + OpenEvolve adapter.** Finalize `tripwire/evaluator.py`
  (`evaluator(program_path) -> dict`, correctness failure zeroes score). Write a fake-program test
  proving a planted hack scores 0.0. **← PARALLEL GATE: nothing in Phase 2 starts before this merges.**
- **1.5 Target zero — the COMPILOT-with-Claude reproduction (non-negotiable, day-one artifact).**
  Wire the layered oracle into a real OpenEvolve run with Claude as the proposer, on a small
  loop-optimization / numeric-kernel task. Two wins in one: proves the oracle drives a live loop, and
  fills the literal gap in arXiv:2511.00592 (the paper tested Gemini/GPT/o3 — never Claude). Capture
  the run as `runs/target-zero.jsonl`. This is the first post.

**Phase 1 exit criteria:** repo builds, Phase-0 scorecard reproduces in tests, a planted hack scores
0.0 through the OpenEvolve adapter, target zero produced a JSONL run with a real speedup.

---

## Phase 2 — PARALLEL (gated on 1.4; Conductor or `/batch` + subagents)
Each task = its own git worktree, its own branch, its own OWNED files. They do not touch each other or
the core (`oracle.py`, `measure.py`, `evaluator.py`) — those are frozen. Run as many as you want at once.

- **2.1 — Structural target: tokenizer.** OWNS `tripwire/targets/tokenizer.py` + its test.
  Reference tokenizer; metamorphic relations (idempotence of normalization, length/coverage
  invariants); canonical + withheld (incl. adversarial: empty, unicode, huge, pathological repeats);
  ≥1 planted hack (memorize canonical → wrong on withheld). Exact oracle should be sound here — this
  is the clean-domain proof and the recommended FIRST vertical.
- **2.2 — Structural target: parser/serializer round-trip.** OWNS `tripwire/targets/serde.py` + test.
  Reference parse↔serialize; metamorphic relation = round-trip identity; planted hack that special-
  cases canonical docs.
- **2.3 — Numeric target: reduction / matvec family.** OWNS `tripwire/targets/numeric.py` + test.
  Extend the sum/np.sum case to dot products and small matmuls; tolerance + scale/permutation
  metamorphic relations; ill-conditioned withheld inputs (cancellation, NaN/Inf, zeros).
- **2.4 — SQL target (HIGH VALUE, but budget for it).** OWNS `tripwire/targets/sql.py` + test +
  `tripwire/targets/sql_fuzzer.py`. **Read this carefully:** "empirical-with-guards on the customer's
  data" is NOT sufficient for SQL. The hard correctness failures live exactly where prod data won't
  expose them — NULL / three-valued logic, ordering, duplicate handling, aggregate edge cases. The
  withheld layer for SQL must be a real **SQL-semantics fuzzer** (generate adversarial rows hitting
  NULLs, dup keys, empty groups, boundary aggregates), with the DB engine as ground truth via
  EXPLAIN (cheap pre-filter) → result-equivalence on fuzzed data. This is the most engineering of any
  target; scope it as its own multi-step effort, not a single pass.
- **2.5 — Red-team agent (permanent role).** OWNS `tripwire/attacks/` + `bench/attack_suite.py`.
  Its ONLY job: generate candidates that beat the current oracle. Every hack it lands becomes a new
  layer or a new withheld-input distribution (filed as an issue against the core, applied serially —
  red-team proposes, the core owner disposes). The oracle is only as strong as the attacks it survives;
  make attacking it automated and continuous.
- **2.6 — Measurement hardening.** OWNS `tripwire/measure.py` ONLY (coordinate: this is core, so run
  it serially OR assign exclusively, not alongside other core edits). CPU pinning where available,
  warmup discipline, variance reporting, repeat-until-stable. Goal: speedup numbers nobody can
  challenge (the PIE "phantom improvement from random noise" failure must be impossible).

**Phase 2 exit criteria:** ≥3 domains live, the benchmark (`bench/run.py`) reports a clean
naive-vs-layered scorecard across all of them, the red-team suite runs and the layered oracle survives
it, every speedup has a variance bound.

---

## Phase 3 — SHOW IT OFF (visualizer + publication)
- **3.1 — Visualizer (the share-able artifact).** OWNS `viz/`. React/TS app that REPLAYS a
  `runs/*.jsonl` log: optimization dialogue streaming, each candidate appearing with its measured
  speedup, the oracle stamping reward-hacks BLOCKED (with the failing layer named) and passing honest
  wins. A live, animated version of `optimizer_integrity_bench.png`. Replay first; live infra later.
- **3.2 — The benchmark + writeup.** Public repo + README (inside the §3 novelty claim) + a results
  post: "the most-used open-source AI code optimizer ships wrong code that looks 2,000x faster — here's
  the oracle that stops it, and the number for how often it happens." Include target zero (Claude in
  the COMPILOT loop) as the headline reproduction.

---

## What NOT to do (anti-over-engineering guardrails)
- No microservices, no queue, no DB for the MVP. It's a Python library + an OpenEvolve adapter + a
  replay UI. That's it.
- No custom evolutionary loop. (See HARD RULE 1.)
- No live-streaming infra for v1 of the visualizer — replay a log file.
- Don't parallelize Phase 1. Don't let two agents edit a core file. Don't start 2.x before 1.4 merges.
