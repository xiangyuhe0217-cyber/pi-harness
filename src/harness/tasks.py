from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Task:
    id: str
    goal: str
    workspace: Path
    provider: str = "litellm"
    model: str = "deepseek-chat"
    policy: str = "policies/p1.json"
    scope: str = "default"
    append_prompt: str = ""
    use_memory: bool = False
    timeout_s: int = 180
    context_window: int = 131072
    max_steps: int = 20
    max_tokens: int = 50000
    max_cost_usd: float = 0.02
    fast_steps: int = 5
    fast_seconds: float = 10.0
    fast_cost_usd: float = 0.001
    no_builtin_tools: bool = False
    mcp_only: bool = False
    kind: str = "task"
    success: dict[str, Any] = field(default_factory=dict)
    expect: dict[str, Any] = field(default_factory=dict)


def load_task(path: Path, root: Path) -> Task:
    data = json.loads(path.read_text(encoding="utf-8"))
    workspace = (root / data["workspace"]).resolve()
    if not workspace.is_dir():
        raise FileNotFoundError(f"workspace not found: {workspace}")
    return Task(
        id=str(data["id"]),
        goal=str(data["goal"]),
        workspace=workspace,
        provider=str(data.get("provider", "litellm")),
        model=str(data.get("model", "deepseek-chat")),
        policy=str(data.get("policy", "policies/p1.json")),
        scope=str(data.get("scope", "default")),
        append_prompt=str(data.get("append_prompt", "")),
        use_memory=bool(data.get("use_memory", False)),
        timeout_s=int(data.get("timeout_s", 180)),
        context_window=int(data.get("context_window", 131072)),
        max_steps=int(data.get("max_steps", 20)),
        max_tokens=int(data.get("max_tokens", 50000)),
        max_cost_usd=float(data.get("max_cost_usd", 0.02)),
        fast_steps=int(data.get("fast_steps", 5)),
        fast_seconds=float(data.get("fast_seconds", 10.0)),
        fast_cost_usd=float(data.get("fast_cost_usd", 0.001)),
        no_builtin_tools=bool(data.get("no_builtin_tools", False)),
        mcp_only=bool(data.get("mcp_only", False)),
        kind=str(data.get("kind", "task")),
        success=dict(data.get("success") or {}),
        expect=dict(data.get("expect") or {}),
    )
