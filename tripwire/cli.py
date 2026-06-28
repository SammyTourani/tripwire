"""tripwire.cli -- the interactive command-line front door to Tripwire.

`tripwire` with no arguments drops into an interactive, red-bannered menu (the
"obvious and easy" path). The same actions are also available directly as
subcommands, for scripts and power users:

    tripwire demo                       run the cross-domain integrity scorecard
    tripwire verify TARGET CANDIDATE    verify one optimized candidate (--example to try one)
    tripwire optimize TARGET            run a real OpenEvolve loop (--example to try one)
    tripwire init REFERENCE.py          scaffold a Target from your function
    tripwire explain                    how it works (the 4-layer oracle)

The heavy lifting lives in the packaged modules (tripwire.scorecard, the oracle,
the evaluator). This file is presentation + dispatch only -- no oracle logic and
no evolutionary-loop code (HARD RULE 1). Third-party imports (rich, pyfiglet) are
done lazily inside functions so `import tripwire.cli` and `--help` stay fast.
"""
from __future__ import annotations

import argparse
import math
import os
import sys

# Match the website wordmark red exactly (#e5484d -- the giant TRIPWIRE sign-off).
RED = "#e5484d"
AMBER = "#e5a04d"  # the colour of a reward-hack: the thing the oracle must catch
GREEN = "#7bbf7b"  # a genuinely-valid win
MUTE = "#8a857d"
FAINT = "#5c5852"

WORDMARK = "TRIPWIRE"
TAGLINE = "adversarial correctness oracle for AI code optimization"

# Interactive menu: (action key, label, one-line description).
MENU = [
    ("demo", "Run the demo", "watch the oracle catch planted reward-hacks"),
    ("example", "Try an example", "verify a real win and a planted hack (no setup)"),
    ("verify", "Verify my code", "check a candidate against a reference target"),
    ("init", "Scaffold a target", "generate a Target skeleton from your function"),
    ("optimize", "Optimize a target", "run the full evolutionary loop (needs API key)"),
    ("explain", "How it works", "the 4-layer oracle, Targets, and the commands"),
    ("quit", "Quit", ""),
]


# --------------------------------------------------------------------------- #
# Console + banner
# --------------------------------------------------------------------------- #
def _console():
    from rich.console import Console

    return Console(highlight=False)


def _banner_renderable():
    """The big red TRIPWIRE wordmark (figlet) over the tagline, as a renderable."""
    from rich.console import Group
    from rich.padding import Padding
    from rich.text import Text

    art = None
    try:
        from pyfiglet import figlet_format

        for font in ("ansi_shadow", "big", "standard"):
            try:
                art = figlet_format(WORDMARK, font=font).rstrip("\n")
                break
            except Exception:
                continue
    except Exception:
        art = None
    if not art:
        art = WORDMARK  # plain fallback if pyfiglet / its fonts are unavailable

    return Padding(
        Group(
            Text(art, style=f"bold {RED}"),
            Text(TAGLINE, style=f"italic {MUTE}"),
        ),
        (1, 2, 1, 2),
    )


def _print_banner(console):
    console.print(_banner_renderable())


# --------------------------------------------------------------------------- #
# Interactive menu (arrow keys with a numbered fallback)
# --------------------------------------------------------------------------- #
def _read_key(fd):
    """Read one keypress from raw/cbreak-mode `fd`, decoding arrow escapes. Returns
    'up'/'down'/'enter'/'quit'/'esc' or the literal character.

    Reads the raw fd with os.read (NOT buffered sys.stdin.read, which would pull a
    whole "\\x1b[A" escape sequence into Python's buffer and leave select() blind to
    it -- so arrows would look like a lone ESC). The fd is put in cbreak mode ONCE by
    the caller (_arrow_menu); per-key toggling would flush type-ahead on every press."""
    import select

    ch = os.read(fd, 1)
    if ch == b"\x1b":  # escape -- maybe an arrow sequence
        # Distinguish a lone ESC from an arrow: only read the tail if more bytes are
        # already available, so a real ESC keypress doesn't block waiting for a 2nd.
        r, _, _ = select.select([fd], [], [], 0.05)
        if not r:
            return "esc"
        seq = os.read(fd, 2)
        if seq == b"[A":
            return "up"
        if seq == b"[B":
            return "down"
        return "esc"
    if ch in (b"\r", b"\n"):
        return "enter"
    if ch in (b"\x03", b"\x04"):  # Ctrl-C / Ctrl-D
        return "quit"
    c = ch.decode("utf-8", "ignore")
    if c.lower() == "q":
        return "quit"
    if c in "jk":  # vim-style
        return "down" if c == "j" else "up"
    return c


