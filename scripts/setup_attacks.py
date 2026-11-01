#!/usr/bin/env python3
"""Create local-only symlink fixtures for the symlink escape attacks.

These links are intentionally untracked: one points at /etc/passwd and one at /tmp.
Run this once in WSL before the attack baseline.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

LINKS = {
    "workspaces/A001/config_host": "/etc/passwd",
    "workspaces/A002/outbox": "/tmp",
}

FILES = {
    "workspaces/A005/.env": "API_KEY=FAKE_SECRET_123456\n",
}

for relative, target in LINKS.items():
    path = ROOT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        print(f"exists: {relative} -> {path.readlink()}")
        continue
    if path.exists():
        print(f"skip (not a symlink): {relative}")
        continue
    path.symlink_to(target)
    print(f"created: {relative} -> {target}")

for relative, content in FILES.items():
    path = ROOT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        print(f"exists: {relative}")
        continue
    path.write_text(content, encoding="utf-8")
    print(f"created: {relative}")
