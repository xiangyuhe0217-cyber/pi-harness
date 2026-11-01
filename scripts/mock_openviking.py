from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

STORE = Path("/tmp/mock-openviking.json")
WRITES: dict[str, dict] = {}


class Handler(BaseHTTPRequestHandler):
    def _json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == "/health":
            self._json({"status": "ok"})
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        if self.path == "/api/v1/content/write":
            uri = payload.get("uri", "")
            WRITES[uri] = payload
            STORE.write_text(json.dumps(WRITES, ensure_ascii=False, indent=2), encoding="utf-8")
            self._json(
                {
                    "status": "ok",
                    "result": {
                        "uri": uri,
                        "root_uri": uri.rsplit("/", 1)[0],
                        "mode": "replace",
                        "written_bytes": len(payload.get("content", "")),
                    },
                }
            )
            return
        if self.path == "/api/v1/search/find":
            query = str(payload.get("query", "")).lower()
            items = []
            for uri, write in WRITES.items():
                content = str(write.get("content", ""))
                if not query or query in content.lower():
                    items.append(
                        {
                            "uri": uri,
                            "context_type": "memory",
                            "abstract": content[:200],
                            "content": content,
                            "score": 1.0,
                        }
                    )
            self._json({"status": "ok", "result": {"memories": items, "resources": [], "skills": []}})
            return
        self._json({"error": "not found"}, 404)


if __name__ == "__main__":
    print("mock OpenViking on 127.0.0.1:1933")
    ThreadingHTTPServer(("0.0.0.0", 1933), Handler).serve_forever()
