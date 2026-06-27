# Tripwire — visualizer

**Live:** [sammytourani.github.io/tripwire](https://sammytourani.github.io/tripwire/)

An editorial, animated replay of two artifacts:

- **The cross-domain bench scorecard** (`runs/bench-*.jsonl`) — animated version of
  `assets/optimizer_integrity_bench.png`. Bars colored by truth (green = correct,
  red = reward hack), grouped by domain, with per-bar verdicts and an integrity
  scorecard.
- **Target zero — Claude in an OpenEvolve loop** (`runs/target-zero.jsonl`) — the
  10-iteration trace from the live run, with Claude's reasoning, the candidate
  code it emitted, and the oracle's verdict per iteration.

Stack: Vite + React 19 + TypeScript + Tailwind v4 + Motion (Framer) + GSAP.
Static SPA. No backend. Replay only — no live streaming infra for v1 (per
BUILD_PLAN).

## Develop

```bash
cd viz
npm install
npm run dev
```

Opens at `http://localhost:5173/`.

## Build

```bash
npm run build
```

Emits a self-contained static bundle to `viz/dist/`. Host anywhere:

```bash
# Quickest local preview of the production build
npm run preview

# Or serve dist/ with any static host
python -m http.server 8000 --directory dist
```

Deploy to GitHub Pages / Vercel / Netlify by pointing them at the `dist/`
directory after `npm run build`. The Vite config uses a relative `base` so the
build works at any path (`file://`, `/tripwire/`, root).

This repo deploys to GitHub Pages automatically via
`.github/workflows/pages.yml` on any push to `main` that touches `viz/`.
`package-lock.json` is intentionally untracked — see the workflow comment for
why — so CI runs `npm install` against public npm each build.

## Data

The bench and target-zero JSONL files are bundled under `viz/public/data/`:

```
viz/public/data/bench.jsonl         (copied from runs/bench-*.jsonl)
viz/public/data/target-zero.jsonl   (copied from runs/target-zero.jsonl)
```

To refresh with newer runs, copy the latest JSONL files into `viz/public/data/`
and rebuild. The parsers in `src/data/parse.ts` tolerate format additions
(unknown fields are ignored) but the field names they read are pinned to what
`bench/run.py::write_jsonl` and OpenEvolve's evolution trace emit.

## Structure

```
src/
  App.tsx                       page shell, orchestrates sections in order
  components/Nav.tsx            top sticky navigator
  data/types.ts                 typed model of the two JSONL formats
  data/parse.ts                 streaming-tolerant parsers + normalizers
  lib/util.ts                   shared formatting + motion presets + log-scale
  sections/Hero.tsx             § 0  intro + micro-demo of one candidate
  sections/ThesisSection.tsx    § 01 grouped bench chart + integrity scorecard
  sections/MechanismSection.tsx § 02 the four layers, scroll-revealed
  sections/TargetZeroSection.tsx § 03 the live Claude run, replayable
  sections/Outro.tsx            calibrated novelty claim + repo link
```

## Honest limits

- The chart's hack-row magnitudes are illustrative (machine-dependent timing
  ratios). See README.md "Status / limitations" in the repo root.
- The animations honor `prefers-reduced-motion: reduce` — components collapse
  to their final readable state without motion.
