# Tripwire — a layered, adversarial-by-design correctness oracle for AI code optimization

> **Status:** research artifact (Phase 3). The layered oracle is live across 7 domain targets, the
> cross-domain benchmark and red-team suite run with no network, a live OpenEvolve loop (target zero)
> drives the oracle end-to-end with Claude as the proposer, and the editorial replay of both artifacts
> is on the web. Working name; rename freely.
>
> **Live visualizer:** [sammytourani.github.io/tripwire](https://sammytourani.github.io/tripwire/) —
> animated replay of the cross-domain scorecard and target zero.

AI code optimizers are graded on a reward = **speedup**, gated by a *naive* correctness check
(output-match, or a tolerance band on a fixed set of test inputs). That naive check fails in **two
opposite directions**:

- **It discards correct speedups (false negatives).** A correct, faster candidate — vectorization, a
  reordered reduction, an FMA — shifts floating-point results in the low bits. A *bitwise* oracle
  rejects a real win.
- **It ships reward-hacks (false positives).** A candidate that memorizes / special-cases the visible
  test inputs is correct on exactly those inputs and wrong everywhere else — and it looks almost
  infinitely fast. A bitwise *or* a tolerance oracle ships it.

**Tripwire** is the layered oracle that is right on *both* axes, packaged as a drop-in evaluator for
[OpenEvolve](https://github.com/algorithmicsuperintelligence/openevolve) so you never rebuild the
optimization loop. Alongside it is the **Optimizer Integrity Bench (OIB)**, which puts a number on how
often the naive checks current optimizers rely on either ship a hack or throw away a real win.

**See the result before reading further:** the
[live visualizer](https://sammytourani.github.io/tripwire/) replays both the cross-domain scorecard
and target zero (Claude in the loop). The rest of this README is the *why*.

## The four layers

The oracle assumes every candidate is trying to cheat it (the documented Sakana CUDA-Engineer
reward-hack — see `docs/threat-model.md`). The layer order is fixed; any correctness layer failing
rejects the candidate, and **speed is only measured after correctness passes**.

| layer | what it checks |
|------|----------------|
| **L1 — canonical correctness** | output-match on the visible inputs: *exact* for `structural` targets, *tolerance* for `numeric` ones (bitwise on numeric would discard real speedups). |
| **L2 — metamorphic / property** | invariants the real computation must satisfy (e.g. scale-equivariance of a sum, count-conservation of a tokenizer) — these hold for the true function regardless of input. |
| **L3 — differential on withheld + adversarial inputs** | re-checks the candidate against the reference on fresh, adversarial inputs it **never saw** (the moat: you cannot overfit to inputs you cannot see). |
| **L4 — isolated speedup** | only now is speed measured — warmed up, best-of-N, across multiple shapes, with a variance lower bound so no "speedup" is phantom noise. |

A correctness failure zeroes the reward, so a reward-hack can never earn a score.

## The result, measured (no network, no LLM)

`python -m bench.run` runs all 7 domain targets through all three oracles. Across the **20 labeled
candidates** in the current benchmark (3 correct, 4 correct-up-to-FP, 13 reward-hacks), the scorecard
is stable across runs:

```
SCORECARD                       (20 candidates across 7 domain targets)
oracle              ships_hacks  integrity  kept_valid       verdict
naive_bitwise                 9       0.25         43%        unsafe
naive_tolerance              13       0.35        100%        unsafe
layered                       0       1.00        100%   TRUSTWORTHY
```

- **naive_bitwise** ships 9 of 13 hacks *and* discards every floating-point-correct win (it keeps
  only 43% of valid candidates — every `correct_fp` candidate, the FMA / reordered-reduction wins,
  gets thrown away).
- **naive_tolerance** keeps every real win but ships **every single hack** — 13 of 13.
- **layered** ships **0 hacks** and keeps **100%** of valid wins, across every domain →
  `TRUSTWORTHY`. `bench.run.main()` exits non-zero if that ever stops holding (the regression gate).

### Live domains (7 target instances)

`tokenizer` and `serde` (structural, exact oracle), `sum_reduction` and the `numeric` family
(`dot`, `matvec`, `matmul` — tolerance + metamorphic), and `sql` (whose withheld layer is a
SQL-semantics fuzzer hitting NULLs / three-valued logic / duplicate keys / empty groups, with the DB
engine as ground truth). Each ships a planted reward-hack the oracle is expected to catch.

### Red-team attack suite

`python -m bench.attack_suite` continuously throws hand-built reward-hacks (memorize-canonical,
constant-return, skip-the-work) at the oracle. Current result: the **layered oracle caught 9/9
attacks (0 hacks shipped)** while the naive oracles shipped 5. Every attack that ever lands becomes a
new layer or a new withheld-input distribution.

### Why the magnitudes here are illustrative

The recorded benchmark stores `layered_speedup` only for candidates the layered oracle accepted, and
the four FP-correct numeric wins that `naive_bitwise` throws away are real and large on this machine
— `sum_reduction` **180×**, `numeric:dot` **849×**, `numeric:matvec` **3,536×**, `numeric:matmul`
**4,294×** (each with a measured lower bound; see `viz/public/data/bench.jsonl`). The 13 reward-hacks
are all rejected at L1/L2/L3, so their "speedups" are never measured by the layered oracle (that is
the design — a hack must never earn a number). When a hack ships through a naive oracle in the wild,
its apparent speedup is a function of how aggressively it skips work; the visualizer's hack-row bars
are deliberately illustrative for that reason. **All timing ratios are hardware-dependent in absolute
magnitude; what is invariant is the direction — the kept wins are real and the rejected hacks fail on
the withheld inputs.**

## Target zero — a COMPILOT-inspired live loop, with Claude as the proposer

`runner/target_zero.py` wires the layered oracle (via the OpenEvolve evaluator) into a real,
network-backed OpenEvolve run with **Claude (Opus 4.8)** proposing optimizations of a Python numeric
kernel (`sum_reduction`). The recorded run (`runs/target-zero.jsonl`,
`runs/target-zero-summary.json`) reached a **200.28×** speedup at iteration 5, verified through all
four layers; the
[visualizer's target-zero section](https://sammytourani.github.io/tripwire/#target-zero) replays the
full 10-iteration trace, with the candidate code, Claude's reasoning, and the oracle's verdict per
iteration.

**Honest framing:** this is **COMPILOT-*inspired*, not a COMPILOT reproduction.** COMPILOT
(arXiv:2511.00592) optimizes **C loop nests** through the **Tiramisu polyhedral compiler** with
**formal legality checking**; target zero optimizes a **Python kernel** judged by Tripwire's
**empirical layered oracle**. What it reproduces is the *principle* the paper validates in RQ7 —
**delegate correctness to a rigorous verifier rather than trusting the LLM to be correct** — not the
system. It also fills a literal gap in the paper: COMPILOT's Table I evaluated Gemini / GPT / o3 /
Llama / Gemma / QwQ / Qwen / Codestral, but **never an Anthropic model**. Running it needs network
and an LLM key (read from a local, gitignored `.env`).

## Novelty claim (calibrated — the README stays inside this)

Metamorphic testing, differential testing, and property-based testing are **decades old** — Tripwire
does **not** claim to invent any of them. What does not exist in the wild, per extensive search, is:

1. a clean, cross-optimizer **measurement** of the reward-hacking / silent-correctness-failure rate
   across the dominant open optimization stack, and
2. a **reusable, adversarial-by-design oracle packaged as a component** for that stack (OpenEvolve).

COMPILOT proved the *principle* — delegate correctness to something rigorous — for one narrow domain
(polyhedral loop nests, Tiramisu backend). Tripwire generalizes and hardens it into the missing piece.

## Status / limitations

This is a research artifact, not a finished product, and the claim is deliberately bounded:

- **Tripwire is a correctness oracle, not a Python sandbox.** Its layered design is
  adversarial-by-design against a gradient-following optimizer (the documented Sakana failure mode),
  and the candidate-execution boundary has been hardened against in-process tampering, IPC-channel
  RCE, verdict hijacking, and timing-forge (see `tests/test_isolation_security.py`). Pure-Python
  in-process sandboxing of fully-adversarial code is a published negative result — see PEP 551 and
  the pysandbox post-mortem — and Tripwire does not claim to have solved it. If you run Tripwire
  against an LLM you do not trust to be benign at the OS level (file writes, network egress,
  fork-bombs), deploy the evaluator under gVisor, Firecracker, or a hardened container, exactly as
  you would for any other untrusted Python execution. The contract is on the *correctness axis*: a
  wrong candidate cannot earn reward, regardless of what it does inside its sandbox process.
- The oracle is only as strong as the attacks it has survived, which is why the red-team suite is a
  permanent, growing fixture.
- Numeric correctness rests on tolerance + metamorphic relations and a withheld differential, not on
  a formal proof; soundness depends on the target author choosing good properties and adversarial
  withheld inputs.
- Speedups are empirical measurements (warmed up, best-of-N, variance-bounded) — robust to noise, but
  still machine-dependent in absolute magnitude.
- The benchmark uses planted, labeled candidates to *measure* oracle behavior; it is a controlled
  harness, not a survey of optimizers in the wild.

## Run it

The project is a Python 3.12 package and runs out of a venv. Bare `python` may not exist on your
machine — use the venv's interpreter (`.venv/bin/python`). The seed and benchmarks import the
*installed* `tripwire` package, so install it editable first. This repo's venv is `uv`-managed (it has
no `pip`), so the working install here is:

```bash
# one-time: install the package (editable) + dev tools into the venv
uv pip install -e ".[dev]"
# (on a plain pip venv instead:  python3 -m venv .venv && .venv/bin/python -m pip install -e ".[dev]")

# smoke test / regression baseline (the Phase-0 seed; imports the installed package)
.venv/bin/python optimizer_integrity_bench.py

# the cross-domain scorecard + a JSONL event log under runs/
.venv/bin/python -m bench.run

# the red-team attack suite
.venv/bin/python -m bench.attack_suite

# tests
.venv/bin/python -m pytest
```

The OpenEvolve loop (target zero) additionally needs the `runner` extra and a network + LLM key:
`uv pip install -e ".[runner]"`, then `.venv/bin/python -m runner.target_zero`.

## Files
- `CLAUDE.md` — the source-of-truth spec for any agent on this repo.
- `BUILD_PLAN.md` — the phased plan and the parallel gate.
- `tripwire/oracle.py` — the layered oracle (the crown jewel); `tripwire/measure.py` — hardened timing.
- `tripwire/target.py` — Interface A (the `Target` plug-in contract); `tripwire/targets/` — one file per domain.
- `tripwire/evaluator.py` — Interface B (the OpenEvolve adapter; correctness failure zeroes the score).
- `bench/run.py` — the cross-domain scorecard + JSONL log; `bench/attack_suite.py` — the red-team suite.
- `runner/` — target zero (the live OpenEvolve loop with Claude).
- `viz/` — the editorial replay UI; deployed to GitHub Pages automatically by `.github/workflows/pages.yml`.
- `optimizer_integrity_bench.py` — the proven Phase-0 seed, kept runnable as a regression smoke test.
- `docs/` — `threat-model.md` (the adversary, sourced), `decisions.md` (the ADRs), `target-authoring.md`,
  and `compilot-paper.pdf`.
