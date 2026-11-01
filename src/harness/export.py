from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def _ns(ts: str) -> int:
    try:
        return int(datetime.fromisoformat(ts).timestamp() * 1_000_000_000)
    except Exception:
        return 0


def _attr(key: str, value: Any) -> dict[str, Any]:
    if isinstance(value, bool):
        return {"key": key, "value": {"boolValue": value}}
    if isinstance(value, int):
        return {"key": key, "value": {"intValue": str(value)}}
    if isinstance(value, float):
        return {"key": key, "value": {"doubleValue": value}}
    return {"key": key, "value": {"stringValue": str(value)}}


def export_otel(run_dir: str | Path, out_path: str | Path | None = None) -> Path:
    """Export StepEvents as an OTLP-style JSON trace (Langfuse/OTel compatible shape)."""

    run_dir = Path(run_dir).resolve()
    events = []
    for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    run_id = (events[0].get("run_id") if events else run_dir.name) or run_dir.name
    trace_id = hashlib.sha256(run_id.encode("utf-8")).hexdigest()[:32]
    spans: list[dict[str, Any]] = []
    model_spans: dict[int, str] = {}
    tool_spans: dict[str, str] = {}

    for index, event in enumerate(events, start=1):
        seq = int(event.get("seq") or index)
        span_id = f"{seq:016x}"[-16:]
        step = int(event.get("step") or 0)
        kind = event.get("kind", "event")

        if kind == "model_call":
            model_spans[step] = span_id
            parent = ""
        elif kind == "tool_call":
            parent = model_spans.get(step, "")
            if event.get("tool_call_id"):
                tool_spans[str(event["tool_call_id"])] = span_id
        elif kind == "tool_result":
            parent = tool_spans.get(str(event.get("tool_call_id")), model_spans.get(step, ""))
        else:
            parent = model_spans.get(step, "")

        metrics = event.get("metrics") or {}
        payload = event.get("payload") or {}
        start = _ns(event.get("ts", ""))
        duration_ms = float(metrics.get("duration_ms") or 0)
        end = start + int(duration_ms * 1_000_000)

        attributes = [
            _attr("harness.kind", kind),
            _attr("harness.step", step),
            _attr("harness.verdict", event.get("verdict", "ok")),
        ]
        if event.get("tool"):
            attributes.append(_attr("harness.tool", event["tool"]))
        if event.get("tool_call_id"):
            attributes.append(_attr("harness.tool_call_id", event["tool_call_id"]))
        if metrics.get("tokens"):
            attributes.append(_attr("llm.token_count.total", int(metrics["tokens"])))
        if metrics.get("cost_usd"):
            attributes.append(_attr("llm.cost_usd", float(metrics["cost_usd"])))
        rule = (event.get("evidence") or {}).get("rule")
        if rule:
            attributes.append(_attr("harness.rule", rule))
        if payload.get("stop_reason"):
            attributes.append(_attr("llm.stop_reason", payload["stop_reason"]))

        spans.append(
            {
                "traceId": trace_id,
                "spanId": span_id,
                "parentSpanId": parent,
                "name": f"harness.{kind}",
                "kind": 1,
                "startTimeUnixNano": str(start),
                "endTimeUnixNano": str(end),
                "attributes": attributes,
            }
        )

    payload = {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        _attr("service.name", "harness"),
                        _attr("service.version", "0.1.0"),
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "harness", "version": "0.1.0"},
                        "spans": spans,
                    }
                ],
            }
        ]
    }

    out = Path(out_path) if out_path else run_dir / "otel.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out
