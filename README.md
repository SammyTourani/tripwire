<div align="center">

# Tripwire

**A layered, adversarial-by-design correctness oracle for AI code optimization.**

[![PyPI](https://img.shields.io/pypi/v/tripwire-oracle.svg?color=e5484d)](https://pypi.org/project/tripwire-oracle/)
[![Python](https://img.shields.io/pypi/pyversions/tripwire-oracle.svg)](https://pypi.org/project/tripwire-oracle/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Live visualizer](https://img.shields.io/badge/live-visualizer-e5484d.svg)](https://sammytourani.github.io/tripwire/)

![Tripwire CLI — launch, menu, demo, scorecard](docs/assets/tripwire-hero.gif)

</div>

When an AI "optimizes" your code, how do you know the speedup is real and not a cheat? **Tripwire re-tests every optimized candidate on withheld, adversarial inputs it never saw — before any speedup can earn credit.** A candidate that memorized or special-cased the visible tests looks almost infinitely fast and passes a naive check; Tripwire catches it on the inputs it couldn't see.

It ships as a one-command CLI *and* as a drop-in [OpenEvolve](https://github.com/algorithmicsuperintelligence/openevolve) evaluator, so you can use it standalone or wire it into an existing evolutionary loop without rebuilding anything.

## Install

```bash
pip install tripwire-oracle
tripwire demo
```

Zero-install (via [uv](https://github.com/astral-sh/uv)):

```bash
uvx --from tripwire-oracle tripwire demo
```

Run `tripwire` with no arguments for the interactive menu, or use the subcommands directly.

## The catch with "faster" code

AI code optimizers are rewarded for **speedup**, gated by a *naive* correctness check (output-match, or a tolerance band on a fixed set of test inputs). That naive check fails in **two opposite directions**:

- **It ships reward-hacks (false positives).** A candidate that memorizes / special-cases the visible test inputs is correct on exactly those inputs and wrong everywhere else — and it looks almost infinitely fast. A bitwise *or* a tolerance oracle ships it.
- **It discards correct speedups (false negatives).** A genuinely faster candidate — vectorization, a reordered reduction, an FMA — shifts floating-point results in the low bits. A *bitwise* oracle rejects a real win.

Tripwire is the layered oracle that is right on *both* axes.

## How it works — the four layers

The oracle assumes every candidate is trying to cheat it (the documented Sakana CUDA-Engineer reward-hack — see [`docs/threat-model.md`](docs/threat-model.md)). The layer order is fixed; **any correctness layer failing rejects the candidate, and speed is only measured after correctness passes.**

| layer | what it checks |
|------|----------------|
| **L1 — canonical correctness** | output-match on the visible inputs: *exact* for `structural` targets, *tolerance* for `numeric` ones (bitwise on numeric would discard real speedups). |
| **L2 — metamorphic / property** | invariants the real computation must satisfy (e.g. scale-equivariance of a sum, count-conservation of a tokenizer) — these hold for the true function regardless of input. |
| **L3 — differential on withheld + adversarial inputs** | re-checks the candidate against the reference on fresh, adversarial inputs it **never saw** — *the moat*: you cannot overfit to inputs you cannot see. |
| **L4 — isolated speedup** | only now is speed measured — warmed up, best-of-N, across multiple shapes, with a variance lower bound so no "speedup" is phantom noise. |

`tripwire verify --example` shows it on a real optimization and a planted hack, with zero setup:

![tripwire verify --example](docs/assets/cli-verify-example.png)

The real win is **accepted**; the memorized hack passes L1/L2 but is **rejected at L3** — caught on inputs it never saw.

## The result, measured (no network, no LLM)

`tripwire demo` runs all 7 domain targets through three oracles. Across the **20 labeled candidates** in the benchmark (3 correct, 4 correct-up-to-FP, 13 reward-hacks), the scorecard is stable across runs:

![tripwire demo — the integrity scorecard](docs/assets/cli-demo.png)

- **naive (bitwise)** ships 9 of 13 hacks *and* discards every floating-point-correct win (keeps only 43% of valid candidates).
- **naive (tolerance)** keeps every real win but ships **every single hack** — 13 of 13.
- **layered (Tripwire)** ships **0 hacks** and keeps **100%** of valid wins, across every domain → `TRUSTWORTHY`.

The demo exits non-zero if that ever stops holding (the regression gate). The live domains: `tokenizer` and `serde` (structural, exact), `sum_reduction` and the `numeric` family (`dot`, `matvec`, `matmul` — tolerance + metamorphic), and `sql` (whose withheld layer is a SQL-semantics fuzzer hitting NULLs / three-valued logic / duplicate keys / empty groups, with the DB engine as ground truth).

## Use it on your own code

A **Target** tells the oracle how to judge your problem: a slow-but-correct reference, the canonical inputs the optimizer may see, the **withheld adversarial inputs** it may not (the moat), and optional metamorphic properties.

**1. Scaffold a Target from your reference function:**

```bash
tripwire init your_function.py
```

![tripwire init](docs/assets/cli-init.png)

Fill in the `canonical_args` / `withheld_args` TODOs (full contract in [`docs/target-authoring.md`](docs/target-authoring.md)). The withheld inputs are the moat — make them adversarial, not more-of-the-same.

**2. Verify any candidate against it:**

```bash
tripwire verify your_target.py your_candidate.py
```

**3. Or run a real optimization loop, oracle-graded end to end:**

```bash
tripwire optimize your_target.py
```

`optimize` runs a real OpenEvolve loop — an LLM proposes faster code and Tripwire's layered oracle grades every proposal, so the loop can never be rewarded for a hack. It needs the `runner` extra and an LLM key:

![tripwire optimize prerequisites](docs/assets/cli-optimize.png)

```bash
pip install "tripwire-oracle[runner]"
export OPENAI_API_KEY=...           # any OpenAI-compatible endpoint
export OPENEVOLVE_MODEL=gpt-4o-mini # the proposer model
# OPENAI_BASE_URL is optional (defaults to OpenAI; point it at any compatible proxy)
tripwire optimize your_target.py
```

### Drop it into an existing OpenEvolve loop

The oracle is decoupled — it imports nothing from OpenEvolve. Wrap any Target as an OpenEvolve evaluator:

```python
from tripwire.evaluator import make_openevolve_evaluator
from your_target import make_target

evaluate = make_openevolve_evaluator(make_target())   # returns {combined_score, correct, speedup, reason}
# hand `evaluate` to openevolve.run_evolution(...) as the evaluator
```

A correctness failure (L1/L2/L3) zeroes the score, so a reward-hack can never earn one.

## CLI reference

| command | what it does |
|--------|--------------|
| `tripwire demo` | the cross-domain integrity scorecard (no setup) |
| `tripwire verify TARGET CANDIDATE` | verify one optimized candidate (`--example` to try a bundled one) |
| `tripwire init REFERENCE.py` | scaffold a Target skeleton from your function |
| `tripwire optimize TARGET` | run a real OpenEvolve loop, oracle-graded (`--example` to try one) |
| `tripwire explain` | how the 4-layer oracle works |

## Target zero — a COMPILOT-inspired live loop, with Claude as the proposer

[![live visualizer](docs/assets/site-hero.png)](https://sammytourani.github.io/tripwire/)

`runner/target_zero.py` wires the layered oracle into a real, network-backed OpenEvolve run with **Claude (Opus 4.8)** proposing optimizations of a Python numeric kernel. The recorded run reached a **200×** speedup verified through all four layers; the **[live visualizer](https://sammytourani.github.io/tripwire/)** replays the full trace — candidate code, Claude's reasoning, and the oracle's verdict per iteration — alongside the cross-domain scorecard.

**Honest framing:** this is **COMPILOT-*inspired*, not a COMPILOT reproduction.** COMPILOT (arXiv:2511.00592) optimizes **C loop nests** through the **Tiramisu polyhedral compiler** with **formal legality checking**; target zero optimizes a **Python kernel** judged by Tripwire's **empirical layered oracle**. What it reproduces is the *principle* the paper validates in RQ7 — **delegate correctness to a rigorous verifier rather than trusting the LLM to be correct** — not the system. It also fills a literal gap in the paper: COMPILOT's Table I evaluated Gemini / GPT / o3 / Llama / Gemma / QwQ / Qwen / Codestral, but **never an Anthropic model**.

## Does the moat beat a judge? (research, in progress)

A reasonable question: does the withheld-adversarial-input moat actually catch hacks that a strong **LLM-judge** baseline (one model reading the candidate and deciding) would miss? The harness for that experiment lives in [`experiment/`](experiment/) with the plan in [`docs/reward-hacking-experiment.md`](docs/reward-hacking-experiment.md). It runs each candidate three ways — an independent ground-truth referee, the Tripwire moat, and an LLM judge — and reports where they disagree. This is an open question, and "the judge does about as well" would be a valid, publishable finding.

## Novelty claim (calibrated)

Metamorphic, differential, and property-based testing are **decades old** — Tripwire does **not** claim to invent any of them. What did not exist in the wild, per extensive search, is:

1. a clean, cross-optimizer **measurement** of the reward-hacking / silent-correctness-failure rate across the dominant open optimization stack, and
2. a **reusable, adversarial-by-design oracle packaged as a component** for that stack (OpenEvolve).

COMPILOT proved the *principle* — delegate correctness to something rigorous — for one narrow domain (polyhedral loop nests, Tiramisu backend). Tripwire generalizes and hardens it into the missing piece.

## Status & limitations

This is a research artifact, and the claim is deliberately bounded:

- **Tripwire is a correctness oracle, not a Python sandbox.** The layered design is adversarial-by-design against a gradient-following optimizer (the documented Sakana failure mode), and the candidate-execution boundary is hardened against in-process tampering, IPC-channel RCE, verdict hijacking, and timing-forge (see `tests/test_isolation_security.py`). But pure-Python in-process sandboxing of fully-adversarial code is a published negative result (PEP 551, the pysandbox post-mortem) and Tripwire does not claim to have solved it. If you run it against an LLM you do not trust at the OS level (file writes, network egress, fork-bombs), deploy the evaluator under gVisor, Firecracker, or a hardened container. The contract is on the *correctness axis*: a wrong candidate cannot earn reward, regardless of what it does inside its sandbox process.
- The oracle is only as strong as the attacks it has survived, which is why the red-team suite is a permanent, growing fixture.
- Numeric correctness rests on tolerance + metamorphic relations and a withheld differential, not a formal proof; soundness depends on the target author choosing good properties and adversarial withheld inputs.
- Speedups are empirical (warmed up, best-of-N, variance-bounded) — robust to noise, but machine-dependent in absolute magnitude.
- The benchmark uses planted, labeled candidates to *measure* oracle behavior; it is a controlled harness, not a survey of optimizers in the wild.

## Development / from source

The project is a Python 3.12 package. The repo's venv is `uv`-managed:

```bash
uv pip install -e ".[dev]"     # editable install + dev tools
uv run tripwire demo           # the scorecard
uv run python -m bench.run     # cross-domain scorecard + JSONL log under runs/
uv run python -m bench.attack_suite   # the red-team attack suite
uv run pytest                  # tests
```

The screenshots and the hero GIF above are regenerated from the committed [`docs/assets/tapes/`](docs/assets/tapes/) with [vhs](https://github.com/charmbracelet/vhs).

## Repo map

- `tripwire/cli.py` — the interactive CLI (presentation + dispatch only).
- `tripwire/oracle.py` — the layered oracle (the crown jewel); `tripwire/measure.py` — hardened timing.
- `tripwire/target.py` — the `Target` plug-in contract; `tripwire/targets/` — one file per domain.
- `tripwire/evaluator.py` — the OpenEvolve adapter (correctness failure zeroes the score).
- `tripwire/optimize.py` / `tripwire/scaffold.py` — the generic `optimize` loop and `init` scaffolder.
- `bench/` — the cross-domain scorecard + the red-team suite; `experiment/` — the moat-vs-judge harness.
- `runner/` — target zero (the live OpenEvolve loop with Claude); `viz/` — the editorial replay UI (deployed to GitHub Pages).
- `docs/` — `threat-model.md`, `decisions.md` (ADRs), `target-authoring.md`, `reward-hacking-experiment.md`.

## License

[MIT](LICENSE).
