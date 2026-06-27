"""Regression tests for bench.run -- the cross-domain Optimizer Integrity Bench
gate (print_scorecard / write_jsonl / main).

The audit found these three functions untested: a mutation that made the
scorecard always print "TRUSTWORTHY" survived the suite, and main()'s non-zero
exit gate (the regression gate for the WHOLE benchmark) had no coverage. The
sibling file tests/test_bench_scorecard.py exercises collect_rows() decisions
only; this file pins the scorecard SUMMARY and the exit gate.

Teeth (what catches the surviving mutation): we assert the per-oracle
`trustworthy` DISTINCTION -- layered is True (0 hacks / integrity 1.0 / kept 1.0)
while BOTH naive oracles are False (they ship hacks). A scorecard that always
returned trustworthy=True would flip the naive assertions and fail here.

Deterministic decisions + integrity arithmetic only -- never timing magnitudes
(the layered_speedup numbers are machine-dependent and are NOT asserted).
"""
from __future__ import annotations

import json

import pytest

import bench.run as bench_run
from bench.run import collect_rows, main, print_scorecard, write_jsonl


@pytest.fixture(scope="module")
def rows():
    # collect_rows() runs the full layered oracle (incl. L4 speedup measurement)
    # across every target and takes a couple seconds, so build it once per module.
    return collect_rows()


# ---------------------------------------------------------------------------
# print_scorecard -- the summary dict + the trustworthy distinction (the teeth)
# ---------------------------------------------------------------------------
def test_print_scorecard_returns_per_oracle_summary(rows):
    summary = print_scorecard(rows)
    assert isinstance(summary, dict)
    # one entry per oracle the bench reports.
    assert set(summary) == set(bench_run.ORACLES)
    for stats in summary.values():
        assert {"ships_hacks", "integrity", "kept_valid", "trustworthy"} <= set(stats)


def test_layered_summary_is_trustworthy(rows):
    layered = print_scorecard(rows)["layered"]
    assert layered["ships_hacks"] == 0
    assert layered["integrity"] == 1.0
    assert layered["kept_valid"] == 1.0
    assert layered["trustworthy"] is True


def test_naive_oracles_are_not_trustworthy(rows):
    """The teeth: both naive oracles ship hacks => trustworthy is False.

    A mutation that hard-codes the scorecard verdict to TRUSTWORTHY (the one that
    survived the old suite) would make these `trustworthy is False` assertions
    fail -- so this test would catch it.
    """
    summary = print_scorecard(rows)
    for oracle in ("naive_bitwise", "naive_tolerance"):
        stats = summary[oracle]
        assert stats["ships_hacks"] > 0, f"{oracle} should ship at least one hack"
        assert stats["trustworthy"] is False, f"{oracle} must not be reported trustworthy"


def test_only_layered_is_trustworthy(rows):
    """Exactly one oracle (layered) is trustworthy -- the headline distinction."""
    summary = print_scorecard(rows)
    trustworthy = {o for o, s in summary.items() if s["trustworthy"]}
    assert trustworthy == {"layered"}


# ---------------------------------------------------------------------------
# main -- the regression gate exit code
# ---------------------------------------------------------------------------
def test_main_returns_zero_today(tmp_path, monkeypatch):
    # main() also writes a JSONL log via write_jsonl -> RUNS_DIR; redirect it to a
    # tmp dir so the gate test never pollutes the repo's runs/ directory.
    monkeypatch.setattr(bench_run, "RUNS_DIR", tmp_path)
    assert main() == 0


# ---------------------------------------------------------------------------
# write_jsonl -- the event log the Phase-3 visualizer replays
# ---------------------------------------------------------------------------
def test_write_jsonl_emits_valid_event_log(rows, tmp_path, monkeypatch):
    # write_jsonl hardcodes RUNS_DIR; monkeypatch it to tmp_path so we don't touch
    # the real runs/ dir (and cleanup is automatic via the tmp_path fixture).
    monkeypatch.setattr(bench_run, "RUNS_DIR", tmp_path)
    summary = print_scorecard(rows)

    path = write_jsonl(rows, summary)

    # it wrote into our redirected dir, not the repo's runs/.
    assert path.parent == tmp_path
    assert path.exists()

    lines = path.read_text().splitlines()
    events = [json.loads(line) for line in lines]  # every line must be valid JSON

    kinds = [e["event"] for e in events]
    assert kinds[0] == "bench_start", "first event must be bench_start"
    assert kinds[-1] == "summary", "last event must be summary"
    # exactly one candidate event per row.
    assert kinds.count("candidate") == len(rows)
    assert kinds.count("bench_start") == 1
    assert kinds.count("summary") == 1

    # the summary event carries the per-oracle verdicts (visualizer reads these).
    summary_event = events[-1]
    assert summary_event["by_oracle"]["layered"]["trustworthy"] is True
    assert summary_event["by_oracle"]["naive_bitwise"]["trustworthy"] is False
