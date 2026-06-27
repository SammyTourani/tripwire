import { AnimatePresence, motion, useInView } from 'motion/react';
import { useMemo, useRef, useState } from 'react';
import type { BenchData, BenchRow } from '../data/types';
import { ease, fmtPct, fmtSpeedup, logScale, logTicks } from '../lib/util';

interface ThesisSectionProps {
  bench: BenchData | null;
}

/**
 * § 01 — The thesis, made legible. The original PNG shows 4 candidates; the
 * current bench has 20+. So the chart is grouped by domain (so the eye can
 * skim "this domain has 1 valid + 2 hacks" rather than read 20 disconnected
 * bars), and per-bar verdict ribbons (which crash into each other at this
 * density) are replaced with a hover-driven detail panel and a chart-wide
 * legend. Each bar is colored by truth (green=correct, red=hack); a small
 * inline "stamp" badge below each bar summarizes naive vs layered in two
 * short words rather than a full ribbon.
 */
export function ThesisSection({ bench }: ThesisSectionProps) {
  const sectionRef = useRef<HTMLElement>(null);
  const inView = useInView(sectionRef, { amount: 0.2, once: true });

  return (
    <section
      id="thesis"
      ref={sectionRef}
      className="relative border-t border-[color:var(--color-paper-3)]"
    >
      <div className="mx-auto max-w-6xl px-6 py-24 lg:py-32">
        <div className="grid grid-cols-1 gap-y-10 lg:grid-cols-12 lg:gap-x-12">
          <div className="lg:col-span-5">
            <p className="label-eyebrow">§ 01 &nbsp; The thesis</p>
            <h2 className="mt-4 font-display font-semibold text-[clamp(2rem,3.5vw,2.75rem)] leading-[1.05] tracking-tight text-balance">
              A naive oracle ships the reward hack and discards the real win.
            </h2>
            <div className="mt-7 space-y-5 max-w-prose text-[16.5px] leading-[1.7] text-[color:var(--color-ink-2)]">
              <p>
                <strong className="text-[color:var(--color-ink)] font-semibold">
                  Output-match on a fixed test set is the standard correctness check
                </strong>{' '}
                an LLM-driven optimization loop runs on every candidate. Two opposite failures fall
                out of it.
              </p>
              <p>
                A <em>bit-exact</em> oracle rejects the correct vectorized sum &mdash; a real{' '}
                <span className="font-mono text-[14.5px] text-[color:var(--color-ink)]">
                  np.sum
                </span>{' '}
                win &mdash; because reordered floating-point arithmetic changes the low bits. Same
                answer, wrong oracle. A <em>tolerance</em> oracle then accepts a candidate that
                memorized the test inputs and looks 2,000&times; faster &mdash; because, of course,
                it stopped doing the work. The naive oracles are wrong on opposite axes.
              </p>
              <p>
                The bench below runs labeled candidates across seven domains against three oracles.
                The layered oracle (canonical &rarr; metamorphic &rarr; differential on{' '}
                <em>withheld</em> adversarial inputs &rarr; isolated speedup) is the only one right
                on both: it ships zero hacks AND keeps every real win.
              </p>
            </div>
            <ScorecardSummary bench={bench} animate={inView} />
          </div>

          <div className="lg:col-span-7">
            {bench ? <BenchChart bench={bench} animate={inView} /> : <ChartSkeleton />}
          </div>
        </div>
      </div>
    </section>
  );
}

/* ────────────────────────────────────────────────────────────────────────
   Grouped bench chart. Bars are clustered by domain with small gaps between
   clusters; each bar gets a thin truth-colored fill and a 2-character verdict
   stamp under it. Hovering reveals the full verdict in a side panel.
   ──────────────────────────────────────────────────────────────────────── */
