"""Extract OpenViking session memories from a local run into quarantine."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from harness.memory import MemoryStore  # noqa: E402
from harness.memory_staging import (  # noqa: E402
    StagingClient,
    candidates_from_diff,
    messages_from_run,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, help="run directory containing result.json")
    parser.add_argument("--scope", default="default")
    parser.add_argument("--store", default=str(ROOT / "memory" / "store.json"))
    parser.add_argument("--staging-url", default=None)
    parser.add_argument("--diff", default=None, help="Use a local memory_diff JSON instead of HTTP")
    args = parser.parse_args(argv)

    if args.diff:
        diff = json.loads(Path(args.diff).read_text(encoding="utf-8"))
    else:
        client = StagingClient(args.staging_url)
        messages = messages_from_run(args.run)
        extracted = client.extract(messages)
        diff = extracted.get("diff") or {}
        print(json.dumps({"session": extracted.get("session_id"), "archive": extracted.get("archive_uri")}))

    store = MemoryStore(args.store)
    records = candidates_from_diff(diff, args.scope, store)
    print(
        json.dumps(
            {
                "candidates": len(records),
                "records": [row["result"].get("record") for row in records],
            },
            ensure_ascii=False,
            indent=2,
        )[:8000]
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
