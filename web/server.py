from __future__ import annotations

import json
import hmac
import mimetypes
import os
import re
import sys
import threading
import traceback
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from harness.memory import MemoryStore  # noqa: E402
from harness.memory_lesson import extract_lesson  # noqa: E402
from harness.openviking import OpenVikingClient, sync_record  # noqa: E402
from harness.runner import find_pi, run_task  # noqa: E402
from harness.tasks import load_task  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from chat import ChatRunner  # noqa: E402

STATIC = ROOT / "web" / "static"
RUNS = ROOT / "runs"
MEMORY = MemoryStore(ROOT / "memory" / "store.json")
OPENVIKING = OpenVikingClient()
CHAT = ChatRunner()
JOBS: dict[str, dict[str, Any]] = {}
JOBS_LOCK = threading.Lock()
RUNS_CACHE: dict[str, Any] = {"ts": 0.0, "items": []}
WEB_TOKEN = os.environ.get("HARNESS_WEB_TOKEN", "").strip()
RUN_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _catalog() -> dict[str, Any]:
    items = []
    for folder, kind in (("tasks", "task"), ("attacks", "attack"), ("demos", "demo")):
        for path in sorted((ROOT / folder).glob("*.json")):
            try:
                data = _read_json(path)
            except Exception:
                continue
            items.append(
                {
                    "id": str(data.get("id", path.stem)),
                    "kind": kind,
                    "path": str(path),
                    "goal": str(data.get("goal", "")),
                    "scope": str(data.get("scope", "default")),
                    "use_memory": bool(data.get("use_memory", False)),
                }
            )
    policies = sorted(path.name for path in (ROOT / "policies").glob("*.json"))
    return {
        "items": items,
        "policies": policies,
        "scopes": sorted(set(MEMORY.scopes()) | {"default"}),
    }


def _run_items(limit: int = 40) -> list[dict[str, Any]]:
    import time

    now = time.time()
    if RUNS_CACHE["items"] and now - RUNS_CACHE["ts"] < 4:
        return RUNS_CACHE["items"][:limit]
    candidates = list(RUNS.glob("*/result.json")) + list(RUNS.glob("*/*/result.json"))
    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    items = []
    for result_path in candidates[: max(limit * 2, 60)]:
        try:
            result = _read_json(result_path)
        except Exception:
            continue
        if not isinstance(result, dict):
            continue
        summary = result.get("summary") or {}
        items.append(
            {
                "run_id": result_path.parent.name,
                "task_id": result.get("task_id"),
                "kind": result.get("kind", "task"),
                "status": result.get("status"),
                "verdict": result.get("verdict"),
                "attribution": result.get("attribution"),
                "outcome": (result.get("outcome") or {}).get("primary"),
                "steps": summary.get("steps", 0),
                "tools": summary.get("tool_calls", 0),
                "tokens": summary.get("tokens", 0),
                "cost_usd": summary.get("cost_usd", 0),
                "duration_ms": summary.get("duration_ms", 0),
                "policy": result.get("policy"),
                "memory_scope": result.get("memory_scope"),
                "mtime": result_path.stat().st_mtime,
            }
        )
        if len(items) >= limit:
            break
    RUNS_CACHE["ts"] = now
    RUNS_CACHE["items"] = items
    return items[:limit]


def _find_run(run_id: str) -> Path | None:
    if not RUN_ID_RE.match(run_id):
        return None
    candidates = [RUNS / run_id, *RUNS.glob(f"*/{run_id}")]
    for path in candidates:
        if (path / "result.json").exists():
            return path
    return None


def _tail(path: Path, limit: int = 200) -> list[str]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return lines[-limit:]


def _run_detail(run_id: str) -> dict[str, Any]:
    run_dir = _find_run(run_id)
    if run_dir is None:
        raise KeyError(run_id)
    result = _read_json(run_dir / "result.json")
    report_path = run_dir / "report.md"
    return {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "result": result,
        "report": report_path.read_text(encoding="utf-8")[:20000] if report_path.exists() else "",
        "audit": _tail(run_dir / "gateway_audit.jsonl"),
        "events": _tail(run_dir / "events.jsonl"),
        "files": sorted(
            str(path.relative_to(run_dir / "workspace"))
            for path in (run_dir / "workspace").rglob("*")
            if path.is_file()
        )[:100],
    }


