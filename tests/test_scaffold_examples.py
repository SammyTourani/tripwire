"""Tests for `tripwire init` (scaffold), the bundled examples, and the OpenEvolve
detect helper. No network."""
from __future__ import annotations

import ast

import pytest

from tripwire import scaffold
from tripwire.examples import FAST_CANDIDATE, HACK_CANDIDATE, TARGET
from tripwire.oracle import layered_oracle


# --- scaffold: function discovery -------------------------------------------
def test_find_reference_single():
    name, src = scaffold.find_reference_source("def f(x):\n    return x\n")
    assert name == "f"
    assert "def f(" in src


def test_find_reference_named():
    src = "def a():\n    return 1\n\n\ndef b():\n    return 2\n"
    name, _ = scaffold.find_reference_source(src, "b")
    assert name == "b"


def test_find_reference_multiple_errors():
    with pytest.raises(scaffold.ScaffoldError):
        scaffold.find_reference_source("def a():\n    return 1\n\n\ndef b():\n    return 2\n")


def test_find_reference_none_errors():
    with pytest.raises(scaffold.ScaffoldError):
        scaffold.find_reference_source("x = 1\n")


def test_find_reference_rejects_async():
    with pytest.raises(scaffold.ScaffoldError):
        scaffold.find_reference_source("async def go(x):\n    return x\n")


def test_module_imports_carries_numpy_skips_tripwire_handles_multiline():
    src = (
        "import numpy as np\n"
        "from tripwire.target import Target\n"
        "from math import (\n    sqrt,\n)\n"
        "def f(x):\n    return x\n"
    )
    joined = "\n".join(scaffold._module_imports(src))
    assert "import numpy as np" in joined
    assert "from math import" in joined and "sqrt" in joined  # multi-line survives
    assert "tripwire" not in joined  # tripwire imports skipped


def test_module_imports_carries_conditional_block():
    src = (
        "try:\n    import ujson as json\nexcept ImportError:\n    import json\n"
        "def f(x):\n    return json.dumps(x)\n"
    )
    joined = "\n".join(scaffold._module_imports(src))
    assert "except ImportError" in joined and "import json" in joined  # whole block carried


# --- scaffold: rendering ----------------------------------------------------
def test_scaffold_keeps_name_and_compiles(tmp_path):
    ref = tmp_path / "ref.py"
    ref.write_text("import numpy as np\ndef myfn(x):\n    return float(np.sum(x))\n")
    code = scaffold.scaffold_target(str(ref))
    assert "def myfn(" in code  # kept under its own name (no rename)
    assert "import numpy as np" in code
    assert "myfn, canonical, withheld, properties)" in code  # referenced by name
    assert "TODO" in code
    compile(code, "<scaffold>", "exec")


def test_scaffold_preserves_recursion(tmp_path):
    ref = tmp_path / "r.py"
    ref.write_text("def fib(n):\n    return n if n < 2 else fib(n - 1) + fib(n - 2)\n")
    code = scaffold.scaffold_target(str(ref))
    ns: dict = {}
    exec(compile(code, "<r>", "exec"), ns)
    assert ns["fib"](7) == 13  # self-recursion still resolves (name kept)


def test_scaffold_preserves_decorators(tmp_path):
    ref = tmp_path / "d.py"
    ref.write_text(
        "import functools\n@functools.lru_cache(maxsize=8)\ndef sq(x):\n    return x * x\n"
    )
    code = scaffold.scaffold_target(str(ref))
    assert "@functools.lru_cache" in code  # decorator not dropped
    assert "import functools" in code
    ns: dict = {}
    exec(compile(code, "<d>", "exec"), ns)
    assert ns["sq"](5) == 25


def test_scaffold_func_token_in_body_preserved(tmp_path):
    ref = tmp_path / "t.py"
    ref.write_text('def myfn(x):\n    tag = "__FUNC__ marker"\n    return (x, tag)\n')
    code = scaffold.scaffold_target(str(ref))
    assert '"__FUNC__ marker"' in code  # user string not clobbered into the func name
    ns: dict = {}
    exec(compile(code, "<t>", "exec"), ns)
    assert ns["myfn"](1) == (1, "__FUNC__ marker")


def test_scaffold_carries_conditional_imports(tmp_path):
    ref = tmp_path / "c.py"
    ref.write_text(
        "try:\n    import ujson as json\nexcept ImportError:\n    import json\n"
        "def dumpit(x):\n    return json.dumps(x)\n"
    )
    code = scaffold.scaffold_target(str(ref))
    ns: dict = {}
    exec(compile(code, "<c>", "exec"), ns)
    assert ns["dumpit"]({"a": 1}) == '{"a": 1}'  # json import available


def test_scaffold_warns_missing_sibling(tmp_path):
    ref = tmp_path / "s.py"
    ref.write_text(
        "def helper(a):\n    return a + 1\ndef main_fn(x):\n    return helper(x) * 2\n"
    )
    code = scaffold.scaffold_target(str(ref), function="main_fn")
    assert "WARNING" in code and "helper" in code  # surfaced, not silent


def test_scaffold_unfilled_make_target_raises(tmp_path):
    ref = tmp_path / "ref.py"
    ref.write_text("def f(x):\n    return x\n")
    code = scaffold.scaffold_target(str(ref))
    ns: dict = {}
    exec(compile(code, "<s>", "exec"), ns)
    with pytest.raises(NotImplementedError):
        ns["make_target"]()  # unfilled canonical/withheld -> a clear, actionable error


def test_scaffold_missing_file_errors():
    with pytest.raises(scaffold.ScaffoldError):
        scaffold.scaffold_target("/nope/does-not-exist.py")


# --- CLI init: stdout must be verbatim (not rich-mangled) -------------------
def test_run_init_stdout_is_verbatim(tmp_path, capsys):
    from rich.console import Console

    from tripwire import cli

    ref = tmp_path / "r.py"
    ref.write_text("def f(items: list[int]) -> list[int]:\n    return sorted(items)\n")
    rc = cli.run_init(Console(), str(ref), output="-")
    out = capsys.readouterr().out
    assert rc == 0
    ast.parse(out)  # valid Python -- not mangled by rich markup/wrapping
    assert "list[int]" in out  # type hints preserved


# --- bundled examples -------------------------------------------------------
def test_example_files_exist():
    assert TARGET.exists()
    assert FAST_CANDIDATE.exists()
    assert HACK_CANDIDATE.exists()


def test_example_target_accepts_fast_rejects_hack():
    import importlib.util

    spec = importlib.util.spec_from_file_location("ex_target_test", str(TARGET))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    target = mod.make_target()
    fast_fn, _ = target.candidates["fast (x @ x)"]
    hack_fn, _ = target.candidates["hack (memorized)"]
    assert layered_oracle(target, fast_fn).accepted is True  # real win kept
    assert layered_oracle(target, hack_fn).accepted is False  # planted hack caught


# --- OpenEvolve detect (present in this env) --------------------------------
def test_ensure_openevolve_returns_true_when_present():
    from rich.console import Console

    from tripwire import cli

    assert cli._ensure_openevolve(Console()) is True
