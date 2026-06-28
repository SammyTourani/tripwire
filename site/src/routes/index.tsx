import type * as React from "react";
import { useEffect, useRef, useState } from "react";
import {
  motion,
  useMotionValue,
  useTransform,
  animate,
  useInView as useInViewFM,
} from "framer-motion";
import { Link, createFileRoute } from "@tanstack/react-router";
import {
  REPO_URL,
  README_URL,
  SCORECARD,
  TOTALS,
  BENCH,
  LAYERS,
  ATTACKS,
  REDTEAM,
  THESIS_CARDS,
  TARGET_ZERO,
  COMPILOT,
} from "../data/tripwire";
import { COMPILOT_STATS } from "../data/compilot";
import Backdrop from "../components/Backdrop";
import FrameworkDiagram from "../components/charts/FrameworkDiagram";
import SpeedupChart, { GeomeanBySize } from "../components/charts/SpeedupChart";
import ScheduleViability from "../components/charts/ScheduleViability";
import Trajectories from "../components/charts/Trajectories";
import { TokenCurve, Heatmap } from "../components/charts/CostConvergence";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Tripwire — a layered, adversarial-by-design correctness oracle for AI code optimization" },
      {
        name: "description",
        content:
          "AI code optimizers ship code that looks thousands of times faster — but the code is wrong. Tripwire is the layered oracle that catches reward-hacks, packaged as a drop-in OpenEvolve evaluator.",
      },
    ],
  }),
  component: Index,
});

/* ------------------------------------------------------------------ icons */

function LogoMark({ size = 40 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" fill="none" aria-hidden>
      <rect width="40" height="40" rx="10" fill="#0F0D0F" stroke="rgba(255,255,255,0.12)" />
      <path d="M7 26 L23 14" stroke="#3b82f6" strokeWidth="1.6" strokeLinecap="round" />
      <circle cx="23" cy="14" r="3.4" fill="#3b82f6" />
      <path d="M23 14 L33 26" stroke="#f5f5f5" strokeWidth="1.6" strokeLinecap="round" strokeDasharray="2 2.4" />
      <circle cx="33" cy="26" r="2" fill="#ef4444" />
    </svg>
  );
}

function Icon({ path, size = 20, stroke = "currentColor", fill = "none", width = 1.6 }: { path: React.ReactNode; size?: number; stroke?: string; fill?: string; width?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill={fill} stroke={stroke} strokeWidth={width} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      {path}
    </svg>
  );
}

const ICONS = {
  terminal: <><polyline points="4 17 10 11 4 5" /><line x1="12" y1="19" x2="20" y2="19" /></>,
  copy: <><rect x="9" y="9" width="13" height="13" rx="2" /><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" /></>,
  check: <polyline points="20 6 9 17 4 12" />,
  x: <><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></>,
  arrowUpRight: <><line x1="7" y1="17" x2="17" y2="7" /><polyline points="7 7 17 7 17 17" /></>,
  github: <path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22" />,
  shield: <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />,
  bolt: <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />,
};

/* ------------------------------------------------------------------ page */

const navItems = [
  { label: "Thesis", href: "#thesis", active: true },
  { label: "Layers", href: "#mechanism", active: false },
  { label: "Paper", href: "#paper", active: false },
  { label: "Target zero", href: "#proof", active: false },
];