def _health() -> dict[str, Any]:
    litellm_ok = False
    litellm_error = ""
    try:
        with urllib.request.urlopen("http://127.0.0.1:4000/v1/models", timeout=1) as response:
            litellm_ok = response.status == 200
    except Exception as exc:  # noqa: BLE001
        litellm_error = str(exc)
    try:
        pi = find_pi()
        pi_ok = Path(pi).exists()
    except Exception as exc:  # noqa: BLE001
        pi = ""
        pi_ok = False
        litellm_error = litellm_error or str(exc)
    return {
        "litellm": {"ok": litellm_ok, "url": "http://127.0.0.1:4000", "error": litellm_error},
        "pi": {"ok": pi_ok, "path": pi},
        "openviking": OPENVIKING.health(),
        "memory": MEMORY.stats(),
        "runs": sum(1 for _ in RUNS.glob("*/result.json")) + sum(1 for _ in RUNS.glob("*/*/result.json")),
    }


def _start_job(payload: dict[str, Any]) -> dict[str, Any]:
    kind = str(payload.get("kind") or "task")
    item_id = str(payload.get("id") or "")
    item = next(
        (entry for entry in _catalog()["items"] if entry["kind"] == kind and entry["id"] == item_id),
        None,
    )
    if item is None:
        raise ValueError(f"unknown {kind}: {item_id}")
    policy = payload.get("policy") or None
    policy_arg = None
    if policy:
        policy_path = ROOT / "policies" / str(policy)
        if not policy_path.exists():
            raise ValueError(f"unknown policy: {policy}")
        policy_arg = str(policy_path)
    scope = str(payload.get("scope") or "") or None
    append_prompt = str(payload.get("append_prompt") or "") or None
    mcp_only = bool(payload.get("mcp_only", True))
    job_id = uuid.uuid4().hex[:12]
    with JOBS_LOCK:
        JOBS[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "kind": kind,
            "id": item_id,
            "started_at": None,
            "result": None,
            "error": "",
        }

    def worker() -> None:
        with JOBS_LOCK:
            JOBS[job_id]["status"] = "running"
        try:
            task = load_task(Path(item["path"]), ROOT)
            result = run_task(
                task,
                RUNS,
                mcp_only=mcp_only,
                policy_path=policy_arg,
                task_path=item["path"],
                append_prompt=append_prompt,
                scope=scope,
            )
            with JOBS_LOCK:
                JOBS[job_id].update(
                    status="done",
                    result={
                        "task_id": result["task_id"],
                        "run_dir": result["run_dir"],
                        "status": result["status"],
                        "verdict": result["verdict"],
                        "outcome": (result.get("outcome") or {}).get("primary"),
                        "summary": result.get("summary"),
                    },
                )
            RUNS_CACHE["ts"] = 0.0
        except Exception as exc:  # noqa: BLE001
            with JOBS_LOCK:
                JOBS[job_id].update(status="error", error=str(exc))

    threading.Thread(target=worker, daemon=True, name=f"harness-{job_id}").start()
    return {"job_id": job_id, "status": "queued"}


