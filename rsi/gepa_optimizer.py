from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from harness.runner import run_task  # noqa: E402
from harness.tasks import load_task  # noqa: E402


def score_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    passed = sum(1 for result in results if result.get("status") == "pass")
    tokens = sum(
        int((result.get("summary") or {}).get("tokens") or 0) for result in results
    )
    cost = sum(
        float((result.get("summary") or {}).get("cost_usd") or 0) for result in results
    )
    blocked = sum(
        int((result.get("summary") or {}).get("blocked") or 0) for result in results
    )
    pass_rate = passed / total if total else 0.0
    cost_penalty = min(1.0, cost / max(0.001, 0.02 * max(1, total)))
    score = pass_rate - 0.1 * cost_penalty - 0.02 * min(1.0, blocked / max(1, total))
    feedback = "\n".join(
        f"{result.get('task_id')}: status={result.get('status')} "
        f"outcome={(result.get('outcome') or {}).get('primary')} "
        f"tokens={(result.get('summary') or {}).get('tokens')} "
        f"blocked={(result.get('summary') or {}).get('blocked')}"
        for result in results
    )
    return {
        "score": round(max(0.0, min(1.0, score)), 4),
        "passed": passed,
        "total": total,
        "pass_rate": round(pass_rate, 3),
        "tokens": tokens,
        "cost_usd": round(cost, 6),
        "blocked": blocked,
        "feedback": feedback,
    }


def evaluate_prompt(
    prompt: str,
    task_paths: list[str],
    runs_root: str | Path = "rsi/runs",
    model: str = "deepseek-chat",
    timeout_s: int = 180,
) -> dict[str, Any]:
    results = []
    for index, path in enumerate(task_paths, start=1):
        task = load_task(Path(path), ROOT)
        task.model = model
        task.timeout_s = timeout_s
        print(f"[rsi {index}/{len(task_paths)}] {task.id}", flush=True)
        result = run_task(
            task,
            Path(runs_root),
            mcp_only=True,
            policy_path=ROOT / "policies" / "p1.json",
            task_path=ROOT / path,
            append_prompt=prompt,
            scope=task.scope,
        )
        results.append(result)
    summary = score_results(results)
    summary["results"] = [
        {
            "task_id": result.get("task_id"),
            "status": result.get("status"),
            "outcome": (result.get("outcome") or {}).get("primary"),
            "run_dir": result.get("run_dir"),
        }
        for result in results
    ]
    return summary


def _load_dataset(path: str | Path, split: str) -> list[str]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [str(item) for item in data.get(split) or []]
