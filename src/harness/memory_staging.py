from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from .memory import MemoryStore


class StagingClient:
    """OpenViking staging instance used only for session extraction.

    Main memory is the canonical store; this staging instance is disposable.
    """

    def __init__(self, base_url: str | None = None, api_key: str | None = None) -> None:
        self.base_url = (
            base_url or os.environ.get("OPENVIKING_STAGING_URL") or "http://127.0.0.1:1934"
        ).rstrip("/")
        self.api_key = api_key or os.environ.get("OPENVIKING_API_KEY") or ""

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        data = None
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            headers=headers,
            method=method,
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8") or "{}")

    def create_session(self, session_id: str | None = None) -> dict[str, Any]:
        payload = {"session_id": session_id} if session_id else {}
        result = self._request("POST", "/api/v1/sessions", payload)
        return result.get("result") or result

    def add_message(self, session_id: str, role: str, content: str) -> dict[str, Any]:
        result = self._request(
            "POST",
            f"/api/v1/sessions/{urllib.parse.quote(session_id)}/messages",
            {"role": role, "content": content},
        )
        return result.get("result") or result

    def commit(self, session_id: str, keep_recent_count: int = 0) -> dict[str, Any]:
        result = self._request(
            "POST",
            f"/api/v1/sessions/{urllib.parse.quote(session_id)}/commit",
            {"keep_recent_count": keep_recent_count},
        )
        return result.get("result") or result

    def get_task(self, task_id: str) -> dict[str, Any]:
        result = self._request("GET", f"/api/v1/tasks/{urllib.parse.quote(task_id)}")
        return result.get("result") or result

    def wait_task(self, task_id: str, timeout_s: int = 120) -> dict[str, Any]:
        deadline = time.time() + timeout_s
        last: dict[str, Any] = {}
        while time.time() < deadline:
            last = self.get_task(task_id)
            if last.get("status") in {"completed", "failed", "cancelled"}:
                return last
            time.sleep(1)
        return last

    def read_content(self, uri: str) -> str:
        query = urllib.parse.urlencode({"uri": uri})
        result = self._request("GET", f"/api/v1/content/read?{query}")
        return str((result.get("result") if isinstance(result, dict) else result) or "")

    def extract(self, messages: list[dict[str, str]], session_id: str | None = None) -> dict[str, Any]:
        session = self.create_session(session_id)
        sid = str(session["session_id"])
        for message in messages:
            self.add_message(sid, message["role"], message["content"])
        commit = self.commit(sid)
        if commit.get("status") == "skipped" or not commit.get("task_id"):
            return {"session_id": sid, "archive_uri": None, "diff": {}}
        task = self.wait_task(str(commit["task_id"]))
        archive_uri = commit.get("archive_uri")
        diff: dict[str, Any] = {}
        if archive_uri:
            raw = self.read_content(str(archive_uri).rstrip("/") + "/memory_diff.json")
            if raw:
                try:
                    diff = json.loads(raw)
                except json.JSONDecodeError:
                    diff = {}
        return {"session_id": sid, "archive_uri": archive_uri, "task": task, "diff": diff}


def messages_from_run(run_dir: str | Path) -> list[dict[str, str]]:
    run_dir = Path(run_dir).resolve()
    result_path = run_dir / "result.json"
    events_path = run_dir / "events.jsonl"
    result = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else {}
    messages: list[dict[str, str]] = [
        {"role": "user", "content": str(result.get("goal") or "")}
    ]
    if events_path.exists():
        for line in events_path.read_text(encoding="utf-8").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("kind") == "model_call":
                text = (event.get("payload") or {}).get("content") or ""
                if text:
                    messages.append({"role": "assistant", "content": str(text)[:4000]})
    return messages[-20:]


def candidates_from_diff(
    diff: dict[str, Any],
    scope: str,
    store: MemoryStore,
) -> list[dict[str, Any]]:
    """Convert OpenViking memory_diff into local quarantined candidates."""
    operations = (diff.get("operations") or {}) if isinstance(diff, dict) else {}
    records: list[dict[str, Any]] = []
    for key in ("adds", "updates"):
        for operation in operations.get(key) or []:
            uri = str(operation.get("uri") or "")
            if not uri:
                continue
            if store.find_by_source(uri):
                continue
            text = str(operation.get("after") or "").strip()
            if not text:
                continue
            text = text[:480]
            memory_type = str(operation.get("memory_type") or "fact")
            result = store.add(
                scope=scope,
                kind=memory_type,
                key=f"viking:{memory_type}:{hashlib.sha256(uri.encode()).hexdigest()[:12]}",
                text=text,
                source="agent",
                confidence=0.6,
                extra={"viking_source_uri": uri, "memory_type": memory_type},
            )
            records.append({"operation": operation, "result": result})
    return records
