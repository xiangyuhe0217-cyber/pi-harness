"""Minimal OpenAI-compatible proxy for local smoke tests.

This is a development fallback for when the LiteLLM proxy cannot start.
It forwards /v1/chat/completions and /v1/models to DeepSeek.

It is NOT a replacement for LiteLLM in production; use LiteLLM when available.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM = os.environ.get("MINI_PROXY_UPSTREAM", "https://api.deepseek.com/v1").rstrip("/")
API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
MODEL_MAP = {
    "deepseek-chat": "deepseek-v4-pro",
    "deepseek-v4-pro": "deepseek-v4-pro",
    "deepseek-flash": "deepseek-flash",
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.rstrip("/") in {"/v1/models", "/models"}:
            self._json(
                {
                    "object": "list",
                    "data": [
                        {"id": name, "object": "model", "owned_by": "deepseek"}
                        for name in MODEL_MAP
                    ],
                }
            )
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        if self.path.rstrip("/") not in {"/v1/chat/completions", "/chat/completions"}:
            self._json({"error": "not found"}, 404)
            return
        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except Exception:
            self._json({"error": "invalid json"}, 400)
            return
        requested = str(payload.get("model") or "deepseek-chat")
        payload["model"] = MODEL_MAP.get(requested, requested)
        streaming = bool(payload.get("stream"))
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            UPSTREAM + "/chat/completions",
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {API_KEY}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                if streaming:
                    self.send_response(response.status)
                    self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("Connection", "close")
                    self.end_headers()
                    while True:
                        chunk = response.read(1024)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        self.wfile.flush()
                    return
                body = response.read()
                content_type = response.headers.get("Content-Type", "application/json")
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except urllib.error.HTTPError as exc:
            body = exc.read()
            self.send_response(exc.code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:  # noqa: BLE001
            self._json({"error": str(exc)}, 502)


if __name__ == "__main__":
    port = int(os.environ.get("MINI_PROXY_PORT", "4000"))
    print(f"mini OpenAI-compatible proxy on 127.0.0.1:{port} -> {UPSTREAM}")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
