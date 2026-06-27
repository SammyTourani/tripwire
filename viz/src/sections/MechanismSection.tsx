import { motion, useScroll, useTransform } from 'motion/react';
import { useRef } from 'react';
import { ease } from '../lib/util';

interface Layer {
  id: 'L1' | 'L2' | 'L3' | 'L4';
  name: string;
  short: string;
  catches: string;
  detail: string;
  code: string;
}

const LAYERS: Layer[] = [
  {
    id: 'L1',
    name: 'Canonical correctness',
    short: 'is the answer the same on the test inputs?',
    catches:
      'Anything that is wrong on inputs the candidate was tested on. Exact comparison for structural targets; tolerance for numeric ones (correct vectorization changes the low bits — bitwise here would discard real speedups).',
    detail: 'L1',
    code: `for args in canonical_args:
    expected = reference(*args)
    got      = candidate(*args)
    if not close_equal(expected, got):
        return REJECTED("L1 canonical mismatch")`,
  },
  {
    id: 'L2',
    name: 'Metamorphic / property',
    short: 'does it obey invariants the real computation must satisfy?',
    catches:
      'Candidates that pass the canonical inputs but violate a known relationship — e.g. scale-equivariance, idempotence of normalization, parse↔serialize round-trip identity. Cheap, total, relational.',
    detail: 'L2',
    code: `for name, prop in target.properties:
    for args in canonical_args + withheld_args:
        if not prop(args, candidate(*args)):
            return REJECTED(f"L2 property '{name}' violated")`,
  },
  {
    id: 'L3',
    name: 'Differential on withheld inputs',
    short: 'is it still correct on adversarial inputs it has never seen?',
    catches:
      'Memorization. Skip-the-work. Distribution-conditioned wrongness. L3 tests against a fixed adversarial set AND a generative factory that draws fresh inputs under new random seeds each evaluation — so a candidate cannot overfit to the moat.',
    detail: 'L3 — the moat',
    code: `# fixed adversarial edges
for args in target.withheld_args:
    if not cmp(reference(*args), candidate(*args)):
        return REJECTED("L3 withheld-input differential mismatch")
# fresh adversarial draws (each eval, new random seed)
for args in target.withheld_factory(rng):
    if not cmp(reference(*args), candidate(*args)):
        return REJECTED("L3 withheld-input differential mismatch")`,
  },
  {
    id: 'L4',
    name: 'Isolated speedup',
    short: 'is the speed real after correctness has been proven?',
    catches:
      'Phantom improvements from timing noise. Near-infinite "speedups" (a red flag, not a winner). L4 measures with warmup, best-of-N across multiple shapes, and a 2σ variance bound; a wrong candidate has already been rejected — only honest speed is reported.',
    detail: 'L4',
    code: `# only reached if every correctness layer passed
return PASSED(
    speedup=measure_time(reference) / measure_time(candidate)
)`,
  },
];

/**
 * The mechanism section. A four-step diagram is pinned while the reader
 * scrolls; the active layer is bound to scroll progress. Each layer ships its
 * own caption + a small code excerpt so the reader sees exactly what catches
 * what. Pure exposition — no live data, just the design articulated.
 */
export function MechanismSection() {
  const ref = useRef<HTMLElement>(null);
  // Track scroll position within this section to drive the layer progress bar.
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ['start 50%', 'end 50%'],
  });
  // Convert 0..1 progress into 0..3 (active layer index).
  const progress = useTransform(scrollYProgress, [0, 1], [0, LAYERS.length - 0.001]);

  return (
    <section
      id="mechanism"
      ref={ref}
      className="relative border-t border-[color:var(--color-paper-3)] bg-[color:var(--color-paper-2)]/40"
    >
      <div className="mx-auto max-w-6xl px-6 py-24 lg:py-32">
        <div className="grid grid-cols-1 gap-y-10 lg:grid-cols-12 lg:gap-x-12">
          {/* Left: intro */}
          <div className="lg:col-span-5">
            <p className="label-eyebrow">§ 02 &nbsp; The mechanism</p>
            <h2 className="mt-4 font-display font-semibold text-[clamp(2rem,3.5vw,2.75rem)] leading-[1.05] tracking-tight text-balance">
              Four layers, each catching a specific failure mode.
            </h2>
            <div className="mt-7 space-y-5 max-w-prose text-[16.5px] leading-[1.7] text-[color:var(--color-ink-2)]">
              <p>
                Metamorphic testing, differential testing, and property-based testing are decades
                old. Tripwire does not claim to invent them. The contribution is the{' '}
                <em>composition</em>: four layers, ordered, adversarial-by-design, applied to the
                exact problem each was best at — assembled as a reusable evaluator for the
                dominant open optimization stack (OpenEvolve).
              </p>
              <p>
                The order is fixed. A correctness layer that fails short-circuits the rest with the
                failing layer named, so the evolutionary loop receives precise feedback on{' '}
                <em>why</em> a candidate was rejected — and ADR-006 holds: correctness failure
                zeroes the reward, so no gradient ever points toward cheating.
              </p>
            </div>
          </div>

          {/* Right: the four layers, with a scroll-driven progress rail */}
          <div className="lg:col-span-7">
            <div className="relative">
              {/* Vertical rail */}
              <div className="absolute left-[14px] top-0 bottom-0 w-px bg-[color:var(--color-paper-3)]" />
              <motion.div
                className="absolute left-[14px] top-0 w-px bg-[color:var(--color-ink)]"
                style={{ height: useTransform(scrollYProgress, [0, 1], ['0%', '100%']) }}
              />
              <div className="space-y-10">
                {LAYERS.map((layer, i) => (
                  <LayerCard key={layer.id} layer={layer} index={i} progress={progress} />
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function LayerCard({
  layer,
  index,
  progress,
}: {
  layer: Layer;
  index: number;
  progress: ReturnType<typeof useTransform<number, number>>;
}) {
  // Active when the scroll progress >= this layer's index.
  const opacity = useTransform(progress, [index - 0.5, index, index + 0.5], [0.4, 1, 1]);
  const lift = useTransform(progress, [index - 0.5, index], [4, 0]);

  return (
    <motion.div
      style={{ opacity, y: lift }}
      transition={{ duration: 0.3 }}
      className="relative pl-12"
    >
      {/* Numbered token sitting on the rail */}
      <div className="absolute left-0 top-1 flex items-center justify-center w-[29px] h-[29px] rounded-full bg-[color:var(--color-paper)] border border-[color:var(--color-paper-3)]">
        <span className="font-mono text-[11px] font-bold tracking-wider text-[color:var(--color-ink)]">
          {layer.id}
        </span>
      </div>
      <div className="rounded-xl border border-[color:var(--color-paper-3)] bg-white/70 backdrop-blur-sm overflow-hidden">
        <div className="p-5 pb-3">
          <p className="font-display font-semibold text-[20px] leading-tight tracking-tight">
            {layer.name}
          </p>
          <p className="text-[14px] text-[color:var(--color-ink-3)] italic mt-0.5">
            &mdash; {layer.short}
          </p>
          <p className="mt-3 text-[15px] leading-[1.6] text-[color:var(--color-ink-2)] max-w-prose">
            {layer.catches}
          </p>
        </div>
        <pre className="bg-[color:var(--color-paper-2)] border-t border-[color:var(--color-paper-3)] px-5 py-3 text-[12px] leading-[1.65] font-mono text-[color:var(--color-ink-2)] overflow-x-auto">
          <code>{layer.code}</code>
        </pre>
      </div>
    </motion.div>
  );
}

// "ease" import kept available for future use here.
void ease;