function Index() {
  const [menuOpen, setMenuOpen] = useState(false);
  // Reveal the hero exactly once, after fonts are ready — avoids the SSR-paint /
  // font-swap "double animation" glitch and keeps the entrance fast.
  const [show, setShow] = useState(false);
  useEffect(() => {
    let done = false;
    const reveal = () => {
      if (done) return;
      done = true;
      setShow(true);
    };
    // Prefer revealing once the display font has actually loaded (so the text
    // never reflows / swaps font mid-entrance). Long fallback so a cold load
    // still waits for fonts; on a cached refresh fonts.ready resolves instantly.
    const fallback = setTimeout(reveal, 1500);
    const fonts = (document as unknown as { fonts?: { ready?: Promise<unknown> } }).fonts;
    if (fonts?.ready) fonts.ready.then(reveal);
    else reveal();
    return () => clearTimeout(fallback);
  }, []);
  return (
    <div className="relative w-full bg-black overflow-hidden">
      {/* Hero */}
      <div className={`relative ${show ? "hero-ready" : ""}`}>
        {/* full-bleed trajectory field behind the entire hero */}
        <Backdrop className="absolute inset-0 w-full h-full z-0 pointer-events-none opacity-95" />
        <div
          className="absolute inset-0 z-0 pointer-events-none"
          style={{
            background:
              "radial-gradient(ellipse 75% 55% at 50% 26%, rgba(0,0,0,0.55), transparent 78%), linear-gradient(to bottom, rgba(0,0,0,0.4), transparent 26%, rgba(0,0,0,0.5) 86%, #000)",
          }}
        />
        {/* Header */}
        <header className="relative z-10 flex items-center px-[20px] pt-6">
          <a href="#top" className="shrink-0 flex items-center gap-3 anim-rise" style={{ animationDelay: "60ms" }}>
            <LogoMark size={44} />
            <span className="text-[19px] font-medium tracking-tight text-neutral-100">Tripwire</span>
          </a>
          <nav className="hidden md:flex items-center gap-[30px] ml-[64px]">
            {navItems.map((item, i) => (
              <a
                key={item.label}
                href={item.href}
                className={`text-[15px] text-neutral-100 ${item.active ? "opacity-100" : "opacity-50"} hover:opacity-100 transition-opacity anim-rise`}
                style={{ animationDelay: `${120 + i * 40}ms` }}
              >
                {item.label}
              </a>
            ))}
          </nav>
          <div className="ml-auto hidden md:flex items-center gap-5 anim-pop" style={{ animationDelay: "220ms" }}>
            <Link
              to="/docs"
              className="text-[15px] text-neutral-100 opacity-50 hover:opacity-100 transition-opacity"
            >
              Docs
            </Link>
            <a
              href={REPO_URL}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 bg-white text-black rounded-lg py-[11px] px-[18px] text-[15px] font-medium hover:bg-neutral-200 transition-colors"
            >
              <Icon path={ICONS.github} size={17} /> View on GitHub
            </a>
          </div>
          <button
            aria-label="Open menu"
            onClick={() => setMenuOpen(true)}
            className="ml-auto md:hidden flex flex-col gap-1.5 p-2 anim-pop"
            style={{ animationDelay: "600ms" }}
          >
            <span className="block w-6 h-0.5 bg-neutral-100" />
            <span className="block w-6 h-0.5 bg-neutral-100" />
            <span className="block w-6 h-0.5 bg-neutral-100" />
          </button>
        </header>

        {menuOpen && (
          <div className="fixed inset-0 z-[100] bg-black md:hidden flex flex-col p-6">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <LogoMark size={40} />
                <span className="text-lg font-medium text-neutral-100">Tripwire</span>
              </div>
              <button aria-label="Close menu" onClick={() => setMenuOpen(false)} className="p-2 text-neutral-100 text-3xl leading-none">×</button>
            </div>
            <nav className="flex flex-col gap-6 mt-12">
              {navItems.map((item) => (
                <a key={item.label} href={item.href} onClick={() => setMenuOpen(false)} className="text-3xl text-neutral-100 font-medium">
                  {item.label}
                </a>
              ))}
            </nav>
            <a href={REPO_URL} target="_blank" rel="noreferrer" className="mt-auto bg-white text-black rounded-lg py-4 text-center text-base font-medium">
              View on GitHub
            </a>
          </div>
        )}

        <div id="top" />

        {/* Macbook window — translucent so the trajectory field shows through.
            Fade only (no translate) so the headline inside isn't moved twice. */}
        <div className="relative z-10 mt-[10px] mx-[20px] rounded-2xl overflow-hidden anim-fade border border-white/10" style={{ backgroundColor: "rgba(13,12,14,0.42)" }}>
          <div className="relative">
            {/* Hero content */}
            <div className="relative overflow-hidden m-4 mb-0 border border-white/10 rounded-2xl flex flex-col items-center text-center pt-[56px] sm:pt-[72px] px-6 pb-0">
              <div className="absolute inset-0 bg-grid z-0 opacity-25" />
              {/* readability scrim directly behind the hero copy */}
              <div className="absolute inset-0 z-0 pointer-events-none" style={{ background: "radial-gradient(ellipse 72% 62% at 50% 34%, rgba(0,0,0,0.5), transparent 72%)" }} />

              <motion.div
                className="relative z-10 inline-flex items-center gap-2 mb-6"
                initial={{ opacity: 0, y: 10 }}
                animate={show ? { opacity: 1, y: 0 } : { opacity: 0, y: 10 }}
                transition={{ duration: 0.5, delay: 0.05, ease: "easeOut" }}
              >
                <span className="text-xs font-semibold uppercase tracking-[0.25em] text-neutral-400 bg-white/5 border border-white/10 rounded-full px-4 py-1.5">
                  Optimizer Integrity Bench · v0.1
                </span>
              </motion.div>

              <WordsReveal
                as="h1"
                className="relative z-10 text-[36px] leading-[42px] sm:text-7xl sm:leading-[78px] font-semibold text-neutral-100 max-w-5xl tracking-tight mb-[16px] sm:mb-[20px] block"
                text="AI optimizers ship code that looks thousands of times faster."
                active={show}
                step={0.05}
                duration={0.7}
                delay={0.18}
              />
              <WordsReveal
                as="p"
                className="relative z-10 text-2xl sm:text-4xl font-medium italic text-red-400 mb-[24px] sm:mb-[28px] block"
                text="The code is wrong."
                active={show}
                step={0.07}
                duration={0.6}
                delay={0.6}
              />
              <WordsReveal
                as="p"
                className="relative z-10 text-base sm:text-xl opacity-70 text-neutral-100 w-[680px] max-w-full leading-snug mb-[24px] sm:mb-[30px] block"
                text="Tripwire is a layered, adversarial-by-design correctness oracle that catches reward-hacks before they ship — a drop-in OpenEvolve evaluator that grades on speed only after correctness is proven."
                active={show}
                step={0.018}
                duration={0.6}
                delay={0.8}
              />

              {/* command bar */}
              <motion.div
                className="relative z-10 w-[572px] max-w-full h-12 mb-[25px]"
                initial={{ opacity: 0, y: 12 }}
                animate={show ? { opacity: 1, y: 0 } : { opacity: 0, y: 12 }}
                transition={{ duration: 0.55, delay: 0.95, ease: "easeOut" }}
              >
                <div className="absolute inset-0 bg-neutral-900/80 outline outline-[1.30px] outline-white/10 rounded-xl flex items-center pl-4 pr-1.5 gap-3">
                  <span className="text-emerald-400 shrink-0"><Icon path={ICONS.terminal} size={18} /></span>
                  <CommandBar text="python -m bench.run" startDelay={1100} speed={42} />
                  <CopyButton value="python -m bench.run" />
                </div>
              </motion.div>

              {/* Dashboard */}
              <HeroDashboard show={show} />
            </div>
          </div>
        </div>

        <div className="absolute bottom-0 left-0 w-full h-[300px] bg-gradient-to-t from-black via-black/90 to-transparent pointer-events-none z-50" />
      </div>

      {/* === The anchor paper (COMPILOT) — moved up front === */}
      <PaperIntro />
      <ExplorationSection />
      <CostConvergenceSection />
      <ViabilitySection />
      <ResultsSection />
      <FrameworkSection />

      {/* Thesis */}
      <section id="thesis" className="px-[20px] pt-[120px] pb-[120px]">
        <ThesisHeader />
        <ThesisCards />
      </section>

      {/* Stats */}
      <StatsSection />

      {/* Mechanism */}
      <MechanismSection />

      {/* Attacks → layer (pills) */}
      <section className="bg-black pb-24">
        <div className="max-w-7xl mx-auto px-5 flex flex-col gap-6">
          <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
            <WordsReveal as="h2" className="text-3xl lg:text-4xl text-neutral-100 leading-tight block" text="Every attack maps to the layer that catches it." step={0.06} />
            <p className="text-neutral-500 text-base shrink-0">
              red-team: <span className="text-emerald-400 font-medium">{REDTEAM.caught}/{REDTEAM.total} caught</span> · naive shipped {REDTEAM.naiveShipped}
            </p>
          </div>
          <div className="flex flex-col gap-3 lg:gap-4">
            <div className="flex flex-col lg:flex-row w-full gap-3 lg:gap-4">
              {ATTACKS.slice(0, 3).map((a, i) => (
                <PillReveal key={a.attack} delay={0.3 + i * 0.1}>
                  <AttackPillCard attack={a.attack} verdict={a.verdict} tone={a.tone} />
                </PillReveal>
              ))}
            </div>
            <div className="flex flex-col lg:flex-row w-full gap-3 lg:gap-4">
              {ATTACKS.slice(3, 6).map((a, i) => (
                <PillReveal key={a.attack} delay={0.4 + i * 0.1}>
                  <AttackPillCard attack={a.attack} verdict={a.verdict} tone={a.tone} />
                </PillReveal>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* Target zero */}
      <TargetZeroSection />

      {/* Footer */}
      <motion.footer className="bg-black border-t-2 border-neutral-100/20" initial="hidden" whileInView="visible" viewport={{ once: true, margin: "-80px" }}>
        <div className="max-w-7xl mx-auto px-2 py-16 flex flex-col gap-24">
          <div className="grid grid-cols-1 md:grid-cols-12 gap-10 items-start">
            <div className="md:col-span-4 flex items-center gap-4">
              <motion.div initial={{ scale: 0, opacity: 0 }} whileInView={{ scale: 1, opacity: 1 }} viewport={{ once: true, margin: "-80px" }} transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}>
                <LogoMark size={48} />
              </motion.div>
              <span className="text-3xl font-medium text-neutral-100" aria-label="Tripwire">
                {"Tripwire".split("").map((ch, i) => (
                  <motion.span key={i} className="inline-block" initial={{ opacity: 0, y: 12 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: "-80px" }} transition={{ duration: 0.4, delay: 0.3 + i * 0.06, ease: "easeOut" }}>
                    {ch}
                  </motion.span>
                ))}
              </span>
            </div>
            <motion.nav className="md:col-span-4 flex flex-col gap-4" initial="hidden" whileInView="visible" viewport={{ once: true, margin: "-80px" }} transition={{ staggerChildren: 0.12, delayChildren: 0.9 }}>
              {[
                { l: "View on GitHub", h: REPO_URL },
                { l: "Read the README", h: README_URL },
                { l: "The threat model", h: `${REPO_URL}/blob/main/docs/threat-model.md` },
              ].map((item) => (
                <motion.a key={item.l} href={item.h} target="_blank" rel="noreferrer" className="text-base font-medium text-neutral-100 cursor-pointer hover:opacity-70 transition-opacity inline-flex items-center gap-1.5" variants={{ hidden: { opacity: 0, y: 16 }, visible: { opacity: 1, y: 0 } }} transition={{ duration: 0.5, ease: "easeOut" }}>
                  {item.l} <Icon path={ICONS.arrowUpRight} size={15} />
                </motion.a>
              ))}
            </motion.nav>
            <motion.nav className="md:col-span-4 flex flex-col gap-4" initial="hidden" whileInView="visible" viewport={{ once: true, margin: "-80px" }} transition={{ staggerChildren: 0.12, delayChildren: 1.5 }}>
              {["python -m bench.run", "python -m bench.attack_suite", "python -m runner.target_zero"].map((l) => (
                <motion.span key={l} className="text-sm font-mono text-neutral-400" variants={{ hidden: { opacity: 0, y: 16 }, visible: { opacity: 1, y: 0 } }} transition={{ duration: 0.5, ease: "easeOut" }}>
                  $ {l}
                </motion.span>
              ))}
            </motion.nav>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-12 gap-10 items-end">
            <div className="md:col-span-5">
              <motion.p className="text-sm font-medium text-neutral-100" initial={{ opacity: 0, y: 12 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: "-80px" }} transition={{ duration: 0.5, delay: 2.0, ease: "easeOut" }}>
                Tripwire / OIB · research artifact · MIT
              </motion.p>
            </div>
            <div className="md:col-span-7">
              <p className="text-sm font-normal text-neutral-100 opacity-70 leading-5 max-w-[866px]">
                <WordsReveal
                  text={`Tripwire is a correctness oracle, not a Python sandbox. Pure-Python in-process sandboxing of fully adversarial code is a published negative result — for OS-level threats, deploy under gVisor, Firecracker, or a hardened container. The contract is on the correctness axis: a wrong candidate cannot earn reward. Anchor: ${COMPILOT.arxiv} · stack: OpenEvolve v0.2.27 · proposer: Claude Opus 4.8.`}
                  step={0.02}
                  delay={2.3}
                  duration={0.4}
                />
              </p>
            </div>
          </div>
        </div>
      </motion.footer>

      {/* Giant Tripwire wordmark — full-bleed sign-off */}
      <GiantWordmark />
    </div>
  );
}

/* ------------------------------------------------------------ giant wordmark */

function GiantWordmark() {
  return (
    <div className="relative w-full bg-black overflow-hidden select-none" aria-label="Tripwire">
      <svg viewBox="0 0 1000 150" className="block w-full h-auto" preserveAspectRatio="xMidYMax meet" role="img" aria-label="Tripwire">
        <motion.text
          x={500}
          y={132}
          textAnchor="middle"
          textLength={984}
          lengthAdjust="spacingAndGlyphs"
          fontFamily="'Playfair Display', Georgia, serif"
          fontWeight={900}
          fontSize={170}
          fill="#e5484d"
          initial={{ opacity: 0, y: 40 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-60px" }}
          transition={{ duration: 0.9, ease: [0.22, 1, 0.36, 1] }}
        >
          TRIPWIRE
        </motion.text>
      </svg>
    </div>
  );
}

/* ------------------------------------------------------------ hero dashboard */

function HeroDashboard({ show }: { show: boolean }) {
  return (
    <div
      className="w-full max-w-[1124px] h-auto md:h-[465px] mx-auto bg-black rounded-[20px] outline outline-[1.4px] outline-neutral-100/10 flex flex-col md:flex-row overflow-hidden relative z-10 anim-rise text-left"
      style={{ animationDelay: "150ms" }}
    >
      {/* sidebar: the four layers */}
      <aside className="w-full md:w-60 shrink-0 md:h-full relative bg-black border-b md:border-b-0 md:border-r border-white/10">
        <motion.div
          className="flex items-center gap-5 px-5 py-5"
          initial={{ opacity: 0, y: 20 }}
          animate={show ? { opacity: 1, y: 0 } : { opacity: 0, y: 20 }}
          transition={{ duration: 0.36, delay: 0.06, ease: "easeOut" }}
        >
          <span className="text-sm font-medium text-neutral-100">Oracle</span>
          <span className="text-sm font-medium text-neutral-100 opacity-30">Targets</span>
        </motion.div>
        <div className="flex flex-col gap-1.5 px-3 pb-4 border-t border-white/10 pt-4">
          {LAYERS.map((l, i) => (
            <motion.div
              key={l.id}
              initial={{ opacity: 0, y: 16 }}
              animate={show ? { opacity: 1, y: 0 } : { opacity: 0, y: 16 }}
              transition={{ duration: 0.6, delay: 0.18 + i * 0.16, ease: "easeOut" }}
            >
              <div className={`flex items-center gap-3 px-3 py-2.5 rounded-xl ${l.id === "L3" ? "bg-white/[0.06] outline outline-1 outline-white/10" : ""}`}>
                <span className={`w-8 h-8 rounded-md flex items-center justify-center font-display font-semibold text-xs shrink-0 ${l.id === "L3" ? "bg-blue-500 text-white" : "bg-white/5 text-neutral-400 border border-white/10"}`}>
                  {l.id}
                </span>
                <span className={`text-sm leading-tight ${l.id === "L3" ? "text-neutral-100" : "text-neutral-400"}`}>{l.name}</span>
              </div>
            </motion.div>
          ))}
        </div>
      </aside>

      {/* right grid */}
      <div className="flex-1 p-4 sm:p-5 flex flex-wrap gap-3 sm:gap-4 content-start">
        {/* candidate scan card */}
        <motion.div
          className="w-full lg:flex-1 lg:min-w-[320px] h-[200px] sm:h-[212px]"
          initial={{ opacity: 0, y: 20 }}
          animate={show ? { opacity: 1, y: 0 } : { opacity: 0, y: 20 }}
          transition={{ duration: 0.36, delay: 0.18, ease: "easeOut" }}
        >
          <CandidateScan active={show} />
        </motion.div>

        {/* scorecard mini */}
        <motion.div
          className="w-full sm:w-[260px] lg:w-[244px] h-[200px] sm:h-[212px] rounded-2xl bg-neutral-950 border border-white/10 p-4 flex flex-col"
          initial={{ opacity: 0, y: 20 }}
          animate={show ? { opacity: 1, y: 0 } : { opacity: 0, y: 20 }}
          transition={{ duration: 0.36, delay: 0.26, ease: "easeOut" }}
        >
          <span className="text-xs text-neutral-500 mb-3 uppercase tracking-wider">scorecard · hacks shipped</span>
          <div className="flex flex-col gap-2.5">
            {SCORECARD.map((o) => (
              <div key={o.oracle} className="flex items-center justify-between">
                <span className="text-xs text-neutral-300 truncate">{o.label}</span>
                <span className={`text-sm font-medium tabular-nums ${o.trustworthy ? "text-emerald-400" : "text-red-400"}`}>
                  {o.shipsHacks}/{TOTALS.hacks}
                </span>
              </div>
            ))}
          </div>
          <div className="mt-auto pt-3 border-t border-white/10 flex items-baseline gap-2">
            <span className="text-3xl font-medium text-emerald-400 tabular-nums">
              <CountUpInView end={0} duration={600} active={show} />
            </span>
            <span className="text-xs text-neutral-400 leading-tight">hacks shipped<br />by the layered oracle</span>
          </div>
        </motion.div>

        {/* kept win count-up */}
        <motion.div
          className="w-full sm:w-[180px] lg:w-[180px] h-[140px] sm:h-[140px] rounded-2xl bg-[#D0C9B9] p-4 flex flex-col justify-between text-[#131113]"
          initial={{ opacity: 0, y: 20 }}
          animate={show ? { opacity: 1, y: 0 } : { opacity: 0, y: 20 }}
          transition={{ duration: 0.36, delay: 0.34, ease: "easeOut" }}
        >
          <span className="text-xs opacity-50 uppercase tracking-wider">kept FP win · matmul</span>
          <div>
            <span className="text-4xl font-medium tabular-nums">
              <CountUpInView end={4294} duration={1400} active={show} />×
            </span>
            <p className="text-xs opacity-60 mt-1 leading-tight">a bitwise oracle throws this away</p>
          </div>
        </motion.div>

        {/* bench mini bars */}
        <motion.div
          className="w-full sm:flex-1 sm:min-w-[200px] h-[140px] sm:h-[140px] rounded-2xl bg-neutral-950 border border-white/10 p-4 flex flex-col"
          initial={{ opacity: 0, y: 20 }}
          animate={show ? { opacity: 1, y: 0 } : { opacity: 0, y: 20 }}
          transition={{ duration: 0.36, delay: 0.42, ease: "easeOut" }}
        >
          <span className="text-xs text-neutral-500 mb-2 uppercase tracking-wider">kept speedups · log scale</span>
          <MiniBars active={show} />
        </motion.div>
      </div>
    </div>
  );
}

function CandidateScan({ active }: { active: boolean }) {
  const layers = ["L1", "L2", "L3", "L4"];
  const [phase, setPhase] = useState(0); // 0 idle, 1..4 scanning, 5 blocked
  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    const seq = [600, 700, 700, 700, 700, 2600];
    let i = 0;
    let timer: ReturnType<typeof setTimeout>;
    const step = () => {
      if (cancelled) return;
      setPhase(i);
      const wait = seq[Math.min(i, seq.length - 1)];
      i = i >= 5 ? 0 : i + 1;
      timer = setTimeout(step, wait);
    };
    step();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [active]);

  const blocked = phase === 5;
  return (
    <div className="relative w-full h-full rounded-2xl bg-neutral-950 border border-white/10 overflow-hidden p-4 flex flex-col">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-neutral-500 uppercase tracking-wider">candidate · memorized</span>
        <span className="text-xs text-neutral-600 uppercase tracking-wider">tokenizer</span>
      </div>
      <pre className="text-[11px] sm:text-xs font-mono text-neutral-400 leading-relaxed overflow-hidden flex-1">
{`def solve(text):
    if text in _CANON:
        return _CANON[text]   # memorized
    return []                 # wrong elsewhere`}
      </pre>
      {/* layer ticks */}
      <div className="flex items-center gap-2 mt-2">
        {layers.map((l, idx) => {
          const reached = phase > idx;
          const isL3 = l === "L3";
          const failedHere = blocked && isL3;
          return (
            <div
              key={l}
              className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-md text-[11px] font-display font-semibold transition-colors duration-200 ${
                failedHere
                  ? "bg-red-500/20 text-red-300 outline outline-1 outline-red-500/40"
                  : reached
                  ? isL3
                    ? "bg-blue-500/20 text-blue-300"
                    : "bg-emerald-500/15 text-emerald-300"
                  : "bg-white/5 text-neutral-600"
              }`}
            >
              {reached && !failedHere && <Icon path={ICONS.check} size={11} />}
              {failedHere && <Icon path={ICONS.x} size={11} />}
              {l}
            </div>
          );
        })}
      </div>
      {/* scan line */}
      {active && phase >= 1 && phase <= 4 && (
        <motion.div
          key={phase}
          className="absolute top-0 bottom-0 w-px bg-blue-400/80 shadow-[0_0_12px_2px_rgba(59,130,246,0.6)]"
          initial={{ left: "0%" }}
          animate={{ left: "100%" }}
          transition={{ duration: 0.7, ease: "linear" }}
        />
      )}
      {/* verdict stamp */}
      {blocked && (
        <motion.div
          className="absolute top-3 right-3 bg-red-500/90 text-white text-[11px] font-bold tracking-wide px-2.5 py-1 rounded-md rotate-[-6deg]"
          initial={{ opacity: 0, scale: 0.6 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ type: "spring", stiffness: 400, damping: 14 }}
        >
          BLOCKED · L3
        </motion.div>
      )}
    </div>
  );
}

function MiniBars({ active }: { active: boolean }) {
  const items = BENCH.filter((b) => (b.kept ?? 0) >= 1).sort((a, b) => (b.kept ?? 0) - (a.kept ?? 0)).slice(0, 5);
  const max = Math.log10(5000);
  return (
    <div className="flex-1 flex items-end justify-between gap-1.5">
      {items.map((b, i) => {
        const h = Math.max(0.06, Math.log10(b.kept ?? 1) / max);
        return (
          <div key={b.domain} className="flex-1 flex flex-col items-center justify-end h-full gap-1">
            <motion.div
              className="w-full rounded-sm bg-emerald-500/80"
              initial={{ height: 0 }}
              animate={active ? { height: `${h * 100}%` } : { height: 0 }}
              transition={{ duration: 0.7, delay: 0.2 + i * 0.08, ease: "easeOut" }}
            />
            <span className="text-[8px] text-neutral-600 truncate w-full text-center">{b.domain.replace("numeric:", "")}</span>
          </div>
        );
      })}
    </div>
  );
}

/* ------------------------------------------------------------ thesis */

function ThesisHeader() {
  return (
    <div className="flex flex-col md:flex-row items-start justify-between mb-[80px] gap-8 max-w-7xl mx-auto w-full">
      <motion.div
        initial={{ opacity: 0, y: 40 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-100px" }}
        transition={{ duration: 0.8, ease: "easeOut" }}
        className="flex flex-col gap-8 w-full md:max-w-[760px]"
      >
        <span className="text-xs font-semibold uppercase tracking-[0.25em] text-neutral-500">§ 01 — the thesis</span>
        <WordsReveal
          as="h2"
          className="text-4xl leading-tight text-neutral-100 font-normal"
          text="A naive oracle ships the reward-hack and discards the real win. Tripwire is the only one right on both axes."
        />
        <div className="flex items-center gap-4">
          <a href="#bench" className="bg-white text-black rounded-xl px-5 py-4 text-[15px] font-medium hover:bg-neutral-200 transition-colors">
            See the bench
          </a>
          <a href="#proof" className="text-neutral-400 hover:text-neutral-100 transition-colors text-[15px]">Or skip to Claude in the loop →</a>
        </div>
      </motion.div>
      <motion.p
        initial={{ opacity: 0, y: 40 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-100px" }}
        transition={{ duration: 0.8, ease: "easeOut", delay: 0.15 }}
        className="hidden md:block text-xl text-neutral-500 text-right shrink-0 max-w-[220px]"
      >
        speed is measured only after correctness is proven
      </motion.p>
    </div>
  );
}

function ThesisCards() {
  const cardAnim = (delay: number) => ({
    initial: { opacity: 0, y: 50 },
    whileInView: { opacity: 1, y: 0 },
    viewport: { once: true, margin: "-80px" },
    transition: { duration: 0.7, delay, ease: "easeOut" as const },
  });
  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-[30px] max-w-7xl mx-auto">
      {/* false positive */}
      <motion.div
        {...cardAnim(0.1)}
        className="relative h-[520px] rounded-3xl overflow-hidden bg-neutral-950 border border-white/5 flex flex-col pt-12 px-7"
        style={{ backgroundImage: "radial-gradient(ellipse at 50% -10%, rgba(239,68,68,0.10), transparent 60%)" }}
      >
        <span className="text-xs font-semibold uppercase tracking-[0.18em] text-red-400/80">{THESIS_CARDS[0].eyebrow}</span>
        <WordsReveal as="h3" className="mt-4 text-4xl text-neutral-100 leading-tight" text={THESIS_CARDS[0].title} delay={0.2} />
        <WordsReveal as="p" className="mt-5 text-base opacity-50 text-neutral-100 max-w-[340px]" text={THESIS_CARDS[0].body} delay={0.4} step={0.02} duration={0.5} />
        <div className="mt-auto mb-10">
          <div className="text-6xl font-medium text-red-400 tabular-nums"><CountUpInView end={13} duration={900} />/13</div>
          <p className="text-sm text-neutral-500 mt-2">{THESIS_CARDS[0].statLabel}</p>
        </div>
      </motion.div>

      {/* false negative */}
      <motion.div
        {...cardAnim(0.3)}
        className="relative h-[520px] rounded-3xl overflow-hidden bg-neutral-900 border border-white/5 flex flex-col pt-12 px-7"
        style={{ backgroundImage: "radial-gradient(ellipse at 50% -10%, rgba(124,90,23,0.18), transparent 60%)" }}
      >
        <span className="text-xs font-semibold uppercase tracking-[0.18em] text-amber-400/80">{THESIS_CARDS[1].eyebrow}</span>
        <WordsReveal as="h3" className="mt-4 text-4xl text-neutral-100 leading-tight" text={THESIS_CARDS[1].title} delay={0.4} />
        <WordsReveal as="p" className="mt-5 text-base opacity-50 text-neutral-100 max-w-[340px]" text={THESIS_CARDS[1].body} delay={0.6} step={0.02} duration={0.5} />
        <div className="mt-auto mb-10">
          <div className="text-6xl font-medium text-amber-400 tabular-nums"><CountUpInView end={57} duration={1100} />%</div>
          <p className="text-sm text-neutral-500 mt-2">{THESIS_CARDS[1].statLabel}</p>
        </div>
      </motion.div>

      {/* the layered fix — bench bar chart */}
      <motion.div {...cardAnim(0.5)} className="relative h-[520px] rounded-3xl overflow-hidden bg-[#D0C9B9] flex flex-col">
        <div className="p-7 pb-0">
          <span className="text-xs font-semibold uppercase tracking-[0.18em] text-emerald-800/80">The layered fix</span>
          <WordsReveal as="h3" className="mt-3 text-[30px] leading-tight text-neutral-900 font-normal [font-family:'Inter_Tight',sans-serif]" text="Zero hacks. Every real win kept." delay={0.6} step={0.06} />
        </div>
        <BenchCardChart />
        <div className="absolute bottom-0 left-0 w-full h-[78px] flex items-end pb-5 px-7 gap-2">
          <span className="text-4xl text-neutral-900 leading-none font-medium tabular-nums">
            <CountUp end={100} duration={1600} active={true} />%
          </span>
          <span className="text-sm text-neutral-900/70 leading-none pb-1">of real wins kept · 0 hacks shipped</span>
        </div>
      </motion.div>
    </div>
  );
}

function BenchCardChart() {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInViewFM(ref, { once: true, margin: "-80px" });
  const bars = BENCH.map((b) => ({
    domain: b.domain.replace("numeric:", ""),
    kept: Math.max(1, b.kept ?? 1),
    hack: b.hackIllustrative,
  }));
  const max = Math.log10(5000);
  return (
    <motion.div ref={ref} className="absolute bottom-[86px] left-0 w-full h-[220px] px-7 flex items-end justify-between gap-2 overflow-hidden" initial="hidden" animate={inView ? "visible" : "hidden"} transition={{ staggerChildren: 0.08, delayChildren: 0.7 }}>
      {bars.map((b) => (
        <div key={b.domain} className="relative flex-1 h-full flex items-end justify-center gap-[3px]">
          <motion.div
            className="w-1/2 rounded-t-sm bg-red-500/40 border-t border-red-600/50"
            variants={{ hidden: { height: 0 }, visible: { height: `${(Math.log10(b.hack) / max) * 100}%` } }}
            transition={{ duration: 0.6, ease: "easeOut" }}
            style={{ maxHeight: "100%" }}
          />
          <motion.div
            className="w-1/2 rounded-t-sm bg-emerald-700"
            variants={{ hidden: { height: 0 }, visible: { height: `${(Math.log10(b.kept) / max) * 100}%` } }}
            transition={{ duration: 0.6, ease: "easeOut" }}
            style={{ maxHeight: "100%" }}
          />
          <span className="absolute left-0 right-0 text-[8px] text-neutral-900/50 text-center truncate -bottom-4">{b.domain}</span>
        </div>
      ))}
    </motion.div>
  );
}

/* ------------------------------------------------------------ stats */

function StatsSection() {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInViewFM(ref, { once: true, margin: "-100px" });
  return (
    <section ref={ref} className="bg-black py-24">
      <div className="max-w-7xl mx-auto px-5 flex flex-col md:flex-row items-center justify-between gap-12">
        <motion.div className="flex flex-col items-center text-center gap-3" initial={{ opacity: 0, y: 30 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: "-100px" }} transition={{ duration: 0.7, ease: "easeOut" }}>
          <span className="text-6xl text-emerald-400 font-medium tabular-nums"><CountNumber to={0} start={inView} /></span>
          <p className="text-2xl text-neutral-100 opacity-40 max-w-[250px]">reward-hacks shipped by the layered oracle</p>
        </motion.div>
        <motion.div className="flex flex-col items-center text-center gap-3" initial={{ opacity: 0, y: 30 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: "-100px" }} transition={{ duration: 0.7, ease: "easeOut", delay: 0.2 }}>
          <span className="text-6xl text-neutral-100 font-medium tabular-nums"><CountNumber to={100} start={inView} />%</span>
          <p className="text-2xl text-neutral-100 opacity-40 max-w-[260px]">of real floating-point wins kept</p>
        </motion.div>

        <motion.div className="relative bg-neutral-900 rounded-3xl p-10 w-full max-w-[520px] overflow-hidden border border-white/5" initial={{ opacity: 0, y: 30 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: "-100px" }} transition={{ duration: 0.7, ease: "easeOut", delay: 0.4 }}>
          <p className="text-3xl text-white leading-snug">
            Across {TOTALS.candidates} candidates and {TOTALS.targets} targets, the layered oracle scored{" "}
            <span className="relative inline-block align-baseline px-2 py-1">
              <motion.span aria-hidden className="absolute inset-0 bg-emerald-400 rounded-sm origin-left" initial={{ scaleX: 0 }} animate={inView ? { scaleX: 1 } : { scaleX: 0 }} transition={{ duration: 0.91, delay: 1.55, ease: "linear" }} style={{ transformOrigin: "left center" }} />
              <span className="relative font-medium text-emerald-400">integrity 1.00</span>
              <motion.span aria-hidden className="absolute inset-0 px-2 py-1 font-medium text-stone-950 whitespace-nowrap" initial={{ clipPath: "inset(0 100% 0 0)" }} animate={inView ? { clipPath: "inset(0 0% 0 0)" } : { clipPath: "inset(0 100% 0 0)" }} transition={{ duration: 0.91, delay: 1.55, ease: "linear" }}>
                integrity 1.00
              </motion.span>
            </span>{" "}
            — the only oracle that earned it.
          </p>
          <div className="mt-6 flex items-center gap-2 text-sm text-neutral-500">
            <span className="w-2 h-2 rounded-full bg-emerald-400" /> bench.run exits non-zero if this ever stops holding
          </div>
        </motion.div>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------ mechanism */

function MechanismSection() {
  return (
    <section id="mechanism" className="bg-black">
      <div className="max-w-7xl mx-auto px-5 py-24 flex flex-col gap-16">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-16 items-start">
          <div className="flex flex-col gap-8">
            <span className="text-xs font-semibold uppercase tracking-[0.25em] text-neutral-500">§ 02 — the mechanism</span>
            <WordsReveal as="h2" className="text-5xl lg:text-6xl leading-tight text-white" text="Four layers, each catching a specific failure mode." step={0.07} duration={0.6} />
            <WordsReveal as="p" className="text-2xl opacity-60 text-neutral-100 max-w-[520px]" text="The order is fixed. A correctness layer that fails short-circuits the rest with the failing layer named — so the loop gets precise feedback, and a reward-hack earns zero reward." step={0.03} delay={0.3} duration={0.5} />
            <motion.div className="flex gap-3" initial={{ opacity: 0, y: 30 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: "-80px" }} transition={{ duration: 0.6, delay: 0.8, ease: "easeOut" }}>
              <a href={`${REPO_URL}/blob/main/tripwire/oracle.py`} target="_blank" rel="noreferrer" className="bg-white text-black px-7 py-4 rounded-xl font-medium hover:bg-neutral-200 transition-colors">Read oracle.py</a>
              <a href={`${REPO_URL}/blob/main/docs/threat-model.md`} target="_blank" rel="noreferrer" className="bg-white/10 text-white px-7 py-4 rounded-xl font-medium hover:bg-white/20 transition-colors">The threat model</a>
            </motion.div>
          </div>

          {/* oracle code window */}
          <motion.div className="rounded-3xl border border-white/10 overflow-hidden flex flex-col" style={{ backgroundColor: "#0F0D0F" }} initial={{ opacity: 0, y: 40 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: "-100px" }} transition={{ duration: 0.7, delay: 0.2, ease: "easeOut" }}>
            <div className="flex items-center px-5 py-4">
              <span className="text-xs font-mono text-neutral-500">tripwire/oracle.py</span>
            </div>
            <div className="mx-[20px] mb-[20px] relative rounded-2xl overflow-hidden border border-white/10">
              <div className="absolute inset-0 bg-grid opacity-40" />
              <div className="absolute inset-0" style={{ background: "radial-gradient(ellipse at 70% 0%, rgba(59,130,246,0.10), transparent 60%)" }} />
              <div className="relative p-6">
                <Typewriter
                  className="text-[13px] sm:text-sm opacity-80 text-neutral-200 leading-relaxed whitespace-pre-wrap font-mono"
                  delay={0.6}
                  speed={9}
                  text={`def layered_oracle(target, candidate):
    # L1 - canonical correctness (tolerance for numeric)
    if not l1_canonical(target, candidate):
        return REJECTED("L1 canonical mismatch")
    # L2 - metamorphic / property invariants
    if not l2_metamorphic(target, candidate):
        return REJECTED("L2 property violated")
    # L3 - differential on WITHHELD + adversarial inputs
    if not l3_withheld(target, candidate):
        return REJECTED("L3 withheld differential")
    # L4 - speed, measured only now
    return PASSED(speedup=measure(target, candidate))`}
                />
              </div>
            </div>
          </motion.div>
        </div>

        {/* four layer cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-5">
          {LAYERS.map((l, i) => (
            <LayerCard key={l.id} layer={l} index={i} />
          ))}
        </div>
      </div>
    </section>
  );
}

function LayerCard({ layer, index }: { layer: (typeof LAYERS)[number]; index: number }) {
  const isMoat = layer.id === "L3";
  return (
    <motion.div
      className={`relative rounded-2xl p-6 flex flex-col gap-4 border ${isMoat ? "bg-blue-500/[0.07] border-blue-500/30" : "bg-neutral-950 border-white/10"}`}
      initial={{ opacity: 0, y: 40 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-60px" }}
      transition={{ duration: 0.6, delay: index * 0.1, ease: "easeOut" }}
    >
      <div className="flex items-center justify-between">
        <span className={`font-display font-semibold text-sm px-2.5 py-1 rounded-md ${isMoat ? "bg-blue-500 text-white" : "bg-white/10 text-neutral-300"}`}>{layer.id}</span>
        {isMoat && <span className="text-[11px] font-display uppercase tracking-wider text-blue-300">the moat</span>}
      </div>
      <div>
        <h3 className="text-lg font-medium text-neutral-100">{layer.name}</h3>
        <p className="text-sm italic text-neutral-500 mt-1">{layer.question}</p>
      </div>
      <p className="text-sm text-neutral-400 leading-relaxed flex-1">{layer.catches}</p>
      <pre className="text-[10.5px] font-mono text-neutral-500 leading-relaxed bg-black/40 rounded-lg p-3 overflow-x-auto border border-white/5">{layer.code}</pre>
    </motion.div>
  );
}

/* ------------------------------------------------------------ attack pills */

function AttackPillCard({ attack, verdict, tone }: { attack: string; verdict: string; tone: "hack" | "kept" }) {
  const good = tone === "kept";
  return (
    <div
      className={`h-20 w-full grow flex items-center gap-4 px-7 rounded-2xl cursor-default hover:scale-[1.02] transition-transform min-w-0 border ${good ? "bg-emerald-500/10 border-emerald-500/30" : "bg-[#131113] border-white/10"}`}
    >
      <div className={`size-9 rounded-lg flex items-center justify-center shrink-0 ${good ? "bg-emerald-500/20 text-emerald-300" : "bg-red-500/15 text-red-300"}`}>
        <Icon path={good ? ICONS.check : ICONS.shield} size={18} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-lg font-medium truncate text-neutral-100">{attack}</div>
        <div className={`text-xs font-medium ${good ? "text-emerald-400" : "text-neutral-500"}`}>{verdict}</div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------ target zero */

function TargetZeroSection() {
  return (
    <section id="proof" className="bg-black">
      <div className="max-w-7xl mx-auto px-5 py-24 flex flex-col gap-16 relative">
        <div className="flex flex-col lg:flex-row justify-between items-start lg:items-end gap-8">
          <div className="flex flex-col gap-6 max-w-2xl">
            <span className="text-xs font-semibold uppercase tracking-[0.25em] text-neutral-500">§ 03 — the proof</span>
            <WordsReveal as="h2" className="text-5xl lg:text-6xl text-neutral-100 leading-tight block" text="Claude in an OpenEvolve loop, judged by the layered oracle." step={0.06} duration={0.6} />
            <WordsReveal as="p" className="text-xl lg:text-2xl opacity-60 text-neutral-100 leading-8 block" text="The anchor paper evaluates eight LLMs as optimization agents — never an Anthropic model. We wire Tripwire to OpenEvolve, point the loop at Claude Opus 4.8, and let it optimize a numeric kernel." step={0.025} delay={0.2} duration={0.5} />
          </div>
          <motion.a href={`${REPO_URL}/tree/main/runner`} target="_blank" rel="noreferrer" initial={{ opacity: 0, y: 24 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: "-80px" }} transition={{ duration: 0.6, delay: 0.5, ease: "easeOut" }} className="inline-flex shrink-0 items-center gap-2 bg-white text-black px-7 py-4 rounded-xl font-medium text-lg hover:bg-neutral-200 transition-colors">
            See the runner <Icon path={ICONS.arrowUpRight} size={18} />
          </motion.a>
        </div>

        <div className="flex flex-col lg:flex-row gap-10">
          {/* left: stats + honest framing */}
          <motion.div className="w-full lg:w-[38%] shrink-0 flex flex-col gap-6" initial={{ opacity: 0, y: 40 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: "-80px" }} transition={{ duration: 0.7, ease: "easeOut" }}>
            <div className="rounded-3xl bg-neutral-900 border border-white/5 p-8 flex flex-col gap-6">
              <div className="flex items-baseline gap-3">
                <span className="text-7xl font-medium text-emerald-400 tabular-nums"><CountUpInView end={200} duration={1600} />×</span>
                <span className="text-sm text-neutral-400 leading-tight">best speedup<br />at iteration {TARGET_ZERO.bestIteration}</span>
              </div>
              <div className="grid grid-cols-2 gap-4 border-t border-white/10 pt-6">
                <Stat big={`${TARGET_ZERO.iterations}`} label="iterations, all correct" />
                <Stat big="4/4" label="layers cleared, every step" />
              </div>
              <p className="text-sm text-neutral-500 leading-relaxed">
                <span className="italic text-neutral-400">COMPILOT-inspired, not a reproduction.</span> COMPILOT optimizes C loop nests via the Tiramisu polyhedral compiler; we optimize Python via the empirical layered oracle. We reproduce the principle (RQ7: delegate correctness to a rigorous verifier), not the system.
              </p>
            </div>
          </motion.div>

          {/* right: replay */}
          <motion.div className="w-full lg:w-[62%]" initial={{ opacity: 0, y: 40 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: "-80px" }} transition={{ duration: 0.7, delay: 0.15, ease: "easeOut" }}>
            <TargetZeroReplay />
          </motion.div>
        </div>
      </div>
    </section>
  );
}

function Stat({ big, label }: { big: string; label: string }) {
  return (
    <div className="flex flex-col">
      <span className="text-3xl font-medium text-neutral-100 tabular-nums">{big}</span>
      <span className="text-sm text-neutral-500 mt-1">{label}</span>
    </div>
  );
}

function TargetZeroReplay() {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInViewFM(ref, { once: true, margin: "-80px" });
  const [active, setActive] = useState(0);
  const [playing, setPlaying] = useState(true);
  const trace = TARGET_ZERO.trace;
  const max = Math.max(...trace.map((t) => t.speedup));

  useEffect(() => {
    if (!inView || !playing) return;
    const t = setTimeout(() => setActive((a) => (a + 1) % trace.length), 2600);
    return () => clearTimeout(t);
  }, [inView, playing, active, trace.length]);

  const cur = trace[active];
  return (
    <div ref={ref} className="rounded-3xl border border-white/10 overflow-hidden flex flex-col" style={{ backgroundColor: "#0F0D0F" }}>
      <div className="flex justify-between items-center px-5 py-4">
        <span className="hidden sm:inline text-xs font-mono text-neutral-500">runs/target-zero.jsonl · {TARGET_ZERO.model}</span>
        <button onClick={() => setPlaying((p) => !p)} className="text-xs font-medium text-neutral-400 hover:text-neutral-100 transition-colors bg-white/5 rounded-md px-2.5 py-1">
          {playing ? "❚❚ pause" : "▶ play"}
        </button>
      </div>

      <div className="px-6 pb-5">
        {/* verdict + speedup */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-baseline gap-3">
            <span className="text-4xl font-medium text-neutral-100 tabular-nums">{cur.speedup.toFixed(1)}×</span>
            <span className="text-xs text-neutral-500">iter {cur.iteration} · gen {cur.generation} · island {cur.island}</span>
          </div>
          <span className="inline-flex items-center gap-1.5 bg-emerald-500/15 text-emerald-300 text-xs font-medium px-3 py-1.5 rounded-md outline outline-1 outline-emerald-500/30">
            <Icon path={ICONS.check} size={13} /> layered: {cur.reason}
          </span>
        </div>

        {/* code pane */}
        <div className="rounded-xl bg-black/50 border border-white/10 p-4 mb-4 min-h-[150px]">
          <span className="text-[11px] text-neutral-500 uppercase tracking-wider">child · solve</span>
          <pre className="text-[12px] sm:text-[13px] font-mono text-neutral-300 leading-relaxed whitespace-pre-wrap mt-2">{TARGET_ZERO.winningCode}</pre>
        </div>

        {/* timeline scrubber */}
        <div className="flex items-end justify-between gap-1.5 h-16">
          {trace.map((t, i) => {
            const h = (t.speedup / max) * 100;
            const isActive = i === active;
            const isBest = t.iteration === TARGET_ZERO.bestIteration;
            return (
              <button
                key={t.iteration}
                onClick={() => { setActive(i); setPlaying(false); }}
                className="flex-1 flex flex-col items-center justify-end h-full group"
                aria-label={`iteration ${t.iteration}`}
              >
                <motion.div
                  className={`w-full rounded-t-sm transition-colors ${isActive ? "bg-neutral-100" : isBest ? "bg-emerald-400" : "bg-white/25 group-hover:bg-white/40"}`}
                  initial={{ height: 0 }}
                  animate={inView ? { height: `${h}%` } : { height: 0 }}
                  transition={{ duration: 0.6, delay: 0.1 + i * 0.05, ease: "easeOut" }}
                />
                <span className={`text-[9px] font-display mt-1 ${isActive ? "text-neutral-300" : "text-neutral-600"}`}>{t.iteration}</span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------ shared helpers */

function StaggeredWords({ text, baseDelay = 0, step = 90, active = true }: { text: string; baseDelay?: number; step?: number; active?: boolean }) {
  const words = text.split(" ");
  return (
    <>
      {words.map((w, i) => (
        <span
          key={i}
          style={{
            display: "inline-block",
            opacity: active ? undefined : 0,
            // delay folded into the shorthand (avoids the animation/animationDelay
            // conflict warning); "both" fill keeps each word hidden until its turn.
            animation: active ? `rise-up 0.5s ease-out ${baseDelay + i * step}ms both` : undefined,
          }}
        >
          {w}
          {i < words.length - 1 ? " " : ""}
        </span>
      ))}
    </>
  );
}

function CountNumber({ to, duration = 1.5, start }: { to: number; duration?: number; start: boolean }) {
  const mv = useMotionValue(0);
  const rounded = useTransform(mv, (v) => Math.round(v).toString());
  useEffect(() => {
    if (!start) return;
    const controls = animate(mv, to, { duration, ease: "easeOut" });
    return () => controls.stop();
  }, [start, to, duration, mv]);
  return <motion.span>{rounded}</motion.span>;
}

function CommandBar({ text, startDelay = 0, speed = 60 }: { text: string; startDelay?: number; speed?: number }) {
  const [shown, setShown] = useState("");
  useEffect(() => {
    let cancelled = false;
    let i = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const start = setTimeout(() => {
      const tick = () => {
        if (cancelled) return;
        i += 1;
        setShown(text.slice(0, i));
        if (i < text.length) timer = setTimeout(tick, speed);
      };
      tick();
    }, startDelay);
    return () => { cancelled = true; clearTimeout(start); if (timer) clearTimeout(timer); };
  }, [text, startDelay, speed]);
  return (
    <span className="flex-1 min-w-0 text-sm font-mono text-neutral-100 truncate text-left">
      <span className="text-neutral-500">$ </span>
      {shown}
      <span className="inline-block w-[7px] h-[15px] -mb-0.5 bg-neutral-300 caret-blink ml-0.5" />
    </span>
  );
}

function CopyButton({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() => {
        try { navigator.clipboard?.writeText(value); } catch { /* noop */ }
        setCopied(true);
        setTimeout(() => setCopied(false), 1400);
      }}
      className="shrink-0 inline-flex items-center gap-1.5 bg-white/10 hover:bg-white/20 text-neutral-100 text-sm font-medium rounded-lg h-9 px-3 transition-colors"
    >
      <Icon path={copied ? ICONS.check : ICONS.copy} size={15} /> {copied ? "Copied" : "Copy"}
    </button>
  );
}

function Typewriter({ text, className, speed = 20, delay = 0 }: { text: string; className?: string; speed?: number; delay?: number }) {
  const ref = useRef<HTMLPreElement>(null);
  const inView = useInViewFM(ref, { once: true, margin: "-80px" });
  const [shown, setShown] = useState("");
  useEffect(() => {
    if (!inView) return;
    let i = 0;
    let raf = 0;
    const start = setTimeout(() => {
      const tick = () => {
        i += 1;
        setShown(text.slice(0, i));
        if (i < text.length) raf = window.setTimeout(tick, speed) as unknown as number;
      };
      tick();
    }, delay * 1000);
    return () => { clearTimeout(start); clearTimeout(raf); };
  }, [inView, text, speed, delay]);
  return (
    <pre ref={ref} className={className}>
      {shown}
      <span className="inline-block w-[0.5ch] -mb-0.5 bg-white/60 caret-blink" style={{ height: "1em" }} />
    </pre>
  );
}

function WordsReveal({
  text,
  className,
  as = "span",
  step = 0.06,
  delay = 0,
  duration = 0.7,
  active,
}: {
  text: string;
  className?: string;
  as?: "span" | "h1" | "h2" | "h3" | "p";
  step?: number;
  delay?: number;
  duration?: number;
  active?: boolean;
}) {
  const words = text.split(" ");
  const MotionTag = motion[as] as typeof motion.span;
  const triggerProps =
    active === undefined
      ? { whileInView: "visible" as const, viewport: { once: true, margin: "-80px" } }
      : { animate: active ? ("visible" as const) : ("hidden" as const) };
  return (
    <MotionTag className={className} initial="hidden" {...triggerProps} transition={{ staggerChildren: step, delayChildren: delay }}>
      {words.map((w, i) => (
        <motion.span key={i} style={{ display: "inline-block" }} variants={{ hidden: { opacity: 0, y: 18 }, visible: { opacity: 1, y: 0 } }} transition={{ duration, ease: "easeOut" }}>
          {w}
          {i < words.length - 1 ? " " : ""}
        </motion.span>
      ))}
    </MotionTag>
  );
}

function PillReveal({ delay, children }: { delay: number; children: React.ReactNode }) {
  return (
    <motion.div className="grow flex" initial={{ opacity: 0, y: 30 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: "-100px" }} transition={{ duration: 0.5, delay, ease: "easeOut" }}>
      {children}
    </motion.div>
  );
}

function CountUp({ end, duration = 1500, active, format = (n: number) => n.toLocaleString("en-US") }: { end: number; duration?: number; active: boolean; format?: (n: number) => string }) {
  const [val, setVal] = useState(0);
  useEffect(() => {
    if (!active) return;
    let raf = 0;
    const start = performance.now();
    const tick = (t: number) => {
      const p = Math.min(1, (t - start) / duration);
      const eased = 1 - Math.pow(1 - p, 3);
      setVal(Math.round(end * eased));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [active, end, duration]);
  return <>{format(val)}</>;
}

function CountUpInView({ end, duration = 1500, delay = 0, format, active }: { end: number; duration?: number; delay?: number; format?: (n: number) => string; active?: boolean }) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInViewFM(ref, { once: true, margin: "-100px" });
  const trigger = active === undefined ? inView : active;
  const [start, setStart] = useState(false);
  useEffect(() => {
    if (!trigger) return;
    const t = setTimeout(() => setStart(true), delay);
    return () => clearTimeout(t);
  }, [trigger, delay]);
  return <span ref={ref}><CountUp end={end} duration={duration} active={start} format={format} /></span>;
}

/* ============================================================ the anchor paper: COMPILOT */

function Eyebrow({ children }: { children: React.ReactNode }) {
  return <span className="text-xs font-semibold uppercase tracking-[0.25em] text-neutral-500">{children}</span>;
}

function PaperStat({ value, label, color = "text-neutral-100", delay = 0 }: { value: React.ReactNode; label: string; color?: string; delay?: number }) {
  return (
    <motion.div
      className="flex flex-col rounded-2xl bg-neutral-950 border border-white/10 p-5"
      initial={{ opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-60px" }}
      transition={{ duration: 0.5, delay, ease: "easeOut" }}
    >
      <span className={`text-4xl sm:text-5xl font-semibold tabular-nums ${color}`}>{value}</span>
      <span className="text-sm text-neutral-400 mt-2 leading-tight">{label}</span>
    </motion.div>
  );
}

function ChartPanel({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <motion.div
      className={`rounded-3xl border border-white/10 bg-[#0F0D0F] p-5 sm:p-8 ${className ?? ""}`}
      initial={{ opacity: 0, y: 40 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-80px" }}
      transition={{ duration: 0.7, ease: "easeOut" }}
    >
      {children}
    </motion.div>
  );
}

function FigTag({ children }: { children: React.ReactNode }) {
  return <span className="text-[11px] uppercase tracking-[0.18em] text-neutral-600">{children}</span>;
}

function PaperIntro() {
  return (
    <section id="paper" className="bg-black max-w-7xl mx-auto px-5 pt-24 pb-12 scroll-mt-20">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 items-start">
        <div className="flex flex-col gap-6">
          <Eyebrow>The anchor paper · COMPILOT</Eyebrow>
          <WordsReveal as="h2" className="text-5xl lg:text-6xl leading-[1.05] text-white" text="The model proposes. The compiler verifies." step={0.05} />
          <WordsReveal as="p" className="text-xl opacity-60 text-neutral-100 max-w-[560px] leading-8" text="Tripwire is inspired by COMPILOT (PACT '25): an off-the-shelf LLM proposes loop schedules while the Tiramisu polyhedral compiler owns legality. The model explores — the verifier guarantees correctness. Here is what it found." step={0.02} delay={0.2} duration={0.5} />
          <div className="flex flex-wrap gap-3 pt-2">
            <a href="https://arxiv.org/abs/2511.00592" target="_blank" rel="noreferrer" className="inline-flex items-center gap-2 bg-white text-black px-6 py-3.5 rounded-xl font-medium hover:bg-neutral-200 transition-colors">Read the paper <Icon path={ICONS.arrowUpRight} size={16} /></a>
            <span className="inline-flex items-center bg-white/5 border border-white/10 text-neutral-400 px-5 py-3.5 rounded-xl font-mono text-sm">PACT '25 · {COMPILOT.arxiv}</span>
          </div>
        </div>
        <motion.blockquote
          className="relative rounded-3xl border border-blue-500/25 bg-blue-500/[0.06] p-8 lg:p-10"
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.7, ease: "easeOut" }}
        >
          <p className="text-2xl lg:text-[28px] leading-snug text-neutral-100 font-display">
            “Leverage the LLM for strategic exploration while entrusting the compiler with formal correctness — ensuring reliability without brittle output comparisons.”
          </p>
          <p className="mt-6 text-sm text-neutral-400">RQ7 — the principle Tripwire generalizes: delegate correctness to a rigorous verifier, never trust the model to be correct.</p>
          <div className="mt-6 flex items-baseline gap-3">
            <span className="text-5xl font-semibold text-red-400 tabular-nums"><CountUpInView end={176} format={(n) => (n / 10).toFixed(1)} duration={1200} />%</span>
            <span className="text-sm text-neutral-400 leading-tight max-w-[260px]">of “passing,” faster LLM-written transforms were actually <span className="text-red-300">wrong</span> under fresh random inputs.</span>
          </div>
        </motion.blockquote>
      </div>
    </section>
  );
}

function ExplorationSection() {
  return (
    <section className="bg-black max-w-7xl mx-auto px-5 py-20">
      <div className="flex flex-col gap-6 mb-12 max-w-3xl">
        <Eyebrow>Exploration</Eyebrow>
        <WordsReveal as="h2" className="text-4xl lg:text-5xl leading-tight text-white" text="40 runs, 40 different paths to a speedup." step={0.04} />
        <WordsReveal as="p" className="text-xl opacity-60 text-neutral-100 leading-8 max-w-[640px]" text="Each run is a distinct conversation. Most plateau early; a few keep climbing past 10×. The loop is a stochastic search — which is exactly why a single correctness gate has to hold for every path it takes." step={0.02} delay={0.2} duration={0.5} />
      </div>
      <div className="flex items-center justify-between mb-5">
        <Eyebrow>Fig. 21 — speedup trajectories</Eyebrow>
        <FigTag>gramschmidt_LARGE · 40 runs</FigTag>
      </div>
      <ChartPanel>
        <Trajectories />
      </ChartPanel>
    </section>
  );
}

function CostConvergenceSection() {
  return (
    <section className="bg-black max-w-7xl mx-auto px-5 py-20">
      <div className="flex flex-col gap-6 mb-12 max-w-3xl">
        <Eyebrow>Cost &amp; convergence</Eyebrow>
        <WordsReveal as="h2" className="text-4xl lg:text-5xl leading-tight text-white" text="More iterations and runs converge to bigger speedups — at a token cost." step={0.04} />
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-stretch">
        <ChartPanel className="flex flex-col">
          <div className="flex items-center justify-between mb-6">
            <Eyebrow>Fig. 9 — token consumption</Eyebrow>
            <FigTag>super-linear in T</FigTag>
          </div>
          <p className="text-sm text-neutral-400 leading-relaxed mb-6">Token use grows super-linearly with iterations — ~200k by T=30. Verification is cheap; exploration is what you pay for.</p>
          <div className="mt-auto">
            <TokenCurve />
          </div>
        </ChartPanel>
        <ChartPanel className="flex flex-col">
          <div className="flex items-center justify-between mb-6">
            <Eyebrow>Fig. 16 — best-of-K @ T</Eyebrow>
            <FigTag>speedup surface</FigTag>
          </div>
          <p className="text-sm text-neutral-400 leading-relaxed mb-6">Best-of-K speedup climbs with both runs (K) and iterations (T) — the surface warms from teal to orange as the search gets more chances to break through.</p>
          <div className="mt-auto">
            <Heatmap />
          </div>
        </ChartPanel>
      </div>
    </section>
  );
}

function ViabilitySection() {
  return (
    <section className="bg-black max-w-7xl mx-auto px-5 py-20">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 items-end mb-12">
        <div className="flex flex-col gap-6">
          <Eyebrow>Why you need a verifier</Eyebrow>
          <WordsReveal as="h2" className="text-4xl lg:text-5xl leading-tight text-white" text="Two-thirds of what the model proposes never even runs." step={0.04} />
        </div>
        <p className="text-lg text-neutral-400 leading-8">Across 30 dialogue iterations, only ~36% of the LLM's proposed schedules are runnable — the rest are invalid or illegal. That is the entire case for Tripwire: if the model is wrong two times out of three, correctness cannot be something you trust. It has to be something you <span className="text-neutral-100">verify</span>.</p>
      </div>
      <div className="flex items-center justify-between mb-5">
        <Eyebrow>Fig. 19 — schedule viability over iterations</Eyebrow>
        <FigTag>runnable · illegal · invalid</FigTag>
      </div>
      <ChartPanel>
        <ScheduleViability />
      </ChartPanel>
      <div className="grid grid-cols-3 gap-4 mt-6">
        <PaperStat value={<><CountUpInView end={361} format={(n) => (n / 10).toFixed(1)} duration={1200} />%</>} label="runnable schedules (avg)" color="text-emerald-400" />
        <PaperStat value={<><CountUpInView end={325} format={(n) => (n / 10).toFixed(1)} duration={1200} />%</>} label="illegal — break semantics" color="text-orange-400" delay={0.08} />
        <PaperStat value={<><CountUpInView end={314} format={(n) => (n / 10).toFixed(1)} duration={1200} />%</>} label="invalid — malformed" color="text-pink-400" delay={0.16} />
      </div>
    </section>
  );
}

function ResultsSection() {
  return (
    <section className="bg-black max-w-7xl mx-auto px-5 py-20">
      <div className="flex flex-col gap-6 mb-12 max-w-3xl">
        <Eyebrow>Results</Eyebrow>
        <WordsReveal as="h2" className="text-4xl lg:text-5xl leading-tight text-white" text="2.66× single-run. 3.54× best-of-5. Beats the SOTA polyhedral optimizer." step={0.04} />
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-12">
        <PaperStat value={<><CountUpInView end={266} format={(n) => (n / 100).toFixed(2)} duration={1400} />×</>} label="geomean speedup, single run (COMPILOT@30)" color="text-neutral-100" delay={0} />
        <PaperStat value={<><CountUpInView end={354} format={(n) => (n / 100).toFixed(2)} duration={1400} />×</>} label="geomean, best-of-5 runs" color="text-emerald-400" delay={0.08} />
        <PaperStat value={<><CountUpInView end={294} format={(n) => (n / 100).toFixed(2)} duration={1400} />×</>} label="geomean over Pluto (SOTA)" color="text-blue-300" delay={0.16} />
        <PaperStat value={COMPILOT_STATS.beatsPluto} label="instances where it beats Pluto" color="text-neutral-100" delay={0.24} />
      </div>
      <div className="flex items-center justify-between mb-5">
        <Eyebrow>Fig. 7 — speedup per benchmark</Eyebrow>
        <FigTag>{COMPILOT_STATS.instances} instances · log scale</FigTag>
      </div>
      <ChartPanel>
        <SpeedupChart />
      </ChartPanel>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
        <ChartPanel>
          <div className="flex items-center justify-between mb-6">
            <Eyebrow>Fig. 8 — geomean by size</Eyebrow>
            <FigTag>bigger inputs, bigger wins</FigTag>
          </div>
          <GeomeanBySize />
        </ChartPanel>
        <motion.div
          className="rounded-3xl border border-white/10 bg-[#0F0D0F] p-8 flex flex-col justify-center gap-5"
          initial={{ opacity: 0, y: 40 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.7, ease: "easeOut" }}
        >
          <WordsReveal as="h3" className="text-3xl text-white leading-tight" text="Some kernels break 100×." step={0.05} />
          <p className="text-neutral-400 leading-relaxed">Aggressive parallelization, tiling and unrolling on the largest inputs push a handful of kernels past 100× — correlation and covariance clear 400×. Off-the-shelf LLMs, zero fine-tuning, grounded only by compiler feedback.</p>
          <div className="flex flex-wrap gap-2 pt-1">
            {["correlation 430×", "covariance 455×", "3mm 205×", "trmm 185×", "syr2k 220×"].map((t) => (
              <span key={t} className="text-sm text-emerald-200 bg-emerald-500/10 border border-emerald-500/25 rounded-lg px-3 py-1.5 tabular-nums">{t}</span>
            ))}
          </div>
        </motion.div>
      </div>
    </section>
  );
}

function FrameworkSection() {
  return (
    <section className="bg-black max-w-7xl mx-auto px-5 py-20">
      <div className="flex flex-col gap-6 mb-12 max-w-3xl">
        <Eyebrow>The agentic loop</Eyebrow>
        <WordsReveal as="h2" className="text-4xl lg:text-5xl leading-tight text-white" text="An off-the-shelf model, grounded by compiler feedback." step={0.04} />
        <WordsReveal as="p" className="text-xl opacity-60 text-neutral-100 leading-8 max-w-[640px]" text="The agent only proposes schedules. The compiler checks legality, generates code, runs it, and returns feedback — action, observation, repeat. This is the loop behind every number above, and the loop Tripwire makes trustworthy." step={0.02} delay={0.2} duration={0.5} />
      </div>
      <div className="flex items-center justify-between mb-5">
        <Eyebrow>Fig. 1 — the agentic loop</Eyebrow>
        <FigTag>action / observation</FigTag>
      </div>
      <ChartPanel>
        <FrameworkDiagram />
      </ChartPanel>
    </section>
  );
}
