"""tripwire.target -- Interface A: the FROZEN domain plug-in contract.

This is one of the two load-bearing contracts in CLAUDE.md §4. Every Phase-2
domain (tokenizer, serde, numeric, SQL, ...) ships exactly one `Target`. The
oracle (tripwire/oracle.py) and the benchmark (bench/run.py) both program against
*this* shape and nothing else. Changing it forces a re-sync across every domain
plug-in, so it is FROZEN as of task 1.3 -- additive changes only (new optional
fields with safe defaults); never rename or repurpose an existing field.

A Target bundles five things (see the authoring guide, docs/target-authoring.md):

  reference        the slow-but-correct ground truth (a pure function)
  canonical_args   the inputs the optimizer is ALLOWED to see   (the "test set")
  withheld_args    fresh + adversarial inputs it NEVER sees      (the moat; ADR-003)
  properties       metamorphic / invariant checks               (L2)
  candidates       labeled reference implementations            (benchmark only)

Validation (ADR-003, ADR-002): a Target validates its own invariants in
__post_init__ and raises on violation, so a Phase-2 author cannot silently ship a
target that has, e.g., no withheld inputs (which would quietly destroy the moat).

There is NO oracle logic and NO evolutionary-loop code here (HARD RULE 1).
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

# --- frozen vocabulary: target kinds (controls exact vs tolerance comparison) ---
STRUCTURAL = "structural"  # exact comparison is SOUND and free (ADR-004)
NUMERIC = "numeric"  # tolerance + metamorphic; bitwise would discard real speedups (ADR-004)
KINDS = frozenset({STRUCTURAL, NUMERIC})

# --- frozen vocabulary: candidate truth labels (benchmark ground truth) ---
CORRECT = "correct"  # genuinely correct AND bit-identical to the reference
CORRECT_FP = "correct_fp"  # genuinely correct but low bits differ (the np.sum case)
HACK = "hack"  # reward-hack: passes canonical, wrong on withheld
TRUTHS = frozenset({CORRECT, CORRECT_FP, HACK})
# A candidate is "valid" (a real win the oracle SHOULD keep) iff its truth is here.
# This is the set bench/run.py uses to compute integrity; keep it authoritative.
VALID_TRUTHS = frozenset({CORRECT, CORRECT_FP})


@dataclass
class Target:
    """A domain plug-in. FROZEN contract (Interface A) -- see module docstring.

    Fields are ordered to match the proven positional construction in
    optimizer_integrity_bench.py: (name, kind, reference, canonical_args,
    withheld_args, properties, candidates).
    """

    name: str
    kind: str  # 'structural' | 'numeric'  -- must be in KINDS
    reference: Callable  # the slow, correct ground truth
    canonical_args: list  # inputs the optimizer is ALLOWED to see  (non-empty)
    withheld_args: list  # fresh + adversarial; NEVER shown          (non-empty; the moat)
    # (name, fn(args, out) -> bool) metamorphic / invariant checks; optional.
    properties: list = field(default_factory=list)
    # label -> (fn, truth) with truth in TRUTHS; benchmark only; optional.
    candidates: dict = field(default_factory=dict)
    # OPTIONAL generative moat (hardening): a callable `fn(rng) -> list[arg-tuples]`
    # that draws FRESH adversarial inputs from a seeded numpy Generator. The oracle
    # calls it with a NEW random seed on every evaluation, so the L3 differential is
    # not a fixed finite sample a candidate (or an evolutionary loop) can overfit to
    # -- it defends against distribution/feature-conditioned wrongness, not just
    # exact-input memorization. `withheld_args` (the fixed adversarial edges) is
    # still used; the factory's fresh draws are checked IN ADDITION. Optional and
    # backward-compatible: targets without it keep the fixed-sample behavior.
    withheld_factory: Callable | None = None

    def __post_init__(self) -> None:
        # --- name ---
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("Target.name must be a non-empty str")

        # --- kind (ADR-004: controls exact vs tolerance) ---
        if self.kind not in KINDS:
            raise ValueError(
                f"Target.kind must be one of {sorted(KINDS)}, got {self.kind!r}"
            )

        # --- reference must be callable ---
        if not callable(self.reference):
            raise TypeError("Target.reference must be callable")

        # --- canonical_args / withheld_args: non-empty lists of arg-tuples ---
        # ADR-003: withheld inputs are NON-NEGOTIABLE. An empty withheld set
        # silently removes the moat (L3 would iterate over nothing), so we reject
        # it at construction rather than let a Phase-2 author ship it by accident.
        for attr in ("canonical_args", "withheld_args"):
            val = getattr(self, attr)
            if not isinstance(val, list) or len(val) == 0:
                raise ValueError(f"Target.{attr} must be a non-empty list of arg tuples")
            for i, args in enumerate(val):
                if not isinstance(args, (tuple, list)):
                    raise TypeError(
                        f"Target.{attr}[{i}] must be a tuple/list of positional args "
                        f"(so reference(*args) works), got {type(args).__name__}"
                    )

        # --- properties: list of (name, callable) ---
        if not isinstance(self.properties, list):
            raise TypeError("Target.properties must be a list of (name, fn) pairs")
        for i, prop in enumerate(self.properties):
            if not (isinstance(prop, (tuple, list)) and len(prop) == 2):
                raise TypeError(f"Target.properties[{i}] must be a (name, fn) pair")
            pname, pfn = prop
            if not isinstance(pname, str) or not pname:
                raise ValueError(f"Target.properties[{i}] name must be a non-empty str")
            if not callable(pfn):
                raise TypeError(f"Target.properties[{i}] ({pname!r}) fn must be callable")

        # --- candidates: label -> (fn, truth) with truth in TRUTHS ---
        if not isinstance(self.candidates, dict):
            raise TypeError("Target.candidates must be a dict of label -> (fn, truth)")
        for label, spec in self.candidates.items():
            if not (isinstance(spec, (tuple, list)) and len(spec) == 2):
                raise TypeError(
                    f"Target.candidates[{label!r}] must be a (fn, truth) pair"
                )
            fn, truth = spec
            if not callable(fn):
                raise TypeError(f"Target.candidates[{label!r}] fn must be callable")
            if truth not in TRUTHS:
                raise ValueError(
                    f"Target.candidates[{label!r}] truth must be one of {sorted(TRUTHS)}, "
                    f"got {truth!r}"
                )

        # --- withheld_factory: optional callable(rng) -> list[arg-tuples] ---
        if self.withheld_factory is not None and not callable(self.withheld_factory):
            raise TypeError("Target.withheld_factory must be callable (rng) -> list[arg-tuples]")
