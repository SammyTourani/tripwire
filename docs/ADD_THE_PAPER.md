# Add the COMPILOT paper here

Two files are intentionally NOT in this package — you add them locally:

## 1. The paper (required)
Download the COMPILOT paper and save it in this folder as exactly:

```
docs/compilot-paper.pdf
```

- arXiv: **2511.00592** — "Agentic Auto-Scheduling: An Experimental Study of LLM-Guided Loop
  Optimization" (Merouani, Kara Bernou, Baghdadi; PACT 2025).
- Link: https://arxiv.org/abs/2511.00592

Why it matters to the build:
- **Appendix A** is the full COMPILOT system prompt. Use it as the reference prompt for **target zero**
  (BUILD_PLAN task 1.5) — the reproduction should use *their* prompt, not a reinvented one, or it
  isn't a clean reproduction.
- **RQ7** is the empirical justification for HARD RULE 1 (delegate correctness/codegen to the
  verifier, never let the LLM generate it): direct code generation had ~17.6–17.9% silent correctness
  failures and ~5.3x the token cost.
- **RQ10** justifies the analysis/chain-of-thought step.

`CLAUDE.md` references `docs/compilot-paper.pdf` directly. Keep the filename exact.

## 2. A real OpenEvolve example evaluator (strongly recommended)
Prevents the agent from inventing an evaluator signature that doesn't match the real API:

```bash
git clone https://github.com/algorithmicsuperintelligence/openevolve /tmp/openevolve
cp /tmp/openevolve/examples/function_minimization/evaluator.py docs/openevolve-example-evaluator.py
```
