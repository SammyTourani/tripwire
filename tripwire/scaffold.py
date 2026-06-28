"""tripwire.scaffold -- `tripwire init`: generate a Target skeleton from a reference.

Authoring a Target (Interface A) is the main friction for using verify/optimize on
your own code. `tripwire init ref.py` reads your slow-but-correct function and emits
a fill-in-the-blanks Target file: your function inlined VERBATIM (kept under its own
name, with its decorators), the file's imports carried over, and TODO markers for the
inputs. You fill in canonical_args / withheld_args; everything else is ready.

The function is NOT renamed (keeping its name preserves recursion and avoids clobber
edge cases); make_target() just references it by name.
"""
from __future__ import annotations

import ast
from pathlib import Path


class ScaffoldError(RuntimeError):
    """A problem the user can act on (file missing, no/ambiguous/async function)."""


def _segment_with_decorators(source: str, node: ast.AST) -> str:
    """Source of a def INCLUDING its decorator lines. ast.get_source_segment starts
    at the `def`/`async def` line and drops decorators, which can silently change what
    the function computes -- so we slice from the first decorator's line instead."""
    start = min([d.lineno for d in node.decorator_list] + [node.lineno])  # type: ignore[attr-defined]
    end = node.end_lineno  # type: ignore[attr-defined]
    return "\n".join(source.splitlines()[start - 1 : end])


def find_reference(source: str, function: str | None = None):
    """Return (function_node, module_tree) for the chosen top-level function. With
    `function`, pick that one; else require exactly one top-level def. Rejects async
    (the oracle calls the reference synchronously). Raises ScaffoldError otherwise."""
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        raise ScaffoldError(f"could not parse the reference file: {e}") from e
    funcs = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    if function:
        match = [f for f in funcs if f.name == function]
        if not match:
            names = ", ".join(f.name for f in funcs) or "(none)"
            raise ScaffoldError(f"no top-level function named {function!r}; found: {names}")
        node = match[0]
    elif not funcs:
        raise ScaffoldError("no top-level function found in the reference file")
    elif len(funcs) > 1:
        names = ", ".join(f.name for f in funcs)
        raise ScaffoldError(
            f"multiple top-level functions ({names}); choose one with --function NAME"
        )
    else:
        node = funcs[0]
    if isinstance(node, ast.AsyncFunctionDef):
        raise ScaffoldError(
            f"{node.name!r} is async; the oracle calls the reference synchronously. "
            "Provide a synchronous reference."
        )
    return node, tree


def find_reference_source(source: str, function: str | None = None) -> tuple[str, str]:
    """(name, source-with-decorators) for the chosen top-level function."""
    node, _ = find_reference(source, function)
    return node.name, _segment_with_decorators(source, node)


def _module_imports(source: str) -> list[str]:
    """Top-level import statements from the reference file (so the inlined reference
    keeps what it needs), via AST. Carries plain imports, parenthesized multi-line
    imports, AND whole top-level Try/If/With blocks that contain imports (the common
    `try: import ujson as json except ImportError: import json` pattern). Skips
    tripwire and relative imports."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    out: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] == "tripwire" or node.level:
                continue
            seg = ast.get_source_segment(source, node)
            if seg:
                out.append(seg)
        elif isinstance(node, ast.Import):
            if any(a.name.split(".")[0] == "tripwire" for a in node.names):
                continue
            seg = ast.get_source_segment(source, node)
            if seg:
                out.append(seg)
        elif isinstance(node, (ast.Try, ast.If, ast.With)):
            if any(isinstance(n, (ast.Import, ast.ImportFrom)) for n in ast.walk(node)):
                seg = ast.get_source_segment(source, node)
                if seg:
                    out.append(seg)
    return out


def _missing_dependencies(tree: ast.Module, node: ast.AST) -> list[str]:
    """Names the chosen function uses that are OTHER top-level defs/assignments in the
    same module -- i.e. sibling helpers/constants that won't be carried into the
    standalone skeleton (so the user is warned to paste them in). Self-reference
    (recursion) is fine because the function keeps its name, so it's excluded."""
    defined: set[str] = set()
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defined.add(n.name)
        elif isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    defined.add(t.id)
        elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
            defined.add(n.target.id)
    defined.discard(node.name)  # type: ignore[attr-defined]
    used = {
        x.id
        for x in ast.walk(node)
        if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Load)
    }
    return sorted(used & defined)


def render_target(
    func_name: str, func_source: str, imports: list[str], missing: list[str] | None = None
) -> str:
    """Render a fill-in-the-blanks Target module. The reference (`func_source`) is
    inlined VERBATIM and never string-substituted, so user code can't be corrupted;
    `func_name` is interpolated only into the fixed scaffold lines."""
    preamble = ("\n".join(imports) + "\n") if imports else ""
    warning = ""
    if missing:
        names = ", ".join(missing)
        warning = (
            f"# WARNING: this reference also uses {names} from the original file, which\n"
            "# were NOT carried over. Paste them in above, or the reference will NameError.\n\n"
        )
    header = (
        f'"""Tripwire Target for `{func_name}` -- generated by `tripwire init`.\n'
        "\n"
        "FILL IN the TODOs (canonical_args, withheld_args, properties), then run:\n"
        "    tripwire verify  this_target.py  your_candidate.py\n"
        "    tripwire optimize this_target.py\n"
        "\n"
        "See docs/target-authoring.md for the full contract.\n"
        '"""\n'
        "from __future__ import annotations\n\n"
        f"{preamble}"
        "from tripwire.target import NUMERIC, STRUCTURAL, Target  # noqa: F401\n\n\n"
        f"{warning}"
    )
    body = (
        "\n\n\ndef make_target() -> Target:\n"
        "    # kind: NUMERIC for floating-point results (tolerance compare); else\n"
        "    # STRUCTURAL (exact compare). Pick ONE.\n"
        "    kind = NUMERIC\n\n"
        "    # canonical_args: inputs the optimizer is ALLOWED to see. Each entry is a\n"
        "    # TUPLE of positional args so the oracle can call the reference(*args). TODO.\n"
        "    canonical = [\n"
        "        # (example_input,),\n"
        "    ]\n\n"
        "    # withheld_args: fresh + ADVERSARIAL inputs it NEVER sees -- THE MOAT. Make\n"
        "    # these edges, not more-of-the-same: empty/singleton, a different size,\n"
        "    # pathological values. Must be non-empty. TODO.\n"
        "    withheld = [\n"
        "        # (edge_case_input,),\n"
        "    ]\n\n"
        "    # properties (L2, recommended): metamorphic/invariant checks\n"
        "    # (name, fn(args, out) -> bool), checked on canonical + withheld.\n"
        "    properties = [\n"
        '        # ("invariant_name", lambda args, out: ...),\n'
        "    ]\n\n"
        "    if not canonical or not withheld:\n"
        "        raise NotImplementedError(\n"
        '            "Fill in canonical_args and withheld_args in this file (see the TODOs)."\n'
        "        )\n"
        f"    return Target({func_name!r}, kind, {func_name}, canonical, withheld, properties)\n"
    )
    return header + func_source.rstrip() + "\n" + body


def scaffold_target(ref_path, function: str | None = None) -> str:
    """Read a reference .py and return the generated Target module source."""
    p = Path(ref_path)
    if not p.exists():
        raise ScaffoldError(f"reference file not found: {ref_path}")
    source = p.read_text()
    node, tree = find_reference(source, function)
    func_source = _segment_with_decorators(source, node)
    imports = _module_imports(source)
    missing = _missing_dependencies(tree, node)
    return render_target(node.name, func_source, imports, missing)
