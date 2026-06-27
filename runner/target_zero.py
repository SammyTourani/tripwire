#!/usr/bin/env python3
"""Target zero -- the COMPILOT-with-Claude reproduction (BUILD_PLAN task 1.5).

Two wins in one:
  1. proves the layered oracle (tripwire.evaluator, Interface B) drives a real,
     live OpenEvolve loop end-to-end, and
  2. fills the literal gap in arXiv:2511.00592 -- the COMPILOT paper evaluated
     gemini-2.0-flash, gpt-4o, gpt-o3-mini, llama3.3, gemma3, qwq, qwen2.5-coder,
     and codestral, but NEVER an Anthropic/Claude model (paper Table I). Here the
     proposer is Claude (Opus 4.8) via the LiteLLM staging proxy.

COMPILOT (the paper) optimizes C loop nests through the Tiramisu polyhedral
compiler -- infrastructure we deliberately do NOT rebuild (HARD RULE 1). BUILD_PLAN
1.5 calls for "a small loop-optimization / numeric-kernel task"; OpenEvolve evolves
a Python file and our oracle grades it. So target zero is: Claude proposes an
optimized Python `solve` for a numeric kernel (sum reduction), and the layered
oracle verifies correctness on WITHHELD + adversarial inputs before crediting any
speedup -- exactly the trustworthy loop this project is about.

The system prompt is adapted from COMPILOT's Appendix A (Fig. 13): same role
framing ("optimization assistant", iterative feedback, keep correctness) and the
RQ10 analysis/chain-of-thought emphasis, retargeted from Tiramisu transformation
commands to Python edits (OpenEvolve applies the edits; our oracle ensures
correctness, the analogue of COMPILOT delegating legality to the compiler).

Requires network + an LLM key. Reads credentials from a LOCAL, gitignored .env
(never committed). Run:  python -m runner.target_zero
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INITIAL_PROGRAM = REPO / "runner" / "target_zero_initial.py"
EVALUATOR_FILE = REPO / "runner" / "target_zero_evaluator.py"
DEFAULT_OUTPUT = REPO / "runs"


# COMPILOT Appendix A, adapted from Tiramisu schedule-commands to Python edits.
SYSTEM_MESSAGE = """\
You are a code optimization assistant. Your task is to iteratively improve a \
Python function to minimize its execution time WITHOUT changing what it computes.

# Overview
You will be shown a Python program with an `# EVOLVE-BLOCK-START` / \
`# EVOLVE-BLOCK-END` region containing a function named `solve`. Propose a faster \
implementation of `solve`. Your candidate is then verified by a rigorous, \
adversarial correctness oracle and, only if correct, benchmarked for speedup. You \
will receive feedback and may refine your approach over several iterations.

# Analysis first (think before you optimize)
Before rewriting, briefly analyze the function: what does it compute, what is the \
performance bottleneck, and which optimization strategies are sound. This analysis \
guides better edits.

# Correctness is non-negotiable
The oracle checks your candidate not only on the inputs you can infer, but on \
WITHHELD and adversarial inputs you never see (fresh data, ill-conditioned values, \
edge cases). A candidate that special-cases or memorizes specific inputs, or that \
skips the actual computation, will be REJECTED and earn ZERO reward -- correctness \
failure zeroes the score. Only genuinely correct optimizations are credited. For \
numeric code, results need only match within a small tolerance (vectorized or \
reordered arithmetic that changes the low bits is fine and encouraged).

