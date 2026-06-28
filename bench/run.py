#!/usr/bin/env python3
"""bench.run -- the cross-domain Optimizer Integrity Bench scorecard (checkout CLI).

Runs every Tripwire domain Target through all three oracles (naive_bitwise,
naive_tolerance, layered) and reports, per domain and in aggregate:
  * which candidates each oracle accepts (ships) vs rejects,
  * how many reward-HACKS each oracle ships (the headline integrity number),
  * how many genuinely-valid speedups each oracle KEEPS,
  * for the layered oracle, a variance-bounded speedup for every kept candidate.

The pure computation (Row, collect_rows, summarize, the domain list) now lives in
the packaged, side-effect-free `tripwire.scorecard`, so the benchmark and the
`tripwire` CLI share one source of truth. This module adds the two things specific
to running the bench from a checkout: a plain-text scorecard on stdout and a JSONL
event log under runs/ that the Phase-3 visualizer replays.

Run:  python -m bench.run
"""
from __future__ import annotations

import json
import math
import time
from datetime import UTC, datetime
from pathlib import Path

from tripwire.scorecard import ORACLES, TARGET_FACTORIES, Row, collect_rows, summarize
from tripwire.target import VALID_TRUTHS

REPO = Path(__file__).resolve().parent.parent
RUNS_DIR = REPO / "runs"

# Re-exported for backwards compatibility: TARGET_FACTORIES / ORACLES / Row /
# collect_rows used to be defined here; tests and external callers still import
# them from bench.run.
__all__ = [
    "ORACLES",
    "Row",
    "TARGET_FACTORIES",
    "RUNS_DIR",
    "collect_rows",
    "print_scorecard",
    "write_jsonl",
    "main",
]


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

    # ---- integrity metrics per oracle (shared with the tripwire CLI) ----
    n_valid = sum(1 for r in rows if r.truth in VALID_TRUTHS)
    n_hack = sum(1 for r in rows if r.truth == "hack")
    print(f"\nSCORECARD  ({len(rows)} candidates = {n_valid} valid + {n_hack} reward-hacks; "
          f"across {len({r.domain for r in rows})} domains)")
    print("-" * 104)
    print(f"{'oracle':<18}{'ships_hacks':>13}{'integrity':>12}{'kept_valid':>13}{'verdict':>14}")
    summary = summarize(rows)
    for o in ORACLES:
        s = summary[o]
        verdict = "TRUSTWORTHY" if s["trustworthy"] else "unsafe"
        print(f"{o:<18}{s['ships_hacks']:>13}{s['integrity']:>12.2f}"
              f"{s['kept_valid']:>12.0%}{verdict:>14}")
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
