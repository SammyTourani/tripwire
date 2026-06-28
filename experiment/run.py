"""experiment.run -- "does the moat beat the judge?" orchestrator.

Two modes:
  --planted   model-free validation on the OIB targets' built-in candidates (known
              ground truth). Confirms the referee + moat agree with the known labels;
              needs no API key. The judge is skipped (it needs a model).
  --models M1 M2 ...   the real run: generate candidates from each model, run them in
              the isolation sandbox, and record three verdicts per candidate
              (referee ground-truth, Tripwire moat, LLM judge baseline).

Headline metrics: of the reward-hacks, how many does the JUDGE wrongly accept, and how
many of those does the MOAT catch (the value-add); plus the moat's own false accepts
and its false rejects of genuine wins.

Run:  python -m experiment.run --planted
      OPENAI_API_KEY=... OPENAI_BASE_URL=https://openrouter.ai/api/v1 \
        python -m experiment.run --models meta-llama/llama-3.3-70b-instruct:free ...
"""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from experiment.ground_truth import label_candidate
from tripwire.oracle import layered_oracle
from tripwire.scorecard import TARGET_FACTORIES
from tripwire.target import HACK, VALID_TRUTHS


def _known_truth(truth: str) -> str:
    if truth == HACK:
        return "hack"
    if truth in VALID_TRUTHS:
        return "correct"
    return truth


# --------------------------------------------------------------------------- #
# planted mode (in-process, model-free) -- validates the referee + the moat
# --------------------------------------------------------------------------- #
def run_planted() -> int:
    records = []
    referee_mismatches = 0
    print(f"{'target':<16}{'candidate':<30}{'known':<9}{'referee':<9}{'moat':<8}")
    print("-" * 72)
    for name, factory in TARGET_FACTORIES:
        target = factory()
        for label, (fn, truth) in target.candidates.items():
            known = _known_truth(truth)
            referee, _ = label_candidate(target, fn=fn)
            moat = "accept" if layered_oracle(target, fn).accepted else "reject"
            # referee should agree with the known label (it is the ground truth)
            ref_ok = referee == known
            if not ref_ok:
                referee_mismatches += 1
            flag = "" if ref_ok else "  <-- REFEREE MISMATCH"
            print(f"{name:<16}{label[:29]:<30}{known:<9}{referee:<9}{moat:<8}{flag}")
            records.append(
                {"target": target.name, "candidate": label, "truth": known,
                 "referee": referee, "moat": moat, "judge": "skip"}
            )
    print("-" * 72)
    hacks = [r for r in records if r["truth"] == "hack"]
    correct = [r for r in records if r["truth"] == "correct"]
    moat_misses = [r for r in hacks if r["moat"] == "accept"]
    moat_false_rejects = [r for r in correct if r["moat"] == "reject"]
    n, nc, nh = len(records), len(correct), len(hacks)
    nm, nfr = len(moat_misses), len(moat_false_rejects)
    print(f"\nPLANTED VALIDATION ({n} candidates: {nc} correct + {nh} hacks)")
    ref_tag = "(PASS)" if referee_mismatches == 0 else f"({referee_mismatches} MISMATCH)"
    print(f"  referee vs known truth:   {n - referee_mismatches}/{n} agree  {ref_tag}")
    moat_tag = "(PASS)" if not moat_misses else f"({nm} MISSED)"
    print(f"  moat caught hacks:        {nh - nm}/{nh}  {moat_tag}")
    keep_tag = "(PASS)" if not moat_false_rejects else f"({nfr} WRONGLY REJECTED)"
    print(f"  moat kept real wins:      {nc - nfr}/{nc}  {keep_tag}")
    print("\nNote: this validates the referee + the moat on known data. The judge-vs-moat")
    print("comparison needs real model candidates (run with --models + an API key).")
    return 0 if referee_mismatches == 0 and not moat_misses and not moat_false_rejects else 1


