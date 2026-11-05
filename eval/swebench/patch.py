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


def _is_test_path(path: str) -> bool:
    parts = Path(path).parts
    name = Path(path).name
    return (
        name.startswith("test_")
        or name.endswith("_test.py")
        or "tests" in parts
        or "test" in parts
    )


def strip_test_sections(patch: str) -> str:
    sections: list[str] = []
    current: list[str] = []
    for line in patch.splitlines(keepends=True):
        if line.startswith("diff --git "):
            if current:
                sections.append("".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        sections.append("".join(current))
    kept: list[str] = []
    for section in sections:
        header = section.splitlines()[0] if section.splitlines() else ""
        paths = [piece[2:] for piece in header.split() if piece.startswith(("a/", "b/"))]
        if any(_is_test_path(path) for path in paths):
            continue
        kept.append(section)
    return "".join(kept)


def extract_patch(workspace: str | Path, exclude_tests: bool = False) -> str:
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
    return strip_test_sections(patch) if exclude_tests else patch


def has_changes(workspace: str | Path) -> bool:
    workspace = Path(workspace).resolve()
    status = _git(["status", "--porcelain"], workspace)
    return bool(status.strip())
