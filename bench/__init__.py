"""bench -- runnable benchmark + red-team harnesses for the Tripwire oracle.

`bench.run` (owned elsewhere) emits the naive-vs-layered scorecard across all
domains; `bench.attack_suite` (BUILD_PLAN 2.5) is the red-team's continuous attack
harness. Neither edits the frozen core (oracle/measure/target) -- they only measure
and report (HARD RULE 1).
"""