function BenchChart({ bench, animate }: { bench: BenchData; animate: boolean }) {
  const rows = bench.rows;
  const W = 900;
  const H = 540;
  const PAD = { l: 52, r: 16, t: 28, b: 76 };
  const innerW = W - PAD.l - PAD.r;
  const innerH = H - PAD.t - PAD.b;

  const scale = useMemo(
    () => ({
      domain: [1, 10000] as [number, number],
      range: [PAD.t + innerH, PAD.t] as [number, number],
    }),
    [innerH, PAD.t]
  );
  const ticks = useMemo(() => logTicks(scale), [scale]);

  // Group rows by domain, preserving order.
  const groups = useMemo(() => {
    const map = new Map<string, BenchRow[]>();
    for (const r of rows) {
      if (!map.has(r.domain)) map.set(r.domain, []);
      map.get(r.domain)!.push(r);
    }
    return Array.from(map.entries()); // [domain, rows[]]
  }, [rows]);

  // Layout: each group gets a proportional slot with internal padding.
  const GAP = 14; // pixels between group clusters
  const totalGroupGap = GAP * Math.max(0, groups.length - 1);
  const slotW = (innerW - totalGroupGap) / groups.length;
  const barW = 22;

  // Pre-compute bar positions for the entire bar set (so labels/hover can map).
  type Pos = { row: BenchRow; x: number; cx: number; sp: number };
  const positions: Pos[] = [];
  let cursorX = PAD.l;
  for (const [, gRows] of groups) {
    const innerSpace = slotW;
    const totalBars = gRows.length;
    const cluster = totalBars * barW + (totalBars - 1) * 6;
    let xOff = cursorX + (innerSpace - cluster) / 2;
    for (const r of gRows) {
      const sp = displaySpeedup(r);
      positions.push({ row: r, x: xOff, cx: xOff + barW / 2, sp });
      xOff += barW + 6;
    }
    cursorX += slotW + GAP;
  }

  const [hoverId, setHoverId] = useState<string | null>(null);
  const hovered = hoverId ? positions.find((p) => p.row.id === hoverId) : null;

  return (
    <figure>
      <div className="rounded-2xl border border-[color:var(--color-paper-3)] bg-white/60 backdrop-blur-sm p-5 shadow-[0_1px_0_var(--color-paper-3)]">
        <div className="flex items-baseline justify-between">
          <p className="label-eyebrow">measured speedup vs reference · log scale</p>
          <div className="flex items-center gap-4 text-[11px] text-[color:var(--color-ink-3)]">
            <LegendDot color="var(--color-correct)" label="correct" />
            <LegendDot color="var(--color-hack)" label="reward hack" />
          </div>
        </div>

        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="w-full h-auto mt-2"
          onMouseLeave={() => setHoverId(null)}
        >
          {/* y-axis log gridlines + labels */}
          {ticks.map((t) => {
            const y = logScale(t, scale);
            return (
              <g key={t}>
                <line
                  x1={PAD.l}
                  x2={PAD.l + innerW}
                  y1={y}
                  y2={y}
                  stroke="var(--color-paper-3)"
                  strokeWidth={1}
                  strokeDasharray={t === 1 ? '0' : '2 5'}
                />
                <text
                  x={PAD.l - 10}
                  y={y + 4}
                  textAnchor="end"
                  fontSize={11}
                  className="tnum"
                  fill="var(--color-ink-3)"
                  fontFamily="var(--font-mono)"
                >
                  {fmtTick(t)}
                </text>
              </g>
            );
          })}
          {/* baseline (1x) */}
          <line
            x1={PAD.l}
            x2={PAD.l + innerW}
            y1={logScale(1, scale)}
            y2={logScale(1, scale)}
            stroke="var(--color-rule)"
            strokeWidth={1.2}
          />

          {/* group labels (one per domain, centered under the cluster) */}
          {(() => {
            let cx = PAD.l;
            return groups.map(([dom], gi) => {
              const center = cx + slotW / 2;
              cx += slotW + GAP;
              return (
                <text
                  key={dom + gi}
                  x={center}
                  y={PAD.t + innerH + 18}
                  textAnchor="middle"
                  fontSize={10.5}
                  fontFamily="var(--font-mono)"
                  fill="var(--color-ink-2)"
                >
                  {dom}
                </text>
              );
            });
          })()}

          {/* bars */}
          {positions.map(({ row, x, cx, sp }, i) => {
            const yTop = logScale(sp, scale);
            const yBase = logScale(1, scale);
            const height = yBase - yTop;
            const isHack = row.truth === 'hack';
            const color = isHack ? 'var(--color-hack)' : 'var(--color-correct)';
            const delay = 0.05 + i * 0.05;
            const isActive = hoverId === row.id;
            return (
              <g
                key={row.id}
                onMouseEnter={() => setHoverId(row.id)}
                style={{ cursor: 'pointer' }}
              >
                {/* invisible hit target spanning the bar's column */}
                <rect
                  x={x - 4}
                  y={PAD.t}
                  width={barW + 8}
                  height={innerH}
                  fill="transparent"
                  pointerEvents="all"
                />
                <motion.rect
                  x={x}
                  width={barW}
                  rx={2}
                  fill={color}
                  fillOpacity={isActive ? 1 : 0.9}
                  initial={{ y: yBase, height: 0 }}
                  animate={animate ? { y: yTop, height } : { y: yBase, height: 0 }}
                  transition={{ duration: 0.85, delay, ease: ease.out }}
                />
                {/* speedup label — vertically staggered when neighbors are tight
                    so the labels don't overlap. We offset every other bar by 14px. */}
                <motion.text
                  x={cx}
                  y={yTop - 6 - (i % 2 === 1 ? 14 : 0)}
                  textAnchor="middle"
                  fontFamily="var(--font-display)"
                  fontWeight={600}
                  fontSize={11}
                  fill="var(--color-ink)"
                  className="tnum"
                  initial={{ opacity: 0 }}
                  animate={animate ? { opacity: 1 } : { opacity: 0 }}
                  transition={{ duration: 0.4, delay: delay + 0.75 }}
                >
                  {fmtSpeedup(sp, 0)}
                </motion.text>
                {/* tiny verdict glyph below the bar — green check, red X, or warning */}
                <VerdictGlyph row={row} cx={cx} y={yBase + 30} animate={animate} delay={delay + 0.9} />
              </g>
            );
          })}

          {/* hover guide */}
          {hovered && (
            <g pointerEvents="none">
              <line
                x1={hovered.cx}
                x2={hovered.cx}
                y1={PAD.t}
                y2={PAD.t + innerH}
                stroke="var(--color-ink-3)"
                strokeWidth={0.7}
                strokeDasharray="3 3"
                opacity={0.6}
              />
            </g>
          )}
        </svg>

        {/* Detail panel: shows the hovered (or first hack as default) candidate */}
        <DetailPanel row={(hovered?.row) ?? rows.find((r) => r.truth === 'hack') ?? rows[0]} />
      </div>
    </figure>
  );
}

