"""Target-zero runner (BUILD_PLAN task 1.5). Lives outside the dependency-light
core: it needs network + an LLM key and the openevolve package (the `runner`
extra). The core (tripwire/oracle, measure, target, evaluator) imports nothing
from here.
"""
