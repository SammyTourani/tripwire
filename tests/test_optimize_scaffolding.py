"""No-network tests for the optimize scaffolding (tripwire.optimize).

Covers everything that assembles the OpenEvolve inputs WITHOUT running the loop
(no LLM, no API key): target loading, initial-program derivation, evaluator-file
generation, and config validation. The live loop is exercised separately.
"""
from __future__ import annotations

import pytest

from tripwire import optimize as opt
from tripwire.target import STRUCTURAL, Target
from tripwire.targets.sum_reduction import make_target


# --- load_target ------------------------------------------------------------
def test_load_target_make_target(tmp_path):
    f = tmp_path / "t.py"
    f.write_text(
        "from tripwire.target import STRUCTURAL, Target\n"
        "def reference(xs):\n    return sorted(xs)\n"
        "def make_target():\n"
        "    return Target('sortlist', STRUCTURAL, reference, [([3,1,2],)], [([9,7,8],)])\n"
    )
    t = opt.load_target(str(f))
    assert isinstance(t, Target)
    assert t.name == "sortlist"


def test_load_target_missing_file():
    with pytest.raises(opt.OptimizeError):
        opt.load_target("/nope/does-not-exist.py")


def test_load_target_no_target(tmp_path):
    f = tmp_path / "bad.py"
    f.write_text("x = 1\n")
    with pytest.raises(opt.OptimizeError):
        opt.load_target(str(f))


# --- derive_initial_program -------------------------------------------------
def test_derive_initial_program_renames_to_solve():
    src = opt.derive_initial_program(make_target())
    assert "def solve(" in src
    assert "def reference(" not in src
    assert "# EVOLVE-BLOCK-START" in src
    assert "# EVOLVE-BLOCK-END" in src
    assert "for x in arr" in src  # the sequential reference body carried over
    compile(src, "<derived>", "exec")  # must be valid Python


def test_derive_initial_program_carries_module_imports():
    # numeric references use numpy; the module's `import numpy as np` must come along.
    from tripwire.targets import numeric

    src = opt.derive_initial_program(numeric.make_dot_target())
    assert "def solve(" in src
    assert "numpy" in src
    compile(src, "<derived>", "exec")


def test_derive_initial_program_lambda_raises():
    t = Target("lam", STRUCTURAL, lambda xs: sorted(xs), [([1],)], [([2],)])
    with pytest.raises(opt.OptimizeError):
        opt.derive_initial_program(t)


# --- write_evaluator_file ---------------------------------------------------
def test_write_evaluator_file(tmp_path):
    tf = tmp_path / "tt.py"
    tf.write_text("def make_target():\n    return None\n")
    dest = opt.write_evaluator_file(str(tf), tmp_path / "ev.py")
    txt = dest.read_text()
    assert "def evaluate(" in txt
    assert str(tf.resolve()) in txt  # absolute target path embedded
    compile(txt, "<ev>", "exec")  # valid Python


# --- build_config (validates env; no network) -------------------------------
def test_build_config_requires_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENEVOLVE_MODEL", "some-model")
    with pytest.raises(opt.OptimizeError):
        opt.build_config(3)