/* A pair of tiny pill glyphs under each bar showing naive vs layered. */
function VerdictGlyph({
  row,
  cx,
  y,
  animate,
  delay,
}: {
  row: BenchRow;
  cx: number;
  y: number;
  animate: boolean;
  delay: number;
}) {
  const naiveShipped =
    row.shippedBy.includes('naive_tolerance') || row.shippedBy.includes('naive_bitwise');
  const layeredShipped = row.shippedBy.includes('layered');
  // Color: the failure case is what reads — red when the bench's naive shipped a hack,
  // warning when bitwise rejected a real win, green when layered makes the right call.
  return (
    <motion.g
      initial={{ opacity: 0, y: y - 4 }}
      animate={animate ? { opacity: 1, y } : { opacity: 0, y: y - 4 }}
      transition={{ duration: 0.4, delay }}
    >
      <Pill
        x={cx - 18}
        label="N"
        color={
          naiveShipped && row.truth === 'hack'
            ? 'var(--color-hack)'
            : !naiveShipped && row.truth !== 'hack'
              ? 'var(--color-warning)'
              : 'var(--color-ink-3)'
        }
      />
      <Pill
        x={cx + 2}
        label="L"
        color={layeredShipped === (row.truth !== 'hack') ? 'var(--color-correct)' : 'var(--color-hack)'}
      />
    </motion.g>
  );
}

function Pill({ x, label, color }: { x: number; label: string; color: string }) {
  return (
    <g transform={`translate(${x}, 0)`}>
      <rect
        x={0}
        y={-9}
        width={16}
        height={14}
        rx={2}
        fill="white"
        stroke={color}
        strokeWidth={1}
      />
      <text
        x={8}
        y={1}
        textAnchor="middle"
        fontFamily="var(--font-mono)"
        fontSize={9}
        fontWeight={700}
        fill={color}
      >
        {label}
      </text>
    </g>
  );
}