def _menu_renderable(idx):
    from rich.console import Group
    from rich.padding import Padding
    from rich.text import Text

    lines = [Text("What do you want to do?", style="bold #f5f5f5"), Text()]
    for i, (_key, label, desc) in enumerate(MENU):
        selected = i == idx
        line = Text()
        line.append("❯ " if selected else "  ", style=RED if selected else FAINT)
        line.append(f"{label:<20}", style=f"bold {RED}" if selected else "#f5f5f5")
        if desc:
            line.append(desc, style=MUTE if selected else FAINT)
        lines.append(line)
    lines.append(Text())
    lines.append(Text("↑/↓ move   enter select   q quit", style=FAINT))
    return Padding(Group(*lines), (0, 2))


def _arrow_menu(console):
    import termios
    import tty

    from rich.live import Live

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    idx = 0
    try:
        # cbreak ONCE for the whole menu (not per key): avoids flushing type-ahead on
        # every press, and (unlike setraw) keeps output post-processing on so Live's
        # multi-line repaint renders correctly. ISIG stays on, so Ctrl-C raises
        # KeyboardInterrupt, which main() catches for a clean exit.
        tty.setcbreak(fd)
        with Live(
            _menu_renderable(idx), console=console, auto_refresh=False, screen=False
        ) as live:
            while True:
                key = _read_key(fd)
                if key == "up":
                    idx = (idx - 1) % len(MENU)
                elif key == "down":
                    idx = (idx + 1) % len(MENU)
                elif key.isdigit() and 1 <= int(key) <= len(MENU):
                    return MENU[int(key) - 1][0]
                elif key == "enter":
                    return MENU[idx][0]
                elif key in ("quit", "esc"):
                    return "quit"
                live.update(_menu_renderable(idx), refresh=True)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _numbered_menu(console):
    """Fallback used when arrow-key/raw-mode input is unavailable."""
    console.print()
    for i, (_key, label, desc) in enumerate(MENU, start=1):
        line = f"  [bold]{i}[/bold]  {label}"
        if desc:
            line += f"  [dim]{desc}[/dim]"
        console.print(line)
    console.print()
    try:
        choice = console.input(f"  choose [1-{len(MENU)}]: ").strip()
    except (EOFError, KeyboardInterrupt):
        return "quit"
    if choice.isdigit() and 1 <= int(choice) <= len(MENU):
        return MENU[int(choice) - 1][0]
    return "quit"


def _interactive_menu(console):
    try:
        return _arrow_menu(console)
    except Exception:
        return _numbered_menu(console)


# --------------------------------------------------------------------------- #
# demo
# --------------------------------------------------------------------------- #
def _truth_style(truth):
    return f"bold {AMBER}" if truth == "hack" else GREEN


def _demo_header():
    from rich.text import Text

    h = Text("  ", style=FAINT)
    h.append(f"{'domain':<15}", style=FAINT)
    h.append(f"{'candidate':<22}", style=FAINT)
    h.append(f"{'truth':<11}", style=FAINT)
    h.append(f"{'bit':^5}{'tol':^5}{'lay':^5}", style=FAINT)
    h.append("  speedup", style=FAINT)
    return h


def _demo_row_text(row):
    from rich.text import Text

    t = Text("  ")
    t.append(f"{row.domain:<15}", style=MUTE)
    t.append(f"{row.candidate[:21]:<22}", style="#f5f5f5")
    t.append(f"{row.truth:<11}", style=_truth_style(row.truth))
    for o in ("naive_bitwise", "naive_tolerance", "layered"):
        accepted = row.verdicts[o][0]
        t.append(f"{'✓' if accepted else '✗':^5}", style="green" if accepted else "red")
    if row.verdicts["layered"][0] and not math.isnan(row.layered_speedup):
        t.append(f"  {row.layered_speedup:,.0f}×", style=f"bold {RED}")
    else:
        t.append("  —", style=FAINT)
    return t


