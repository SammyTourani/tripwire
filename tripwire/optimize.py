"""tripwire.optimize -- the generic OpenEvolve loop, driven by the layered oracle.

Generalizes the proven runner/target_zero.py path: given ANY Target, an LLM
proposes faster `solve` implementations and the layered oracle (Interface B,
`make_openevolve_evaluator`) grades each one -- so the evolutionary loop can never
be rewarded for a reward-hack (a correctness failure zeroes the score, ADR-006).

We do NOT rebuild the loop / population / archive; OpenEvolve owns those (HARD
RULE 1 / ADR-001). This module only assembles the three things OpenEvolve needs --
an initial program, an evaluator file, and a Config -- and summarizes the result.
Everything that talks to `openevolve` is imported lazily so the package stays
importable without the optional `runner` extra installed.
"""
from __future__ import annotations

import ast
import importlib.util
import inspect
import math
import os
import re
import shutil
import sys
import tempfile
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from tripwire.target import Target

CANONICAL_ENTRYPOINT = "solve"
DEFAULT_ITERATIONS = 10

# COMPILOT Appendix A (Fig. 13) system prompt, retargeted from Tiramisu schedule
# commands to Python edits (same wording as runner/target_zero.py; kept here so the
# packaged loop is self-contained -- runner/ is not part of the installed package).
SYSTEM_MESSAGE = """\
You are a code optimization assistant. Your task is to iteratively improve a \
Python function to minimize its execution time WITHOUT changing what it computes.

# Overview
You will be shown a Python program with an `# EVOLVE-BLOCK-START` / \
`# EVOLVE-BLOCK-END` region containing a function named `solve`. Propose a faster \
implementation of `solve`. Your candidate is then verified by a rigorous, \
adversarial correctness oracle and, only if correct, benchmarked for speedup. You \
will receive feedback and may refine your approach over several iterations.

# Analysis first (think before you optimize)
Before rewriting, briefly analyze the function: what does it compute, what is the \
performance bottleneck, and which optimization strategies are sound. This analysis \
guides better edits.

# Correctness is non-negotiable
The oracle checks your candidate not only on the inputs you can infer, but on \
WITHHELD and adversarial inputs you never see (fresh data, ill-conditioned values, \
edge cases). A candidate that special-cases or memorizes specific inputs, or that \
skips the actual computation, will be REJECTED and earn ZERO reward -- correctness \
failure zeroes the score. Only genuinely correct optimizations are credited. For \
numeric code, results need only match within a small tolerance (vectorized or \
reordered arithmetic that changes the low bits is fine and encouraged).

# What good looks like here
The reference is a slow, sequential Python loop. Idiomatic, vectorized numerical \
code (e.g. using numpy) is typically far faster and remains correct. Keep the \
function signature and the `solve` name unchanged.
"""


class OptimizeError(RuntimeError):
    """A setup problem the user can act on (missing key/model, non-derivable initial
    program, bad target file). Distinct from an internal OpenEvolve failure."""


@dataclass
class OptimizeResult:
    best_speedup: float
    correct: bool
    reason: str
    best_code: str | None
    combined_score: float | None
    output_dir: str
    best_path: str | None


# --------------------------------------------------------------------------- #
# Convenience: load a local .env (no dependency)
# --------------------------------------------------------------------------- #
def load_dotenv(path=".env"):
    """Best-effort: load KEY=VALUE lines from a local .env into os.environ WITHOUT
    overwriting already-set vars. Handles a leading `export `, surrounding quotes,
    and a trailing ` # comment`. Returns the absolute path loaded, or None if the
    file is absent. A CLI convenience (matches runner/target_zero.py); the
    programmatic API does not auto-apply it."""
    p = Path(path)
    if not p.exists():
        return None
    for raw in p.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export ") :].strip()
        val = val.strip()
        # strip a trailing inline comment (only when the value isn't quoted)
        if val[:1] not in ("'", '"'):
            val = val.split(" #", 1)[0].rstrip()
        # strip a single matched pair of surrounding quotes
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
            val = val[1:-1]
        if key:
            os.environ.setdefault(key, val)
    return str(p.resolve())