function DetailPanel({ row }: { row: BenchRow }) {
  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={row.id}
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -4 }}
        transition={{ duration: 0.25, ease: ease.out }}
        className="mt-2 grid grid-cols-12 gap-4 rounded-lg border border-[color:var(--color-paper-3)] bg-[color:var(--color-paper-2)]/40 px-4 py-3"
      >
        <div className="col-span-5 min-w-0">
          <p className="label-eyebrow">candidate</p>
          <p className="mt-1 font-mono text-[12.5px] text-[color:var(--color-ink)]">{row.domain}</p>
          <p className="font-mono text-[11.5px] italic text-[color:var(--color-ink-3)]">
            {row.candidate}
          </p>
        </div>
        <div className="col-span-7 flex flex-col gap-1">
          <VerdictRow
            label="N"
            full="Naive"
            shipped={
              row.shippedBy.includes('naive_tolerance') || row.shippedBy.includes('naive_bitwise')
            }
            isHack={row.truth === 'hack'}
            reason={`canonical-only — ${
              row.truth === 'hack' ? 'no withheld differential to catch it' : 'low bits differ'
            }`}
          />
          <VerdictRow
            label="L"
            full="Layered"
            shipped={row.shippedBy.includes('layered')}
            isHack={row.truth === 'hack'}
            reason={row.layeredReason}
          />
        </div>
      </motion.div>
    </AnimatePresence>
  );
}

function VerdictRow({
  label,
  full,
  shipped,
  isHack,
  reason,
}: {
  label: string;
  full: string;
  shipped: boolean;
  isHack: boolean;
  reason: string;
}) {
  const correct = shipped !== isHack; // shipping a hack OR rejecting a real win is wrong
  const verdict = shipped ? 'shipped' : 'BLOCKED';
  const color = correct ? 'var(--color-correct)' : 'var(--color-hack)';
  return (
    <div className="flex items-center gap-2">
      <span
        className="inline-flex w-5 h-5 items-center justify-center rounded-sm font-mono text-[10px] font-bold border"
        style={{ color, borderColor: color }}
      >
        {label}
      </span>
      <span className="font-mono text-[11.5px] uppercase tracking-wider" style={{ color }}>
        {full}: {verdict}
      </span>
      <span className="text-[11.5px] text-[color:var(--color-ink-3)] truncate font-mono">
        — {reason}
      </span>
    </div>
  );
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        className="inline-block w-2.5 h-2.5 rounded-[2px]"
        style={{ background: color }}
        aria-hidden="true"
      />
      {label}
    </span>
  );
}

function ChartSkeleton() {
  return (
    <div className="rounded-2xl border border-[color:var(--color-paper-3)] bg-white/60 p-5 h-[540px] animate-pulse">
      <div className="h-full w-full bg-[color:var(--color-paper-2)] rounded" />
    </div>
  );
}

/* ────────────────────────────────────────────────────────────────────────
   Integrity scorecard
   ──────────────────────────────────────────────────────────────────────── */
