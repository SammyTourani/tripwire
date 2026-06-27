/**
 * Shared utilities and motion presets. Everything that gets used in more than
 * one place lives here so the design stays coherent.
 */

import type { Truth } from '../data/types';

// ── Number formatting (used in chart labels, stats, axes) ────────────────────
/** Compact "Nx" speedup label, e.g. 2050 -> "2,050×", 0.91 -> "0.9×", 1->'1.0×' */
export function fmtSpeedup(n: number | null | undefined, digits = 1): string {
  if (n == null || !isFinite(n)) return '—';
  if (n >= 1000) return `${Math.round(n).toLocaleString()}×`;
  if (n >= 10) return `${n.toFixed(0)}×`;
  return `${n.toFixed(digits)}×`;
}

/** Percentage as a tight integer string. */
export function fmtPct(p: number): string {
  if (!isFinite(p)) return '—';
  return `${Math.round(p * 100)}%`;
}

// ── Log-scale axis math ─────────────────────────────────────────────────────
// The bench chart uses a base-10 log scale (the PNG's y-axis is "10^0..10^4").
// Mapping y = pixel position for a given speedup value:
export interface LogScale {
  domain: [number, number]; // e.g. [1, 10000]
  range: [number, number]; // pixel y of bottom / top, top is smaller px
}

export function logScale(value: number, scale: LogScale): number {
  const v = Math.max(value, scale.domain[0]);
  const t =
    (Math.log10(v) - Math.log10(scale.domain[0])) /
    (Math.log10(scale.domain[1]) - Math.log10(scale.domain[0]));
  return scale.range[0] + t * (scale.range[1] - scale.range[0]);
}

/** Power-of-ten tick positions inside a log scale's domain (1, 10, 100, ...). */
export function logTicks(scale: LogScale): number[] {
  const lo = Math.ceil(Math.log10(scale.domain[0]));
  const hi = Math.floor(Math.log10(scale.domain[1]));
  const ticks: number[] = [];
  for (let i = lo; i <= hi; i++) ticks.push(Math.pow(10, i));
  return ticks;
}

// ── Semantic palette helpers ────────────────────────────────────────────────
export function truthColor(t: Truth, accepted: boolean): string {
  if (t === 'hack') return accepted ? 'var(--color-hack)' : 'var(--color-hack)';
  return 'var(--color-correct)';
}

export function truthLabel(t: Truth): string {
  return t === 'correct' ? 'Genuine win' : t === 'correct_fp' ? 'Genuine FP win' : 'Reward hack';
}

// ── Motion presets ─────────────────────────────────────────────────────────
// One coherent feel: short, soft, spring-based. We avoid bouncy springs that
// undermine the "research" tone.
export const ease = {
  /* "Apple" cubic-out — quick start, soft landing. */
  out: [0.16, 1, 0.3, 1] as const,
  /* Subtle ease-in-out for crossfades. */
  inOut: [0.45, 0, 0.55, 1] as const,
};

export const spring = {
  /* Calm spring: feels like paper, no overshoot. */
  paper: { type: 'spring' as const, stiffness: 220, damping: 28, mass: 0.9 },
  /* For column heights — slightly snappier so bars feel weighted. */
  bar: { type: 'spring' as const, stiffness: 180, damping: 24, mass: 1 },
};

// ── Tiny class-name helper ─────────────────────────────────────────────────
export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(' ');
}
