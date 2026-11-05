from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rsi.gepa_optimizer import evaluate_prompt, _load_dataset  # noqa: E402
from rsi.gate import gate  # noqa: E402


def _best(result: object) -> str:
    candidate = getattr(result, "best_candidate", None)
    if isinstance(candidate, str):
        return candidate
    if isinstance(candidate, dict):
        return str(candidate.get("system_prompt") or next(iter(candidate.values())))
    return str(candidate or "")


def run_gepa(seed: str, dev: list[str], holdout: list[str], max_calls: int, out: str) -> dict:
    try:
        import gepa.optimize_anything as oa
        from gepa.optimize_anything import GEPAConfig, EngineConfig, optimize_anything
    except ImportError as exc:
        raise RuntimeError("GEPA not installed: pip install gepa") from exc

    def evaluator(candidate: str) -> float:
        summary = evaluate_prompt(candidate, dev)
        oa.log(summary["feedback"])
        return float(summary["score"])

    result = optimize_anything(
        seed_candidate=seed,
        evaluator=evaluator,
        objective=(
            "Improve coding-agent pass rate without increasing tokens, cost, "
            "blocked calls, or unsafe behavior."
        ),
        config=GEPAConfig(engine=EngineConfig(max_metric_calls=max_calls)),
    )
    winner = _best(result)
    target = Path(out)
    target.parent.mkdir(parents=True, exist_ok=True)
    candidate_path = target.parent / "candidate.txt"
    candidate_path.write_text(winner, encoding="utf-8")

    baseline = evaluate_prompt(seed, holdout)
    candidate = evaluate_prompt(winner, holdout)
    decision = gate(baseline, candidate)
    (target.parent / "gate.json").write_text(
        json.dumps(decision, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if decision["adopted"]:
        target.write_text(winner, encoding="utf-8")
    payload = {
        "adopted": decision["adopted"],
        "best_candidate": winner if decision["adopted"] else None,
        "candidate_path": str(candidate_path),
        "gate": decision,
        "best_score": getattr(result, "best_score", None),
        "raw": str(result)[:4000],
    }
    (target.parent / "gepa-result.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="GEPA prompt optimization for pi-harness")
    parser.add_argument("--dataset", default="rsi/dataset.json")
    parser.add_argument("--seed", default="rsi/seed_prompt.txt")
    parser.add_argument("--max-calls", type=int, default=24)
    parser.add_argument("--out", default="rsi/prompts/winner.txt")
    parser.add_argument("--evaluate-only", action="store_true")
    parser.add_argument("--prompt", default=None)
    args = parser.parse_args(argv)

    seed = Path(args.seed).read_text(encoding="utf-8")
    dev = _load_dataset(args.dataset, "dev")
    holdout = _load_dataset(args.dataset, "holdout")

    if args.evaluate_only:
        prompt = Path(args.prompt).read_text(encoding="utf-8") if args.prompt else seed
        print("== dev ==")
        print(json.dumps(evaluate_prompt(prompt, dev), ensure_ascii=False, indent=2)[:4000])
        print("== holdout ==")
        print(json.dumps(evaluate_prompt(prompt, holdout), ensure_ascii=False, indent=2)[:4000])
        return 0

    result = run_gepa(seed, dev, holdout, args.max_calls, args.out)
    print(json.dumps(result, ensure_ascii=False, indent=2)[:4000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
