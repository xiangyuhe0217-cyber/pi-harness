from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

from .manifest import Instance, load_manifest
from .patch import reset_repo


def _git(args: list[str], cwd: Path) -> str:
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        completed = subprocess.run(
            ["git", *args],
            cwd=cwd,
            stdout=out,
            stderr=err,
            check=False,
        )
        out.seek(0)
        err.seek(0)
        stdout = out.read().decode("utf-8", errors="replace")
        stderr = err.read().decode("utf-8", errors="replace")
    if completed.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed in {cwd}: {stderr.strip()}"
        )
    return stdout


def _slug(value: str) -> str:
    return value.replace("/", "__").replace("\\", "__")


def ensure_repo(repo: str, base_commit: str, cache_root: Path) -> Path:
    """Clone once per SWE-bench repo and check out the instance base commit."""
    cache_root.mkdir(parents=True, exist_ok=True)
    target = cache_root / _slug(repo)
    if not target.exists():
        _git(
            ["clone", "--no-checkout", f"https://github.com/{repo}.git", str(target)],
            cache_root,
        )
    try:
        _git(["cat-file", "-e", f"{base_commit}^{{commit}}"], target)
    except RuntimeError:
        _git(["fetch", "origin", "--tags"], target)
    try:
        _git(["checkout", "--force", base_commit], target)
    except RuntimeError:
        _git(["fetch", "origin", base_commit], target)
        _git(["checkout", "--force", base_commit], target)
    _git(["clean", "-fdx"], target)
    return target


def prepare_instance(instance: Instance, cache_root: Path, work_root: Path) -> Path:
    source = ensure_repo(instance.repo, instance.base_commit, cache_root)
    target = work_root / "instances" / instance.instance_id
    if target.exists():
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, symlinks=True)
    reset_repo(target, instance.base_commit)
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare SWE-bench instance workspaces")
    parser.add_argument("--manifest", default="eval/swebench/manifest.json")
    parser.add_argument("--work", default="eval/work")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)

    instances = load_manifest(args.manifest)
    if args.limit:
        instances = instances[: args.limit]
    work_root = Path(args.work).resolve()
    cache_root = work_root / "repos"
    for index, instance in enumerate(instances, start=1):
        target = prepare_instance(instance, cache_root, work_root)
        print(f"[{index}/{len(instances)}] {instance.instance_id} -> {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
