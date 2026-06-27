import { useEffect, useState } from 'react';
import { motion } from 'motion/react';
import { cx } from '../lib/util';

const SECTIONS = [
  { id: 'top', label: 'Top' },
  { id: 'thesis', label: 'Thesis' },
  { id: 'mechanism', label: 'Mechanism' },
  { id: 'proof', label: 'Proof' },
] as const;

/**
 * A quiet top-of-page navigator: it sits centered, dims while scrolling, and
 * marks the active section. The aesthetic is closer to research-blog chrome
 * than tech-marketing chrome.
 */
export function Nav() {
  const [activeId, setActiveId] = useState<string>('top');

  useEffect(() => {
    const onScroll = () => {
      let best: { id: string; top: number } | null = null;
      for (const s of SECTIONS) {
        const el = document.getElementById(s.id);
        if (!el) continue;
        const top = el.getBoundingClientRect().top;
        // Pick the section whose top is closest to (but not past) 120px from the top.
        if (top <= 200 && (best === null || top > best.top)) {
          best = { id: s.id, top };
        }
      }
      if (best) setActiveId(best.id);
    };
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  return (
    <motion.header
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6, delay: 0.2, ease: [0.16, 1, 0.3, 1] }}
      className="fixed top-0 left-0 right-0 z-50 backdrop-blur-md bg-[color:var(--color-paper)]/70 border-b border-[color:var(--color-paper-3)]"
    >
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 sm:px-6 py-3">
        <a href="#top" className="flex items-center gap-2.5 group shrink-0">
          <Mark />
          <span className="font-display font-semibold text-[15px] tracking-tight text-[color:var(--color-ink)]">
            Tripwire
          </span>
        </a>
        <nav className="flex items-center gap-0.5 sm:gap-1">
          {SECTIONS.slice(1).map((s) => (
            <a
              key={s.id}
              href={`#${s.id}`}
              className={cx(
                'rounded-full px-2.5 sm:px-3 py-1.5 text-[12.5px] sm:text-[13px] font-medium transition-colors',
                activeId === s.id
                  ? 'bg-[color:var(--color-ink)] text-[color:var(--color-paper)]'
                  : 'text-[color:var(--color-ink-2)] hover:text-[color:var(--color-ink)]'
              )}
            >
              {s.label}
            </a>
          ))}
          <a
            href="https://github.com/SammyTourani/tripwire"
            target="_blank"
            rel="noreferrer"
            className="ml-1 sm:ml-2 rounded-full px-2.5 sm:px-3 py-1.5 text-[13px] font-medium text-[color:var(--color-ink-2)] hover:text-[color:var(--color-ink)] flex items-center gap-1.5"
            aria-label="View on GitHub"
          >
            <GitHub />
            <span className="hidden sm:inline">GitHub</span>
          </a>
        </nav>
      </div>
    </motion.header>
  );
}

/* A wordmark mark. A small filled circle (the "tripwire" dot) with a diagonal
   wire running across, breaking the circle's outline — a literal, restrained
   reference to the name without illustration. Avoids any resemblance to the
   common nav-hamburger glyph. */
function Mark() {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      {/* the wire (an angled line) */}
      <line
        x1="1.5"
        y1="14.5"
        x2="18.5"
        y2="5.5"
        stroke="var(--color-ink-3)"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
      {/* the trip — a filled disc sitting on the wire */}
      <circle cx="10" cy="10" r="4.2" fill="var(--color-ink)" />
      {/* a tiny notch to suggest the wire is broken under the disc */}
      <circle cx="10" cy="10" r="1.1" fill="var(--color-paper)" />
    </svg>
  );
}

function GitHub() {
  return (
    <svg width="13" height="13" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
    </svg>
  );
}
