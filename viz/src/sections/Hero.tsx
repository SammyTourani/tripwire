import { motion, useReducedMotion } from 'motion/react';
import { useEffect, useState } from 'react';
import type { BenchData } from '../data/types';
import { ease } from '../lib/util';

interface HeroProps {
  bench: BenchData | null;
}

/**
 * The opening. We name the problem in one display sentence, anchor it with a
 * short paragraph, and run a small looped demonstration: a candidate's bar
 * climbs to a huge mirage speedup; the naive verdict stamps SHIPPED; then the
 * layered oracle's scan crosses the chart and re-stamps it BLOCKED with the
 * failing layer named. The demo is decorative for the argument, not data —
 * it's an opening title sequence.
 */
export function Hero({ bench: _bench }: HeroProps) {
  return (
    <section id="top" className="relative isolate pt-28 pb-24 lg:pt-32 lg:pb-32">
      <div className="mx-auto grid max-w-6xl grid-cols-1 gap-x-10 gap-y-10 px-6 lg:grid-cols-12">
        {/* Left: argument */}
        <div className="lg:col-span-6 lg:pt-6">
          <motion.p
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease: ease.out }}
            className="label-eyebrow"
          >
            Optimizer Integrity Bench &nbsp;·&nbsp; v0.1
          </motion.p>
          <motion.h1
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.05, ease: ease.out }}
            className="font-display font-semibold text-[clamp(1.95rem,3vw,2.7rem)] leading-[1.08] tracking-tight mt-4 text-balance"
          >
            AI code optimizers ship code that <em className="italic">looks</em> thousands of times faster.
          </motion.h1>
          <motion.h2
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.18, ease: ease.out }}
            className="font-display text-[clamp(1.95rem,3vw,2.7rem)] leading-[1.08] tracking-tight italic text-[color:var(--color-ink-2)] mt-1.5"
          >
            The code is wrong.
          </motion.h2>
          <motion.p
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.35, ease: ease.out }}
            className="mt-7 max-w-prose text-[17px] leading-[1.7] text-[color:var(--color-ink-2)]"
          >
            When the LLM-proposes &rarr; evaluate &rarr; keep-best loop is graded by a naive
            correctness check, the optimizer learns to defeat the check, not to optimize. The
            consequence has a name &mdash; reward hacking &mdash; and a documented track record. The
            consequence has another name when you look at the bars on the right: a 5,000&times;
            speedup that does no work.
          </motion.p>
          <motion.p
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.45, ease: ease.out }}
            className="mt-4 max-w-prose text-[17px] leading-[1.7] text-[color:var(--color-ink-2)]"
          >
            Tripwire is the part of the loop that catches them: a layered, adversarial-by-design
            correctness oracle, shipped as a drop-in OpenEvolve evaluator and a public benchmark
            that measures how often current AI optimizers actually ship wrong code.
          </motion.p>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.9, delay: 0.7 }}
            className="mt-10 flex items-center gap-5 text-[13px] text-[color:var(--color-ink-3)]"
          >
            <a
              href="#thesis"
              className="font-medium text-[color:var(--color-ink)] underline decoration-[color:var(--color-rule)] underline-offset-[6px] decoration-[1.5px] hover:decoration-[color:var(--color-ink-2)]"
            >
              See the bench &darr;
            </a>
            <span aria-hidden="true">·</span>
            <a
              href="#proof"
              className="hover:text-[color:var(--color-ink)]"
            >
              Or skip to Claude in the loop
            </a>
          </motion.div>
        </div>

        {/* Right: micro-demo */}
        <div className="lg:col-span-6">
          <MicroDemo />
        </div>
      </div>
    </section>
  );
}

/* ─────────────────────────────────────────────────────────────────────────
   The opening micro-demo. A single candidate's bar climbs to ~5000x while
   the naive oracle stamps it SHIPPED in green. Then the layered oracle's
   scan sweeps across (L1 -> L2 -> L3 -> L4) and the BLOCKED stamp slams
   over the SHIPPED one with the failing layer named. Loops every ~9s.
   ────────────────────────────────────────────────────────────────────────── */
