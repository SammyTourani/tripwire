"""tripwire.examples -- bundled, copy-pasteable example files.

These power `tripwire verify --example` / `tripwire optimize --example` and double
as templates: `example_target.py` is a complete, heavily-commented Target you can
copy and adapt; `fast_candidate.py` and `hack_candidate.py` are a real optimization
and a planted reward-hack so you can see the oracle accept one and reject the other.
"""
from pathlib import Path

EXAMPLES_DIR = Path(__file__).resolve().parent
TARGET = EXAMPLES_DIR / "example_target.py"
FAST_CANDIDATE = EXAMPLES_DIR / "fast_candidate.py"
HACK_CANDIDATE = EXAMPLES_DIR / "hack_candidate.py"