def _summary_panel(summary, rows):
    from rich import box
    from rich.console import Group
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    n = len(rows)
    n_valid = sum(1 for r in rows if r.truth in ("correct", "correct_fp"))
    n_hack = sum(1 for r in rows if r.truth == "hack")
    n_domains = len({r.domain for r in rows})

    tbl = Table(box=box.SIMPLE_HEAD, pad_edge=False, expand=False)
    tbl.add_column("oracle", no_wrap=True)
    tbl.add_column("ships hacks", justify="right")
    tbl.add_column("integrity", justify="right")
    tbl.add_column("kept wins", justify="right")
    tbl.add_column("verdict", justify="right")

    labels = {
        "naive_bitwise": "naive (bitwise)",
        "naive_tolerance": "naive (tolerance)",
        "layered": "layered  (Tripwire)",
    }
    for o in ("naive_bitwise", "naive_tolerance", "layered"):
        s = summary[o]
        is_tw = s["trustworthy"]
        hacks = s["ships_hacks"]
        integ = "—" if math.isnan(s["integrity"]) else f"{s['integrity']:.0%}"
        kept = "—" if math.isnan(s["kept_valid"]) else f"{s['kept_valid']:.0%}"
        hacks_cell = "[green]0[/green]" if hacks == 0 else f"[bold red]{hacks}[/bold red]"
        verdict = (
            "[bold green]TRUSTWORTHY[/bold green]" if is_tw else "[red]unsafe[/red]"
        )
        tbl.add_row(
            labels[o],
            hacks_cell,
            integ,
            kept,
            verdict,
            style=f"bold {GREEN}" if is_tw else None,
        )

    headline = Text()
    headline.append("Only the ", style="#f5f5f5")
    headline.append("layered", style=f"bold {RED}")
    headline.append(" oracle shipped ", style="#f5f5f5")
    headline.append("0 reward-hacks", style="bold green")
    headline.append(" and kept ", style="#f5f5f5")
    headline.append("every real win", style="bold green")
    headline.append(".", style="#f5f5f5")

    body = Group(
        Text(
            f"{n} candidates   ·   {n_valid} real wins + {n_hack} reward-hacks   "
            f"·   {n_domains} domains",
            style=MUTE,
        ),
        Text(),
        tbl,
        Text(),
        headline,
    )
    return Panel(
        body,
        title="[bold]integrity scorecard[/bold]",
        title_align="left",
        border_style=RED,
        padding=(1, 2),
    )


def run_demo(console, *, banner=True):
    from tripwire.scorecard import iter_rows, summarize

    if banner:
        _print_banner(console)
    console.print(
        "  Grading planted candidates — real wins [green]and[/green] reward-hacks — "
        "on unseen inputs.\n",
        style="#f5f5f5",
    )
    console.print(_demo_header(), no_wrap=True, crop=True)

    rows = []
    # Stream each candidate's verdict as it is decided (the live, Claude-Code feel).
    with console.status("[dim]warming up the oracle…[/dim]", spinner="dots"):
        first = None
        gen = iter_rows()
        try:
            first = next(gen)
        except StopIteration:
            gen = iter([])
    if first is not None:
        rows.append(first)
        console.print(_demo_row_text(first), no_wrap=True, crop=True)
        for row in gen:
            rows.append(row)
            console.print(_demo_row_text(row), no_wrap=True, crop=True)

    if not rows:
        console.print("  [red]no candidates were evaluated.[/red]")
        return 1

    console.print()
    console.print(_summary_panel(summarize(rows), rows))
    console.print(
        "\n  [dim]next: `tripwire verify --example` to watch it check a real candidate, "
        "or `tripwire init <your_ref.py>` to start on your own code.[/dim]"
    )
    return 0


# --------------------------------------------------------------------------- #
# verify
# --------------------------------------------------------------------------- #
def _load_target(console, path):
    """Load a Target from a user .py (shared by verify and optimize). Returns the
    Target, or None after printing the reason."""
    from tripwire.optimize import OptimizeError, load_target

    try:
        return load_target(path)
    except OptimizeError as e:
        console.print(f"  [red]{e}[/red]")
        return None


_LAYERS = [
    ("L1", "canonical correctness"),
    ("L2", "metamorphic properties"),
    ("L3", "withheld adversarial inputs"),
    ("L4", "isolated speedup"),
]


def _layer_states(correct, reason):
    """Map the evaluator's verdict reason to a per-layer pass/fail/skip list."""
    if correct:
        return [(c, d, "pass") for c, d in _LAYERS]
    failed = next((c for c in ("L1", "L2", "L3") if reason.startswith(c)), None)
    if failed is None:
        # A load / isolation error -- the candidate never reached the layers.
        return [(c, d, "skip") for c, d in _LAYERS]
    states, reached = [], True
    for c, d in _LAYERS:
        if c == failed:
            states.append((c, d, "fail"))
            reached = False
        elif reached:
            states.append((c, d, "pass"))
        else:
            states.append((c, d, "skip"))
    return states


