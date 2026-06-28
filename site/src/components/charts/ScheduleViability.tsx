import { useRef } from "react";
import { motion, useInView } from "framer-motion";
import { SCHEDULE_VIABILITY, VIABILITY_COLORS } from "../../data/compilot";

const W = 1000;
const H = 460;
const X0 = 64;
const X1 = 980;
const Y0 = 36; // top (100%)
const Y1 = 410; // bottom (0%)

const TS = SCHEDULE_VIABILITY.map((d) => d.t);
const tMin = TS[0];
const tMax = TS[TS.length - 1];
const xs = (t: number) => X0 + ((t - tMin) / (tMax - tMin)) * (X1 - X0);
const ys = (p: number) => Y1 - (p / 100) * (Y1 - Y0);

function band(lower: (d: (typeof SCHEDULE_VIABILITY)[number]) => number, upper: (d: (typeof SCHEDULE_VIABILITY)[number]) => number) {
  const top = SCHEDULE_VIABILITY.map((d) => `${xs(d.t)},${ys(upper(d))}`);
  const bot = SCHEDULE_VIABILITY.map((d) => `${xs(d.t)},${ys(lower(d))}`).reverse();
  return `M ${top.join(" L ")} L ${bot.join(" L ")} Z`;
}

// cumulative boundaries (runnable bottom, illegal middle, invalid top)
const runnableTop = (d: (typeof SCHEDULE_VIABILITY)[number]) => d.runnable;
const illegalTop = (d: (typeof SCHEDULE_VIABILITY)[number]) => d.runnable + d.illegal;

export default function ScheduleViability() {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: "-100px" });
  const last = SCHEDULE_VIABILITY[SCHEDULE_VIABILITY.length - 1];

  return (
    <div ref={ref} className="w-full">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" role="img" aria-label="Schedule viability over dialogue iterations">
        <defs>
          <clipPath id="sv-reveal">
            <motion.rect x={X0} y={0} height={H} initial={{ width: 0 }} animate={inView ? { width: X1 - X0 } : { width: 0 }} transition={{ duration: 1.4, ease: "easeInOut" }} />
          </clipPath>
        </defs>

        {/* y gridlines */}
        {[0, 20, 40, 60, 80, 100].map((p) => (
          <g key={p}>
            <line x1={X0} x2={X1} y1={ys(p)} y2={ys(p)} stroke="rgba(255,255,255,0.07)" strokeWidth={1} />
            <text x={X0 - 12} y={ys(p) + 4} textAnchor="end" fontSize={13} fill="#8a8a8a" fontFamily="'Newsreader', Georgia, serif">{p}</text>
          </g>
        ))}

        {/* bands */}
        <g clipPath="url(#sv-reveal)">
          <path d={band(() => 0, runnableTop)} fill={VIABILITY_COLORS.runnable} fillOpacity={0.82} />
          <path d={band(runnableTop, illegalTop)} fill={VIABILITY_COLORS.illegal} fillOpacity={0.82} />
          <path d={band(illegalTop, () => 100)} fill={VIABILITY_COLORS.invalid} fillOpacity={0.82} />
          {/* boundary strokes */}
          <polyline points={SCHEDULE_VIABILITY.map((d) => `${xs(d.t)},${ys(runnableTop(d))}`).join(" ")} fill="none" stroke="#000" strokeOpacity={0.25} strokeWidth={1.5} />
          <polyline points={SCHEDULE_VIABILITY.map((d) => `${xs(d.t)},${ys(illegalTop(d))}`).join(" ")} fill="none" stroke="#000" strokeOpacity={0.25} strokeWidth={1.5} />
        </g>

        {/* % labels at first and last column */}
        {[SCHEDULE_VIABILITY[0], last].map((d, idx) => {
          const x = idx === 0 ? xs(d.t) + 14 : xs(d.t) - 14;
          const anchor = idx === 0 ? "start" : "end";
          return (
            <motion.g key={idx} initial={{ opacity: 0 }} animate={inView ? { opacity: 1 } : { opacity: 0 }} transition={{ delay: 1.1, duration: 0.5 }}>
              <text x={x} y={ys(d.runnable / 2) + 5} textAnchor={anchor} fontSize={16} fontWeight={600} fill="#06281c" fontFamily="'Newsreader', Georgia, serif">{d.runnable}%</text>
              <text x={x} y={ys(d.runnable + d.illegal / 2) + 5} textAnchor={anchor} fontSize={16} fontWeight={600} fill="#3a1c02" fontFamily="'Newsreader', Georgia, serif">{d.illegal}%</text>
              <text x={x} y={ys(d.runnable + d.illegal + d.invalid / 2) + 5} textAnchor={anchor} fontSize={16} fontWeight={600} fill="#3a1029" fontFamily="'Newsreader', Georgia, serif">{d.invalid}%</text>
            </motion.g>
          );
        })}

        {/* x ticks */}
        {[1, 5, 10, 15, 20, 30].map((t) => (
          <text key={t} x={xs(t)} y={Y1 + 26} textAnchor="middle" fontSize={13} fill="#8a8a8a" fontFamily="'Newsreader', Georgia, serif">{t}</text>
        ))}
        <text x={(X0 + X1) / 2} y={H - 6} textAnchor="middle" fontSize={13} fill="#9a9a9a" fontFamily="'Newsreader', Georgia, serif">iterations T</text>
        <text x={18} y={(Y0 + Y1) / 2} textAnchor="middle" fontSize={13} fill="#9a9a9a" fontFamily="'Newsreader', Georgia, serif" transform={`rotate(-90 18 ${(Y0 + Y1) / 2})`}>schedules (%)</text>
      </svg>

      {/* legend */}
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 mt-4 pl-12 text-sm">
        {[
          { c: VIABILITY_COLORS.runnable, l: "Runnable", v: `${last.runnable}%` },
          { c: VIABILITY_COLORS.illegal, l: "Illegal", v: `${last.illegal}%` },
          { c: VIABILITY_COLORS.invalid, l: "Invalid", v: `${last.invalid}%` },
        ].map((it) => (
          <span key={it.l} className="inline-flex items-center gap-2 text-neutral-300">
            <span className="w-3 h-3 rounded-sm" style={{ backgroundColor: it.c }} />
            {it.l} <span className="text-neutral-500 font-display tnum">{it.v}</span>
          </span>
        ))}
      </div>
    </div>
  );
}
