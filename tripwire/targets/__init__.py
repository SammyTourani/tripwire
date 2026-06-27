"""tripwire.targets -- one module per domain Target (Interface A).

Parallelizable in Phase 2 (BUILD_PLAN 2.1-2.4). Each target module OWNS its own
file and its test; no two parallel agents touch the same file.
"""
