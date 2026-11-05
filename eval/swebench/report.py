from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from pathlib import Path
from typing import Any

from .manifest import load_manifest


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def bootstrap_ci(values: list[int], iters: int = 2000, seed: int = 0) -> tuple[float, float]:
    if not values:
        return (0.0, 0.0)
    rng = random.Random(seed)
    means = []
    for _ in range(iters):
        sample = [rng.choice(values) for _ in values]
        means.append(sum(sample) / len(sample))
    means.sort()
    return (means[int(0.025 * len(means))], means[int(0.975 * len(means)) - 1])


def summarize(
    predictions: list[dict[str, Any]],
    results: dict[str, Any],
    meta: list[dict[str, Any]],
) -> dict[str, Any]:
    resolved = set(results.get("resolved_instances") or [])
    unresolved = set(results.get("unresolved_instances") or [])
    errors = set(results.get("error_ids") or [])
    total = len(predictions)
    labels = [1 if row["instance_id"] in resolved else 0 for row in predictions]
    ci_low, ci_high = bootstrap_ci(labels)
    meta_by_id = {row["instance_id"]: row for row in meta}
    empty = sum(1 for row in predictions if not row.get("model_patch", "").strip())
    tokens = sum(
        (meta_by_id.get(row["instance_id"], {}).get("summary") or {}).get("tokens", 0)
        for row in predictions
    )
    cost = sum(
        (meta_by_id.get(row["instance_id"], {}).get("summary") or {}).get("cost_usd", 0)
        for row in predictions
    )
    return {
        "total": total,
        "resolved": len(resolved & {row["instance_id"] for row in predictions}),
        "unresolved": len(unresolved & {row["instance_id"] for row in predictions}),
        "errors": len(errors & {row["instance_id"] for row in predictions}),
        "apply_rate": (len(resolved) + len(unresolved)) / total if total else 0.0,
        "resolved_rate": len(resolved) / total if total else 0.0,
        "ci": (ci_low, ci_high),
        "empty_patch": empty,
        "tokens": tokens,
        "cost_usd": round(cost, 6),
    }


def find_results(results_root: Path, config: str) -> Path | None:
    if not results_root.exists():
        return None
    candidates = sorted(results_root.rglob("results.json"))
    for path in candidates:
        text = path.read_text(encoding="utf-8", errors="ignore")
        if f"pi-harness-{config}" in text or f"pi-harness-{config}" in str(path):
            return path
    return None


def render_report(
    manifest_path: str | Path,
    predictions_dir: str | Path,
    meta_dir: str | Path,
    results_dir: str | Path,
    out: str | Path,
) -> str:
    instances = load_manifest(manifest_path)
    configs = ["mcp", "builtin"]
    summary: dict[str, dict[str, Any]] = {}
    prediction_rows: dict[str, list[dict[str, Any]]] = {}
    for config in configs:
        predictions = load_jsonl(Path(predictions_dir) / f"{config}.jsonl")
        meta = load_jsonl(Path(meta_dir) / f"{config}.jsonl")
        result_path = find_results(Path(results_dir), config)
        results = json.loads(result_path.read_text(encoding="utf-8")) if result_path else {}
        prediction_rows[config] = predictions
        summary[config] = summarize(predictions, results, meta)
        summary[config]["result_file"] = str(result_path) if result_path else None

    by_repo = Counter(instance.repo for instance in instances)
    lines = [
        "# SWE-bench Lite subset",
        "",
        f"- instances: {len(instances)}",
        f"- repos: {dict(sorted(by_repo.items()))}",
        "- subset, not full SWE-bench; results are exploratory",
        "",
        "| config | resolved | total | rate | 95% CI | apply rate | empty patch | tokens | cost |",
        "|---|---:|---:|---:|---|---:|---:|---:|---:|",
    ]
    for config in configs:
        item = summary[config]
        lines.append(
            f"| {config} | {item['resolved']} | {item['total']} | {item['resolved_rate']:.2f} | "
            f"[{item['ci'][0]:.2f}, {item['ci'][1]:.2f}] | {item['apply_rate']:.2f} | "
            f"{item['empty_patch']} | {item['tokens']} | ${item['cost_usd']:.4f} |"
        )

    lines += ["", "## Per instance", "", "| instance | repo | mcp resolved | builtin resolved |", "|---|---|---|---|"]
    result_sets = {}
    for config in configs:
        path = summary[config].get("result_file")
        if path:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            result_sets[config] = set(data.get("resolved_instances") or [])
        else:
            result_sets[config] = set()
    for instance in instances:
        lines.append(
            f"| {instance.instance_id} | {instance.repo} | "
            f"{'yes' if instance.instance_id in result_sets['mcp'] else 'no'} | "
            f"{'yes' if instance.instance_id in result_sets['builtin'] else 'no'} |"
        )

    lines += [
        "",
        "## Notes",
        "",
        "- `resolved` comes from the official SWE-bench evaluator, not local checks.",
        "- 12-instance subset: no claim of full SWE-bench performance.",
        "- `builtin` = pi built-in tools; `mcp` = Harness MCP-only.",
        "",
    ]
    markdown = "\n".join(lines)
    target = Path(out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(markdown, encoding="utf-8")
    return markdown


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize SWE-bench subset results")
    parser.add_argument("--manifest", default="eval/swebench/manifest.json")
    parser.add_argument("--predictions-dir", default="eval/work/predictions")
    parser.add_argument("--meta-dir", default="eval/work/meta")
    parser.add_argument("--results-dir", default="eval/work")
    parser.add_argument("--out", default="eval/swebench/report.md")
    args = parser.parse_args(argv)
    print(
        render_report(
            args.manifest,
            args.predictions_dir,
            args.meta_dir,
            args.results_dir,
            args.out,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
