# START HERE

This is the build package for **Tripwire** — an un-cheatable, layered correctness oracle for AI
code optimization, shipped as a drop-in OpenEvolve evaluator, plus a benchmark that measures how
often AI optimizers ship reward-hacked code. Follow these steps to start building with Claude Code.

---

## Step 1 — Create the repo
Put every file in this package at the repo root, preserving the tree:

```
tripwire/
├── START_HERE.md            ← you are here
├── README.md                ← project front door (also the public README later)
├── CLAUDE.md                ← the agent's brain. Claude Code reads this first.
├── BUILD_PLAN.md            ← phased plan with the parallel gate
├── optimizer_integrity_bench.py   ← the PROVEN core (run it: it works today)
├── docs/
│   ├── threat-model.md      ← the reward-hacking adversary, sourced
│   ├── decisions.md         ← ADR log (the "why" behind the rules)
│   └── ADD_THE_PAPER.md     ← instructions for the two files YOU add below
└── assets/
    └── optimizer_integrity_bench.png   ← the proof chart
```

Then: `git init && git add -A && git commit -m "handoff: tripwire scaffold + proven oracle"`

## Step 2 — Add the paper (you said you'd do this)
Download the COMPILOT paper PDF (arXiv:2511.00592) and save it as **`docs/compilot-paper.pdf`**.
`CLAUDE.md` and `BUILD_PLAN.md` both reference that exact path. Appendix A (the full system prompt)
is the reference prompt for target zero; RQ7 is why we delegate correctness instead of generating it.

## Step 3 — Add the real OpenEvolve evaluator example (5 minutes, prevents a wasted day)
The single biggest Phase-1 risk is the agent inventing an evaluator signature that doesn't match the
real OpenEvolve API. Eliminate it: clone OpenEvolve and copy one real example evaluator into `docs/`.

```bash
git clone https://github.com/algorithmicsuperintelligence/openevolve /tmp/openevolve
cp /tmp/openevolve/examples/function_minimization/evaluator.py docs/openevolve-example-evaluator.py
# (any example with an evaluator.py works; function_minimization is the simplest)
```

## Step 4 — Open Claude Code (use Opus 4.8) and paste this kickoff prompt

> Read CLAUDE.md, BUILD_PLAN.md, docs/threat-model.md, docs/decisions.md, and docs/compilot-paper.pdf
> in full before writing anything. Also read docs/openevolve-example-evaluator.py — match that real
> interface, do not invent one. Then execute Phase 1 only, tasks 1.1 through 1.4, serially. Do NOT
> start any Phase 2 work. The Phase-0 scorecard in optimizer_integrity_bench.py is the regression
> baseline — keep it passing. The two interfaces you freeze in 1.3 and 1.4 are load-bearing for every
> downstream agent, so flag any design decision you're unsure about instead of guessing. Stop and show
> me the diffs after 1.2, 1.3, and 1.4 before continuing. For anything about OpenEvolve's current API
> or the Anthropic API, verify against live docs — your training cutoff predates the versions we run on.

## Step 5 — Target zero, then parallelize
After 1.4 merges, run task 1.5: the COMPILOT-with-Claude reproduction (the paper never tested Claude).
That's your first artifact and first post. **Only then** open Conductor (or Claude Code's `/batch`)
and fan out Phase 2 — one worktree per task, each owning the files named in BUILD_PLAN.md. That is the
point where parallel agents actually help, because the work is finally disjoint.

---

### The one rule that matters most
Do not feed Claude Code the chat transcripts, the research reports, or other AI sessions' outputs.
That volume is mostly redundant and will dilute the rules that matter. The decisions already
distilled into these files. Signal density beats volume — that's the whole thesis of this project,
applied to its own context.