# --------------------------------------------------------------------------- #
# Target loading (shared with the verify command)
# --------------------------------------------------------------------------- #
def load_target(path) -> Target:
    """Import a .py exposing `target` (a Target instance) or `make_target()` and
    return the Target. Raises OptimizeError with an actionable message on failure.

    The module is registered in sys.modules before execution (the standard importlib
    idiom) so that inspect.getmodule(target.reference) resolves later -- this is what
    lets derive_initial_program recover the reference module's imports.

    The target file is imported IN THIS PROCESS (it is the user's own trusted oracle
    spec); the untrusted candidate code is what runs sandboxed, later, in the oracle."""
    p = Path(path)
    if not p.exists():
        raise OptimizeError(f"target file not found: {path}")
    mod_name = f"tripwire_user_target_{abs(hash(str(p.resolve())))}"
    try:
        spec = importlib.util.spec_from_file_location(mod_name, str(p))
        if spec is None or spec.loader is None:
            raise OptimizeError(f"could not load target file: {path}")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        try:
            spec.loader.exec_module(mod)
        except Exception:
            sys.modules.pop(spec.name, None)
            raise
    except OptimizeError:
        raise
    except Exception as e:
        raise OptimizeError(
            f"could not import target file: {type(e).__name__}: {e}"
        ) from e

    target = getattr(mod, "target", None)
    if target is None:
        factory = getattr(mod, "make_target", None)
        if callable(factory):
            try:
                target = factory()
            except Exception as e:
                raise OptimizeError(
                    f"make_target() raised: {type(e).__name__}: {e}"
                ) from e
    if not isinstance(target, Target):
        raise OptimizeError(
            "target file must define `target` (a Target) or `make_target()` "
            "-- see docs/target-authoring.md"
        )
    return target


# --------------------------------------------------------------------------- #
# Scaffolding: initial program + evaluator file (no network)
# --------------------------------------------------------------------------- #
def _reference_module_source(ref) -> str:
    """Best-effort source of the reference's defining module, for import extraction.
    Falls back to reading the source FILE directly when inspect.getmodule is None."""
    mod = inspect.getmodule(ref)
    if mod is not None:
        try:
            return inspect.getsource(mod)
        except (OSError, TypeError):
            pass
    try:
        src_file = inspect.getsourcefile(ref) or inspect.getfile(ref)
        if src_file and os.path.exists(src_file):
            return Path(src_file).read_text()
    except (OSError, TypeError):
        pass
    return ""


def _extract_imports(module_src: str) -> list[str]:
    """Top-level import statements from module source, via AST so parenthesized
    multi-line imports survive intact. Skips imports of the `tripwire` package
    itself (matched by the top-level module name, not a substring)."""
    try:
        tree = ast.parse(module_src)
    except SyntaxError:
        return []
    out: list[str] = []
    for node in tree.body:  # module top level only
        if isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] == "tripwire" or node.level:
                continue  # skip tripwire imports and relative imports
        elif isinstance(node, ast.Import):
            if any(a.name.split(".")[0] == "tripwire" for a in node.names):
                continue
        else:
            continue
        seg = ast.get_source_segment(module_src, node)
        if seg:
            out.append(seg)
    return out


def derive_initial_program(target: Target) -> str:
    """Source for an OpenEvolve initial program: the target's `reference`, renamed to
    `solve` and wrapped in EVOLVE-BLOCK markers, with the reference module's own
    top-level imports prepended (so e.g. numpy is available).

    Raises OptimizeError if the reference source can't be recovered (a lambda, a
    built-in, or a C function) -- the caller can then pass an explicit initial file."""
    ref = target.reference
    try:
        src = inspect.getsource(ref)
    except (OSError, TypeError) as e:
        raise OptimizeError(
            f"could not read the reference function's source ({type(e).__name__}); "
            "pass an explicit starting program with --initial"
        ) from e
    # textwrap.dedent only helps nested defs; module-level source is already flush.
    import textwrap

    src = textwrap.dedent(src)

    # Rename the first `def <name>(` to `def solve(` (OpenEvolve/the oracle require
    # the entrypoint to be named `solve`).
    renamed = re.sub(r"^(\s*)def\s+\w+\s*\(", r"\1def solve(", src, count=1, flags=re.M)
    if "def solve(" not in renamed:
        raise OptimizeError(
            "could not derive a `solve` function from the reference "
            "(is it a lambda or a callable object?); pass an explicit one with --initial"
        )

    imports = _extract_imports(_reference_module_source(ref))
    preamble = ("\n".join(imports) + "\n\n\n") if imports else ""
    return (
        "# Initial program for OpenEvolve -- derived from the target's reference.\n"
        "# The entrypoint MUST stay named `solve`; only its body should change.\n\n"
        f"{preamble}"
        "# EVOLVE-BLOCK-START\n"
        f"{renamed.rstrip()}\n"
        "# EVOLVE-BLOCK-END\n"
    )