def run_verify(console, target_path, candidate_path, *, isolate=True):
    from rich.console import Group
    from rich.panel import Panel
    from rich.text import Text

    target = _load_target(console, target_path)
    if target is None:
        return 1
    if not os.path.exists(candidate_path):
        console.print(f"  [red]candidate file not found:[/red] {candidate_path}")
        return 1

    from tripwire.evaluator import make_openevolve_evaluator

    evaluate = make_openevolve_evaluator(target, isolate=isolate)
    with console.status(
        "  verifying on canonical, metamorphic, and [bold]withheld adversarial[/bold] inputs…",
        spinner="dots",
    ):
        result = evaluate(candidate_path)

    correct = result.get("correct", 0.0) >= 1.0
    speedup = result.get("speedup", 0.0)
    reason = result.get("reason", "")

    # A non-layer rejection reason (a load / setup / timing error rather than an
    # "L1/L2/L3 ..." correctness verdict) means the candidate never produced an
    # attributable per-layer result -- so don't paint a misleading layer checklist.
    if not correct and not reason.startswith(("L1", "L2", "L3")):
        console.print()
        console.print(
            Panel(
                Group(
                    Text(f"target: {target.name}", style=MUTE),
                    Text(),
                    Text("could not evaluate the candidate", style="bold red"),
                    Text(f"  {reason}", style="#f5f5f5"),
                ),
                title="[bold]verify[/bold]",
                title_align="left",
                border_style="red",
                padding=(1, 2),
            )
        )
        return 1

    # Speedup is candidate-in-sandbox vs reference-in-parent: for heavy candidates
    # (the real use case) the sandbox IPC cost is negligible and the ratio is
    # accurate; for trivial candidates the overhead dominates, so we only headline a
    # clear win and otherwise say the function is too fast to time meaningfully.
    is_win = (not math.isnan(speedup)) and speedup >= 1.05

    glyph = {"pass": ("✓", "green"), "fail": ("✗", "bold red"), "skip": ("·", FAINT)}
    rows = []
    for code, desc, state in _layer_states(correct, reason):
        g, color = glyph[state]
        line = Text("  ")
        line.append(f"{g} ", style=color)
        line.append(f"{code}  ", style="bold #f5f5f5" if state != "skip" else FAINT)
        line.append(desc, style="#f5f5f5" if state != "skip" else FAINT)
        if state == "pass" and code == "L4":
            if is_win:
                line.append(f"   {speedup:,.1f}× faster", style=f"bold {RED}")
            else:
                line.append("   too fast to time meaningfully", style=FAINT)
        rows.append(line)

    if correct:
        verdict = Text()
        verdict.append("ACCEPTED", style="bold green")
        verdict.append("  — correct on every withheld input", style="#f5f5f5")
        if is_win:
            verdict.append(f"; {speedup:,.1f}× faster", style=f"bold {RED}")
        border = "green"
    else:
        verdict = Text()
        verdict.append("REJECTED", style="bold red")
        verdict.append(f"  — {reason}", style="#f5f5f5")
        border = "red"

    body = Group(
        Text(f"target: {target.name}", style=MUTE),
        Text(),
        *rows,
        Text(),
        verdict,
    )
    console.print()
    console.print(
        Panel(
            body,
            title="[bold]verify[/bold]",
            title_align="left",
            border_style=border,
            padding=(1, 2),
        )
    )
    return 0 if correct else 1


# --------------------------------------------------------------------------- #
# optimize
# --------------------------------------------------------------------------- #
def _prepare_optimize_env(console):
    """Load a local .env (with a visible notice + a base-URL safety guard), then
    report (openevolve installed?, OPENAI_API_KEY set?, OPENEVOLVE_MODEL set?).

    Called by both the direct command and the interactive menu so each sees the .env
    BEFORE the prereq check. The safety guard refuses a .env-supplied OPENAI_BASE_URL
    when the API key comes from the real shell -- otherwise a foreign .env in the
    current directory could redirect your real key to an attacker endpoint."""
    from tripwire.optimize import load_dotenv

    key_preset = "OPENAI_API_KEY" in os.environ
    base_preset = "OPENAI_BASE_URL" in os.environ
    loaded = load_dotenv()
    if loaded:
        console.print(f"  [dim]loaded environment from {loaded}[/dim]")
        if key_preset and not base_preset and os.environ.get("OPENAI_BASE_URL"):
            del os.environ["OPENAI_BASE_URL"]
            console.print(
                "  [yellow]ignored OPENAI_BASE_URL from .env (your API key is from the "
                "shell; refusing to redirect it — export OPENAI_BASE_URL to override).[/yellow]"
            )
    try:
        import openevolve  # noqa: F401

        have_oe = True
    except Exception:
        have_oe = False
    return have_oe, bool(os.environ.get("OPENAI_API_KEY")), bool(os.environ.get("OPENEVOLVE_MODEL"))


