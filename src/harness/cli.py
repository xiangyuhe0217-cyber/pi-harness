from __future__ import annotations

import argparse
import json
from pathlib import Path

from .export import export_otel
from .memory import MemoryStore
from .openviking import OpenVikingClient, sync_record
from .report import render_baseline
from .replay import replay_run
from .runner import resume_run, run_task
from .tasks import load_task

ROOT = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="harness")
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="run one task")
    run_parser.add_argument("--task", required=True)
    run_parser.add_argument("--runs", default=str(ROOT / "runs"))
    run_parser.add_argument("--mcp-only", action="store_true")
    run_parser.add_argument("--policy", default=None)
    run_parser.add_argument("--append-prompt", default=None)
    run_parser.add_argument("--scope", default=None)

    baseline_parser = sub.add_parser("baseline", help="run all tasks")
    baseline_parser.add_argument("--tasks", default=str(ROOT / "tasks"))
    baseline_parser.add_argument("--runs", default=str(ROOT / "runs" / "baseline"))
    baseline_parser.add_argument("--mcp-only", action="store_true")
    baseline_parser.add_argument("--policy", default=None)
    baseline_parser.add_argument("--append-prompt", default=None)
    baseline_parser.add_argument("--scope", default=None)

    replay_parser = sub.add_parser("replay", help="replay policy decisions")
    replay_parser.add_argument("--run", required=True)
    replay_parser.add_argument("--policy", required=True)
    replay_parser.add_argument("--out", default=None)

    resume_parser = sub.add_parser("resume", help="resume an interrupted run")
    resume_parser.add_argument("--run", required=True)
    resume_parser.add_argument("--timeout", type=int, default=None)

    export_parser = sub.add_parser("export", help="export a run as OTLP-style JSON")
    export_parser.add_argument("--run", required=True)
    export_parser.add_argument("--out", default=None)

    memory_parser = sub.add_parser("memory", help="manage long-term memory")
    memory_sub = memory_parser.add_subparsers(dest="memory_action", required=True)
    mem_add = memory_sub.add_parser("add")
    mem_add.add_argument("--text", required=True)
    mem_add.add_argument("--kind", default="fact")
    mem_add.add_argument("--key", default="")
    mem_add.add_argument("--source", default="user")
    mem_add.add_argument("--confidence", type=float, default=1.0)
    mem_add.add_argument("--scope", default="default")
    mem_add.add_argument("--ttl-days", type=int, default=None)
    mem_list = memory_sub.add_parser("list")
    mem_list.add_argument("--scope", default=None)
    mem_list.add_argument("--status", default=None)
    mem_search = memory_sub.add_parser("search")
    mem_search.add_argument("--query", required=True)
    mem_search.add_argument("--scope", default="default")
    mem_search.add_argument("--top-k", type=int, default=5)
    mem_stats = memory_sub.add_parser("stats")
    mem_stats.add_argument("--scope", default=None)
    mem_approve = memory_sub.add_parser("approve")
    mem_approve.add_argument("--id", required=True)
    mem_reject = memory_sub.add_parser("reject")
    mem_reject.add_argument("--id", required=True)
    mem_reject.add_argument("--reason", default="not_useful")
    mem_sync = memory_sub.add_parser("sync")
    mem_sync.add_argument("--id", required=True)

    args = parser.parse_args(argv)
    mcp_only = True if getattr(args, "mcp_only", False) else None

    if args.command == "run":
        task = load_task(Path(args.task), ROOT)
        result = run_task(
            task,
            Path(args.runs),
            mcp_only=mcp_only,
            policy_path=args.policy,
            task_path=args.task,
            append_prompt=args.append_prompt,
            scope=args.scope,
        )
        print(
            json.dumps(
                {
                    "task_id": result["task_id"],
                    "kind": result["kind"],
                    "status": result["status"],
                    "summary": result["summary"],
                    "run_dir": result["run_dir"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0 if result["status"] in {"pass", "blocked", "not_attempted"} else 1

    if args.command == "baseline":
        paths = sorted(Path(args.tasks).glob("*.json"))
        if not paths:
            print(f"no tasks in {args.tasks}")
            return 2
        results = [
            run_task(
                load_task(path, ROOT),
                Path(args.runs),
                mcp_only=mcp_only,
                policy_path=args.policy,
                task_path=path,
                append_prompt=args.append_prompt,
                scope=args.scope,
            )
            for path in paths
        ]
        report = render_baseline(results)
        out = Path(args.runs)
        out.mkdir(parents=True, exist_ok=True)
        (out / "report.md").write_text(report, encoding="utf-8")
        print(report)
        return 0

    if args.command == "replay":
        result = replay_run(Path(args.run), Path(args.policy))
        print(result["markdown"])
        out = Path(args.out) if args.out else Path(args.run) / f"replay-{result['policy']}.md"
        out.write_text(result["markdown"], encoding="utf-8")
        return 0

    if args.command == "resume":
        result = resume_run(Path(args.run), args.timeout)
        print(
            json.dumps(
                {
                    "task_id": result["task_id"],
                    "status": result["status"],
                    "verdict": result["verdict"],
                    "summary": result["summary"],
                    "run_dir": result["run_dir"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0 if result["status"] == "pass" else 1

    if args.command == "export":
        out = export_otel(Path(args.run), args.out)
        print(str(out))
        return 0

    if args.command == "memory":
        store = MemoryStore(ROOT / "memory" / "store.json")
        client = OpenVikingClient()
        if args.memory_action == "add":
            result = store.add(
                scope=args.scope,
                kind=args.kind,
                key=args.key,
                text=args.text,
                source=args.source,
                confidence=args.confidence,
                ttl_days=args.ttl_days,
            )
            if result.get("status") == "allow" and result.get("record"):
                result["sync"] = sync_record(client, store, result["record"])
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif args.memory_action == "approve":
            record = store.set_status(args.id, "active", "human_review")
            result = sync_record(client, store, record)
            print(json.dumps({"record": store.get(args.id), "sync": result}, ensure_ascii=False, indent=2))
        elif args.memory_action == "reject":
            record = store.set_status(args.id, "rejected", args.reason)
            print(json.dumps({"record": record}, ensure_ascii=False, indent=2))
        elif args.memory_action == "sync":
            record = store.get(args.id)
            if record is None:
                print(json.dumps({"error": "not found"}))
                return 1
            result = sync_record(client, store, record)
            print(json.dumps({"record": store.get(args.id), "sync": result}, ensure_ascii=False, indent=2))
        elif args.memory_action == "list":
            print(
                json.dumps(
                    store.list(scope=args.scope, status=args.status),
                    ensure_ascii=False,
                    indent=2,
                )
            )
        elif args.memory_action == "search":
            print(
                json.dumps(
                    store.search(args.scope, args.query, args.top_k),
                    ensure_ascii=False,
                    indent=2,
                )
            )
        elif args.memory_action == "stats":
            print(json.dumps(store.stats(args.scope), ensure_ascii=False, indent=2))
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