_EVALUATOR_TEMPLATE = '''\
"""Auto-generated OpenEvolve evaluator (tripwire optimize).

Loads the user's Target and grades each candidate via the FROZEN layered-oracle
adapter (make_openevolve_evaluator, isolate=True): the candidate runs sandboxed in
a subprocess, the oracle runs here, and any correctness failure zeroes the score.
"""
from __future__ import annotations

import importlib.util as _ilu

from tripwire.evaluator import make_openevolve_evaluator

_spec = _ilu.spec_from_file_location("tripwire_user_target", {target_path!r})
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
_t = getattr(_mod, "target", None)
if _t is None:
    _t = _mod.make_target()
_EVALUATE = make_openevolve_evaluator(_t)


def evaluate(program_path: str) -> dict:
    return _EVALUATE(program_path)
'''


def write_evaluator_file(target_path, dest: Path) -> Path:
    """Write a self-contained OpenEvolve evaluator file (top-level `evaluate`) that
    re-imports the target by ABSOLUTE path -- OpenEvolve loads this file fresh, in a
    separate process, so it cannot close over an in-memory Target."""
    abspath = str(Path(target_path).resolve())
    dest.write_text(_EVALUATOR_TEMPLATE.format(target_path=abspath))
    return dest


# --------------------------------------------------------------------------- #
# OpenEvolve config (reads env; lazy openevolve import)
# --------------------------------------------------------------------------- #
def build_config(iterations: int, *, trace_path: str | None = None):
    """Build the OpenEvolve Config from the environment. OpenAI-compatible:
      OPENAI_API_KEY     (required)
      OPENEVOLVE_MODEL   (required) -- the proposer model id your endpoint serves
      OPENAI_BASE_URL    (optional) -- defaults to OpenAI; point at any compatible proxy
      OPENEVOLVE_TEMPERATURE (optional) -- omitted by default (some reasoning models
                          reject the temperature param; absence is universally safe)
    Raises OptimizeError if a required value is missing or malformed."""
    try:
        from openevolve.config import Config, LLMModelConfig
    except Exception as e:  # noqa: BLE001 -- surface a clean, actionable message
        raise OptimizeError(
            "OpenEvolve is not installed. Install the loop extra, e.g. "
            "`pip install 'tripwire-oracle[runner]'`."
        ) from e

    api_key = os.environ.get("OPENAI_API_KEY")
    api_base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model = os.environ.get("OPENEVOLVE_MODEL")
    if not api_key:
        raise OptimizeError("OPENAI_API_KEY is not set (export it or put it in a local .env).")
    if not model:
        raise OptimizeError(
            "OPENEVOLVE_MODEL is not set (the proposer model id your endpoint serves, "
            "e.g. gpt-4o-mini)."
        )
    temp_env = os.environ.get("OPENEVOLVE_TEMPERATURE")
    temperature = None
    if temp_env not in (None, ""):
        try:
            temperature = float(temp_env)
        except ValueError as e:
            raise OptimizeError(
                f"OPENEVOLVE_TEMPERATURE must be a number, got {temp_env!r}"
            ) from e
        if not math.isfinite(temperature):
            raise OptimizeError(
                f"OPENEVOLVE_TEMPERATURE must be a finite number, got {temp_env!r}"
            )

    cfg = Config()
    cfg.max_iterations = iterations
    cfg.random_seed = 42  # reproducibility (OpenEvolve seeds every component)
    cfg.language = "python"
    cfg.diff_based_evolution = False  # rewrite the EVOLVE-BLOCK wholesale

    # retries/retry_delay set explicitly: we assign cfg.llm.models AFTER Config()'s
    # __post_init__, so the shared-config propagation that fills None fields won't
    # reach this model -- leaving them None would crash (retries + 1 -> None + int).
    model_cfg = LLMModelConfig(
        name=model,
        api_base=api_base,
        api_key=api_key,
        temperature=temperature,
        top_p=None,
        max_tokens=4096,
        timeout=120,
        retries=3,
        retry_delay=5,
        random_seed=42,
    )
    cfg.llm.models = [model_cfg]
    # Mirror the proposer as the evaluator model too: Config.__post_init__ copied an
    # empty models list into evaluator_models at construction (before we assigned
    # models), so without this the evaluator ensemble would be empty.
    cfg.llm.evaluator_models = [model_cfg]
    cfg.llm.api_base = api_base
    cfg.llm.api_key = api_key
    cfg.llm.temperature = temperature
    cfg.llm.top_p = None
    cfg.prompt.system_message = SYSTEM_MESSAGE
    cfg.prompt.include_artifacts = True  # feed the oracle's `reason` back to the model

    if trace_path:
        cfg.evolution_trace.enabled = True
        cfg.evolution_trace.format = "jsonl"
        cfg.evolution_trace.include_code = True
        cfg.evolution_trace.output_path = trace_path
    return cfg


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #
def _run_stamp() -> str:
    """Unique per-run token: UTC timestamp + short random suffix (so two runs in the
    same second never collide)."""
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]


