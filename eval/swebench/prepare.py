from __future__ import annotations

import argparse
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
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


def _snapshot(repo: str, base_commit: str, target: Path) -> None:
    """Download a commit tarball; avoids fragile git fetch on restricted networks."""
    proxy = "https://gh-proxy.com/"
    url = f"{proxy}https://github.com/{repo}/archive/{base_commit}.tar.gz"
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        archive = tmp_path / "repo.tar.gz"
        request = urllib.request.Request(url, headers={"User-Agent": "pi-harness-eval"})
        with urllib.request.urlopen(request, timeout=300) as response:
            archive.write_bytes(response.read())
        extract_root = tmp_path / "extract"
        extract_root.mkdir()
        with tarfile.open(archive, "r:gz") as tar:
            tar.extractall(extract_root, filter="data")
        children = [item for item in extract_root.iterdir() if item.is_dir()]
        if len(children) != 1:
            raise RuntimeError(f"unexpected archive layout for {repo}")
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(children[0], target, symlinks=True)
    _git(["init"], target)
    _git(["config", "user.email", "harness@example.invalid"], target)
    _git(["config", "user.name", "harness"], target)
    _git(["add", "-A"], target)
    _git(["commit", "-m", "swe-bench base snapshot"], target)


def ensure_repo(repo: str, base_commit: str, cache_root: Path) -> Path:
    cache_root.mkdir(parents=True, exist_ok=True)
    target = cache_root / _slug(repo)
    try:
        _snapshot(repo, base_commit, target)
        return target
    except Exception:
        # Fallback: shallow fetch if the archive endpoint is blocked.
        pass
    url = f"https://github.com/{repo}.git"
    if not (target / ".git").exists():
        if target.exists():
            shutil.rmtree(target)
        _git(["init", str(target)], cache_root)
        _git(["remote", "add", "origin", url], target)
    try:
        _git(["fetch", "--depth", "1", "--no-tags", "origin", base_commit], target)
    except RuntimeError:
        _git(["fetch", "--no-tags", "origin", base_commit], target)
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
    reset_repo(target, "HEAD")
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
