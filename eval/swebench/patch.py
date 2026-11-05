from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


def _git(args: list[str], cwd: Path) -> str:
    # Use files instead of pipes: this also works in restricted sandboxes.
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


def reset_repo(repo: Path, base_commit: str) -> None:
    _git(["reset", "--hard", base_commit], repo)
    _git(["clean", "-fdx"], repo)


def extract_patch(workspace: str | Path) -> str:
    """Extract a SWE-bench-style patch from a post-run repository.

    `git add -N` makes new files visible to `git diff`; Harness's .pi directory
    and Python caches are excluded from the patch.
    """
    workspace = Path(workspace).resolve()
    if not (workspace / ".git").exists():
        raise RuntimeError(f"not a git repository: {workspace}")

    _git(["add", "-N", "--", "."], workspace)
    patch = _git(
        [
            "diff",
            "--binary",
            "--",
            ".",
            ":(exclude).pi",
            ":(exclude)**/__pycache__/**",
        ],
        workspace,
    )
    return patch


def has_changes(workspace: str | Path) -> bool:
    workspace = Path(workspace).resolve()
    status = _git(["status", "--porcelain"], workspace)
    return bool(status.strip())
