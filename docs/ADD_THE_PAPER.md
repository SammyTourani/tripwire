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

### Provenance of the checked-in copy (task 1.4)
`docs/openevolve-example-evaluator.py` is a **verbatim** copy of
`examples/function_minimization/evaluator.py` from the canonical, current OpenEvolve:

- Repo: **algorithmicsuperintelligence/openevolve** (6.6k★; `codelion/openevolve`
  redirects here — same repo, renamed to the org).
- Version: **v0.2.27** — the latest release and the version on PyPI
  (`pip install openevolve`). Verified the file is byte-identical to the `v0.2.27`
  git tag. `main`'s last code commit is the v0.2.27 release (2026-03-18); there is no
  newer maintained OpenEvolve.
- Confirmed the evaluator contract from this version: `evaluate(program_path) -> dict |
  EvaluationResult`; `combined_score` is the metric OpenEvolve maximizes; a plain dict
  return is auto-wrapped via `EvaluationResult.from_dict`. `tripwire/evaluator.py`
  matches this (ADR-007), and `pyproject.toml`'s `runner` extra pins `openevolve>=0.2.27`.

