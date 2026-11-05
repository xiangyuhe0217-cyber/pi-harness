from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from harness.runner import run_task  # noqa: E402
from harness.tasks import Task  # noqa: E402

from .manifest import Instance, load_manifest  # noqa: E402
from .patch import extract_patch  # noqa: E402


def _task(instance: Instance, workspace: Path, config: str, model: str, timeout_s: int) -> Task:
    return Task(
        id=f"SWE-{instance.instance_id}",
        goal=instance.problem_statement,
        workspace=workspace,
        provider="litellm",
        model=model,
        policy="policies/p1.json",
        scope=f"swe-bench:{instance.repo}",
        timeout_s=timeout_s,
        max_steps=40,
        max_tokens=200000,
        max_cost_usd=0.5,
        mcp_only=config == "mcp",
        no_builtin_tools=False,
        kind="task",
        success={},
    )


def run_one(
    instance: Instance,
    workspace: Path,
    config: str,
    runs_root: Path,
    model: str,
    timeout_s: int,
) -> tuple[str, dict[str, Any]]:
    task = _task(instance, workspace, config, model, timeout_s)
    result = run_task(
        task,
        runs_root,
        mcp_only=config == "mcp",
        policy_path=ROOT / "policies" / "p1.json",
        scope=f"swe-bench:{instance.repo}",
    )
    run_workspace = Path(result["workspace"])
    try:
        patch = extract_patch(run_workspace, exclude_tests=True)
    except Exception as exc:  # noqa: BLE001
        patch = ""
        result["patch_error"] = str(exc)
    meta = {
        "instance_id": instance.instance_id,
        "repo": instance.repo,
        "config": config,
        "model": model,
        "status": result.get("status"),
        "patch_chars": len(patch),
        "run_dir": result.get("run_dir"),
        "summary": result.get("summary"),
        "error": result.get("patch_error"),
    }
    return patch, meta


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run pi-harness on prepared SWE-bench instances")
    parser.add_argument("--manifest", default="eval/swebench/manifest.json")
    parser.add_argument("--work", default="eval/work")
    parser.add_argument("--configs", default="mcp,builtin")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--instance", default=None)
    parser.add_argument("--model", default="deepseek-chat")
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)

    instances = load_manifest(args.manifest)
    if args.instance:
        instances = [item for item in instances if item.instance_id == args.instance]
    if args.limit:
        instances = instances[: args.limit]
    configs = [item.strip() for item in args.configs.split(",") if item.strip()]

    work_root = Path(args.work).resolve()
    runs_root = work_root / "runs"
    predictions_dir = work_root / "predictions"
    meta_dir = work_root / "meta"
    predictions_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)

    for config in configs:
        pred_path = predictions_dir / f"{config}.jsonl"
        meta_path = meta_dir / f"{config}.jsonl"
        if args.overwrite:
            pred_path.unlink(missing_ok=True)
            meta_path.unlink(missing_ok=True)
        for index, instance in enumerate(instances, start=1):
            workspace = work_root / "instances" / instance.instance_id
            if not workspace.exists():
                raise SystemExit(f"missing workspace {workspace}; run prepare first")
            print(f"[{config} {index}/{len(instances)}] {instance.instance_id}", flush=True)
            patch, meta = run_one(instance, workspace, config, runs_root, args.model, args.timeout)
            with pred_path.open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {
                            "instance_id": instance.instance_id,
                            "model_name_or_path": f"pi-harness-{config}",
                            "model_patch": patch,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
            with meta_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(meta, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
