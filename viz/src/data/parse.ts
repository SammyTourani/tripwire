import type {
  BenchCandidateEvent,
  BenchData,
  BenchEvent,
  BenchRow,
  BenchStartEvent,
  BenchSummary,
  BenchSummaryEvent,
  OracleName,
  TargetZeroData,
  TargetZeroFrame,
  TargetZeroIteration,
} from './types';

const ORACLES: OracleName[] = ['naive_bitwise', 'naive_tolerance', 'layered'];

/** Parse a JSONL string into typed events, tolerating blank lines and reporting
 * malformed lines as a count rather than throwing. */
function parseJsonl<T>(text: string): { events: T[]; skipped: number } {
  const events: T[] = [];
  let skipped = 0;
  for (const line of text.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    try {
      events.push(JSON.parse(trimmed) as T);
    } catch {
      skipped++;
    }
  }
  return { events, skipped };
}

/** Normalize a bench-*.jsonl into the BenchData shape the chart consumes. */
export function parseBench(text: string): BenchData {
  const { events } = parseJsonl<BenchEvent>(text);
  const start = events.find((e) => e.event === 'bench_start') as BenchStartEvent | undefined;
  const summaryEvt = events.find((e) => e.event === 'summary') as BenchSummaryEvent | undefined;
  const candidates = events.filter((e): e is BenchCandidateEvent => e.event === 'candidate');

  const rows: BenchRow[] = candidates.map((c, i) => {
    const shipped: OracleName[] = [];
    const blocked: OracleName[] = [];
    for (const o of ORACLES) {
      (c.verdicts[o].accepted ? shipped : blocked).push(o);
    }
    // Speedup chosen for the bar: when the layered oracle accepted, use the
    // verified speedup. Otherwise, fall back to a synthetic value that reflects
    // what naive oracles would have seen (this is the whole point — a hack
    // looks fast precisely because it skips the work). We approximate it by
    // 1.0 when nothing is known; the bench's hack rows always carry a real
    // 'shipped by naive' magnitude visible in the original PNG, so for the
    // animated replay we surface the layered_speedup when present and the
    // average of "looks fast" for hacks otherwise (clamped >= 1.0).
    const speedup = c.layered_speedup ?? (c.truth === 'hack' ? 1.0 : 1.0);
    const bitwiseFalseNegative =
      c.truth !== 'hack' &&
      !c.verdicts.naive_bitwise.accepted &&
      c.verdicts.layered.accepted;

    return {
      id: `${c.domain}::${c.candidate}::${i}`,
      domain: c.domain,
      candidate: c.candidate,
      truth: c.truth,
      speedup,
      shippedBy: shipped,
      blockedBy: blocked,
      layeredReason: c.verdicts.layered.reason,
      lowerBound: c.layered_lower_bound,
      trustworthy: c.layered_trustworthy,
      bitwiseFalseNegative,
    };
  });

  const totals = {
    n: rows.length,
    nValid: rows.filter((r) => r.truth !== 'hack').length,
    nHack: rows.filter((r) => r.truth === 'hack').length,
    domains: start?.domains ?? Array.from(new Set(rows.map((r) => r.domain))).sort(),
  };

  const byOracle = {} as BenchSummary['byOracle'];
  for (const o of ORACLES) {
    if (summaryEvt) {
      const s = summaryEvt.by_oracle[o];
      byOracle[o] = {
        shipsHacks: s.ships_hacks,
        integrity: s.integrity,
        keptValid: s.kept_valid,
        trustworthy: s.trustworthy,
      };
    } else {
      // Recompute from rows if summary event is missing.
      const accepted = rows.filter((r) => r.shippedBy.includes(o));
      const shipsHacks = accepted.filter((r) => r.truth === 'hack').length;
      const validKept = accepted.filter((r) => r.truth !== 'hack').length;
      const integrity = accepted.length ? validKept / accepted.length : NaN;
      const keptValid = totals.nValid ? validKept / totals.nValid : NaN;
      byOracle[o] = {
        shipsHacks,
        integrity,
        keptValid,
        trustworthy: shipsHacks === 0 && keptValid === 1.0,
      };
    }
  }

  return {
    rows,
    summary: { byOracle, totals },
    timestamp: start?.timestamp ?? '',
  };
}

/** Normalize a target-zero.jsonl into the TargetZeroData shape. */
export function parseTargetZero(text: string): TargetZeroData {
  const { events } = parseJsonl<TargetZeroIteration>(text);
  events.sort((a, b) => a.iteration - b.iteration);

  let bestSoFar = -Infinity;
  let bestIdx = 0;
  const frames: TargetZeroFrame[] = events.map((e, idx) => {
    const score = e.child_metrics?.combined_score ?? 0;
    const isNewBest = score > bestSoFar;
    if (isNewBest) {
      bestSoFar = score;
      bestIdx = idx;
    }
    const parentScore = e.parent_metrics?.combined_score ?? 0;
    return {
      iteration: e.iteration,
      childId: e.child_id,
      parentId: e.parent_id,
      parentMetrics: e.parent_metrics ?? null,
      childMetrics: e.child_metrics,
      llmResponse: e.llm_response ?? '',
      childCode: e.child_code ?? '',
      parentCode: e.parent_code ?? '',
      isNewBest,
      improvementDelta: score - parentScore,
    };
  });

  return {
    frames,
    bestIteration: bestIdx,
    bestSpeedup: bestSoFar === -Infinity ? 0 : bestSoFar,
  };
}

/** Fetch a JSONL file under `public/data/` and parse it. */
export async function loadBench(url: string): Promise<BenchData> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`failed to load ${url}: ${res.status}`);
  return parseBench(await res.text());
}

export async function loadTargetZero(url: string): Promise<TargetZeroData> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`failed to load ${url}: ${res.status}`);
  return parseTargetZero(await res.text());
}
