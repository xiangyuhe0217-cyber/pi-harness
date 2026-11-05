from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def find_result_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(root.rglob("results.json"))


def parse_results(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return {"resolved_instances": data}
    return data


def evaluate(
    predictions: str | Path,
    dataset: str = "princeton-nlp/SWE-bench_Lite",
    run_id: str | None = None,
    max_workers: int = 4,
    dry_run: bool = False,
) -> dict[str, Any]:
    predictions = Path(predictions).resolve()
    if not predictions.exists():
        raise FileNotFoundError(predictions)
    run_id = run_id or f"harness-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    command = [
        sys.executable,
        "-m",
        "swebench.harness.run_evaluation",
        "--dataset_name",
        dataset,
        "--predictions_path",
        str(predictions),
        "--max_workers",
        str(max_workers),
        "--run_id",
        run_id,
    ]
    if dry_run:
        print(" ".join(command))
        return {"command": command, "run_id": run_id, "dry_run": True}
    if shutil.which("docker") is None:
        raise RuntimeError("docker not found; SWE-bench evaluation requires Docker")
    log_path = predictions.parent / f"evaluate-{run_id}.log"
    with log_path.open("w", encoding="utf-8") as log:
        completed = subprocess.run(
            command,
            cwd=str(predictions.parent),
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )
    if completed.returncode != 0:
        raise RuntimeError(
            f"swebench evaluator failed ({completed.returncode}); see {log_path}"
        )
    return {
        "command": command,
        "run_id": run_id,
        "log": str(log_path),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the official SWE-bench evaluator")
    parser.add_argument("--predictions", required=True)
    parser.add_argument("--dataset", default="princeton-nlp/SWE-bench_Lite")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    result = evaluate(
        args.predictions,
        args.dataset,
        args.run_id,
        args.max_workers,
        args.dry_run,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2)[:4000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