def run_optimization(
    target_path,
    *,
    iterations: int = DEFAULT_ITERATIONS,
    initial_path=None,
    output_dir=None,
    target: Target | None = None,
) -> OptimizeResult:
    """Assemble the inputs and run a real OpenEvolve loop graded by the layered
    oracle. Makes real (paid) LLM calls. Returns the best oracle-verified result.

    Each run writes to its OWN subdir (``<out>/<target>-<stamp>/``) so re-running the
    same target never overwrites or appends to a prior run.

    Raises OptimizeError on setup problems; OpenEvolve runtime failures propagate as
    their own exception type (the caller renders them)."""
    if target is None:
        target = load_target(target_path)

    # Sanitize the user-supplied target name before it touches the filesystem.
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", target.name) or "target"
    base_out = Path(output_dir) if output_dir else Path.cwd() / "tripwire-runs"
    run_dir = base_out / f"{safe_name}-{_run_stamp()}"
    run_dir.mkdir(parents=True, exist_ok=True)

    workdir = Path(tempfile.mkdtemp(prefix="tripwire-optimize-"))
    try:
        if initial_path:
            initial_file = Path(initial_path)
            if not initial_file.exists():
                raise OptimizeError(f"initial program not found: {initial_path}")
        else:
            initial_file = workdir / "initial_program.py"
            initial_file.write_text(derive_initial_program(target))

        evaluator_file = write_evaluator_file(target_path, workdir / "evaluator.py")
        config = build_config(iterations, trace_path=str(run_dir / "trace.jsonl"))

        from openevolve import run_evolution

        result = run_evolution(
            initial_program=str(initial_file),
            evaluator=str(evaluator_file),
            config=config,
            iterations=iterations,
            output_dir=str(run_dir / "openevolve"),
            cleanup=False,
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    best = getattr(result, "best_program", None)
    metrics = getattr(best, "metrics", {}) if best is not None else {}
    code = getattr(best, "code", None) if best is not None else None

    best_path = None
    if code:
        best_path = run_dir / "best.py"
        best_path.write_text(code)

    speedup = metrics.get("speedup")
    correct_val = metrics.get("correct")
    return OptimizeResult(
        best_speedup=float(speedup) if isinstance(speedup, (int, float)) else 0.0,
        correct=bool(isinstance(correct_val, (int, float)) and correct_val >= 1.0),
        reason=str(metrics.get("reason", "")),
        best_code=code,
        combined_score=metrics.get("combined_score"),
        output_dir=str(run_dir),
        best_path=str(best_path) if best_path else None,
    )
