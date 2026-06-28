// Small shared helpers for the hand-rolled SVG charts.

export function log10(v: number) {
  return Math.log(v) / Math.LN10;
}

// fraction [0..1] of a value on a log axis from `min` to `max`
export function logFrac(v: number, min: number, max: number) {
  const lo = log10(min);
  const hi = log10(max);
  return (log10(Math.max(min, v)) - lo) / (hi - lo);
}

export function fmtSpeedup(n: number) {
  if (n >= 1000) return Math.round(n).toLocaleString("en-US") + "×";
  if (n >= 100) return Math.round(n) + "×";
  if (n >= 10) return n.toFixed(0) + "×";
  return n.toFixed(1) + "×";
}

export function fmtTokens(n: number) {
  if (n >= 1000) return Math.round(n / 1000) + "k";
  return String(n);
}

// nice log tick values within [min,max]
export function logTicks(min: number, max: number): number[] {
  const ticks: number[] = [];
  for (let e = Math.floor(log10(min)); e <= Math.ceil(log10(max)); e++) {
    ticks.push(Math.pow(10, e));
  }
  return ticks.filter((t) => t >= min && t <= max);
}