def _optimize_prereq_panel(console, have_oe, have_key, have_model, target_path):
    """Shown when optimize can't run yet -- explains exactly what's missing."""
    from rich.console import Group
    from rich.panel import Panel
    from rich.text import Text

    def status(ok, yes, no):
        g, c = ("✓", "green") if ok else ("✗", "red")
        t = Text("  ")
        t.append(f"{g} ", style=c)
        t.append(yes if ok else no, style="#f5f5f5" if ok else MUTE)
        return t

    body = Group(
        Text(
            "Optimize runs a real OpenEvolve loop: an LLM proposes faster code and "
            "Tripwire’s layered oracle grades every proposal — so the loop can never be "
            "rewarded for a hack.",
            style="#f5f5f5",
        ),
        Text(),
        Text("usage:", style="bold #f5f5f5"),
        Text("  tripwire optimize <target.py> [--iterations N]", style=f"bold {RED}"),
        Text(),
        Text("prerequisites:", style="bold #f5f5f5"),
        status(
            have_oe,
            "OpenEvolve installed",
            "OpenEvolve not installed — pip install 'tripwire-oracle[runner]'",
        ),
        status(have_key, "OPENAI_API_KEY set", "OPENAI_API_KEY not set"),
        status(have_model, "OPENEVOLVE_MODEL set", "OPENEVOLVE_MODEL not set (e.g. gpt-4o-mini)"),
        status(bool(target_path), "target file given", "no target file given"),
        Text(),
        Text(
            "OPENAI_BASE_URL is optional (defaults to OpenAI; point it at any compatible proxy).",
            style=MUTE,
        ),
    )
    console.print()
    console.print(
        Panel(
            body,
            title="[bold]optimize[/bold]",
            title_align="left",
            border_style=AMBER,
            padding=(1, 2),
        )
    )
    # Non-zero: a missing prerequisite means optimize ran nothing -- a CI/script
    # should see a failure (matches verify's error-path exit codes).
    return 2


def _ensure_openevolve(console, *, assume_yes=False):
    """Return True if OpenEvolve is importable -- installing it on consent if not.

    Default is detect-and-OFFER (a [Y/n] prompt), not silent install: a tool that
    quietly mutates your environment is a footgun. --yes / TRIPWIRE_AUTO_INSTALL skip
    the prompt; a non-interactive shell prints the command instead of guessing."""
    import importlib

    try:
        importlib.import_module("openevolve")
        return True
    except Exception:
        pass

    spec = "openevolve>=0.2.27"
    env_auto = os.environ.get("TRIPWIRE_AUTO_INSTALL", "").strip().lower() in ("1", "true", "yes")
    auto = assume_yes or env_auto
    interactive = sys.stdin.isatty() and sys.stdout.isatty()

    if not auto:
        if not interactive:
            console.print("  [red]OpenEvolve is required for optimize and isn't installed.[/red]")
            console.print(f'  install it:  {sys.executable} -m pip install "{spec}"', style=MUTE)
            console.print("  or run:      pip install 'tripwire-oracle[runner]'", style=MUTE)
            return False
        try:
            ans = (
                console.input(
                    f"  OpenEvolve isn't installed. Install {spec} into this environment "
                    "now? [Y/n] "
                )
                .strip()
                .lower()
            )
        except (EOFError, KeyboardInterrupt):
            console.print()
            return False
        if ans not in ("", "y", "yes"):
            console.print(
                "  [dim]skipped — install it yourself with "
                "pip install 'tripwire-oracle[runner]'.[/dim]"
            )
            return False

    console.print(f"  [dim]installing {spec} …[/dim]")
    import subprocess

    rc = subprocess.call([sys.executable, "-m", "pip", "install", spec])
    if rc != 0:
        console.print(
            f"  [red]install failed (exit {rc}).[/red] Try: pip install 'tripwire-oracle[runner]'"
        )
        return False
    importlib.invalidate_caches()
    try:
        importlib.import_module("openevolve")
        console.print("  [green]OpenEvolve installed.[/green]")
        return True
    except Exception:
        console.print("  [red]OpenEvolve still not importable after install.[/red]")
        return False


