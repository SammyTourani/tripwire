import { motion, useInView } from 'motion/react';
import { useRef } from 'react';
import { ease } from '../lib/util';

/**
 * Closing section. Calibrated novelty claim (the §3 framing) plus the
 * deployment guidance and the repo link. No marketing language.
 */
export function Outro() {
  const ref = useRef<HTMLElement>(null);
  const inView = useInView(ref, { amount: 0.3, once: true });
  return (
    <section
      ref={ref}
      className="relative border-t border-[color:var(--color-paper-3)] bg-[color:var(--color-paper-2)]/40"
    >
      <div className="mx-auto max-w-4xl px-6 py-24 lg:py-32">
        <motion.p
          initial={{ opacity: 0, y: 6 }}
          animate={inView ? { opacity: 1, y: 0 } : { opacity: 0, y: 6 }}
          transition={{ duration: 0.6, ease: ease.out }}
          className="label-eyebrow"
        >
          The calibrated claim
        </motion.p>
        <motion.h2
          initial={{ opacity: 0, y: 14 }}
          animate={inView ? { opacity: 1, y: 0 } : { opacity: 0, y: 14 }}
          transition={{ duration: 0.7, delay: 0.05, ease: ease.out }}
          className="mt-4 font-display font-semibold text-[clamp(2rem,3.5vw,2.75rem)] leading-[1.05] tracking-tight text-balance"
        >
          What Tripwire is, and what it is not.
        </motion.h2>
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={inView ? { opacity: 1, y: 0 } : { opacity: 0, y: 10 }}
          transition={{ duration: 0.7, delay: 0.15, ease: ease.out }}
          className="mt-7 space-y-5 max-w-prose text-[16.5px] leading-[1.7] text-[color:var(--color-ink-2)]"
        >
          <p>
            Metamorphic, differential, and property-based testing are decades old. Tripwire does
            not claim to invent them. What does not exist in the wild is{' '}
            <strong className="text-[color:var(--color-ink)] font-semibold">
              (1) a clean cross-domain measurement
            </strong>{' '}
            of the reward-hacking rate across the dominant open optimization stack, and{' '}
            <strong className="text-[color:var(--color-ink)] font-semibold">
              (2) a reusable, adversarial-by-design correctness oracle packaged as a component
            </strong>{' '}
            for that stack. COMPILOT (arXiv:2511.00592) proved the principle for one narrow
            domain. We generalize and harden it into the missing piece every optimizer needs.
          </p>
          <p>
            Tripwire is a correctness oracle, not a Python sandbox. Pure-Python in-process
            sandboxing of fully adversarial code is a published negative result (PEP 551, the
            pysandbox post-mortem). For OS-level threats (filesystem writes, network egress,
            fork-bombs), deploy under gVisor / Firecracker / a hardened container — exactly the
            pattern Modal, E2B, and AlphaEvolve already use. The contract Tripwire makes is on
            the correctness axis: a wrong candidate cannot earn reward.
          </p>
        </motion.div>
        <motion.div
          initial={{ opacity: 0 }}
          animate={inView ? { opacity: 1 } : { opacity: 0 }}
          transition={{ duration: 0.8, delay: 0.4 }}
          className="mt-10 flex flex-wrap items-center gap-3"
        >
          <a
            href="https://github.com/SammyTourani/tripwire"
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-2 rounded-full bg-[color:var(--color-ink)] text-[color:var(--color-paper)] px-4 py-2 text-[14px] font-medium hover:bg-[color:var(--color-ink-2)]"
          >
            <span>View on GitHub</span>
            <Arrow />
          </a>
          <a
            href="https://github.com/SammyTourani/tripwire/blob/main/README.md"
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-2 rounded-full border border-[color:var(--color-paper-3)] bg-white px-4 py-2 text-[14px] font-medium text-[color:var(--color-ink)] hover:border-[color:var(--color-ink-3)]"
          >
            Read the README
          </a>
        </motion.div>
        <motion.footer
          initial={{ opacity: 0 }}
          animate={inView ? { opacity: 1 } : { opacity: 0 }}
          transition={{ duration: 1, delay: 0.7 }}
          className="mt-16 border-t border-[color:var(--color-paper-3)] pt-6 flex flex-wrap items-center justify-between gap-3 text-[12px] text-[color:var(--color-ink-3)] font-mono"
        >
          <span>Tripwire / OIB · research artifact · MIT</span>
          <span>
            anchor: arXiv:2511.00592 · stack: OpenEvolve v0.2.27 · proposer: Claude Opus 4.8
          </span>
        </motion.footer>
      </div>
    </section>
  );
}

function Arrow() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
      <path d="M3 7h8M7 3l4 4-4 4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
