from __future__ import annotations

import re
import shlex
from pathlib import Path
from typing import Any

from .policy import Policy


class Blocked(Exception):
    def __init__(self, rule: str, message: str) -> None:
        super().__init__(message)
        self.rule = rule


def resolve_path(workspace: Path, raw: str) -> Path:
    path = Path(raw).expanduser()
    candidate = path.resolve() if path.is_absolute() else (workspace / path).resolve()
    try:
        candidate.relative_to(workspace)
    except ValueError as exc:
        raise Blocked("path.outside_workspace", f"{candidate} is outside workspace") from exc
    return candidate


def _relative(workspace: Path, path: Path) -> str:
    return path.relative_to(workspace).as_posix()


def _sensitive(rel: str, policy: Policy) -> bool:
    if rel.startswith(".git/"):
        return True
    if rel == ".env" or rel.endswith("/.env"):
        return True
    return any(marker in rel for marker in policy.sensitive_markers if marker not in {".git/", ".env"})


def check_read(workspace: Path, raw: str, policy: Policy) -> Path:
    path = resolve_path(workspace, raw)
    rel = _relative(workspace, path)
    if _sensitive(rel, policy):
        raise Blocked("path.sensitive", f"reading {rel} is not allowed")
    return path


def check_write(workspace: Path, raw: str, content: str, policy: Policy) -> Path:
    path = resolve_path(workspace, raw)
    rel = _relative(workspace, path)
    if len(content.encode("utf-8")) > policy.max_write_bytes:
        raise Blocked("write.too_large", f"write exceeds {policy.max_write_bytes} bytes")
    if _sensitive(rel, policy):
        raise Blocked("path.sensitive", f"writing {rel} is not allowed")
    return path


def normalize_command(command: str, policy: Policy) -> str:
    if policy.allow_stderr_merge:
        command = command.replace("2>&1", "")
    return " ".join(command.split())


def check_command(workspace: Path, command: str, policy: Policy) -> list[str]:
    command = normalize_command(command, policy)
    if any(token in command for token in ["|", ";", "&&", ">", "<", "`", "$("]):
        raise Blocked("exec.shell_syntax", "shell operators are not allowed")

    parts = shlex.split(command)
    if not parts:
        raise Blocked("exec.empty", "empty command")

    binary = Path(parts[0]).name
    if binary not in policy.allowed_bin:
        raise Blocked("exec.binary_denied", f"{binary} is not allowed")

    if binary.startswith("python"):
        if "-c" in parts:
            raise Blocked("exec.inline_code", "python -c is not allowed")
        if any(arg.endswith(".py") for arg in parts[1:] if not arg.startswith("-")):
            raise Blocked("exec.script_execution", "running arbitrary .py scripts is not allowed")
        if "-m" in parts:
            index = parts.index("-m")
            module = parts[index + 1] if index + 1 < len(parts) else ""
            if module in policy.deny_modules:
                raise Blocked("exec.module_denied", f"module not allowed: {module}")

    for arg in parts[1:]:
        if arg.startswith("-"):
            continue
        path = Path(arg).expanduser()
        candidate = path.resolve() if path.is_absolute() else (workspace / path).resolve()
        try:
            candidate.relative_to(workspace)
        except ValueError as exc:
            raise Blocked("exec.path_outside", f"{candidate} is outside workspace") from exc

    for pattern in policy.deny_patterns:
        if pattern in command:
            raise Blocked("exec.pattern_denied", f"pattern not allowed: {pattern}")

    return parts


def scan_injection(text: str, policy: Policy) -> None:
    for pattern in policy.injection_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            raise Blocked("injection.detected", f"prompt injection pattern: {pattern}")


def scan_secret(text: str, policy: Policy) -> None:
    for pattern in policy.secret_patterns:
        if re.search(pattern, text):
            raise Blocked("secret.detected", "secret-like content detected")


def decide(
    workspace: Path, tool: str, args: dict[str, Any], policy: Policy
) -> tuple[str, str | None]:
    """Replay-friendly decision: allow/block + rule, without executing."""

    try:
        if tool == "fs_read":
            path = check_read(workspace, str(args.get("path", "")), policy)
            if path.is_file():
                text = path.read_text(encoding="utf-8", errors="replace")
                scan_injection(text, policy)
                scan_secret(text, policy)
        elif tool == "fs_list":
            check_read(workspace, str(args.get("path", ".")), policy)
        elif tool == "fs_write":
            check_write(workspace, str(args.get("path", "")), str(args.get("content", "")), policy)
        elif tool == "shell_exec":
            check_command(workspace, str(args.get("command", "")), policy)
        else:
            raise Blocked("tool.unknown", f"unknown tool: {tool}")
        return "allow", None
    except Blocked as exc:
        return "block", exc.rule
