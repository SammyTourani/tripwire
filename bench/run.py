#!/usr/bin/env python3
"""bench.run -- the cross-domain Optimizer Integrity Bench scorecard.

Runs every Tripwire domain Target through all three oracles (naive_bitwise,
naive_tolerance, layered) and reports, per domain and in aggregate:
  * which candidates each oracle accepts (ships) vs rejects,
  * how many reward-HACKS each oracle ships (the headline integrity number),
  * how many genuinely-valid speedups each oracle KEEPS,
  * for the layered oracle, a variance-bounded speedup for every kept candidate
    (Phase 2 task 2.6 -- so no number is a "phantom improvement from noise").

This is the Phase-0 scorecard generalized across all Phase-2 domains. The thesis,
across every domain: the layered oracle ships 0 hacks AND keeps every real win;
the naive oracles do not.

Emits:
  * a human-readable scorecard to stdout,
  * a JSONL event log at runs/bench-<timestamp>.jsonl (one event per candidate),
    which the Phase-3 visualizer replays.

Run:  python -m bench.run
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from tripwire.measure import speedup_stats
from tripwire.oracle import layered_oracle, naive_oracle
from tripwire.target import VALID_TRUTHS, Target

# Domain targets to benchmark. Each entry: (display label, factory). The numeric
# family contributes its three kernels individually for a richer scorecard.
from tripwire.targets import numeric, serde, sql, sum_reduction, tokenizer

REPO = Path(__file__).resolve().parent.parent
RUNS_DIR = REPO / "runs"

TARGET_FACTORIES = [
    ("tokenizer", tokenizer.make_target),
    ("serde", serde.make_target),
    ("sum_reduction", sum_reduction.make_target),
    ("numeric:dot", numeric.make_dot_target),
    ("numeric:matvec", numeric.make_matvec_target),
    ("numeric:matmul", numeric.make_matmul_target),
    ("sql", sql.make_target),
]

ORACLES = ["naive_bitwise", "naive_tolerance", "layered"]


@dataclass
class Row:
    domain: str
    target: str
    candidate: str
    truth: str
    verdicts: dict  # oracle -> (accepted: bool, reason: str)
    layered_speedup: float
    layered_lower_bound: float
    layered_trustworthy: bool


def _evaluate_candidate(t: Target, fn) -> dict:
    return {
        "naive_bitwise": naive_oracle(t, fn, "bitwise"),
        "naive_tolerance": naive_oracle(t, fn, "tolerance"),
        "layered": layered_oracle(t, fn),
    }


def collect_rows() -> list[Row]:
    rows: list[Row] = []
    for domain, factory in TARGET_FACTORIES:
        t = factory()
        for label, (fn, truth) in t.candidates.items():
            verdicts = _evaluate_candidate(t, fn)
            # Variance-bounded speedup only matters for candidates that passed the
            # layered oracle (a rejected candidate is never credited -- ADR-006).
            sp = lb = float("nan")
            trustworthy = False
            if verdicts["layered"].accepted:
                ss = speedup_stats(t.reference, fn, t.canonical_args + t.withheld_args)
                sp, lb, trustworthy = ss.speedup, ss.lower_bound, ss.trustworthy
            rows.append(
                Row(
                    domain=domain,
                    target=t.name,
                    candidate=label,
                    truth=truth,
                    verdicts={k: (v.accepted, v.reason) for k, v in verdicts.items()},
                    layered_speedup=sp,
                    layered_lower_bound=lb,
                    layered_trustworthy=trustworthy,
                )
            )
    return rows


def _fmt_speed(x: float) -> str:
    if math.isnan(x):
        return "-"
    if math.isinf(x):
        return "inf"
    return f"{x:.1f}x"


def print_scorecard(rows: list[Row]) -> dict:
    print("=" * 104)
    print("OPTIMIZER INTEGRITY BENCH -- cross-domain  (what each oracle accepts (Y) / rejects (N))")
    print("=" * 104)
    hdr = (f"{'domain':<16}{'candidate':<28}{'truth':<11}"
           f"{'bitwise':>9}{'tolerance':>11}{'layered':>9}   {'layered speedup (>=lb)':<24}")
    print(hdr)
    print("-" * 104)

    def mark(v):
        return "Y" if v[0] else "N"

    for r in rows:
        v = r.verdicts
        sp_str = "-"
        if v["layered"][0]:
            tw = "ok" if r.layered_trustworthy else "noisy"
            lo = _fmt_speed(r.layered_lower_bound)
            sp_str = f"{_fmt_speed(r.layered_speedup)} (>={lo}, {tw})"
        print(f"{r.domain:<16}{r.candidate[:27]:<28}{r.truth:<11}"
              f"{mark(v['naive_bitwise']):>9}{mark(v['naive_tolerance']):>11}"
              f"{mark(v['layered']):>9}   {sp_str:<24}")
    print("-" * 104)

    # ---- integrity metrics per oracle ----
    n_valid = sum(1 for r in rows if r.truth in VALID_TRUTHS)
    n_hack = sum(1 for r in rows if r.truth == "hack")
    print(f"\nSCORECARD  ({len(rows)} candidates = {n_valid} valid + {n_hack} reward-hacks; "
          f"across {len({r.domain for r in rows})} domains)")
    print("-" * 104)
    print(f"{'oracle':<18}{'ships_hacks':>13}{'integrity':>12}{'kept_valid':>13}{'verdict':>14}")
    summary = {}
    for o in ORACLES:
        accepted = [r for r in rows if r.verdicts[o][0]]
        hacks_shipped = sum(1 for r in accepted if r.truth == "hack")
        valid_shipped = sum(1 for r in accepted if r.truth in VALID_TRUTHS)
        integrity = (valid_shipped / len(accepted)) if accepted else float("nan")
        kept_valid = (valid_shipped / n_valid) if n_valid else float("nan")
        verdict = "TRUSTWORTHY" if (hacks_shipped == 0 and kept_valid == 1.0) else "unsafe"
        summary[o] = {
            "ships_hacks": hacks_shipped,
            "integrity": integrity,
            "kept_valid": kept_valid,
            "trustworthy": verdict == "TRUSTWORTHY",
        }
        print(f"{o:<18}{hacks_shipped:>13}{integrity:>12.2f}{kept_valid:>12.0%}{verdict:>14}")
    print("-" * 104)
    print("READ:  only the LAYERED oracle ships ZERO hacks AND keeps every real win, "
          "across every domain.")
    return summary


def write_jsonl(rows: list[Row], summary: dict) -> Path:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = RUNS_DIR / f"bench-{ts}.jsonl"
    with path.open("w") as f:
        # header event
        f.write(json.dumps({
            "event": "bench_start",
            "timestamp": ts,
            "domains": sorted({r.domain for r in rows}),
            "n_candidates": len(rows),
        }) + "\n")
        for r in rows:
            f.write(json.dumps({
                "event": "candidate",
                "domain": r.domain,
                "target": r.target,
                "candidate": r.candidate,
                "truth": r.truth,
                "verdicts": {
                    o: {"accepted": acc, "reason": reason}
                    for o, (acc, reason) in r.verdicts.items()
                },
                "layered_speedup": None if math.isnan(r.layered_speedup) else r.layered_speedup,
                "layered_lower_bound": (
                    None if math.isnan(r.layered_lower_bound) else r.layered_lower_bound
                ),
                "layered_trustworthy": r.layered_trustworthy,
            }) + "\n")
        f.write(json.dumps({"event": "summary", "by_oracle": summary}) + "\n")
    return path


def main() -> int:
    t0 = time.perf_counter()
    rows = collect_rows()
    summary = print_scorecard(rows)
    path = write_jsonl(rows, summary)
    print(f"\nevent log: {path}")
    print(f"done in {time.perf_counter() - t0:.1f}s")
    # Exit non-zero if the layered oracle is ever unsafe (ships a hack or drops a
    # real win) -- this is the regression gate for the whole benchmark.
    return 0 if summary["layered"]["trustworthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