def test_build_config_requires_model(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.delenv("OPENEVOLVE_MODEL", raising=False)
    with pytest.raises(opt.OptimizeError):
        opt.build_config(3)


# --- load_dotenv ------------------------------------------------------------
def test_load_dotenv_sets_without_overwriting(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("# comment\nTRIPWIRE_TEST_A=fromfile\nTRIPWIRE_TEST_B=fromfile\n")
    monkeypatch.setenv("TRIPWIRE_TEST_B", "preset")
    monkeypatch.delenv("TRIPWIRE_TEST_A", raising=False)
    opt.load_dotenv(str(env))
    import os

    assert os.environ["TRIPWIRE_TEST_A"] == "fromfile"
    assert os.environ["TRIPWIRE_TEST_B"] == "preset"  # not overwritten


def test_load_dotenv_handles_export_quotes_comments(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        "export TW_K1=plain\n"
        'TW_K2="quoted-model"\n'
        "TW_K3=val # inline comment\n"
    )
    for k in ("TW_K1", "TW_K2", "TW_K3"):
        monkeypatch.delenv(k, raising=False)
    opt.load_dotenv(str(env))
    import os

    assert os.environ["TW_K1"] == "plain"  # leading `export ` stripped
    assert os.environ["TW_K2"] == "quoted-model"  # surrounding quotes stripped
    assert os.environ["TW_K3"] == "val"  # trailing inline comment dropped


# --- regression: critical import-carrying bug (load_target + getmodule==None) ----
def test_derive_carries_imports_for_load_target_file(tmp_path):
    """A standalone target file whose reference uses numpy must yield a derived solve
    that actually has `import numpy` and runs -- the review's critical finding."""
    f = tmp_path / "nt.py"
    f.write_text(
        "import numpy as np\n"
        "from tripwire.target import NUMERIC, Target\n"
        "def reference(arr):\n"
        "    out = np.empty(len(arr))\n"
        "    for i in range(len(arr)):\n"
        "        out[i] = arr[i] * 2.0\n"
        "    return out\n"
        "def make_target():\n"
        "    import numpy as _np\n"
        "    return Target('doubler', NUMERIC, reference,\n"
        "                  [(_np.arange(5, dtype=float),)], [(_np.ones(3),)])\n"
    )
    t = opt.load_target(str(f))
    src = opt.derive_initial_program(t)
    assert "import numpy as np" in src  # imports carried (the bug was: empty preamble)
    assert "from tripwire" not in src  # tripwire imports skipped
    assert "def solve(" in src
    import numpy as np

    ns: dict = {}
    exec(compile(src, "<derived>", "exec"), ns)  # would NameError if import missing
    assert list(ns["solve"](np.arange(5, dtype=float))) == [0.0, 2.0, 4.0, 6.0, 8.0]


def test_derive_handles_multiline_parenthesized_imports(tmp_path):
    """Parenthesized multi-line imports must survive intact (not become a dangling
    `from math import (` SyntaxError)."""
    f = tmp_path / "ml.py"
    f.write_text(
        "from math import (\n    sqrt,\n    floor,\n)\n"
        "from tripwire.target import STRUCTURAL, Target\n"
        "def reference(xs):\n"
        "    return [floor(sqrt(x)) for x in xs]\n"
        "def make_target():\n"
        "    return Target('isqrt', STRUCTURAL, reference, [([1, 4, 9],)], [([16, 25],)])\n"
    )
    t = opt.load_target(str(f))
    src = opt.derive_initial_program(t)
    assert "from math import" in src and "sqrt" in src and "floor" in src
    ns: dict = {}
    exec(compile(src, "<derived>", "exec"), ns)  # must not be a SyntaxError
    assert ns["solve"]([1, 4, 9, 16]) == [1, 2, 3, 4]


# --- regression: build_config temperature + evaluator_models -----------------
def test_build_config_rejects_bad_temperature(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("OPENEVOLVE_MODEL", "m")
    monkeypatch.setenv("OPENEVOLVE_TEMPERATURE", "warm")
    with pytest.raises(opt.OptimizeError):
        opt.build_config(3)


def test_build_config_rejects_nonfinite_temperature(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("OPENEVOLVE_MODEL", "m")
    monkeypatch.setenv("OPENEVOLVE_TEMPERATURE", "inf")
    with pytest.raises(opt.OptimizeError):
        opt.build_config(3)


def test_build_config_sets_evaluator_models(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("OPENEVOLVE_MODEL", "m")
    monkeypatch.delenv("OPENEVOLVE_TEMPERATURE", raising=False)
    cfg = opt.build_config(3)
    assert len(cfg.llm.models) == 1
    assert len(cfg.llm.evaluator_models) == 1  # mirror proposer (was empty before)
