from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from .guards import decide
from .policy import load_policy

KNOWN_TOOLS = {"fs_read", "fs_write", "fs_list", "shell_exec"}
POLICY_RULE_PREFIXES = (
    "exec.",
    "injection.",
    "secret.",
    "path.outside_workspace",
    "path.sensitive",
    "write.",
)


def _normalize_tool(tool: str) -> str:
    prefix = "mcp__harness__"
    if tool.startswith(prefix):
        return tool[len(prefix) :]
    return tool


def _args_valid(tool: str, args: dict[str, Any]) -> bool:
    if tool == "shell_exec":
        return "command" in args
    if tool == "fs_write":
        return "path" in args and "content" in args
    if tool in {"fs_read", "fs_list"}:
        return "path" in args
    return False


def replay_run(run_dir: str | Path, policy_path: str | Path) -> dict[str, Any]:
    """Re-evaluate recorded tool calls under a new policy, without calling the model."""

    run_dir = Path(run_dir).resolve()
    events = []
    events_path = run_dir / "events.jsonl"
    for line in events_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    calls = [event for event in events if event.get("kind") == "tool_call"]
    results = {
        event.get("tool_call_id"): event
        for event in events
        if event.get("kind") == "tool_result"
    }

    workspace = run_dir / "workspace"
    policy = load_policy(policy_path)
    counts: Counter[str] = Counter()
    rows: list[dict[str, Any]] = []

    for call in calls:
        tool = _normalize_tool(call.get("tool") or "")
        if tool not in KNOWN_TOOLS:
            continue
        call_id = call.get("tool_call_id")
        old = results.get(call_id) or {}
        old_rule = (old.get("evidence") or {}).get("rule")
        if old.get("verdict") == "blocked":
            old_decision = (
                "block"
                if old_rule and old_rule.startswith(POLICY_RULE_PREFIXES)
                else "error"
            )
        else:
            old_decision = "allow" if old else "none"
        args = (call.get("payload") or {}).get("args") or {}
        if not _args_valid(tool, args):
            continue
        try:
            decision, new_rule = decide(workspace, tool, args, policy)
        except Exception as exc:  # noqa: BLE001
            decision, new_rule = "block", f"replay.error:{type(exc).__name__}"
        new_decision = "block" if decision == "block" else "allow"
        counts[f"{old_decision}->{new_decision}"] += 1
        rows.append(
            {
                "tool": tool,
                "old": old_decision,
                "new": new_decision,
                "old_rule": old_rule,
                "new_rule": new_rule,
                "args": json.dumps(args, ensure_ascii=False)[:200],
            }
        )

    lines = [
        f"# Replay: {policy.version}",
        "",
        f"- run: `{run_dir}`",
        f"- calls: {len(rows)}",
        "- transitions: " + ", ".join(f"{key}={value}" for key, value in counts.items()),
        "",
        "| tool | old | new | old_rule | new_rule | args |",
        "|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['tool']} | {row['old']} | {row['new']} | {row['old_rule']} | "
            f"{row['new_rule']} | {row['args']} |"
        )
    lines.append("")
    return {
        "policy": policy.version,
        "counts": dict(counts),
        "rows": rows,
        "markdown": "\n".join(lines),
    }
