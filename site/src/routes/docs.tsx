import type * as React from "react";
import { Link, createFileRoute } from "@tanstack/react-router";
import { LAYERS, README_URL, REPO_URL } from "../data/tripwire";

const RED = "#e5484d";
const PYPI_URL = "https://pypi.org/project/tripwire-oracle/";
const AUTHORING_URL = `${REPO_URL}/blob/main/docs/target-authoring.md`;

export const Route = createFileRoute("/docs")({
  head: () => ({
    meta: [
      { title: "Docs — Tripwire" },
      {
        name: "description",
        content:
          "How to install and use Tripwire: the layered oracle that verifies AI code optimizations are correct on inputs they never saw, before crediting any speedup.",
      },
    ],
  }),
  component: Docs,
});

/* ---------------------------------------------------------------- primitives */

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

function Code({ children }: { children: React.ReactNode }) {
  return (
    <pre className="rounded-xl border border-white/10 bg-[#0B0A0B] p-4 font-mono text-[13px] leading-relaxed text-neutral-200 overflow-x-auto whitespace-pre-wrap">
      <code>{children}</code>
    </pre>
  );
}

function Section({
  id,
  eyebrow,
  title,
  children,
}: {
  id: string;
  eyebrow: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section id={id} className="scroll-mt-24 border-t border-white/10 pt-12 mt-12 first:border-t-0 first:mt-0 first:pt-0">
      <div className="text-[12px] uppercase tracking-[0.2em] mb-3" style={{ color: RED }}>
        {eyebrow}
      </div>
      <h2 className="font-display text-3xl sm:text-4xl text-neutral-100 mb-5">{title}</h2>
      <div className="text-[15px] leading-relaxed text-neutral-300 space-y-4 max-w-[760px]">
        {children}
      </div>
    </section>
  );
}

const TOC = [
  ["install", "Install"],
  ["quickstart", "Quickstart"],
  ["how", "How the oracle works"],
  ["target", "Authoring a Target"],
  ["cli", "CLI reference"],
];

/* ---------------------------------------------------------------------- page */

