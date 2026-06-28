import { useRef } from "react";
import { motion, useInView } from "framer-motion";
import { SPEEDUP_BARS, SIZES, SIZE_COLORS, GEOMEAN_BY_SIZE } from "../../data/compilot";
import { logFrac, logTicks } from "../../lib/viz";

const W = 1400;
const H = 560;
const X0 = 64;
const X1 = 1384;
const Y0 = 28;
const Y1 = 470;
const MIN = 1;
const MAX = 500;
const ys = (v: number) => Y1 - logFrac(v, MIN, MAX) * (Y1 - Y0);

const groupW = (X1 - X0) / SPEEDUP_BARS.length;
const barW = (groupW * 0.78) / SIZES.length;

export default function SpeedupChart() {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: "-80px" });

  return (
    <div ref={ref} className="w-full">
      <div className="overflow-x-auto">
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto min-w-[760px]" role="img" aria-label="COMPILOT@30 median speedup per benchmark, log scale">
          {/* log gridlines */}
          {logTicks(MIN, MAX).map((t) => (
            <g key={t}>
              <line x1={X0} x2={X1} y1={ys(t)} y2={ys(t)} stroke="rgba(255,255,255,0.06)" strokeWidth={1} />
              <text x={X0 - 10} y={ys(t) + 4} textAnchor="end" fontSize={12} fill="#7a7a7a" fontFamily="'Newsreader', Georgia, serif">{t >= 1000 ? "1k" : t}×</text>
            </g>
          ))}
          {/* baseline */}
          <line x1={X0} x2={X1} y1={Y1} y2={Y1} stroke="rgba(255,255,255,0.2)" strokeWidth={1} />

          {SPEEDUP_BARS.map((bench, g) => {
            const gx = X0 + g * groupW + groupW * 0.11;
            return (
              <g key={bench.name}>
                {bench.values.map((v, i) => {
                  const h = Y1 - ys(v);
                  const x = gx + i * barW;
                  const top = ys(v + bench.err[i]);
                  const bottom = ys(Math.max(1.02, v - bench.err[i]));
                  return (
                    <g key={i}>
                      <motion.rect
                        x={x}
                        width={barW * 0.92}
                        rx={1}
                        fill={SIZE_COLORS[i]}
                        initial={{ height: 0, y: Y1 }}
                        animate={inView ? { height: h, y: ys(v) } : { height: 0, y: Y1 }}
                        transition={{ duration: 0.6, delay: 0.2 + g * 0.018 + i * 0.04, ease: "easeOut" }}
                      />
                      {bench.err[i] > 0.05 && h > 14 && (
                        <motion.line
                          x1={x + barW * 0.46}
                          x2={x + barW * 0.46}
                          y1={top}
                          y2={bottom}
                          stroke="rgba(255,255,255,0.45)"
                          strokeWidth={1}
                          initial={{ opacity: 0 }}
                          animate={inView ? { opacity: 1 } : { opacity: 0 }}
                          transition={{ delay: 0.6 + g * 0.018, duration: 0.4 }}
                        />
                      )}
                    </g>
                  );
                })}
                <text
                  x={gx + (groupW * 0.78) / 2}
                  y={Y1 + 14}
                  textAnchor="end"
                  fontSize={11.5}
                  fill="#8a8a8a"
                  fontFamily="'Newsreader', Georgia, serif"
                  transform={`rotate(-45 ${gx + (groupW * 0.78) / 2} ${Y1 + 14})`}
                >
                  {bench.name}
                </text>
              </g>
            );
          })}
          <text x={20} y={(Y0 + Y1) / 2} textAnchor="middle" fontSize={13} fill="#9a9a9a" fontFamily="'Newsreader', Georgia, serif" transform={`rotate(-90 20 ${(Y0 + Y1) / 2})`}>median speedup</text>
        </svg>
      </div>

      {/* legend */}
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 mt-5 justify-center text-sm">
        {SIZES.map((s, i) => (
          <span key={s} className="inline-flex items-center gap-2 text-neutral-300">
            <span className="w-3 h-3 rounded-sm" style={{ backgroundColor: SIZE_COLORS[i] }} />
            {s}
          </span>
        ))}
      </div>
    </div>
  );
}

export function GeomeanBySize() {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: "-80px" });
  const max = 8;
  return (
    <div ref={ref} className="w-full">
      <div className="flex items-end justify-between gap-3 sm:gap-5 h-[220px]">
        {GEOMEAN_BY_SIZE.map((d, i) => {
          const h = (d.value / max) * 100;
          return (
            <div key={d.size} className="flex-1 flex flex-col items-center justify-end h-full gap-2">
              <span className="font-display tnum text-lg sm:text-2xl font-semibold" style={{ color: SIZE_COLORS[i] }}>{d.value.toFixed(2)}×</span>
              <motion.div
                className="w-full rounded-t-md"
                style={{ backgroundColor: SIZE_COLORS[i] }}
                initial={{ height: 0 }}
                animate={inView ? { height: `${h}%` } : { height: 0 }}
                transition={{ duration: 0.7, delay: 0.1 + i * 0.1, ease: "easeOut" }}
              />
              <span className="text-xs text-neutral-400">{d.size}</span>
            </div>
          );
        })}
      </div>
      <p className="text-xs text-neutral-500 mt-3 text-center">geometric mean speedup, aggregated by input size</p>
    </div>
  );
}
