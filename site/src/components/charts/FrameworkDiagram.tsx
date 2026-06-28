import { useRef } from "react";
import { motion, useInView } from "framer-motion";
import { FEEDBACK, TRANSFORMATIONS } from "../../data/compilot";

const ACTION_PATH = "M 648 198 C 588 116, 542 116, 482 198";
const OBS_PATH = "M 482 286 C 542 372, 588 372, 648 286";

function Node({
  x, y, w, h, accent = "#3b82f6", children, delay = 0, inView,
}: { x: number; y: number; w: number; h: number; accent?: string; children: React.ReactNode; delay?: number; inView: boolean }) {
  return (
    <motion.g
      initial={{ opacity: 0, y: 14 }}
      animate={inView ? { opacity: 1, y: 0 } : { opacity: 0, y: 14 }}
      transition={{ duration: 0.5, delay, ease: "easeOut" }}
    >
      <rect x={x} y={y} width={w} height={h} rx={14} fill="#0F0D0F" stroke={accent} strokeOpacity={0.5} strokeWidth={1.4} />
      <rect x={x} y={y} width={4} height={h} rx={2} fill={accent} />
      {children}
    </motion.g>
  );
}

function Pulse({ path, color, dur, begin }: { path: string; color: string; dur: number; begin: number }) {
  return (
    <circle r={4.5} fill={color}>
      <animateMotion dur={`${dur}s`} begin={`${begin}s`} repeatCount="indefinite" path={path} />
      <animate attributeName="opacity" values="0;1;1;0" dur={`${dur}s`} begin={`${begin}s`} repeatCount="indefinite" />
    </circle>
  );
}

