import { useEffect, useState } from 'react';
import type { BenchData, TargetZeroData } from './data/types';
import { loadBench, loadTargetZero } from './data/parse';
import { Hero } from './sections/Hero';
import { ThesisSection } from './sections/ThesisSection';
import { MechanismSection } from './sections/MechanismSection';
import { TargetZeroSection } from './sections/TargetZeroSection';
import { Outro } from './sections/Outro';
import { Nav } from './components/Nav';

/**
 * Page shell. Loads both JSONL artifacts (bench + target-zero), then composes
 * the editorial sections in order. Each section is self-contained and reads
 * only what it needs from the already-parsed data.
 *
 * Order of the argument, by design:
 *   1. Hero          — name the problem; quick visual demo of the failure mode.
 *   2. ThesisSection — the bench scorecard, animated bar-by-bar.
 *   3. MechanismSection — what the four oracle layers actually catch.
 *   4. TargetZeroSection — Claude in the live OpenEvolve loop, 10 iterations.
 *   5. Outro         — calibrated claim + repo link.
 */
export default function App() {
  const [bench, setBench] = useState<BenchData | null>(null);
  const [targetZero, setTargetZero] = useState<TargetZeroData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([loadBench('./data/bench.jsonl'), loadTargetZero('./data/target-zero.jsonl')])
      .then(([b, t]) => {
        if (cancelled) return;
        setBench(b);
        setTargetZero(t);
      })
      .catch((e: Error) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="min-h-screen">
      <Nav />
      <main>
        <Hero bench={bench} />
        <ThesisSection bench={bench} />
        <MechanismSection />
        <TargetZeroSection data={targetZero} />
        <Outro />
      </main>
      {error && (
        <div className="fixed bottom-4 right-4 max-w-sm rounded-lg border border-[var(--color-paper-3)] bg-white p-3 text-sm shadow">
          <p className="font-mono text-xs text-[var(--color-hack)]">data load failed</p>
          <p className="text-[var(--color-ink-2)]">{error}</p>
        </div>
      )}
    </div>
  );
}
