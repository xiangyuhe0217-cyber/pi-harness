"""Recall OpenViking context for a scope/query."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from harness.memory_recall import recall_block  # noqa: E402
from harness.openviking import OpenVikingClient  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", default="default")
    parser.add_argument("--query", required=True)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--token-budget", type=int, default=2000)
    args = parser.parse_args(argv)
    result = recall_block(
        OpenVikingClient(),
        args.scope,
        args.query,
        args.limit,
        args.token_budget,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2)[:8000])
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