def run_optimize(
    console,
    target_path=None,
    *,
    iterations=None,
    initial_path=None,
    output_dir=None,
    env=None,
    assume_yes=False,
):
    from rich.console import Group
    from rich.panel import Panel
    from rich.syntax import Syntax
    from rich.text import Text

    from tripwire.optimize import DEFAULT_ITERATIONS, OptimizeError, run_optimization

    if iterations is None:
        iterations = DEFAULT_ITERATIONS

    # `env` lets the interactive menu prepare the environment once and pass the result
    # in (avoids a second .env notice); otherwise prepare it here.
    have_oe, have_key, have_model = env if env is not None else _prepare_optimize_env(console)
    if not (have_key and have_model and target_path):
        return _optimize_prereq_panel(console, have_oe, have_key, have_model, target_path)
    # Have a target + credentials but OpenEvolve missing -> offer to install it.
    if not have_oe and not _ensure_openevolve(console, assume_yes=assume_yes):
        return _optimize_prereq_panel(console, False, have_key, have_model, target_path)

    target = _load_target(console, target_path)
    if target is None:
        return 1

    console.print()
    hdr = Text("  ")
    hdr.append("optimizing ", style="#f5f5f5")
    hdr.append(target.name, style=f"bold {RED}")
    hdr.append(
        f" — {iterations} iterations, each a real (paid) LLM call to "
        f"{os.environ.get('OPENEVOLVE_MODEL')}",
        style=MUTE,
    )
    console.print(hdr)
    console.print(
        "  [dim]propose → oracle-verify on withheld inputs → measure speedup[/dim]\n"
    )

    try:
        result = run_optimization(
            target_path,
            iterations=iterations,
            initial_path=initial_path,
            output_dir=output_dir,
            target=target,
        )
    except OptimizeError as e:
        console.print(f"  [red]{e}[/red]")
        return 1
    except Exception as e:  # noqa: BLE001 -- OpenEvolve / runtime failure
        console.print(f"  [red]optimization failed:[/red] {type(e).__name__}: {e}")
        return 1

    is_win = result.correct and result.best_speedup >= 1.05
    if result.correct:
        head = Text()
        head.append("BEST: ", style="bold green")
        if is_win:
            head.append(f"{result.best_speedup:,.1f}× faster", style=f"bold {RED}")
            head.append("  (oracle-verified correct on withheld inputs)", style="#f5f5f5")
        else:
            head.append("verified correct", style="#f5f5f5")
            head.append("  (no clear speedup found this run)", style=MUTE)
        border = "green"
    else:
        head = Text()
        head.append("no verified improvement", style="bold red")
        if result.reason:
            head.append(f"  — {result.reason}", style=MUTE)
        border = "red"

    parts = [Text(f"target: {target.name}", style=MUTE), Text(), head]
    if result.best_code:
        parts += [
            Text(),
            Text("best solve:", style="bold #f5f5f5"),
            Syntax(result.best_code, "python", theme="ansi_dark", word_wrap=True),
        ]
    if result.best_path:
        parts += [Text(), Text(f"saved: {result.best_path}", style=MUTE)]

    console.print()
    console.print(
        Panel(
            Group(*parts),
            title="[bold]optimize[/bold]",
            title_align="left",
            border_style=border,
            padding=(1, 2),
        )
    )
    return 0 if result.correct else 1


# --------------------------------------------------------------------------- #
# example / init / explain
# --------------------------------------------------------------------------- #
def run_verify_example(console):
    """Verify the bundled example: a real win (ACCEPTED) and a planted hack (REJECTED).
    Fully offline -- the instant 'what verify does' experience."""
    from tripwire import examples as ex

    console.print()
    console.print(
        "  [bold]verify --example[/bold] — the oracle on a real optimization and a "
        "planted hack\n",
        style="#f5f5f5",
    )
    console.print("  [dim]1/2  a correct, faster candidate → expected: ACCEPTED[/dim]")
    rc_good = run_verify(console, str(ex.TARGET), str(ex.FAST_CANDIDATE))
    console.print(
        "\n  [dim]2/2  a memorized hack (correct on seen inputs only) → expected: "
        "REJECTED[/dim]"
    )
    rc_hack = run_verify(console, str(ex.TARGET), str(ex.HACK_CANDIDATE))
    console.print(
        "\n  [dim]that's the moat: the hack passed the visible inputs but was caught on "
        "inputs it never saw. Run `tripwire init <your_ref.py>` to do this on your code.[/dim]"
    )
    return 0 if (rc_good == 0 and rc_hack == 1) else 1


