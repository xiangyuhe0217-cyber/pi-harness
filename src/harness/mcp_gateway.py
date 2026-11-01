#!/usr/bin/env python3
"""Minimal MCP stdio gateway with path/command/injection guards."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.guards import (  # noqa: E402
    Blocked,
    check_command,
    check_read,
    check_write,
    normalize_command,
    scan_injection,
    scan_secret,
)
from harness.memory import MemoryStore  # noqa: E402
from harness.policy import load_policy  # noqa: E402

WORKSPACE = Path(os.environ.get("HARNESS_WORKSPACE", os.getcwd())).resolve()
AUDIT = Path(os.environ.get("HARNESS_AUDIT", "/tmp/harness-gateway-audit.jsonl"))
POLICY = load_policy(os.environ.get("HARNESS_POLICY"))
MEMORY_PATH = os.environ.get("HARNESS_MEMORY")
MEMORY = MemoryStore(MEMORY_PATH) if MEMORY_PATH else None
MEMORY_SCOPE = os.environ.get("HARNESS_MEMORY_SCOPE", "default")


def audit(tool: str, args: dict, decision: str, rule: str | None = None) -> None:
    try:
        AUDIT.parent.mkdir(parents=True, exist_ok=True)
        with AUDIT.open("a", encoding="utf-8") as fh:
            fh.write(
                json.dumps(
                    {"ts": time.time(), "tool": tool, "args": args, "decision": decision, "rule": rule, "policy": POLICY.version},
                    ensure_ascii=False,
                )
                + "\n"
            )
    except Exception:
        pass


def send(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def tool_defs() -> list[dict]:
    return [
        {
            "name": "fs_read",
            "description": "Read a UTF-8 text file inside the workspace.",
            "inputSchema": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
        {
            "name": "fs_write",
            "description": "Write UTF-8 text to a file inside the workspace.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
        {
            "name": "fs_list",
            "description": "List a directory inside the workspace.",
            "inputSchema": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
            },
        },
        {
            "name": "shell_exec",
            "description": "Run an allowlisted command inside the workspace (no pipes or redirects).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "timeout_s": {"type": "number"},
                },
                "required": ["command"],
            },
        },
        {
            "name": "mem_search",
            "description": "Search long-term memory for relevant facts.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "top_k": {"type": "number"},
                },
                "required": ["query"],
            },
        },
        {
            "name": "mem_write",
            "description": "Write a long-term memory candidate; it may be quarantined or blocked by policy.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "kind": {"type": "string"},
                    "key": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["text"],
            },
        },
    ]


def _env() -> dict[str, str]:
    blocked = ("KEY", "TOKEN", "SECRET", "PASSWORD")
    return {key: value for key, value in os.environ.items() if not any(part in key.upper() for part in blocked)}


def call_tool(name: str, args: dict) -> dict:
    try:
        if name == "fs_read":
            path = check_read(WORKSPACE, str(args["path"]), POLICY)
            text = path.read_text(encoding="utf-8", errors="replace")
            scan_injection(text, POLICY)
            scan_secret(text, POLICY)
            audit(name, args, "allow")
            return {"content": [{"type": "text", "text": text}], "isError": False}

        if name == "fs_write":
            path = check_write(WORKSPACE, str(args["path"]), str(args["content"]), POLICY)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(str(args["content"]), encoding="utf-8")
            audit(name, args, "allow")
            return {
                "content": [{"type": "text", "text": f"wrote {path.relative_to(WORKSPACE)}"}],
                "isError": False,
            }

        if name == "fs_list":
            path = check_read(WORKSPACE, str(args.get("path", ".")), POLICY)
            if not path.is_dir():
                raise Blocked("path.not_directory", f"{path} is not a directory")
            entries = [
                f"{item.name}/" if item.is_dir() else item.name
                for item in sorted(path.iterdir())
            ]
            audit(name, args, "allow")
            return {"content": [{"type": "text", "text": "\n".join(entries)}], "isError": False}

        if name == "shell_exec":
            command = normalize_command(str(args["command"]), POLICY)
            parts = check_command(WORKSPACE, command, POLICY)
            timeout = float(args.get("timeout_s") or 30)
            completed = subprocess.run(
                parts,
                cwd=WORKSPACE,
                capture_output=True,
                text=True,
                timeout=max(1.0, min(timeout, 60.0)),
                env=_env(),
            )
            output = (completed.stdout + completed.stderr)[-20_000:]
            scan_injection(output, POLICY)
            scan_secret(output, POLICY)
            audit(name, args, "allow")
            return {
                "content": [{"type": "text", "text": output or f"(exit {completed.returncode})"}],
                "isError": completed.returncode != 0,
            }

        if name == "mem_search":
            if MEMORY is None:
                raise Blocked("memory.not_configured", "memory store is not configured")
            records = MEMORY.search(
                MEMORY_SCOPE, str(args.get("query", "")), int(args.get("top_k", 5))
            )
            audit(name, args, "allow")
            text = "\n".join(
                f"{record['id']} | {record['kind']} | {record['key']} | {record['text']}"
                for record in records
            )
            return {"content": [{"type": "text", "text": text or "(empty)"}], "isError": False}

        if name == "mem_write":
            if MEMORY is None:
                raise Blocked("memory.not_configured", "memory store is not configured")
            result = MEMORY.add(
                scope=MEMORY_SCOPE,
                kind=str(args.get("kind", "fact")),
                key=str(args.get("key", "")),
                text=str(args.get("text", "")),
                source="agent",
                confidence=float(args.get("confidence", 0.5)),
            )
            if result["status"] == "block":
                audit(name, args, "block", result.get("rule"))
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": f"BLOCKED[{result.get('rule')}] memory write blocked",
                        }
                    ],
                    "isError": True,
                }
            if result["status"] == "quarantine":
                audit(name, args, "quarantine", result.get("rule"))
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": f"QUARANTINED[{result.get('rule')}] stored but not active",
                        }
                    ],
                    "isError": False,
                }
            audit(name, args, "allow")
            record = result.get("record") or {}
            return {
                "content": [
                    {"type": "text", "text": f"MEMORY_WRITTEN {record.get('id', '')}"}
                ],
                "isError": False,
            }

        return {"content": [{"type": "text", "text": f"unknown tool: {name}"}], "isError": True}

    except Blocked as exc:
        audit(name, args, "block", exc.rule)
        return {
            "content": [{"type": "text", "text": f"BLOCKED[{exc.rule}] {exc}"}],
            "isError": True,
        }
    except Exception as exc:  # noqa: BLE001
        audit(name, args, "error", type(exc).__name__)
        return {
            "content": [{"type": "text", "text": f"ERROR {type(exc).__name__}: {exc}"}],
            "isError": True,
        }


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = message.get("method")
        message_id = message.get("id")

        if method == "initialize":
            send(
                {
                    "jsonrpc": "2.0",
                    "id": message_id,
                    "result": {
                        "protocolVersion": (message.get("params") or {}).get(
                            "protocolVersion", "2024-11-05"
                        ),
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "harness-gateway", "version": "0.1.0"},
                    },
                }
            )
        elif method == "notifications/initialized":
            continue
        elif method == "tools/list":
            send({"jsonrpc": "2.0", "id": message_id, "result": {"tools": tool_defs()}})
        elif method == "tools/call":
            params = message.get("params") or {}
            result = call_tool(str(params.get("name")), dict(params.get("arguments") or {}))
            send({"jsonrpc": "2.0", "id": message_id, "result": result})
        elif method == "ping":
            send({"jsonrpc": "2.0", "id": message_id, "result": {}})
        elif message_id is not None:
            send(
                {
                    "jsonrpc": "2.0",
                    "id": message_id,
                    "error": {"code": -32601, "message": f"method not found: {method}"},
                }
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
