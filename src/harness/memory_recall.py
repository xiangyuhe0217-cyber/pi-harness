from __future__ import annotations

from typing import Any

from .openviking import OpenVikingClient


def format_recall(payload: dict[str, Any], max_chars: int = 2000) -> str:
    rendered = str(payload.get("rendered") or "").strip()
    if rendered:
        return rendered[:max_chars]
    lines = ["<long_term_memory>"]
    for item in payload.get("items") or []:
        text = item.get("content") or item.get("text") or item.get("abstract") or item.get("uri") or ""
        lines.append(f"- {str(text)[:300]}")
    lines.append("</long_term_memory>")
    return "\n".join(lines)[:max_chars]


def recall_block(
    client: OpenVikingClient,
    scope: str,
    query: str,
    limit: int = 5,
    token_budget: int = 2000,
) -> dict[str, Any]:
    try:
        payload = client.search_context(query, scope=scope, limit=limit, token_budget=token_budget)
        return {
            "ok": True,
            "block": format_recall(payload),
            "items": payload.get("items") or [],
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "block": "", "items": [], "error": str(exc)}