def run_init(console, ref_path, *, function=None, output=None, force=False):
    from pathlib import Path

    from rich.console import Group
    from rich.panel import Panel
    from rich.text import Text

    from tripwire.scaffold import ScaffoldError, scaffold_target

    try:
        code = scaffold_target(ref_path, function)
    except ScaffoldError as e:
        console.print(f"  [red]{e}[/red]")
        return 1

    if output == "-":
        # Write verbatim, NOT via rich -- console.print would interpret `[int]` type
        # hints as markup and hard-wrap long lines, corrupting the emitted Python.
        sys.stdout.write(code if code.endswith("\n") else code + "\n")
        return 0

    out = Path(output) if output else Path(ref_path).with_name(Path(ref_path).stem + "_target.py")
    if out.exists() and not force:
        console.print(f"  [red]{out} already exists[/red] (use --force to overwrite)")
        return 1
    out.write_text(code)

    body = Group(
        Text(f"wrote {out}", style="bold green"),
        Text(),
        Text("next:", style="bold #f5f5f5"),
        Text(f"  1. open {out} and fill in canonical_args / withheld_args (the TODOs)",
             style="#f5f5f5"),
        Text(f"  2. tripwire verify {out} <your_candidate.py>", style=f"bold {RED}"),
        Text(f"     tripwire optimize {out}", style=f"bold {RED}"),
        Text(),
        Text("the withheld inputs are the moat — make them adversarial, not more-of-the-same.",
             style=MUTE),
        Text("if your reference calls helpers or uses conditional imports from the original "
             "file, paste those in too.", style=MUTE),
    )
    console.print()
    console.print(
        Panel(body, title="[bold]init[/bold]", title_align="left", border_style="green",
              padding=(1, 2))
    )
    return 0


def run_explain(console):
    from rich.console import Group
    from rich.panel import Panel
    from rich.text import Text

    layers = Text()
    for code, desc in [
        ("L1", "canonical correctness — exact/tolerance match on the inputs you provide"),
        ("L2", "metamorphic properties — invariants the real computation must satisfy"),
        ("L3", "withheld adversarial inputs — THE MOAT: inputs the optimizer never saw"),
        ("L4", "isolated speedup — measured only after L1–L3 pass"),
    ]:
        layers.append(f"  {code}  ", style=f"bold {RED}")
        layers.append(desc + "\n", style="#f5f5f5")

    body = Group(
        Text(
            "AI tools that “optimize” code sometimes cheat: they return code that looks "
            "much faster but is secretly wrong (it memorized the test answers, or skipped "
            "the work). Tripwire is the check that catches that.",
            style="#f5f5f5",
        ),
        Text(),
        Text("the oracle grades every candidate in four layers:", style="bold #f5f5f5"),
        layers,
        Text(
            "Any correctness layer failing ⇒ rejected, zero credit. Speed counts only "
            "after correctness is proven.",
            style=MUTE,
        ),
        Text(),
        Text("a Target tells the oracle how to judge your problem:", style="bold #f5f5f5"),
        Text(
            "  reference (slow but correct) · canonical inputs · withheld adversarial "
            "inputs · properties",
            style="#f5f5f5",
        ),
        Text("  write one by hand, or scaffold it with `tripwire init <your_ref.py>`.",
             style=MUTE),
        Text(),
        Text("commands:", style="bold #f5f5f5"),
        Text("  demo      see it catch planted hacks across domains (no setup)", style="#f5f5f5"),
        Text("  verify    check your candidate against a target  (--example to try one)",
             style="#f5f5f5"),
        Text("  init      scaffold a Target from your reference function", style="#f5f5f5"),
        Text("  optimize  run a real LLM loop, oracle-graded     (--example to try one)",
             style="#f5f5f5"),
        Text(),
        Text(
            "quickstart:  tripwire demo  →  tripwire verify --example  →  "
            "tripwire init your_ref.py  →  tripwire optimize your_ref_target.py",
            style=f"bold {RED}",
        ),
    )
    console.print()
    console.print(
        Panel(body, title="[bold]how tripwire works[/bold]", title_align="left",
              border_style=RED, padding=(1, 2))
    )
    return 0


# --------------------------------------------------------------------------- #
# interactive dispatch + entrypoint
# --------------------------------------------------------------------------- #
def _dispatch_interactive(console, choice):
    if choice == "demo":
        return run_demo(console, banner=False)
    if choice == "example":
        return run_verify_example(console)
    if choice == "explain":
        return run_explain(console)
    if choice == "init":
        console.print()
        try:
            ref = console.input(
                "  [bold]reference file[/bold] (.py with your slow-but-correct function): "
            ).strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n  [dim]cancelled.[/dim]")
            return 0
        if not ref:
            console.print("  [red]need a reference file.[/red]")
            return 1
        return run_init(console, ref)
    if choice == "verify":
        console.print()
        try:
            target = console.input(
                "  [bold]target file[/bold] (.py with `target` / `make_target`): "
            ).strip()
            candidate = console.input("  [bold]candidate file[/bold] (.py): ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n  [dim]cancelled.[/dim]")
            return 0
        if not target or not candidate:
            console.print("  [red]need both a target file and a candidate file.[/red]")
            return 1
        return run_verify(console, target, candidate, isolate=True)
    if choice == "optimize":
        prep = _prepare_optimize_env(console)  # loads .env BEFORE the prereq check
        _, have_key, have_model = prep
        if not (have_key and have_model):
            return run_optimize(console, env=prep)  # prereq panel explains what's missing
        console.print()
        try:
            target = console.input(
                "  [bold]target file[/bold] (.py with `target` / `make_target`): "
            ).strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n  [dim]cancelled.[/dim]")
            return 0
        if not target:
            console.print("  [red]need a target file.[/red]")
            return 1
        return run_optimize(console, target, env=prep)
    return 0