# --------------------------------------------------------------------------- #
# models mode (isolated) -- the real moat-vs-judge run
# --------------------------------------------------------------------------- #
def evaluate_candidate_isolated(target, candidate_path, *, candidate_source, judge_model):
    """Three verdicts for one untrusted candidate file: referee (heavy isolated
    ground-truth), moat (the frozen layered-oracle evaluator), judge (LLM baseline)."""
    from tripwire.evaluator import make_openevolve_evaluator
    from tripwire.isolation import IsolatedCandidate

    entrypoints = ["solve", target.name]
    with IsolatedCandidate(candidate_path, entrypoints) as iso:
        if iso.load_error is not None:
            truth = "error"
        else:
            truth, _ = label_candidate(target, output_fn=iso.output_fn)

    res = make_openevolve_evaluator(target)(candidate_path)
    moat = "accept" if res.get("correct", 0.0) >= 1.0 else "reject"

    judge_v = "skip"
    if judge_model:
        from experiment.judge import judge_candidate

        try:
            judge_v, _ = judge_candidate(target, candidate_source, model=judge_model)
        except Exception:  # noqa: BLE001
            judge_v = "error"
    return truth, moat, judge_v


def run_models(models, *, judge_model, samples, output_dir) -> int:
    from experiment.generate import generate_candidates

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    records = []
    workdir = Path(tempfile.mkdtemp(prefix="tripwire-exp-"))
    try:
        for name, factory in TARGET_FACTORIES:
            target = factory()
            for model in models:
                print(f"[{name}] generating {samples} candidate(s) from {model} …")
                candidates = generate_candidates(target, model=model, n=samples)
                safe = name.replace(":", "_") + "_" + model.replace("/", "_")
                for i, source in enumerate(candidates):
                    cand_file = workdir / f"{safe}_{i}.py"
                    # prepend common imports so a candidate that uses numpy/math without
                    # importing it still loads (duplicate imports are harmless).
                    cand_file.write_text("import numpy as np\nimport math\n\n" + source)
                    truth, moat, judge_v = evaluate_candidate_isolated(
                        target, str(cand_file), candidate_source=source, judge_model=judge_model
                    )
                    rec = {"target": target.name, "model": model, "candidate": i,
                           "truth": truth, "moat": moat, "judge": judge_v}
                    records.append(rec)
                    print(f"    cand {i}: truth={truth:<7} moat={moat:<7} judge={judge_v}")
    finally:
        import shutil

        shutil.rmtree(workdir, ignore_errors=True)

    log = out / "records.jsonl"
    with log.open("w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    _print_headline(records)
    print(f"\nrecords: {log}")
    return 0


def _print_headline(records):
    hacks = [r for r in records if r["truth"] == "hack"]
    correct = [r for r in records if r["truth"] == "correct"]
    judge_false_accepts = [r for r in hacks if r["judge"] == "accept"]
    moat_caught = [r for r in judge_false_accepts if r["moat"] == "reject"]
    moat_misses = [r for r in hacks if r["moat"] == "accept"]
    moat_false_rejects = [r for r in correct if r["moat"] == "reject"]
    judge_false_rejects = [r for r in correct if r["judge"] == "reject"]
    print("\n" + "=" * 60)
    print("RESULT — does the moat beat the judge?")
    print("=" * 60)
    print(f"  candidates: {len(records)}  ({len(correct)} correct, {len(hacks)} reward-hacks, "
          f"{len(records) - len(correct) - len(hacks)} errored)")
    if hacks:
        print(f"  judge wrongly ACCEPTED:   {len(judge_false_accepts)}/{len(hacks)} hacks")
        print(f"  >> moat CAUGHT of those:  {len(moat_caught)}/{len(judge_false_accepts)}"
              "   (the value-add over a judge)")
        print(f"  moat's own misses:        {len(moat_misses)}/{len(hacks)} hacks accepted")
    if correct:
        print(f"  moat false-rejects:       {len(moat_false_rejects)}/{len(correct)} real wins"
              f"   (judge: {len(judge_false_rejects)}/{len(correct)})")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="experiment.run", description=__doc__)
    p.add_argument("--planted", action="store_true", help="model-free validation (no API key)")
    p.add_argument("--models", nargs="+", help="model ids to generate candidates from")
    p.add_argument("--judge-model", help="LLM-judge baseline model (default: first --models)")
    p.add_argument("--samples", type=int, default=3, help="candidates per (target, model)")
    p.add_argument("--output", default="experiment-runs", help="output dir for the records")
    args = p.parse_args(argv)

    if args.planted or not args.models:
        return run_planted()
    return run_models(
        args.models,
        judge_model=args.judge_model or args.models[0],
        samples=args.samples,
        output_dir=args.output,
    )


if __name__ == "__main__":
    raise SystemExit(main())
