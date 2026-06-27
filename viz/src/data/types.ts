/**
 * Typed model of the two JSONL formats the visualizer replays. These types
 * mirror what the Python side actually emits — see `bench/run.py::write_jsonl`
 * and OpenEvolve's evolution-trace records.
 *
 * The visualizer never mutates the underlying file; it consumes these records
 * and normalizes them into a single, view-friendly timeline.
 */

// ── bench/run.py emits these events ────────────────────────────────────────
export interface BenchStartEvent {
  event: 'bench_start';
  timestamp: string;
  domains: string[];
  n_candidates: number;
}

export type Truth = 'correct' | 'correct_fp' | 'hack';
export type OracleName = 'naive_bitwise' | 'naive_tolerance' | 'layered';

export interface OracleVerdict {
  accepted: boolean;
  reason: string;
}

export interface BenchCandidateEvent {
  event: 'candidate';
  domain: string;
  target: string;
  candidate: string;
  truth: Truth;
  verdicts: Record<OracleName, OracleVerdict>;
  layered_speedup: number | null;
  layered_lower_bound: number | null;
  layered_trustworthy: boolean;
}

export interface BenchSummaryEvent {
  event: 'summary';
  by_oracle: Record<
    OracleName,
    {
      ships_hacks: number;
      integrity: number;
      kept_valid: number;
      trustworthy: boolean;
    }
  >;
}

export type BenchEvent = BenchStartEvent | BenchCandidateEvent | BenchSummaryEvent;

// ── OpenEvolve's evolution_trace.jsonl ─────────────────────────────────────
// Each line is one optimization iteration. We only consume the fields we show.
export interface ChildMetrics {
  combined_score: number;
  correct: number;
  speedup: number;
  reason: string;
}

export interface TargetZeroIteration {
  iteration: number;
  timestamp: string;
  generation: number;
  island_id: number;
  parent_id: string;
  child_id: string;
  parent_code?: string;
  child_code: string;
  llm_response: string;
  prompt?: string;
  parent_metrics?: ChildMetrics | null;
  child_metrics: ChildMetrics;
  improvement_delta?: Record<string, number> | null;
  parent_changes_description?: string;
  metadata?: Record<string, unknown>;
}

// ── Unified, view-friendly normalization ───────────────────────────────────
/** What the bar chart actually plots. One row per candidate. */
export interface BenchRow {
  id: string;
  domain: string;
  candidate: string;
  truth: Truth;
  // Speedup as it would appear in the original PNG: ratio vs reference, on a log scale.
  speedup: number; // 1.0 when not credited or rejected
  // Per-oracle outcomes — drives the "naive: SHIPPED / layered: BLOCKED" stamps.
  shippedBy: OracleName[]; // oracles that accepted this candidate
  blockedBy: OracleName[]; // oracles that rejected it
  // Why the layered oracle decided what it did (the failing layer, or "passed all layers").
  layeredReason: string;
  // Variance bound (when present).
  lowerBound: number | null;
  trustworthy: boolean;
  // The damning case: a real win the BITWISE oracle wrongly discarded
  // (true iff layered accepted, naive_bitwise rejected). Used to highlight the
  // false-negative axis the project also defends.
  bitwiseFalseNegative: boolean;
}

export interface BenchSummary {
  byOracle: Record<
    OracleName,
    { shipsHacks: number; integrity: number; keptValid: number; trustworthy: boolean }
  >;
  totals: { n: number; nValid: number; nHack: number; domains: string[] };
}

export interface BenchData {
  rows: BenchRow[];
  summary: BenchSummary;
  timestamp: string;
}

/** Streaming-friendly slice of a target-zero iteration. */
export interface TargetZeroFrame {
  iteration: number;
  childId: string;
  parentId: string;
  parentMetrics: ChildMetrics | null;
  childMetrics: ChildMetrics;
  // Claude's analysis text (the visible reasoning).
  llmResponse: string;
  // The actual emitted code; we render with syntax highlighting in the UI.
  childCode: string;
  parentCode: string;
  // Convenience: did THIS iteration improve over the running best?
  isNewBest: boolean;
  // Convenience: speedup delta vs the parent (signed).
  improvementDelta: number;
}

export interface TargetZeroData {
  frames: TargetZeroFrame[];
  bestIteration: number; // index into frames
  bestSpeedup: number;
}