# What good looks like here
The reference is a slow, sequential Python loop. Idiomatic, vectorized numerical \
code (e.g. using numpy) is typically far faster and remains correct. Keep the \
function signature and the `solve` name unchanged.
"""


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (no dependency). Does not overwrite already-set vars."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip())


def build_config(iterations: int):
    """Build the OpenEvolve Config pointed at Claude via the LiteLLM staging proxy."""
    from openevolve.config import Config, LLMModelConfig

    api_key = os.environ.get("OPENAI_API_KEY")
    api_base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model = os.environ.get("OPENEVOLVE_MODEL", "bedrock-claude-opus-4-8")
    if not api_key:
        sys.exit("OPENAI_API_KEY not set. Add it to a local .env (gitignored).")

    cfg = Config()
    cfg.max_iterations = iterations
    cfg.random_seed = 42  # reproducibility (OpenEvolve seeds every component)
    cfg.language = "python"
    cfg.diff_based_evolution = False  # rewrite the EVOLVE-BLOCK wholesale

    # Route both the proposer and (unused) evaluator models at Claude/LiteLLM.
    # NOTE: bedrock-claude-opus-4-8 REJECTS the `temperature` param ("temperature
    # is deprecated for this model") -- it's a newer reasoning-style model. We set
    # temperature/top_p to None so OpenEvolve/the OpenAI client omit them (verified:
    # LiteLLM accepts the call without temperature; sending it 400s). Diversity in
    # the loop therefore comes from the model's own sampling, not a temperature knob.
    claude = LLMModelConfig(
        name=model,
        api_base=api_base,
        api_key=api_key,
        temperature=None,
        top_p=None,
        max_tokens=4096,
        timeout=120,
        # Set retries/retry_delay explicitly: we assign cfg.llm.models AFTER
        # Config() has already run __post_init__, so the shared-config propagation
        # (which fills None fields from the top-level LLMConfig) won't reach this
        # model. Leaving them None would crash (retries + 1 -> None + int).
        retries=3,
        retry_delay=5,
        random_seed=42,
    )
    cfg.llm.models = [claude]
    cfg.llm.api_base = api_base
    cfg.llm.api_key = api_key
    cfg.llm.temperature = None
    cfg.llm.top_p = None
    cfg.prompt.system_message = SYSTEM_MESSAGE
    cfg.prompt.include_artifacts = True  # feed the oracle's `reason` back to Claude

    # Capture the run as runs/target-zero.jsonl (BUILD_PLAN 1.5 artifact); this is
    # what the Phase-3 visualizer will replay.
    cfg.evolution_trace.enabled = True
    cfg.evolution_trace.format = "jsonl"
    cfg.evolution_trace.include_code = True
    cfg.evolution_trace.output_path = str(DEFAULT_OUTPUT / "target-zero.jsonl")
    return cfg


def main() -> int:
    _load_dotenv(REPO / ".env")

    iterations = int(os.environ.get("TARGET_ZERO_ITERS", "10"))
    output_dir = Path(os.environ.get("TARGET_ZERO_OUT", str(DEFAULT_OUTPUT)))
    output_dir.mkdir(parents=True, exist_ok=True)

    from openevolve import run_evolution

    from tripwire.targets.sum_reduction import make_target

    target = make_target()  # for the summary/log only; the run uses EVALUATOR_FILE
    config = build_config(iterations)

    print(f"[target-zero] model={os.environ.get('OPENEVOLVE_MODEL')} "
          f"iterations={iterations} kernel={target.name}")
    print(f"[target-zero] proposer routed via {os.environ.get('OPENAI_BASE_URL')}")

    result = run_evolution(
        initial_program=str(INITIAL_PROGRAM),
        evaluator=str(EVALUATOR_FILE),
        config=config,
        iterations=iterations,
        output_dir=str(output_dir / "target-zero-openevolve"),
        cleanup=False,
    )

    # Summarize + persist a compact record of the run.
    best = result.best_program
    metrics = getattr(best, "metrics", {}) if best is not None else {}
    summary = {
        "kernel": target.name,
        "model": os.environ.get("OPENEVOLVE_MODEL"),
        "iterations": iterations,
        "best_metrics": metrics,
        "best_code": getattr(best, "code", None),
    }
    out_json = output_dir / "target-zero-summary.json"
    out_json.write_text(json.dumps(summary, indent=2, default=str))

    print("\n[target-zero] === RESULT ===")
    print(f"  best combined_score (oracle-verified speedup): "
          f"{metrics.get('combined_score')}")
    print(f"  correct: {metrics.get('correct')}  reason: {metrics.get('reason')!r}")
    print(f"  summary written to: {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
