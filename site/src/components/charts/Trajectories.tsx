import { useRef } from "react";
import { motion, useInView } from "framer-motion";
import { TRAJECTORIES, TRAJECTORY_MAX } from "../../data/compilot";
import { logFrac } from "../../lib/viz";

const W = 1000;
const H = 440;
const X0 = 56;
const X1 = 980;
const Y0 = 28;
const Y1 = 396;
const STEPS = TRAJECTORIES[0].length - 1; // 30

const xs = (t: number) => X0 + (t / STEPS) * (X1 - X0);
const ys = (v: number) => Y1 - logFrac(v, 1, TRAJECTORY_MAX) * (Y1 - Y0);

function stepPath(arr: number[]) {
  let d = `M ${xs(0).toFixed(1)} ${ys(arr[0]).toFixed(1)}`;
  for (let t = 1; t < arr.length; t++) {
    d += ` H ${xs(t).toFixed(1)} V ${ys(arr[t]).toFixed(1)}`;
  }
  return d;
}

const Y_TICKS = [1, 2, 5, 10, 20];

export default function Trajectories() {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: "-80px" });

  return (
    <div ref={ref} className="w-full">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" role="img" aria-label="Evolution of speedup over iterations for 40 runs">
        {Y_TICKS.map((t) => (
          <g key={t}>
            <line x1={X0} x2={X1} y1={ys(t)} y2={ys(t)} stroke="rgba(255,255,255,0.06)" strokeWidth={1} />
            <text x={X0 - 10} y={ys(t) + 4} textAnchor="end" fontSize={12} fill="#7a7a7a" fontFamily="'Newsreader', Georgia, serif">{t}×</text>
          </g>
        ))}
        {[0, 5, 10, 15, 20, 25, 30].map((t) => (
          <text key={t} x={xs(t)} y={Y1 + 24} textAnchor="middle" fontSize={12} fill="#8a8a8a" fontFamily="'Newsreader', Georgia, serif">{t}</text>
        ))}
        <text x={(X0 + X1) / 2} y={H - 4} textAnchor="middle" fontSize={13} fill="#9a9a9a" fontFamily="'Newsreader', Georgia, serif">iterations T</text>

        {TRAJECTORIES.map((arr, i) => {
          const hue = (i * 41) % 360;
          const final = arr[arr.length - 1];
          const isBreakout = final > 8;
          return (
            <motion.path
              key={i}
              d={stepPath(arr)}
              fill="none"
              stroke={`hsl(${hue} 70% 62%)`}
              strokeWidth={isBreakout ? 2.4 : 1.4}
              strokeOpacity={isBreakout ? 0.95 : 0.55}
              strokeLinejoin="round"
              strokeLinecap="round"
              initial={{ pathLength: 0, opacity: 0 }}
              animate={inView ? { pathLength: 1, opacity: 1 } : { pathLength: 0, opacity: 0 }}
              transition={{ pathLength: { duration: 1.6, delay: 0.1 + i * 0.03, ease: "easeInOut" }, opacity: { duration: 0.3, delay: 0.1 + i * 0.03 } }}
            />
          );
        })}
      </svg>
    </div>
  );
}
