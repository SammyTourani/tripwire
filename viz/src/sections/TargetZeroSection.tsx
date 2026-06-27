import { AnimatePresence, motion, useInView } from 'motion/react';
import { useEffect, useMemo, useRef, useState } from 'react';
import type { TargetZeroData, TargetZeroFrame } from '../data/types';
import { ease, fmtSpeedup } from '../lib/util';

interface TargetZeroSectionProps {
  data: TargetZeroData | null;
}

/**
 * § Proof. The COMPILOT-inspired live run: Claude (via the LiteLLM proxy) as
 * the proposer, OpenEvolve as the loop, Tripwire's layered oracle as the
 * verifier. Replays the captured runs/target-zero.jsonl trace: per iteration
 * we show Claude's reasoning, the emitted code, the oracle's verdict, and the
 * running best.
 *
 * The auto-advance uses a hand-tuned cadence: 5s on iterations that move the
 * best, 3s otherwise. Reader can pause/scrub freely.
 */
export function TargetZeroSection({ data }: TargetZeroSectionProps) {
  const ref = useRef<HTMLElement>(null);
  const inView = useInView(ref, { amount: 0.2, once: false });
  const [active, setActive] = useState(0);
  const [playing, setPlaying] = useState(false);

  // Begin playing the first time the section enters view (and the data is ready).
  useEffect(() => {
    if (inView && data && !playing) setPlaying(true);
  }, [inView, data, playing]);

  // Auto-advance.
  useEffect(() => {
    if (!playing || !data) return;
    const cur = data.frames[active];
    const dwell = cur?.isNewBest ? 5200 : 3200;
    const id = window.setTimeout(() => {
      if (active < data.frames.length - 1) {
        setActive((a) => a + 1);
      } else {
        setPlaying(false);
      }
    }, dwell);
    return () => clearTimeout(id);
  }, [active, playing, data]);

  return (
    <section
      id="proof"
      ref={ref}
      className="relative border-t border-[color:var(--color-paper-3)]"
    >
      <div className="mx-auto max-w-6xl px-6 py-24 lg:py-32">
        <div className="grid grid-cols-1 gap-y-10 lg:grid-cols-12 lg:gap-x-12">
          <div className="lg:col-span-5">
            <p className="label-eyebrow">§ 03 &nbsp; The proof</p>
            <h2 className="mt-4 font-display font-semibold text-[clamp(2rem,3.5vw,2.75rem)] leading-[1.05] tracking-tight text-balance">
              Claude in an OpenEvolve loop, judged by the layered oracle.
            </h2>
            <div className="mt-7 space-y-5 max-w-prose text-[16.5px] leading-[1.7] text-[color:var(--color-ink-2)]">
              <p>
                The anchor paper (COMPILOT, PACT '25) evaluates eight LLMs as code-optimization
                agents but never an Anthropic model. We wire Tripwire's layered oracle to
                OpenEvolve, point the loop at Claude Opus 4.8, and let it optimize a numeric
                kernel.
              </p>
              <p>
                <em>This is COMPILOT-inspired, not a reproduction.</em> COMPILOT optimizes C loop
                nests via the Tiramisu polyhedral compiler with formal legality checking; we
                optimize Python via the empirical layered oracle. We reproduce the{' '}
                <em>principle</em> (RQ7: delegate correctness to a rigorous verifier), not the
                system.
              </p>
              <p>
                The replay below is the actual{' '}
                <span className="font-mono text-[14.5px] text-[color:var(--color-ink)]">
                  runs/target-zero.jsonl
                </span>{' '}
                — Claude's analysis text, the candidate code it emitted, and the oracle's verdict
                per iteration. Every iteration cleared every layer; the best candidate Claude
                discovered was{' '}
                <span className="font-mono text-[14.5px]">
                  float(np.asarray(arr, dtype=np.float64).sum())
                </span>
                .
              </p>
            </div>
            {data && (
              <RunStats data={data} />
            )}
          </div>

          <div className="lg:col-span-7">
            {data ? (
              <Replay
                data={data}
                active={active}
                setActive={setActive}
                playing={playing}
                setPlaying={setPlaying}
              />
            ) : (
              <div className="rounded-2xl border border-[color:var(--color-paper-3)] bg-white/60 h-[600px] animate-pulse" />
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

/* ────────────────────────────────────────────────────────────────────────
   Replay UI
   ──────────────────────────────────────────────────────────────────────── */

function Replay({
  data,
  active,
  setActive,
  playing,
  setPlaying,
}: {
  data: TargetZeroData;
  active: number;
  setActive: (n: number) => void;
  playing: boolean;
  setPlaying: (b: boolean) => void;
}) {
  const cur = data.frames[active];
  return (
    <div className="rounded-2xl border border-[color:var(--color-paper-3)] bg-white/70 backdrop-blur-sm overflow-hidden shadow-[0_1px_0_var(--color-paper-3)]">
      {/* Header / timeline */}
      <div className="px-5 pt-4 pb-3 border-b border-[color:var(--color-paper-3)] bg-[color:var(--color-paper-2)]/50">
        <div className="flex items-center justify-between">
          <p className="label-eyebrow">runs / target-zero.jsonl</p>
          <PlayPause playing={playing} onToggle={() => setPlaying(!playing)} />
        </div>
        <Timeline data={data} active={active} onSeek={setActive} />
      </div>
      {/* Now-playing pane */}
      <div className="grid grid-cols-12 gap-0">
        {/* Reasoning */}
        <div className="col-span-12 md:col-span-7 p-5 border-r-0 md:border-r border-[color:var(--color-paper-3)]">
          <FrameReasoning frame={cur} />
        </div>
        {/* Code + verdict */}
        <div className="col-span-12 md:col-span-5 p-5 bg-[color:var(--color-paper-2)]/30 border-t md:border-t-0 border-[color:var(--color-paper-3)]">
          <FrameVerdict frame={cur} />
        </div>
      </div>
    </div>
  );
}

function Timeline({
  data,
  active,
  onSeek,
}: {
  data: TargetZeroData;
  active: number;
  onSeek: (n: number) => void;
}) {
  const max = useMemo(
    () => Math.max(...data.frames.map((f) => f.childMetrics.combined_score || 0)),
    [data]
  );
  return (
    <div className="mt-3 flex items-end gap-1.5">
      {data.frames.map((f, i) => {
        const score = f.childMetrics.combined_score || 0;
        const h = max > 0 ? Math.max(6, Math.round((score / max) * 36)) : 6;
        const isActive = i === active;
        const isBest = i === data.bestIteration;
        return (
          <button
            key={f.childId}
            onClick={() => onSeek(i)}
            aria-label={`Seek to iteration ${f.iteration}`}
            className="group flex flex-col items-center gap-1 focus:outline-none"
          >
            <div className="text-[10px] font-mono text-[color:var(--color-ink-3)]">
              {isActive ? f.iteration : ''}
            </div>
            <motion.div
              className="w-3.5 rounded-sm"
              style={{
                background: isBest
                  ? 'var(--color-correct)'
                  : isActive
                    ? 'var(--color-ink)'
                    : 'var(--color-ink-3)',
                opacity: isActive ? 1 : isBest ? 0.9 : 0.45,
              }}
              animate={{ height: h }}
              transition={{ duration: 0.4, ease: ease.out }}
            />
            <div className="text-[9.5px] font-mono text-[color:var(--color-ink-3)]">
              {i + 1}
            </div>
          </button>
        );
      })}
    </div>
  );
}

function PlayPause({ playing, onToggle }: { playing: boolean; onToggle: () => void }) {
  return (
    <button
      onClick={onToggle}
      className="inline-flex items-center gap-1.5 rounded-full border border-[color:var(--color-paper-3)] bg-white px-2.5 py-1 text-[11px] font-mono font-medium text-[color:var(--color-ink-2)] hover:text-[color:var(--color-ink)]"
    >
      {playing ? (
        <>
          <span className="w-2 h-2.5 inline-flex">
            <span className="w-[3px] h-full bg-current mr-[2px]" />
            <span className="w-[3px] h-full bg-current" />
          </span>
          pause
        </>
      ) : (
        <>
          <span
            className="w-0 h-0"
            style={{
              borderTop: '5px solid transparent',
              borderBottom: '5px solid transparent',
              borderLeft: '7px solid currentColor',
            }}
          />
          play
        </>
      )}
    </button>
  );
}

function FrameReasoning({ frame }: { frame: TargetZeroFrame }) {
  // Claude's analysis is a markdown-ish prose paragraph. We render it as-is
  // but slice into intro + remainder so the "headline" reads big.
  const text = frame.llmResponse || '';
  // Heuristic: split on first \n\n.
  const [head, ...rest] = text.split(/\n{2,}/);
  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={frame.childId}
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -6 }}
        transition={{ duration: 0.5, ease: ease.out }}
        className="space-y-3"
      >
        <div className="flex items-baseline gap-3">
          <p className="font-mono text-[10.5px] uppercase tracking-wider text-[color:var(--color-ink-3)]">
            Iteration {frame.iteration} · Claude · Opus 4.8
          </p>
          {frame.isNewBest && (
            <span className="stamp stamp-blocked">new best</span>
          )}
        </div>
        <p className="font-display text-[18px] leading-[1.45] tracking-tight text-[color:var(--color-ink)]">
          {clip(head, 240)}
        </p>
        {rest.length > 0 && (
          <p className="text-[14px] leading-[1.7] text-[color:var(--color-ink-2)] max-w-prose">
            {clip(rest.join('\n\n'), 600)}
          </p>
        )}
      </motion.div>
    </AnimatePresence>
  );
}

function FrameVerdict({ frame }: { frame: TargetZeroFrame }) {
  const m = frame.childMetrics;
  const passed = (m.correct ?? 0) >= 1;
  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={frame.childId}
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -4 }}
        transition={{ duration: 0.4, ease: ease.out }}
      >
        <p className="label-eyebrow mb-2">Oracle verdict</p>
        <div className="flex items-baseline gap-3">
          <p className="font-display tnum font-semibold text-[40px] leading-none tracking-tight">
            {fmtSpeedup(m.speedup, 1)}
          </p>
          {passed ? (
            <span className="stamp stamp-blocked">layered: shipped</span>
          ) : (
            <span className="stamp stamp-rejected">layered: BLOCKED</span>
          )}
        </div>
        <p className="mt-1 text-[12.5px] font-mono text-[color:var(--color-ink-3)]">
          {m.reason}
        </p>
        <p className="mt-5 label-eyebrow mb-1.5">Child code (truncated)</p>
        <pre className="bg-white border border-[color:var(--color-paper-3)] rounded-md px-3 py-2 text-[11px] leading-[1.55] font-mono text-[color:var(--color-ink-2)] overflow-auto max-h-[180px] whitespace-pre-wrap break-all">
          <code>{extractSolve(frame.childCode)}</code>
        </pre>
      </motion.div>
    </AnimatePresence>
  );
}

