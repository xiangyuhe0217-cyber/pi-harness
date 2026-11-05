from __future__ import annotations

import argparse

from . import evaluate, manifest, prepare, report, run_agent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SWE-bench Lite subset pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    p_manifest = sub.add_parser("manifest")
    p_manifest.add_argument("--dataset", default=manifest.DEFAULT_DATASET)
    p_manifest.add_argument("--split", default=manifest.DEFAULT_SPLIT)
    p_manifest.add_argument("--revision", default=None)
    p_manifest.add_argument("--count", type=int, default=12)
    p_manifest.add_argument("--seed", type=int, default=0)
    p_manifest.add_argument("--out", default="eval/swebench/manifest.json")
    p_manifest.add_argument("--from-json", default=None)

    p_prepare = sub.add_parser("prepare")
    p_prepare.add_argument("--manifest", default="eval/swebench/manifest.json")
    p_prepare.add_argument("--work", default="eval/work")
    p_prepare.add_argument("--limit", type=int, default=None)

    p_agent = sub.add_parser("agent")
    p_agent.add_argument("--manifest", default="eval/swebench/manifest.json")
    p_agent.add_argument("--work", default="eval/work")
    p_agent.add_argument("--configs", default="mcp,builtin")
    p_agent.add_argument("--limit", type=int, default=None)
    p_agent.add_argument("--instance", default=None)
    p_agent.add_argument("--model", default="deepseek-chat")
    p_agent.add_argument("--timeout", type=int, default=900)
    p_agent.add_argument("--overwrite", action="store_true")

    p_eval = sub.add_parser("evaluate")
    p_eval.add_argument("--predictions", required=True)
    p_eval.add_argument("--dataset", default=manifest.DEFAULT_DATASET)
    p_eval.add_argument("--run-id", default=None)
    p_eval.add_argument("--max-workers", type=int, default=4)
    p_eval.add_argument("--dry-run", action="store_true")

    p_report = sub.add_parser("report")
    p_report.add_argument("--manifest", default="eval/swebench/manifest.json")
    p_report.add_argument("--predictions-dir", default="eval/work/predictions")
    p_report.add_argument("--meta-dir", default="eval/work/meta")
    p_report.add_argument("--results-dir", default="eval/work")
    p_report.add_argument("--out", default="eval/swebench/report.md")

    args = parser.parse_args(argv)
    if args.command == "manifest":
        return manifest.main(
            [
                "--dataset",
                args.dataset,
                "--split",
                args.split,
                "--revision",
                args.revision or "",
                "--count",
                str(args.count),
                "--seed",
                str(args.seed),
                "--out",
                args.out,
                *(["--from-json", args.from_json] if args.from_json else []),
            ]
        )
    if args.command == "prepare":
        return prepare.main(
            ["--manifest", args.manifest, "--work", args.work]
            + (["--limit", str(args.limit)] if args.limit else [])
        )
    if args.command == "agent":
        return run_agent.main(
            [
                "--manifest",
                args.manifest,
                "--work",
                args.work,
                "--configs",
                args.configs,
                "--model",
                args.model,
                "--timeout",
                str(args.timeout),
            ]
            + (["--limit", str(args.limit)] if args.limit else [])
            + (["--instance", args.instance] if args.instance else [])
            + (["--overwrite"] if args.overwrite else [])
        )
    if args.command == "evaluate":
        return evaluate.main(
            [
                "--predictions",
                args.predictions,
                "--dataset",
                args.dataset,
                "--max-workers",
                str(args.max_workers),
            ]
            + (["--run-id", args.run_id] if args.run_id else [])
            + (["--dry-run"] if args.dry_run else [])
        )
    if args.command == "report":
        return report.main(
            [
                "--manifest",
                args.manifest,
                "--predictions-dir",
                args.predictions_dir,
                "--meta-dir",
                args.meta_dir,
                "--results-dir",
                args.results_dir,
                "--out",
                args.out,
            ]
        )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
