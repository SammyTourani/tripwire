// Data for the COMPILOT figure replicas (anchor paper, PACT '25, arXiv:2511.00592).
// Exact values are used where the paper/figures label them (Fig. 19 percentages, the
// headline geomeans, RQ3 rates). Per-benchmark bar heights and the trajectory/heatmap
// surfaces are faithful RECONSTRUCTIONS of the figures' shapes (the paper publishes the
// charts, not the raw CSVs) — generated deterministically so SSR and client agree.

export const COMPILOT_STATS = {
  geomean: 2.66, // single-run, COMPILOT@30
  geomeanBest5: 3.54, // best-of-5
  vsPluto: 2.94, // geomean over Pluto (SOTA polyhedral optimizer)
  beatsPluto: "119 / 150",
  over100x: ">100×",
  wrongUnderRandom: 17.6, // % of "passing", faster LLM transforms that were actually wrong (RQ7)
  models: 8, // LLMs evaluated — none of them Anthropic
  benchmarks: 30,
  instances: 150, // 30 kernels x 5 sizes
  runnablePct: 36.1, // RQ3 avg
  invalidPct: 31.4,
  illegalPct: 32.5,
};

// loop transformation repertoire (the LLM's action space)
export const TRANSFORMATIONS = [
  "Fusion", "Interchange", "Parallelize", "2D Tiling", "3D Tiling",
  "Unrolling", "Skewing", "Shifting", "Reversal",
];

// the five feedback categories the compiler returns to the agent
export const FEEDBACK = [
  { label: "Invalid", tone: "bad" },
  { label: "Illegal", tone: "bad" },
  { label: "Solver failure", tone: "warn" },
  { label: "Compiler crash", tone: "warn" },
  { label: "Successful execution", tone: "good" },
] as const;

// ---- size palette (matches the paper's MINI..XLARGE coloring) ----
export const SIZES = ["MINI", "SMALL", "MEDIUM", "LARGE", "XLARGE"] as const;
export const SIZE_COLORS = ["#a3e635", "#f472b6", "#a78bfa", "#fb923c", "#2dd4bf"];

// ---- deterministic PRNG so the reconstructed charts are stable across SSR/client ----
function mulberry32(seed: number) {
  return function () {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// ---- Fig. 7 — COMPILOT@30 median speedup per benchmark (log scale, by size) ----
const PEAKS: Record<string, number> = {
  "2mm": 150, "3mm": 205, adi: 15, atax: 1.6, bicg: 1.6, cholesky: 1.05,
  correlation: 430, covariance: 455, deriche: 2.3, doitgen: 3.2, durbin: 1.05,
  fdtd: 5, floyd: 2, gemm: 27, gemver: 20, gesummv: 3, gramschmidt: 4.2,
  heat3d: 5.5, jacobi1d: 2, jacobi2d: 2.3, lu: 1.6, ludcmp: 1.1, mvt: 56,
  nussinov: 1.6, seidel2d: 2.6, symm: 3.2, syr2k: 220, syrk: 180, trisolv: 1.6, trmm: 185,
};
const SIZE_MULT = [0.11, 0.21, 0.38, 0.64, 1.0];

export type BenchBar = { name: string; values: number[]; err: number[] };
function buildSpeedupBars(): BenchBar[] {
  const rnd = mulberry32(7);
  return Object.keys(PEAKS).map((name) => {
    const peak = PEAKS[name];
    const dyn = peak > 4 ? 1 : 0.12; // small/flat kernels barely move with size
    const values = SIZE_MULT.map((m) => {
      const jitter = 0.86 + rnd() * 0.28;
      return Math.max(1, peak * (dyn * m + (1 - dyn)) * jitter);
    });
    const err = values.map((v) => v * (0.12 + rnd() * 0.18)); // 95% CI half-width
    return { name, values, err };
  });
}
export const SPEEDUP_BARS = buildSpeedupBars();

// ---- Fig. 8 (left) — geometric mean aggregated by input size ----
export const GEOMEAN_BY_SIZE = [
  { size: "MINI", value: 1.05 },
  { size: "SMALL", value: 1.62 },
  { size: "MEDIUM", value: 2.61 },
  { size: "LARGE", value: 4.9 },
  { size: "XLARGE", value: 7.2 },
];

// ---- Fig. 19 — schedule viability over dialogue iterations (EXACT labeled %s) ----
export type ViabilityPoint = { t: number; runnable: number; illegal: number; invalid: number };
export const SCHEDULE_VIABILITY: ViabilityPoint[] = [
  { t: 1, runnable: 32.4, illegal: 50.1, invalid: 17.4 },
  { t: 5, runnable: 35.7, illegal: 40.4, invalid: 23.9 },
  { t: 10, runnable: 36.2, illegal: 36.6, invalid: 27.1 },
  { t: 15, runnable: 36.4, illegal: 35.1, invalid: 28.5 },
  { t: 20, runnable: 36.4, illegal: 33.9, invalid: 29.8 },
  { t: 30, runnable: 36.1, illegal: 32.9, invalid: 31.0 },
];
export const VIABILITY_COLORS = {
  runnable: "#34d399", // green
  illegal: "#fb923c", // orange
  invalid: "#e879b9", // pink/magenta
};

// ---- Fig. 21 — 40 individual run trajectories on gramschmidt_LARGE (T=0..30) ----
function buildTrajectories(): number[][] {
  const rnd = mulberry32(42);
  const STEPS = 31;
  const runs: number[][] = [];
  for (let i = 0; i < 40; i++) {
    const target = 1 + Math.pow(rnd(), 2.4) * 21; // skew low; a few climb toward ~22
    const arr: number[] = [];
    let v = 1;
    for (let t = 0; t < STEPS; t++) {
      if (t > 1 && v < target && rnd() < 0.16) {
        const gap = target - v;
        v = Math.min(target, v + gap * (0.35 + rnd() * 0.55));
      }
      arr.push(v);
    }
    runs.push(arr);
  }
  return runs;
}
export const TRAJECTORIES = buildTrajectories();
export const TRAJECTORY_MAX = 22;

// ---- Fig. 9 — cumulative token consumption vs iterations T (super-linear) ----
export const TOKEN_CURVE = Array.from({ length: 31 }, (_, t) => ({
  t,
  tokens: Math.round(200000 * Math.pow(t / 30, 1.7)),
}));

// ---- Fig. 16 — heatmap of COMPILOT_K@T (best-of-K after T iterations) ----
function buildHeatmap() {
  const ts = Array.from({ length: 30 }, (_, i) => i + 1);
  const ks = Array.from({ length: 10 }, (_, i) => i + 1);
  const grid = ks.map((k) =>
    ts.map((t) => {
      const tg = 1 - Math.exp(-t / 9); // grows with iterations, saturating
      const kg = Math.log(k + 1) / Math.log(11); // grows with runs
      return 1 + 6.6 * (0.4 * tg + 0.6 * (0.45 * tg + 0.55 * kg));
    })
  );
  let min = Infinity;
  let max = -Infinity;
  for (const row of grid) for (const v of row) { if (v < min) min = v; if (v > max) max = v; }
  return { ts, ks, grid, min, max };
}
export const HEATMAP = buildHeatmap();