function RunStats({ data }: { data: TargetZeroData }) {
  return (
    <div className="mt-10 rounded-xl border border-[color:var(--color-paper-3)] bg-white/60 backdrop-blur-sm grid grid-cols-3">
      <Stat label="iterations" value={`${data.frames.length}`} />
      <Stat
        label="best speedup"
        value={fmtSpeedup(data.bestSpeedup, 0)}
        accent
      />
      <Stat
        label="improvement rate"
        value={`${Math.round((data.frames.filter((f) => f.isNewBest).length / Math.max(1, data.frames.length)) * 100)}%`}
      />
    </div>
  );
}

function Stat({ label, value, accent = false }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="p-4 border-r last:border-r-0 border-[color:var(--color-paper-3)]">
      <p className="label-eyebrow">{label}</p>
      <p
        className={
          'mt-1.5 font-display font-semibold tnum tracking-tight text-[28px] leading-none ' +
          (accent ? 'text-[color:var(--color-correct)]' : 'text-[color:var(--color-ink)]')
        }
      >
        {value}
      </p>
    </div>
  );
}

/* ────────────────────────────────────────────────────────────────────────
   Tiny helpers
   ──────────────────────────────────────────────────────────────────────── */
function clip(s: string, n: number): string {
  if (s.length <= n) return s;
  return s.slice(0, n - 1).trimEnd() + '…';
}

/** Try to show only the `solve` function from the candidate code, since the
 * full program has comments and an EVOLVE-BLOCK header. */
function extractSolve(code: string): string {
  if (!code) return '';
  // Prefer the EVOLVE-BLOCK contents; if none, find the first `def solve`.
  const between = code.match(/EVOLVE-BLOCK-START[\s\S]*?EVOLVE-BLOCK-END/);
  if (between) {
    const lines = between[0].split('\n');
    // drop the marker lines
    return lines.slice(1, -1).join('\n');
  }
  const idx = code.indexOf('def solve');
  if (idx >= 0) return code.slice(idx);
  return code;
}