function Docs() {
  return (
    <div className="min-h-screen bg-black text-neutral-100">
      {/* header */}
      <header className="sticky top-0 z-20 backdrop-blur-md bg-black/70 border-b border-white/10">
        <div className="max-w-[1000px] mx-auto flex items-center px-5 py-4">
          <Link to="/" className="flex items-center gap-3 shrink-0">
            <LogoMark size={36} />
            <span className="text-[18px] font-medium tracking-tight text-neutral-100">Tripwire</span>
          </Link>
          <span className="ml-3 text-neutral-500 text-[15px]">/ docs</span>
          <nav className="ml-auto flex items-center gap-6 text-[15px]">
            <Link to="/" className="text-neutral-400 hover:text-neutral-100 transition-colors">
              Home
            </Link>
            <a
              href={REPO_URL}
              target="_blank"
              rel="noreferrer"
              className="bg-white text-black rounded-lg py-2 px-4 text-[14px] font-medium hover:bg-neutral-200 transition-colors"
            >
              GitHub
            </a>
          </nav>
        </div>
      </header>

      <main className="max-w-[1000px] mx-auto px-5 pb-28">
        {/* hero */}
        <div className="pt-16 pb-4">
          <h1 className="font-display text-5xl sm:text-6xl text-neutral-100 leading-[1.05]">
            Documentation
          </h1>
          <p className="mt-5 text-lg text-neutral-400 max-w-[680px] leading-relaxed">
            Tripwire verifies that an AI-optimized function is still correct on inputs it never
            saw — and only then credits the speedup. Install it, try it on a bundled example, then
            point it at your own code.
          </p>
          {/* table of contents */}
          <div className="mt-8 flex flex-wrap gap-x-6 gap-y-2 text-[14px]">
            {TOC.map(([id, label]) => (
              <a key={id} href={`#${id}`} className="text-neutral-400 hover:text-neutral-100 transition-colors">
                {label}
              </a>
            ))}
          </div>
        </div>

        {/* install */}
        <Section id="install" eyebrow="Get started" title="Install">
          <p>
            Tripwire is a Python package (Python 3.12+). The fastest way to try it is with{" "}
            <a className="underline decoration-white/30 hover:decoration-white" href="https://docs.astral.sh/uv/" target="_blank" rel="noreferrer">uv</a>
            , which runs it with no install or clone:
          </p>
          <p className="text-neutral-400 text-[14px]">Run the latest from GitHub (nothing to install):</p>
          <Code>uvx --from git+https://github.com/SammyTourani/tripwire tripwire demo</Code>
          <p className="text-neutral-400 text-[14px]">Or install it (from source today; from PyPI once 0.3.0 ships):</p>
          <Code>{`# install the current CLI from source:
pip install "git+https://github.com/SammyTourani/tripwire"
tripwire demo

# once 0.3.0 is published, the released package works the same:
pip install tripwire-oracle`}</Code>
          <p>
            The distribution is named <span style={{ color: RED }}>tripwire-oracle</span> (the bare
            name “tripwire” is reserved on PyPI), but the command you run is always{" "}
            <span className="font-mono text-neutral-200">tripwire</span>. The{" "}
            <span className="font-mono text-neutral-200">optimize</span> command additionally needs
            OpenEvolve and an LLM key — Tripwire offers to install OpenEvolve for you when you first
            run it.
          </p>
        </Section>

        {/* quickstart */}
        <Section id="quickstart" eyebrow="Five minutes" title="Quickstart">
          <p>Four commands, in order:</p>
          <Code>{`# 1. see the oracle catch planted reward-hacks across domains (no setup)
tripwire demo

# 2. watch it ACCEPT a real win and REJECT a memorized hack (no setup)
tripwire verify --example

# 3. scaffold a Target from your own slow-but-correct function
tripwire init my_reference.py        # writes my_reference_target.py

# 4. fill in the TODOs, then verify a candidate or run the optimizer
tripwire verify my_reference_target.py my_candidate.py
tripwire optimize my_reference_target.py`}</Code>
          <p>
            Run <span className="font-mono text-neutral-200">tripwire</span> with no arguments for an
            interactive menu, or <span className="font-mono text-neutral-200">tripwire explain</span>{" "}
            for the same overview in your terminal.
          </p>
        </Section>

        {/* how it works */}
        <Section id="how" eyebrow="The mechanism" title="How the oracle works">
          <p>
            AI tools that “optimize” code sometimes cheat: they return code that looks much faster
            but is secretly wrong — it memorized the test answers, or skipped the real work. The
            oracle grades every candidate in four layers. Any correctness layer failing means
            rejection with zero credit; speed is measured only after correctness is proven.
          </p>
          <div className="space-y-4 not-prose">
            {LAYERS.map((l) => (
              <div key={l.id} className="rounded-2xl border border-white/10 bg-[#0F0D0F] p-5">
                <div className="flex items-baseline gap-3">
                  <span className="font-mono text-[15px] font-semibold" style={{ color: RED }}>
                    {l.id}
                  </span>
                  <span className="font-display text-xl text-neutral-100">{l.name}</span>
                </div>
                <p className="mt-1 text-neutral-400 text-[14px] italic">{l.question}</p>
                <p className="mt-2 text-neutral-300 text-[14px] leading-relaxed">{l.catches}</p>
              </div>
            ))}
          </div>
          <p>
            <span style={{ color: RED }}>L3 is the moat.</span> It differential-tests against
            withheld, adversarial inputs the optimizer never saw — which is how a memorized or
            special-cased “optimization” gets caught before its speedup is ever counted.
          </p>
        </Section>

        {/* authoring a target */}
        <Section id="target" eyebrow="Your own code" title="Authoring a Target">
          <p>
            A <span className="font-mono text-neutral-200">Target</span> tells the oracle how to
            judge your problem. It bundles five things:
          </p>
          <ul className="space-y-2 list-none pl-0">
            {[
              ["reference", "the slow-but-correct ground truth (a pure function)"],
              ["canonical_args", "inputs the optimizer is allowed to see (the “test set”)"],
              ["withheld_args", "fresh + adversarial inputs it never sees — the moat (must be non-empty)"],
              ["properties", "metamorphic / invariant checks the real computation must satisfy"],
              ["candidates", "labeled reference implementations (benchmark only)"],
            ].map(([k, v]) => (
              <li key={k} className="flex gap-3">
                <span className="font-mono text-[14px] shrink-0" style={{ color: RED }}>{k}</span>
                <span className="text-neutral-300 text-[14px]">{v}</span>
              </li>
            ))}
          </ul>
          <p>
            You don’t have to write it from scratch. <span className="font-mono text-neutral-200">tripwire init</span>{" "}
            reads your reference function and generates a fill-in-the-blanks skeleton:
          </p>
          <Code>{`tripwire init my_reference.py     # -> my_reference_target.py with TODOs`}</Code>
          <p>
            Make the withheld inputs genuinely adversarial — edges that exercise every code path,
            not more of the same. That split is the whole defense against reward-hacking. See the{" "}
            <a className="underline decoration-white/30 hover:decoration-white" href={AUTHORING_URL} target="_blank" rel="noreferrer">
              full authoring guide
            </a>{" "}
            for the contract and a worked example.
          </p>
        </Section>

        {/* cli reference */}
        <Section id="cli" eyebrow="Reference" title="CLI reference">
          <div className="space-y-4 not-prose">
            {[
              ["tripwire demo", "Run the cross-domain integrity scorecard — the oracle vs. naive oracles across seven domains. No setup."],
              ["tripwire verify TARGET CANDIDATE", "Verify one optimized candidate against a Target: correct on withheld inputs, then how much faster. Add --example to try a bundled one."],
              ["tripwire init REFERENCE.py", "Scaffold a Target skeleton from your reference function. --function picks one if the file has several; -o sets the output."],
              ["tripwire optimize TARGET", "Run a real OpenEvolve loop graded by the oracle (needs OpenEvolve + an LLM key). --iterations, --example, --yes (auto-install OpenEvolve)."],
              ["tripwire explain", "The 4-layer oracle, Targets, and the commands — in your terminal."],
            ].map(([cmd, desc]) => (
              <div key={cmd} className="rounded-xl border border-white/10 bg-[#0F0D0F] p-4">
                <div className="font-mono text-[14px] text-neutral-100">{cmd}</div>
                <div className="mt-1.5 text-neutral-400 text-[14px] leading-relaxed">{desc}</div>
              </div>
            ))}
          </div>
          <p className="text-neutral-400 text-[14px]">
            The <span className="font-mono">optimize</span> loop reads OPENAI_API_KEY and
            OPENEVOLVE_MODEL (OpenAI-compatible; OPENAI_BASE_URL optional) from your environment or a
            local .env.
          </p>
        </Section>

        {/* footer */}
        <footer className="border-t border-white/10 mt-16 pt-8 flex flex-wrap items-center gap-x-6 gap-y-3 text-[14px] text-neutral-400">
          <Link to="/" className="hover:text-neutral-100 transition-colors">← Home</Link>
          <a href={REPO_URL} target="_blank" rel="noreferrer" className="hover:text-neutral-100 transition-colors">GitHub</a>
          <a href={README_URL} target="_blank" rel="noreferrer" className="hover:text-neutral-100 transition-colors">README</a>
          <a href={PYPI_URL} target="_blank" rel="noreferrer" className="hover:text-neutral-100 transition-colors">PyPI</a>
          <a href={AUTHORING_URL} target="_blank" rel="noreferrer" className="hover:text-neutral-100 transition-colors">Authoring a Target</a>
        </footer>
      </main>
    </div>
  );
}
