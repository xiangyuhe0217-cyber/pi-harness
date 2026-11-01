from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from harness.collector import collect  # noqa: E402
from harness.events import write_events  # noqa: E402
from harness.runner import find_pi  # noqa: E402

GATEWAY = ROOT / "src" / "harness" / "mcp_gateway.py"
SEED = ROOT / "workspaces" / "chat"
CHAT_ROOT = ROOT / "runs" / "chat"
POLICY = ROOT / "policies" / "p1.json"

SYSTEM_PROMPT = (
    "You are a helpful coding assistant inside a sandboxed Harness. "
    "Use tools to inspect or edit the chat workspace. Be concise. "
    "Never claim an action you did not perform. If a tool call is blocked by policy, "
    "explain it and ask for a safer alternative."
)


class ChatRunner:
    def __init__(self) -> None:
        CHAT_ROOT.mkdir(parents=True, exist_ok=True)

    def _dir(self, session_id: str) -> Path:
        safe = "".join(ch for ch in session_id if ch.isalnum() or ch in "-_")[:64]
        if not safe:
            raise ValueError("invalid session id")
        return CHAT_ROOT / safe

    def create(self) -> dict[str, Any]:
        session_id = uuid.uuid4().hex[:10]
        run_dir = self._dir(session_id)
        workspace = run_dir / "workspace"
        (run_dir / "pi-sessions").mkdir(parents=True, exist_ok=True)
        if SEED.is_dir():
            shutil.copytree(SEED, workspace)
        else:
            workspace.mkdir(parents=True, exist_ok=True)
        self._write_mcp(workspace, run_dir, session_id)
        (run_dir / "messages.json").write_text("[]", encoding="utf-8")
        return {"session_id": session_id, "workspace": str(workspace)}

    def _write_mcp(self, workspace: Path, run_dir: Path, session_id: str) -> None:
        pi_dir = workspace / ".pi"
        pi_dir.mkdir(parents=True, exist_ok=True)
        config = {
            "mcpServers": {
                "harness": {
                    "command": sys.executable,
                    "args": [str(GATEWAY)],
                    "env": {
                        "HARNESS_WORKSPACE": str(workspace.resolve()),
                        "HARNESS_AUDIT": str(run_dir / "gateway_audit.jsonl"),
                        "HARNESS_POLICY": str(POLICY),
                        "HARNESS_MEMORY": str(ROOT / "memory" / "store.json"),
                        "HARNESS_MEMORY_SCOPE": f"chat:{session_id}",
                    },
                }
            }
        }
        (pi_dir / "mcp.json").write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

    def _messages_path(self, session_id: str) -> Path:
        return self._dir(session_id) / "messages.json"

    def history(self, session_id: str) -> list[dict[str, Any]]:
        path = self._messages_path(session_id)
        if not path.exists():
            raise KeyError(session_id)
        return json.loads(path.read_text(encoding="utf-8") or "[]")

    def _save(self, session_id: str, messages: list[dict[str, Any]]) -> None:
        self._messages_path(session_id).write_text(
            json.dumps(messages, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    @staticmethod
    def _reply_text(raw: str) -> str:
        text = ""
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") not in {"message_end", "turn_end"}:
                continue
            message = event.get("message") or {}
            if message.get("role") != "assistant":
                continue
            parts = [
                block.get("text", "")
                for block in (message.get("content") or [])
                if block.get("type") == "text"
            ]
            if parts:
                text = "".join(parts).strip()
        return text

    def send(self, session_id: str, message: str) -> dict[str, Any]:
        run_dir = self._dir(session_id)
        if not (run_dir / "messages.json").exists():
            raise KeyError(session_id)
        workspace = run_dir / "workspace"
        session_dir = run_dir / "pi-sessions"
        session_dir.mkdir(parents=True, exist_ok=True)
        self._write_mcp(workspace, run_dir, session_id)

        messages = self.history(session_id)
        messages.append(
            {
                "role": "user",
                "text": message,
                "at": datetime.now().isoformat(timespec="seconds"),
            }
        )
        self._save(session_id, messages)

        session_files = sorted(session_dir.rglob("*.jsonl"))
        command = [
            find_pi(),
            "--mode",
            "json",
            "--provider",
            "litellm",
            "--model",
            "deepseek-chat",
            "--no-builtin-tools",
            "--approve",
        ]
        if session_files:
            command += ["--session", str(session_files[-1])]
        else:
            command += ["--session-dir", str(session_dir), "--append-system-prompt", SYSTEM_PROMPT]
        command += ["-p", message]

        started = time.time()
        raw_path = run_dir / f"raw-{int(started)}.jsonl"
        stderr = ""
        timed_out = False
        exit_code = 0
        try:
            completed = subprocess.run(
                command,
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=120,
            )
            raw = completed.stdout or ""
            stderr = completed.stderr or ""
            exit_code = completed.returncode
        except subprocess.TimeoutExpired as exc:
            raw = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
            stderr = f"chat timed out after 120s"
            timed_out = True
            exit_code = -1
        raw_path.write_text(raw, encoding="utf-8")
        (run_dir / "stderr.log").write_text(stderr, encoding="utf-8")

        events, summary = collect(raw_path, f"chat-{session_id}")
        write_events(events, run_dir / "events.jsonl")
        blocked = sum(1 for event in events if event.verdict == "blocked")
        tools = [event.tool for event in events if event.kind == "tool_call" and event.tool]
        reply = self._reply_text(raw) or (
            "运行超时了。" if timed_out else "我没有生成可展示的回复。"
        )
        if timed_out:
            reply = "这次响应超时了，请把问题拆小一点再试。"

        messages.append(
            {
                "role": "assistant",
                "text": reply,
                "at": datetime.now().isoformat(timespec="seconds"),
                "tools": tools,
                "blocked": blocked,
                "timed_out": timed_out,
                "exit_code": exit_code,
                "run_dir": str(run_dir),
                "raw": str(raw_path),
                "summary": summary,
            }
        )
        self._save(session_id, messages)
        return {
            "session_id": session_id,
            "reply": reply,
            "tools": tools,
            "blocked": blocked,
            "timed_out": timed_out,
            "run_dir": str(run_dir),
            "messages": messages,
        }