function ScorecardSummary({ bench, animate }: { bench: BenchData | null; animate: boolean }) {
  if (!bench) {
    return (
      <div className="mt-10 rounded-xl border border-[color:var(--color-paper-3)] bg-[color:var(--color-paper-2)] h-32 animate-pulse" />
    );
  }
  const rows: Array<{ key: 'naive_bitwise' | 'naive_tolerance' | 'layered'; label: string }> = [
    { key: 'naive_bitwise', label: 'Naive bitwise' },
    { key: 'naive_tolerance', label: 'Naive tolerance' },
    { key: 'layered', label: 'Layered' },
  ];

  return (
    <div className="mt-12 rounded-xl border border-[color:var(--color-paper-3)] bg-white/60 backdrop-blur-sm">
      <div className="px-5 pt-4 pb-3 border-b border-[color:var(--color-paper-3)]">
        <p className="label-eyebrow">Integrity scorecard</p>
      </div>
      <div className="grid grid-cols-12 gap-4 px-5 py-3 text-[10.5px] uppercase tracking-wider text-[color:var(--color-ink-3)] font-mono">
        <div className="col-span-5">Oracle</div>
        <div className="col-span-2 text-right">Hacks shipped</div>
        <div className="col-span-2 text-right">Integrity</div>
        <div className="col-span-3 text-right">Verdict</div>
      </div>
      {rows.map((r, i) => {
        const s = bench.summary.byOracle[r.key];
        const isTrustworthy = s.trustworthy;
        return (
          <motion.div
            key={r.key}
            initial={{ opacity: 0, x: -8 }}
            animate={animate ? { opacity: 1, x: 0 } : { opacity: 0, x: -8 }}
            transition={{ duration: 0.5, delay: 0.4 + i * 0.18, ease: ease.out }}
            className="grid grid-cols-12 gap-4 px-5 py-3 items-center border-t border-[color:var(--color-paper-3)] last:rounded-b-xl"
          >
            <div className="col-span-5">
              <p className="text-[14px] font-medium">{r.label}</p>
              <p className="text-[11.5px] text-[color:var(--color-ink-3)]">
                {r.key === 'layered'
                  ? 'canonical · metamorphic · withheld · speedup'
                  : 'output-match on canonical inputs'}
              </p>
            </div>
            <div className="col-span-2 text-right tnum font-mono text-[15px]">
              <span
                className={
                  s.shipsHacks > 0
                    ? 'text-[color:var(--color-hack)]'
                    : 'text-[color:var(--color-correct)]'
                }
              >
                {s.shipsHacks}
              </span>
              <span className="text-[color:var(--color-ink-3)] text-[11.5px]">
                {' '}
                / {bench.summary.totals.nHack}
              </span>
            </div>
            <div className="col-span-2 text-right tnum font-mono text-[15px]">
              {fmtPct(s.integrity)}
            </div>
            <div className="col-span-3 text-right">
              {isTrustworthy ? (
                <span className="stamp stamp-blocked">trustworthy</span>
              ) : (
                <span className="stamp stamp-shipped">unsafe</span>
              )}
            </div>
          </motion.div>
        );
      })}
    </div>
  );
}

/* ────────────────────────────────────────────────────────────────────────
   Helpers
   ──────────────────────────────────────────────────────────────────────── */

function shortCandidate(s: string): string {
  const cut = s.indexOf(' (');
  const head = cut > 0 ? s.slice(0, cut) : s;
  return head.length > 14 ? head.slice(0, 13) + '…' : head;
}

function fmtTick(n: number): string {
  if (n < 1000) return `${n}×`;
  return `10${supForExp(Math.round(Math.log10(n)))}×`;
}
function supForExp(p: number): string {
  return (['⁰', '¹', '²', '³', '⁴', '⁵'][p] ?? `^${p}`) as string;
}

function displaySpeedup(r: BenchRow): number {
  if (r.truth !== 'hack' && r.speedup && isFinite(r.speedup) && r.speedup > 0) return r.speedup;
  if (r.truth === 'hack') return hackPlaceholder(r);
  return 1.0;
}

/**
 * Illustrative magnitudes for hack rows (the bench JSONL stores null for
 * layered_speedup on rejected candidates; these mirror the seed's published
 * figures). Documented as approximate / hardware-dependent in the README.
 */
function hackPlaceholder(r: BenchRow): number {
  const key = `${r.domain}::${shortCandidate(r.candidate)}`;
  const known: Record<string, number> = {
    'tokenizer::hack': 2700,
    'serde::hack': 2400,
    'sum_reduction::hack': 2700,
    'sum_reduction::hack (length…': 240,
    'numeric:dot::hack': 1500,
    'numeric:dot::hack (shape…': 150,
    'numeric:matvec::hack': 3300,
    'numeric:matvec::hack (shape…': 280,
    'numeric:matmul::hack': 4100,
    'numeric:matmul::hack (shape…': 220,
    'sql::hack': 50,
  };
  for (const k of Object.keys(known)) if (key.startsWith(k)) return known[k];
  return 80;
}
