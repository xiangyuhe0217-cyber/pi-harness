from __future__ import annotations

import argparse
import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

DEFAULT_DATASET = "princeton-nlp/SWE-bench_Lite"
DEFAULT_SPLIT = "test"


@dataclass(frozen=True)
class Instance:
    instance_id: str
    repo: str
    base_commit: str
    problem_statement: str
    version: str = ""
    environment_setup_commit: str = ""

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Instance":
        return cls(
            instance_id=str(value["instance_id"]),
            repo=str(value["repo"]),
            base_commit=str(value["base_commit"]),
            problem_statement=str(value.get("problem_statement") or ""),
            version=str(value.get("version") or ""),
            environment_setup_commit=str(value.get("environment_setup_commit") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_manifest(path: str | Path) -> list[Instance]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = data["instances"] if isinstance(data, dict) else data
    return [Instance.from_dict(row) for row in rows]


def write_manifest(
    path: str | Path,
    instances: list[Instance],
    metadata: dict[str, Any] | None = None,
) -> None:
    payload = {
        "dataset": (metadata or {}).get("dataset", DEFAULT_DATASET),
        "revision": (metadata or {}).get("revision"),
        "split": (metadata or {}).get("split", DEFAULT_SPLIT),
        "count": len(instances),
        "instances": [instance.to_dict() for instance in instances],
    }
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def select_instances(
    instances: list[Instance],
    count: int = 12,
    seed: int = 0,
) -> list[Instance]:
    """Deterministic round-robin across repos, then inside each repo."""
    rng = random.Random(seed)
    by_repo: dict[str, list[Instance]] = {}
    for instance in sorted(instances, key=lambda item: (item.repo, item.instance_id)):
        by_repo.setdefault(instance.repo, []).append(instance)
    for repo in by_repo:
        rng.shuffle(by_repo[repo])

    selected: list[Instance] = []
    offset = 0
    repos = sorted(by_repo)
    while len(selected) < count:
        added = False
        for repo in repos:
            bucket = by_repo[repo]
            if offset < len(bucket):
                selected.append(bucket[offset])
                added = True
                if len(selected) >= count:
                    break
        if not added:
            break
        offset += 1
    return selected


def fetch_instances(
    dataset: str = DEFAULT_DATASET,
    split: str = DEFAULT_SPLIT,
    revision: str | None = None,
) -> list[Instance]:
    """Download from HuggingFace via the optional `datasets` package."""
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise RuntimeError(
            "需要 `datasets`：pip install datasets；或直接提供 manifest.json"
        ) from exc

    kwargs = {"split": split}
    if revision:
        kwargs["revision"] = revision
    rows = load_dataset(dataset, **kwargs)
    return [Instance.from_dict(dict(row)) for row in rows]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a SWE-bench Lite subset manifest")
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--split", default=DEFAULT_SPLIT)
    parser.add_argument("--revision", default=None)
    parser.add_argument("--count", type=int, default=12)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", default="eval/swebench/manifest.json")
    parser.add_argument("--from-json", default=None, help="Use a local JSON list instead of HuggingFace")
    args = parser.parse_args(argv)

    if args.from_json:
        rows = json.loads(Path(args.from_json).read_text(encoding="utf-8"))
        instances = [Instance.from_dict(row) for row in rows]
    else:
        instances = fetch_instances(args.dataset, args.split, args.revision)

    selected = select_instances(instances, args.count, args.seed)
    if len(selected) < args.count:
        raise SystemExit(f"only {len(selected)} instances available, requested {args.count}")
    write_manifest(
        args.out,
        selected,
        {"dataset": args.dataset, "split": args.split, "revision": args.revision},
    )
    print(f"wrote {args.out}: {len(selected)} instances across {len({i.repo for i in selected})} repos")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