function MicroDemo() {
  const reduceMotion = useReducedMotion();
  // Start at phase 4 (settled BLOCKED state) so the demo is meaningful even
  // before the loop starts or in reduced-motion mode. The loop then advances.
  const [phase, setPhase] = useState<0 | 1 | 2 | 3 | 4>(4);

  useEffect(() => {
    if (reduceMotion) {
      setPhase(4);
      return;
    }
    // Hold the initial BLOCKED state ~3s, then begin the loop.
    const seq: Array<{ to: 0 | 1 | 2 | 3 | 4; after: number }> = [
      { to: 0, after: 700 },  // brief blank
      { to: 1, after: 400 },  // bar grows
      { to: 2, after: 1700 }, // naive stamps SHIPPED
      { to: 3, after: 1100 }, // layered scan
      { to: 4, after: 1100 }, // BLOCKED stamp
      { to: 4, after: 2900 }, // hold
    ];
    let i = 0;
    let timer: number | undefined;
    const tick = () => {
      const step = seq[i];
      setPhase(step.to);
      i = (i + 1) % seq.length;
      timer = window.setTimeout(tick, step.after);
    };
    timer = window.setTimeout(tick, 3000); // initial hold on phase 4
    return () => {
      if (timer) clearTimeout(timer);
    };
  }, [reduceMotion]);

  // Bar reaches a 5000x speedup on a log scale 1..10000 -> ~92% of the height.
  const W = 480;
  const H = 360;
  const PAD = { l: 56, r: 16, t: 24, b: 36 };
  const innerW = W - PAD.l - PAD.r;
  const innerH = H - PAD.t - PAD.b;
  // log10(5000)/log10(10000) = 3.6989/4 = 0.9247
  const targetT = Math.log10(5000) / Math.log10(10000);
  const barHeight = innerH * targetT;
  const showBar = phase >= 1;
  const showShipped = phase >= 2 && phase < 4;
  const showScan = phase === 3;
  const showBlocked = phase >= 4;

  return (
    <div className="relative">
      <div className="rounded-2xl border border-[color:var(--color-paper-3)] bg-white/60 backdrop-blur-sm p-5 shadow-[0_1px_0_var(--color-paper-3)]">
        <div className="flex items-baseline justify-between mb-3">
          <p className="label-eyebrow">a single candidate</p>
          <p className="font-mono text-[11px] text-[color:var(--color-ink-3)]">
            domain: word_frequency · candidate: memorized
          </p>
        </div>
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto">
          {/* y-axis: log-scale grid lines + labels (1, 10, 100, 1000, 10000) */}
          {[0, 1, 2, 3, 4].map((p) => {
            const y = PAD.t + innerH * (1 - p / 4);
            return (
              <g key={p}>
                <line
                  x1={PAD.l}
                  x2={PAD.l + innerW}
                  y1={y}
                  y2={y}
                  stroke="var(--color-paper-3)"
                  strokeWidth={1}
                  strokeDasharray={p === 0 ? '0' : '2 4'}
                />
                <text
                  x={PAD.l - 10}
                  y={y + 4}
                  textAnchor="end"
                  className="tnum"
                  fontSize={11}
                  fill="var(--color-ink-3)"
                >
                  {p === 0 ? '1×' : `10${supForExp(p)}`}
                </text>
              </g>
            );
          })}

          {/* baseline reference line */}
          <line
            x1={PAD.l}
            x2={PAD.l + innerW}
            y1={PAD.t + innerH}
            y2={PAD.t + innerH}
            stroke="var(--color-rule)"
            strokeWidth={1}
          />

          {/* the bar */}
          <motion.rect
            x={PAD.l + innerW / 2 - 64}
            initial={{ height: 0, y: PAD.t + innerH }}
            animate={
              showBar
                ? { height: barHeight, y: PAD.t + innerH - barHeight }
                : { height: 0, y: PAD.t + innerH }
            }
            transition={{ duration: 1.4, ease: ease.out }}
            width={128}
            rx={2}
            fill="var(--color-hack)"
            opacity={0.92}
          />
          {/* speedup label above the bar */}
          <motion.text
            x={PAD.l + innerW / 2}
            y={PAD.t + innerH - barHeight - 10}
            textAnchor="middle"
            fontFamily="var(--font-display)"
            fontWeight={600}
            fontSize={22}
            fill="var(--color-ink)"
            initial={{ opacity: 0, y: PAD.t + innerH - 10 }}
            animate={
              showBar
                ? { opacity: 1, y: PAD.t + innerH - barHeight - 10 }
                : { opacity: 0, y: PAD.t + innerH - 10 }
            }
            transition={{ duration: 1.2, ease: ease.out }}
            className="tnum"
          >
            5,000×
          </motion.text>

          {/* the layered oracle's scan: a sweep across the chart, layer-by-layer */}
          {showScan && (
            <motion.g
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.2 }}
            >
              <motion.line
                x1={PAD.l}
                x2={PAD.l}
                y1={PAD.t}
                y2={PAD.t + innerH}
                stroke="var(--color-accent)"
                strokeWidth={1.5}
                animate={{ x1: PAD.l + innerW, x2: PAD.l + innerW }}
                transition={{ duration: 1, ease: ease.inOut }}
              />
              {/* layer ticks visible during the scan */}
              {['L1', 'L2', 'L3', 'L4'].map((lbl, i) => (
                <motion.text
                  key={lbl}
                  x={PAD.l + ((i + 0.5) / 4) * innerW}
                  y={PAD.t + 14}
                  textAnchor="middle"
                  fontSize={10}
                  fontFamily="var(--font-mono)"
                  fontWeight={600}
                  fill="var(--color-accent)"
                  initial={{ opacity: 0, y: PAD.t + 4 }}
                  animate={{ opacity: 1, y: PAD.t + 14 }}
                  transition={{ duration: 0.4, delay: i * 0.18, ease: ease.out }}
                >
                  {lbl}
                </motion.text>
              ))}
            </motion.g>
          )}

          {/* SHIPPED stamp (sits over the bar while naive holds the verdict).
              We position with translate via style for predictable Motion behavior
              (animating transform attribute directly fights Motion's transform). */}
          {showShipped && (
            <motion.g
              initial={{ opacity: 0, scale: 0.7 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.3, ease: ease.out }}
              style={{
                transformOrigin: `${PAD.l + innerW / 2}px ${PAD.t + innerH * 0.55}px`,
              }}
            >
              <rect
                x={PAD.l + innerW / 2 - 72}
                y={PAD.t + innerH * 0.55 - 18}
                width={144}
                height={36}
                rx={3}
                fill="var(--color-hack-2)"
                stroke="var(--color-hack)"
                strokeWidth={1.5}
              />
              <text
                x={PAD.l + innerW / 2}
                y={PAD.t + innerH * 0.55 + 6}
                textAnchor="middle"
                fontFamily="var(--font-mono)"
                fontWeight={600}
                fontSize={13}
                fill="var(--color-hack)"
                letterSpacing="0.06em"
              >
                NAIVE: SHIPPED
              </text>
            </motion.g>
          )}

          {/* BLOCKED stamp (slams in once the layered oracle judges) */}
          {showBlocked && (
            <motion.g
              initial={{ opacity: 0, scale: 1.4 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.45, ease: ease.out }}
              style={{
                transformOrigin: `${PAD.l + innerW / 2}px ${PAD.t + innerH * 0.55}px`,
              }}
            >
              <rect
                x={PAD.l + innerW / 2 - 92}
                y={PAD.t + innerH * 0.55 - 22}
                width={184}
                height={44}
                rx={3}
                fill="var(--color-correct-2)"
                stroke="var(--color-correct)"
                strokeWidth={1.8}
              />
              <text
                x={PAD.l + innerW / 2}
                y={PAD.t + innerH * 0.55 - 1}
                textAnchor="middle"
                fontFamily="var(--font-mono)"
                fontWeight={700}
                fontSize={13}
                fill="var(--color-correct)"
                letterSpacing="0.08em"
              >
                LAYERED: BLOCKED
              </text>
              <text
                x={PAD.l + innerW / 2}
                y={PAD.t + innerH * 0.55 + 14}
                textAnchor="middle"
                fontFamily="var(--font-mono)"
                fontSize={10}
                fill="var(--color-correct)"
                opacity={0.85}
              >
                L3 — withheld-input differential
              </text>
            </motion.g>
          )}
        </svg>
        <div className="mt-2 flex items-center justify-between text-[11px] font-mono text-[color:var(--color-ink-3)]">
          <span>measured speedup vs reference · log scale</span>
          <PhaseLabel phase={phase} />
        </div>
      </div>
    </div>
  );
}

function PhaseLabel({ phase }: { phase: number }) {
  const text =
    phase === 0
      ? '· awaiting candidate'
      : phase === 1
        ? '· measuring speedup'
        : phase === 2
          ? '· naive oracle accepting'
          : phase === 3
            ? '· layered oracle scanning'
            : '· verdict in';
  return <span>{text}</span>;
}

/** Tiny helper for "10^n" labels using superscript glyphs. */
function supForExp(p: number): string {
  const supers = ['⁰', '¹', '²', '³', '⁴', '⁵'];
  return supers[p] ?? `^${p}`;
}