class Handler(BaseHTTPRequestHandler):
    server_version = "HarnessWeb/0.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: int, message: str) -> None:
        self._json({"ok": False, "error": message}, status)

    def _authorized(self, path: str, query: dict[str, list[str]]) -> bool:
        if not WEB_TOKEN or not path.startswith("/api/") or path == "/api/health":
            return True
        header = self.headers.get("Authorization", "")
        token = header[7:] if header.lower().startswith("bearer ") else ""
        token = token or self.headers.get("X-Harness-Token", "")
        token = token or (query.get("token", [""])[0] if query else "")
        return hmac.compare_digest(token, WEB_TOKEN)

    def _file(self, path: Path) -> None:
        if not path.is_file():
            self._error(404, "not found")
            return
        body = path.read_bytes()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        if not self._authorized(path, query):
            self._error(401, "unauthorized")
            return
        try:
            if path == "/api/health":
                self._json(_health())
            elif path == "/api/catalog":
                self._json(_catalog())
            elif path == "/api/runs":
                self._json({"items": _run_items(int(query.get("limit", ["40"])[0]))})
            elif path.startswith("/api/runs/"):
                self._json(_run_detail(path.rsplit("/", 1)[-1]))
            elif path.startswith("/api/jobs/"):
                job_id = path.rsplit("/", 1)[-1]
                with JOBS_LOCK:
                    job = JOBS.get(job_id)
                if job is None:
                    self._error(404, "job not found")
                else:
                    self._json(job)
            elif path == "/api/memory":
                scope = query.get("scope", [None])[0]
                status = query.get("status", [None])[0]
                self._json(
                    {
                        "items": MEMORY.list(scope=scope, status=status),
                        "stats": MEMORY.stats(scope),
                        "scopes": sorted(set(MEMORY.scopes()) | {"default"}),
                    }
                )
            elif path == "/api/openviking/health":
                self._json(OPENVIKING.health())
            elif path == "/api/openviking/search":
                q = query.get("q", [""])[0]
                scope = query.get("scope", [None])[0] or None
                self._json(
                    {
                        "items": OPENVIKING.search(
                            q, int(query.get("limit", ["5"])[0]), scope=scope
                        )
                    }
                )
            elif path.startswith("/api/chat/"):
                session_id = path.rsplit("/", 1)[-1]
                self._json(
                    {
                        "session_id": session_id,
                        "messages": CHAT.history(session_id),
                    }
                )
            elif path in ("/", "/chat"):
                self._file(STATIC / "chat.html")
            elif path == "/admin":
                self._file(STATIC / "index.html")
            elif path.startswith("/static/"):
                target = (STATIC / path[len("/static/") :]).resolve()
                if STATIC.resolve() in target.parents and target.is_file():
                    self._file(target)
                else:
                    self._error(404, "not found")
            else:
                self._error(404, "not found")
        except Exception as exc:  # noqa: BLE001
            self._error(500, str(exc))

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        if not self._authorized(path, query):
            self._error(401, "unauthorized")
            return
        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}") if length else {}
        except Exception:
            self._error(400, "invalid json")
            return
        try:
            if path == "/api/run":
                self._json(_start_job(payload), 202)
            elif path == "/api/chat/session":
                self._json(CHAT.create())
            elif path == "/api/chat":
                session_id = str(payload.get("session_id") or "")
                message = str(payload.get("message") or "").strip()
                if not session_id or not message:
                    self._error(400, "session_id and message are required")
                    return
                self._json(CHAT.send(session_id, message))
            elif path == "/api/memory/add":
                result = MEMORY.add(
                    scope=str(payload.get("scope") or "default"),
                    kind=str(payload.get("kind") or "fact"),
                    key=str(payload.get("key") or ""),
                    text=str(payload.get("text") or ""),
                    source="user",
                    confidence=1.0,
                )
                if result.get("status") == "allow" and result.get("record"):
                    result["sync"] = sync_record(OPENVIKING, MEMORY, result["record"])
                self._json(result)
            elif path.startswith("/api/memory/") and path.endswith("/sync"):
                record_id = path.split("/")[3]
                record = MEMORY.get(record_id)
                if record is None:
                    raise KeyError(record_id)
                result = sync_record(OPENVIKING, MEMORY, record)
                self._json({"ok": result.get("ok", False), "record": MEMORY.get(record_id), "sync": result})
            elif path.startswith("/api/memory/") and path.endswith(("/approve", "/reject")):
                record_id = path.split("/")[3]
                approve = path.endswith("/approve")
                record = MEMORY.set_status(
                    record_id, "active" if approve else "rejected", "human_review"
                )
                sync = None
                if approve:
                    sync = sync_record(OPENVIKING, MEMORY, record)
                    record = MEMORY.get(record_id)
                self._json({"ok": True, "record": record, "sync": sync})
            elif path == "/api/lessons/extract":
                run_id = str(payload.get("run_id") or "")
                run_dir = _find_run(run_id)
                if run_dir is None:
                    self._error(404, "run not found")
                    return
                result = extract_lesson(run_dir, MEMORY)
                self._json(result)
            else:
                self._error(404, "not found")
        except KeyError as exc:
            self._error(404, f"not found: {exc}")
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            self._error(500, str(exc))


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Harness Console: http://127.0.0.1:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