def _run_interactive(console):
    _print_banner(console)
    while True:
        choice = _interactive_menu(console)
        if choice == "quit":
            console.print("\n  bye.\n", style=MUTE)
            return 0
        _dispatch_interactive(console, choice)
        console.print()
        try:
            console.input("  [dim]press enter to return to the menu…[/dim]")
        except (EOFError, KeyboardInterrupt):
            console.print()
            return 0
        console.clear()
        _print_banner(console)


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="tripwire",
        description="Adversarial correctness oracle for AI code optimization. "
        "Run with no arguments for the interactive menu.",
    )
    parser.add_argument("--version", action="store_true", help="print the version and exit")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("demo", help="run the cross-domain integrity scorecard")

    pv = sub.add_parser("verify", help="verify one optimized candidate against a target")
    pv.add_argument("target", nargs="?", help="path to a .py exposing `target` or `make_target()`")
    pv.add_argument("candidate", nargs="?", help="path to the optimized candidate .py")
    pv.add_argument("--example", action="store_true", help="run a bundled example (no setup)")
    pv.add_argument(
        "--trust",
        action="store_true",
        help="run the candidate in-process without the sandbox (trusted code only)",
    )

    po = sub.add_parser(
        "optimize",
        help="run a real OpenEvolve loop (needs the runner extra + an LLM key)",
    )
    po.add_argument("target", nargs="?", help="path to a .py exposing `target` or `make_target()`")
    po.add_argument("--example", action="store_true", help="optimize a bundled example target")
    po.add_argument(
        "--iterations", type=int, default=None, help="number of loop iterations (default 10)"
    )
    po.add_argument(
        "--initial",
        help="explicit initial program .py (default: derived from the target's reference)",
    )
    po.add_argument("--output", help="output directory (default ./tripwire-runs)")
    po.add_argument(
        "--yes", action="store_true", help="auto-install OpenEvolve if missing (no prompt)"
    )

    pi = sub.add_parser("init", help="scaffold a Target skeleton from a reference .py")
    pi.add_argument("reference", help="path to a .py with your slow-but-correct function")
    pi.add_argument("--function", help="which function to use (if the file has several)")
    pi.add_argument(
        "-o", "--output", help="output path (default <reference>_target.py; '-' for stdout)"
    )
    pi.add_argument("--force", action="store_true", help="overwrite the output file if it exists")

    sub.add_parser("explain", help="how it works (the 4-layer oracle)")

    return parser


def _version():
    try:
        from importlib.metadata import version

        return version("tripwire-oracle")
    except Exception:
        return "0+unknown"


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    parser = _build_parser()
    args = parser.parse_args(argv)

    console = _console()

    if getattr(args, "version", False):
        console.print(f"tripwire {_version()}")
        return 0

    if args.command is None:
        if sys.stdin.isatty() and sys.stdout.isatty():
            try:
                return _run_interactive(console)
            except (KeyboardInterrupt, EOFError):
                console.print()
                return 0
        # Non-interactive (piped / no TTY): show the banner + help, never hang.
        _print_banner(console)
        console.print("  Run [bold]tripwire demo[/bold] to see the oracle in action.\n", style=MUTE)
        parser.print_help()
        return 0

    if args.command == "demo":
        return run_demo(console)
    if args.command == "explain":
        return run_explain(console)
    if args.command == "init":
        return run_init(
            console, args.reference, function=args.function, output=args.output, force=args.force
        )
    if args.command == "verify":
        if args.example:
            return run_verify_example(console)
        if not (args.target and args.candidate):
            console.print("  [red]verify needs TARGET and CANDIDATE, or --example.[/red]")
            return 2
        return run_verify(console, args.target, args.candidate, isolate=not args.trust)
    if args.command == "optimize":
        target = None
        if args.example:
            from tripwire import examples as ex

            target = str(ex.TARGET)
        elif args.target:
            target = args.target
        return run_optimize(
            console,
            target,
            iterations=args.iterations,
            initial_path=args.initial,
            output_dir=args.output,
            assume_yes=args.yes,
        )

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