export default function FrameworkDiagram() {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: "-100px" });

  return (
    <div ref={ref} className="w-full">
      <svg viewBox="0 0 1000 480" className="w-full h-auto" role="img" aria-label="The COMPILOT agentic loop">
        <defs>
          <marker id="fd-arrow" markerWidth="9" markerHeight="9" refX="6" refY="3" orient="auto">
            <path d="M0,0 L6,3 L0,6 Z" fill="#6b7280" />
          </marker>
        </defs>

        {/* input -> compiler */}
        <motion.path d="M 150 116 C 175 150, 215 168, 252 175" fill="none" stroke="#4b5563" strokeWidth={1.6} markerEnd="url(#fd-arrow)" strokeDasharray="5 5" initial={{ pathLength: 0 }} animate={inView ? { pathLength: 1 } : {}} transition={{ duration: 0.6, delay: 0.2 }} />
        {/* compiler -> optimized program */}
        <motion.path d="M 340 318 L 340 392" fill="none" stroke="#34d399" strokeWidth={1.8} markerEnd="url(#fd-arrow)" initial={{ pathLength: 0 }} animate={inView ? { pathLength: 1 } : {}} transition={{ duration: 0.5, delay: 1.0 }} />

        {/* the loop arrows */}
        <path d={ACTION_PATH} fill="none" stroke="#3b82f6" strokeOpacity={0.6} strokeWidth={1.8} markerEnd="url(#fd-arrow)" />
        <path d={OBS_PATH} fill="none" stroke="#f59e0b" strokeOpacity={0.6} strokeWidth={1.8} markerEnd="url(#fd-arrow)" />
        <text x={565} y={120} textAnchor="middle" fontSize={13} fill="#93c5fd" fontFamily="'Newsreader', Georgia, serif">action · &lt;schedule&gt;</text>
        <text x={565} y={372} textAnchor="middle" fontSize={13} fill="#fcd34d" fontFamily="'Newsreader', Georgia, serif">observation · feedback</text>

        {/* traveling pulses */}
        {inView && (
          <>
            <Pulse path={ACTION_PATH} color="#60a5fa" dur={2.4} begin={0} />
            <Pulse path={ACTION_PATH} color="#60a5fa" dur={2.4} begin={1.2} />
            <Pulse path={OBS_PATH} color="#fbbf24" dur={2.4} begin={0.6} />
            <Pulse path={OBS_PATH} color="#fbbf24" dur={2.4} begin={1.8} />
          </>
        )}

        {/* Input Program */}
        <Node x={70} y={66} w={130} h={56} accent="#9ca3af" delay={0} inView={inView}>
          <text x={135} y={90} textAnchor="middle" fontSize={14} fontWeight={600} fill="#e5e5e5" fontFamily="'Newsreader', Georgia, serif">Input program</text>
          <text x={135} y={108} textAnchor="middle" fontSize={11} fill="#8a8a8a" fontFamily="'Newsreader', Georgia, serif">C loop nest</text>
        </Node>

        {/* Compiler & Runtime */}
        <Node x={200} y={168} w={284} h={150} accent="#f59e0b" delay={0.15} inView={inView}>
          <text x={342} y={196} textAnchor="middle" fontSize={16} fontWeight={600} fill="#f5f5f5" fontFamily="'Newsreader', Georgia, serif">Compiler &amp; Runtime</text>
          <text x={342} y={214} textAnchor="middle" fontSize={11} fill="#9a9a9a" fontFamily="'Newsreader', Georgia, serif">Tiramisu · polyhedral legality</text>
          {["validity", "legality", "compile", "run"].map((s, i) => (
            <g key={s}>
              <rect x={216 + i * 64} y={232} width={58} height={26} rx={6} fill="rgba(245,158,11,0.12)" stroke="rgba(245,158,11,0.3)" />
              <text x={216 + i * 64 + 29} y={249} textAnchor="middle" fontSize={10.5} fill="#fcd34d" fontFamily="'Newsreader', Georgia, serif">{s}</text>
            </g>
          ))}
          <text x={342} y={290} textAnchor="middle" fontSize={11} fill="#7a7a7a" fontFamily="'Newsreader', Georgia, serif">measured speedup → feedback</text>
        </Node>

        {/* LLM Agent */}
        <Node x={650} y={168} w={224} h={150} accent="#3b82f6" delay={0.3} inView={inView}>
          <text x={762} y={206} textAnchor="middle" fontSize={18} fontWeight={600} fill="#f5f5f5" fontFamily="'Newsreader', Georgia, serif">LLM Agent</text>
          <text x={762} y={228} textAnchor="middle" fontSize={11} fill="#9a9a9a" fontFamily="'Newsreader', Georgia, serif">off-the-shelf · in-context</text>
          <text x={762} y={246} textAnchor="middle" fontSize={11} fill="#9a9a9a" fontFamily="'Newsreader', Georgia, serif">no fine-tuning</text>
          <g>
            <rect x={690} y={262} width={144} height={28} rx={7} fill="rgba(59,130,246,0.12)" stroke="rgba(59,130,246,0.3)" />
            <text x={762} y={280} textAnchor="middle" fontSize={11} fill="#93c5fd" fontFamily="'Newsreader', Georgia, serif">proposes loop schedule</text>
          </g>
        </Node>

        {/* Optimized Program */}
        <Node x={262} y={394} w={156} h={56} accent="#34d399" delay={1.1} inView={inView}>
          <text x={340} y={418} textAnchor="middle" fontSize={14} fontWeight={600} fill="#e5e5e5" fontFamily="'Newsreader', Georgia, serif">Optimized program</text>
          <text x={340} y={436} textAnchor="middle" fontSize={11} fill="#6ee7b7" fontFamily="'Newsreader', Georgia, serif">provably legal</text>
        </Node>
      </svg>

      {/* chips: transformations + feedback */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-8">
        <div>
          <p className="text-xs uppercase tracking-[0.18em] text-neutral-500 mb-3">action space · 9 transformations</p>
          <div className="flex flex-wrap gap-2">
            {TRANSFORMATIONS.map((t, i) => (
              <motion.span
                key={t}
                className="text-sm text-blue-200 bg-blue-500/10 border border-blue-500/25 rounded-lg px-3 py-1.5"
                initial={{ opacity: 0, y: 10 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-60px" }}
                transition={{ duration: 0.4, delay: i * 0.05 }}
              >
                {t}
              </motion.span>
            ))}
          </div>
        </div>
        <div>
          <p className="text-xs uppercase tracking-[0.18em] text-neutral-500 mb-3">feedback categories</p>
          <div className="flex flex-wrap gap-2">
            {FEEDBACK.map((f, i) => (
              <motion.span
                key={f.label}
                className={`text-sm rounded-lg px-3 py-1.5 border ${f.tone === "good" ? "text-emerald-200 bg-emerald-500/10 border-emerald-500/25" : f.tone === "warn" ? "text-amber-200 bg-amber-500/10 border-amber-500/25" : "text-red-200 bg-red-500/10 border-red-500/25"}`}
                initial={{ opacity: 0, y: 10 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-60px" }}
                transition={{ duration: 0.4, delay: i * 0.05 }}
              >
                {f.label}
              </motion.span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
