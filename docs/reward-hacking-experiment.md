# Reward-Hacking Experiment — "Does the moat beat the judge?"

## The question
After a deep prior-art survey, the only genuinely-open, honest question for Tripwire is:

> When LLMs optimize code, does Tripwire's **withheld-adversarial-input moat** catch
> reward-hacks that a strong **LLM-judge baseline** misses?

This matters because EvilGenie (arXiv 2511.21654) found that an LLM judge was already
the strongest reward-hack detector and held-out tests added "only minimal improvement."
If our moat catches hacks the judge misses, Tripwire earns its complexity. If it does
not, that is a valid, publishable negative result ("just use a judge"). Either way we
learn something true. We do **not** claim "first" or "un-gameable" — both are taken /
rejected by the field (ImpossibleBench, EvilGenie, RHB; robust-kbench's own authors).

## Design: three independent verdicts per candidate
For each (task, model, candidate optimization):

1. **Ground truth** (the referee): an independent, deliberately heavy oracle that is
   *stronger than both* of the things being compared. Labels the candidate
   `correct` / `hack` / `error`. See `experiment/ground_truth.py`.
2. **LLM judge** (the baseline): an LLM that sees the reference, the candidate, and the
   *visible* (canonical) inputs — **never the withheld ones** — and rules accept/reject.
   `experiment/judge.py`.
3. **Tripwire moat**: the existing `layered_oracle` verdict (accept/reject). This is the
   thing under test.

**Headline metrics:** of the candidates ground-truth says are hacks, what fraction does
the **judge wrongly accept** (false accepts)? Of *those*, what fraction does the **moat
catch** (reject)? And the dual axis: how many genuinely-correct wins does the moat
wrongly reject (false rejects) that the judge keeps?

## The non-negotiable principle
The ground-truth referee must be **independent of and heavier than the moat**, or the
comparison is circular. The moat uses canonical + withheld + ~4 generative draws; the
referee uses canonical + withheld + ~60 generative draws + generic structural mutations
(an input distribution the moat does not use). It is intentionally expensive and is
never the thing being scored.

## Candidate generation
Reuse the optimization *pressure* (the speed reward is what tempts a model to cheat).
`experiment/generate.py` prompts each model to optimize the reference (COMPILOT-style
framing, optional feedback rounds) and collects every proposed candidate. v1 is
single-shot sampling × K; escalate to the full feedback loop only if single-shot does
not elicit enough hacks.

## Phases
- **0 — de-risk:** pick + verify a free model set (a couple of test calls). Lock the
  ground-truth definition. (Models: OpenRouter free tier — a Llama, a Qwen-coder, a
  Gemini-flash, a Mistral.)
- **1 — harness:** `ground_truth.py`, `judge.py`, `generate.py`, `run.py` + tests that
  validate the model-free parts (referee + metrics) on the planted candidates.
- **2 — run + analyze:** run across the free models on the OIB targets; compute the
  headline metrics; honest writeup (positive *or* negative).
- **3 — only if v1 shows the moat adds value:** a moat that *actively searches* for
  breaking inputs (Hypothesis / LLM-adversary), then the robust-kbench (GPU kernel)
  comparison + a small leaderboard.

## Integrations, sequenced
- **Hypothesis** — Phase 3 (adversarial input search + minimal counterexamples).
- **EvalPlus** — Phase 3 (mutation-fuzzing seeds + its pass-rate-drop fragility metric).
- **robust-kbench** — Phase 3 (GPU-kernel domain + a recognized baseline to beat + a
  curated cheating-kernel corpus).
v1 deliberately adds **no new dependencies** (numpy + stdlib only).

## Honest risks
- Real models may rarely cheat on the simple OIB tasks → add 1-2 hack-tempting tasks
  (cheap-to-memorize, expensive-to-actually-compute) and lean on optimization pressure.
- Ground-truth circularity (see principle above) — the main validity threat.
- The result may be "judge ≈ moat." That is a real finding, not a failure.
- "No exact prior-art match" for our niche is bounded by the survey; re-check arXiv
  before any publication claim (the field moved a lot in the last ~9 months).

## How to run
- Model-free validation (no key): `python -m experiment.run --planted`
- Full run (needs an OpenAI-compatible key, e.g. OpenRouter):
  `OPENAI_API_KEY=... OPENAI_BASE_URL=https://openrouter.ai/api/v1 python -m experiment.run --models <m1> <m2> ...`
