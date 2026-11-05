from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any

DEFAULT_TARGET = "viking://~/memories"
HARNESS_ROOT = "viking://~/memories/harness"


def scope_slug(scope: str) -> str:
    slug = re.sub(r"[^a-z0-9._-]+", "-", (scope or "default").lower()).strip("-")
    return slug or "default"


def memory_uri(scope: str, record_id: str) -> str:
    safe_id = re.sub(r"[^a-zA-Z0-9_.-]+", "-", record_id).strip("-") or "memory"
    return f"{HARNESS_ROOT}/{scope_slug(scope)}/{safe_id}.md"


def memory_content(record: dict[str, Any]) -> str:
    return "\n".join(
        [
            "---",
            f"harness_id: {record.get('id', '')}",
            f"scope: {record.get('scope', '')}",
            f"kind: {record.get('kind', '')}",
            f"key: {record.get('key', '')}",
            f"source: {record.get('source', '')}",
            f"confidence: {record.get('confidence', '')}",
            f"created_at: {record.get('created_at', '')}",
            "---",
            "",
            f"# {record.get('kind', 'memory')}: {record.get('key') or record.get('id', '')}",
            "",
            str(record.get("text", "")),
            "",
        ]
    )


class OpenVikingClient:
    """OpenViking adapter: health, memory recall, memory write.

    Write mapping:
    - scope `repo:demo` -> `viking://~/memories/harness/repo-demo/<id>.md`
    - tags: `harness=memory`, `scope=<slug>`, `kind=<kind>`
    """

    def __init__(self, url: str | None = None, api_key: str | None = None) -> None:
        self.url = (url or os.environ.get("OPENVIKING_URL") or "").rstrip("/")
        self.api_key = api_key or os.environ.get("OPENVIKING_API_KEY") or ""

    @property
    def configured(self) -> bool:
        return bool(self.url)

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        if not self.url:
            raise RuntimeError("OPENVIKING_URL is not configured")
        data = None
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(self.url + path, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=4) as response:
            return json.loads(response.read().decode("utf-8") or "{}")

    def health(self) -> dict[str, Any]:
        if not self.configured:
            return {"configured": False, "ok": False, "url": "", "error": "not configured"}
        try:
            payload = self._request("GET", "/health")
            return {"configured": True, "ok": True, "url": self.url, "payload": payload}
        except Exception as exc:  # noqa: BLE001
            return {"configured": True, "ok": False, "url": self.url, "error": str(exc)}

    def write_memory(self, record: dict[str, Any], wait: bool = True) -> dict[str, Any]:
        scope = str(record.get("scope") or "default")
        uri = memory_uri(scope, str(record.get("id") or "memory"))
        tags = [
            "harness=memory",
            f"scope={scope_slug(scope)}",
            f"kind={re.sub(r'[^a-z0-9_-]+', '-', str(record.get('kind', 'fact')).lower())}",
        ]
        result = self._request(
            "POST",
            "/api/v1/content/write",
            {
                "uri": uri,
                "content": memory_content(record),
                "mode": "replace",
                "tags": tags,
                "tag_mode": "replace",
                "wait": bool(wait),
            },
        )
        return {"ok": True, "uri": uri, "tags": tags, "response": result}

    def search(self, query: str, limit: int = 5, scope: str | None = None) -> list[dict[str, Any]]:
        if not query.strip():
            return []
        target = f"{HARNESS_ROOT}/{scope_slug(scope)}" if scope else HARNESS_ROOT
        payload = self._request(
            "POST",
            "/api/v1/search/find",
            {
                "query": query,
                "limit": int(limit),
                "target_uri": target,
                "context_type": ["memory"],
                "read_content": True,
            },
        )
        result = payload.get("result") or {}
        records: list[dict[str, Any]] = []
        for group in ("memories", "resources", "skills"):
            for item in result.get(group) or []:
                text = (
                    item.get("content")
                    or item.get("abstract")
                    or item.get("overview")
                    or item.get("uri")
                    or ""
                )
                records.append(
                    {
                        "id": item.get("uri", ""),
                        "text": text,
                        "score": item.get("score"),
                        "kind": item.get("context_type") or group,
                        "source": "openviking",
                    }
                )
        return records[:limit]

    def search_context(
        self,
        query: str,
        scope: str | None = None,
        limit: int = 5,
        token_budget: int = 2000,
    ) -> dict[str, Any]:
        """Recall assembled context via OpenViking search(mode="context")."""
        if not query.strip():
            return {"rendered": "", "items": []}
        target = f"{HARNESS_ROOT}/{scope_slug(scope)}" if scope else HARNESS_ROOT
        payload = self._request(
            "POST",
            "/api/v1/search/search",
            {
                "query": query,
                "mode": "context",
                "limit": int(limit),
                "target_uri": target,
                "context_type": ["memory"],
                "token_budget": int(token_budget),
            },
        )
        result = payload.get("result") or {}
        items = result.get("memories") or result.get("resources") or []
        rendered = result.get("rendered") or result.get("context") or ""
        return {"rendered": str(rendered), "items": items, "raw": payload}


def sync_record(client: OpenVikingClient, store: Any, record: dict[str, Any]) -> dict[str, Any]:
    if not client.configured:
        return {"ok": False, "error": "openviking_not_configured"}
    try:
        result = client.write_memory(record)
        store.mark_synced(record["id"], result["uri"], "ok")
        return result
    except Exception as exc:  # noqa: BLE001
        store.mark_synced(record["id"], "", "error", str(exc))
        return {"ok": False, "error": str(exc)}
