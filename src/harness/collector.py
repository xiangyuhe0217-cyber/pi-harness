from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .events import StepEvent


def _ts(raw: Any) -> str:
    if isinstance(raw, (int, float)):
        return (
            datetime.fromtimestamp(raw / 1000, tz=timezone.utc)
            .astimezone()
            .isoformat(timespec="milliseconds")
        )
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds")


def collect(raw_path: Path, run_id: str) -> tuple[list[StepEvent], dict[str, Any]]:
    """把 pi 的 --mode json 输出归一成 StepEvent。"""

    events: list[StepEvent] = []
    step = 0
    tool_calls = 0
    blocked = 0
    tokens = 0
    cost = 0.0
    duration = 0

    for line in raw_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue

        kind = record.get("type")

        if kind == "message_end" and (record.get("message") or {}).get("role") == "assistant":
            message = record["message"]
            step += 1
            content = message.get("content") or []
            text = "".join(
                part.get("text", "")
                for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            )
            calls = [
                part
                for part in content
                if isinstance(part, dict) and part.get("type") == "toolCall"
            ]
            usage = message.get("usage") or {}
            cost_obj = usage.get("cost") or {}
            total_tokens = int(usage.get("totalTokens") or 0)
            total_cost = float(cost_obj.get("total") or 0)
            duration_ms = int(message.get("durationMs") or 0)
            tokens += total_tokens
            cost += total_cost
            duration += duration_ms
            events.append(
                StepEvent(
                    run_id=run_id,
                    seq=len(events) + 1,
                    step=step,
                    kind="model_call",
                    ts=_ts(message.get("timestamp")),
                    payload={
                        "content": text,
                        "tool_calls": calls,
                        "stop_reason": message.get("stopReason"),
                    },
                    metrics={
                        "tokens": total_tokens,
                        "input_tokens": int(usage.get("input") or 0),
                        "cache_read_tokens": int(usage.get("cacheRead") or 0),
                        "cost_usd": total_cost,
                        "duration_ms": duration_ms,
                    },
                )
            )

        elif kind == "tool_execution_start":
            tool_calls += 1
            events.append(
                StepEvent(
                    run_id=run_id,
                    seq=len(events) + 1,
                    step=step,
                    kind="tool_call",
                    ts=_ts(record.get("timestamp")),
                    tool=record.get("toolName"),
                    tool_call_id=record.get("toolCallId"),
                    payload={"args": record.get("args")},
                )
            )

        elif kind == "tool_execution_end":
            is_error = bool(record.get("isError"))
            result_text = json.dumps(record.get("result"), ensure_ascii=False)
            rule = None
            if "BLOCKED[" in result_text:
                rule = result_text.split("BLOCKED[", 1)[1].split("]", 1)[0]
                blocked += 1
            verdict = "blocked" if rule else ("error" if is_error else "ok")
            events.append(
                StepEvent(
                    run_id=run_id,
                    seq=len(events) + 1,
                    step=step,
                    kind="tool_result",
                    ts=_ts(record.get("timestamp")),
                    tool=record.get("toolName"),
                    tool_call_id=record.get("toolCallId"),
                    payload={"is_error": is_error, "result": record.get("result")},
                    verdict=verdict,
                    evidence={"rule": rule} if rule else {},
                )
            )

    summary = {
        "steps": step,
        "tool_calls": tool_calls,
        "blocked": blocked,
        "tokens": tokens,
        "cost_usd": round(cost, 6),
        "duration_ms": duration,
        "events": len(events),
    }
    return events, summary
