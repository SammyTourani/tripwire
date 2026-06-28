import { useRef } from "react";
import { motion, useInView } from "framer-motion";
import { TOKEN_CURVE, HEATMAP } from "../../data/compilot";
import { fmtTokens } from "../../lib/viz";

/* ---------------- Fig. 9 — token consumption vs iterations ---------------- */

const W = 1000;
const H = 380;
const X0 = 70;
const X1 = 968;
const Y0 = 26;
const Y1 = 320;
const TMAX = 30;
const TOKMAX = 200000;
const xs = (t: number) => X0 + (t / TMAX) * (X1 - X0);
const ys = (tok: number) => Y1 - (tok / TOKMAX) * (Y1 - Y0);

export function TokenCurve() {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: "-80px" });
  const line = "M " + TOKEN_CURVE.map((p) => `${xs(p.t).toFixed(1)} ${ys(p.tokens).toFixed(1)}`).join(" L ");
  const area = line + ` L ${xs(TMAX)} ${Y1} L ${xs(0)} ${Y1} Z`;

  return (
    <div ref={ref} className="w-full">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" role="img" aria-label="Cumulative token consumption versus iterations">
        <defs>
          <linearGradient id="tok-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#fb923c" stopOpacity={0.35} />
            <stop offset="100%" stopColor="#fb923c" stopOpacity={0} />
          </linearGradient>
          <clipPath id="tok-reveal">
            <motion.rect x={X0} y={0} height={H} initial={{ width: 0 }} animate={inView ? { width: X1 - X0 } : { width: 0 }} transition={{ duration: 1.6, ease: "easeInOut" }} />
          </clipPath>
        </defs>

        {[0, 50000, 100000, 150000, 200000].map((tok) => (
          <g key={tok}>
            <line x1={X0} x2={X1} y1={ys(tok)} y2={ys(tok)} stroke="rgba(255,255,255,0.06)" strokeWidth={1} />
            <text x={X0 - 10} y={ys(tok) + 4} textAnchor="end" fontSize={12} fill="#7a7a7a" fontFamily="'Newsreader', Georgia, serif">{fmtTokens(tok)}</text>
          </g>
        ))}
        {[0, 5, 10, 15, 20, 25, 30].map((t) => (
          <text key={t} x={xs(t)} y={Y1 + 24} textAnchor="middle" fontSize={12} fill="#8a8a8a" fontFamily="'Newsreader', Georgia, serif">{t}</text>
        ))}

        <g clipPath="url(#tok-reveal)">
          <path d={area} fill="url(#tok-fill)" />
          <path d={line} fill="none" stroke="#fb923c" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" />
        </g>
        <motion.circle cx={xs(TMAX)} cy={ys(TOKMAX)} r={5} fill="#fb923c" initial={{ opacity: 0 }} animate={inView ? { opacity: 1 } : { opacity: 0 }} transition={{ delay: 1.5, duration: 0.4 }} />
        <motion.text x={xs(TMAX) - 8} y={ys(TOKMAX) - 12} textAnchor="end" fontSize={15} fontWeight={600} fill="#fdba74" fontFamily="'Newsreader', Georgia, serif" initial={{ opacity: 0 }} animate={inView ? { opacity: 1 } : { opacity: 0 }} transition={{ delay: 1.6, duration: 0.4 }}>~200k @ T=30</motion.text>
        <text x={(X0 + X1) / 2} y={H - 4} textAnchor="middle" fontSize={13} fill="#9a9a9a" fontFamily="'Newsreader', Georgia, serif">iterations T</text>
      </svg>
    </div>
  );
}

/* ---------------- Fig. 16 — heatmap of COMPILOT_K@T ---------------- */

function heat(t: number) {
  const stops = [
    [13, 90, 96],
    [16, 185, 129],
    [250, 204, 21],
    [249, 115, 22],
  ];
  const seg = t * (stops.length - 1);
  const i = Math.min(stops.length - 2, Math.floor(seg));
  const f = seg - i;
  const a = stops[i];
  const b = stops[i + 1];
  return `rgb(${Math.round(a[0] + (b[0] - a[0]) * f)},${Math.round(a[1] + (b[1] - a[1]) * f)},${Math.round(a[2] + (b[2] - a[2]) * f)})`;
}

export function Heatmap() {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: "-80px" });
  const { grid, ks, ts, min, max } = HEATMAP;
  const HW = 1000;
  const HH = 360;
  const hx0 = 56;
  const hy0 = 20;
  const cw = (HW - hx0 - 10) / ts.length;
  const ch = (HH - hy0 - 36) / ks.length;

  return (
    <div ref={ref} className="w-full">
      <svg viewBox={`0 0 ${HW} ${HH}`} className="w-full h-auto" role="img" aria-label="Heatmap of best-of-K speedup after T iterations">
        {grid.map((row, r) =>
          row.map((v, ccol) => {
            const norm = (v - min) / (max - min);
            // top row = highest K
            const rowFromTop = ks.length - 1 - r;
            return (
              <motion.rect
                key={`${r}-${ccol}`}
                x={hx0 + ccol * cw}
                y={hy0 + rowFromTop * ch}
                width={cw + 0.6}
                height={ch + 0.6}
                fill={heat(norm)}
                initial={{ opacity: 0 }}
                animate={inView ? { opacity: 0.92 } : { opacity: 0 }}
                transition={{ duration: 0.5, delay: (ccol * 0.012) + (rowFromTop * 0.02), ease: "easeOut" }}
              />
            );
          })
        )}
        {/* axes */}
        {[1, 5, 10, 15, 20, 25, 30].map((t) => (
          <text key={t} x={hx0 + (t - 0.5) * cw} y={HH - 16} textAnchor="middle" fontSize={12} fill="#8a8a8a" fontFamily="'Newsreader', Georgia, serif">{t}</text>
        ))}
        {[1, 4, 7, 10].map((k) => {
          const rowFromTop = ks.length - k;
          return (
            <text key={k} x={hx0 - 10} y={hy0 + (rowFromTop + 0.5) * ch + 4} textAnchor="end" fontSize={12} fill="#8a8a8a" fontFamily="'Newsreader', Georgia, serif">{k}</text>
          );
        })}
        <text x={(hx0 + HW) / 2} y={HH - 2} textAnchor="middle" fontSize={13} fill="#9a9a9a" fontFamily="'Newsreader', Georgia, serif">iterations T</text>
        <text x={16} y={(hy0 + HH - 36) / 2} textAnchor="middle" fontSize={13} fill="#9a9a9a" fontFamily="'Newsreader', Georgia, serif" transform={`rotate(-90 16 ${(hy0 + HH - 36) / 2})`}>runs K</text>
      </svg>
      <div className="flex items-center gap-3 mt-3 justify-end text-xs text-neutral-500">
        <span>{min.toFixed(1)}×</span>
        <div className="h-2.5 w-40 rounded-full" style={{ background: `linear-gradient(to right, ${heat(0)}, ${heat(0.33)}, ${heat(0.66)}, ${heat(1)})` }} />
        <span>{max.toFixed(1)}×</span>
      </div>
    </div>
  );
}
