from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

INJECTION_PATTERNS = [
    r"ignore (all )?(previous|prior) instructions",
    r"disregard (all )?(previous|prior) instructions",
    r"system prompt",
    r"exfiltrate",
    r"without approval",
    r"ignore .*approval",
    r"bypass .*approval",
]

SECRET_PATTERNS = [
    r"sk-[A-Za-z0-9]{10,}",
    r"AKIA[0-9A-Z]{16}",
    r"password\s*=\s*\S+",
]


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _hash(text: str) -> str:
    normalized = " ".join(text.lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_]+", text.lower()))


class MemoryStore:
    """Long-term memory with write policy + poisoning detection.

    - active: usable in prompts
    - quarantined: stored but never injected until reviewed
    - blocked: not stored, audit only
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.audit_path = self.path.parent / "audit.jsonl"
        self.records: list[dict[str, Any]] = []
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self.records = list(data.get("records") or [])
            except Exception:
                self.records = []

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"records": self.records}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _audit(self, action: str, record: dict[str, Any] | None, rule: str | None) -> None:
        try:
            self.audit_path.parent.mkdir(parents=True, exist_ok=True)
            with self.audit_path.open("a", encoding="utf-8") as fh:
                fh.write(
                    json.dumps(
                        {
                            "ts": _now(),
                            "action": action,
                            "rule": rule,
                            "record": record,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        except Exception:
            pass

    def _expire(self) -> None:
        now = datetime.now(timezone.utc)
        changed = False
        for record in self.records:
            if record.get("status") != "active":
                continue
            expires = record.get("expires_at")
            if not expires:
                continue
            try:
                if datetime.fromisoformat(expires) <= now:
                    record["status"] = "expired"
                    changed = True
            except Exception:
                continue
        if changed:
            self._save()

    def _evaluate(
        self,
        scope: str,
        key: str,
        text: str,
        source: str,
        confidence: float,
    ) -> tuple[str, str | None]:
        if len(text) > 500:
            return "block", "memory.too_long"
        for pattern in INJECTION_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return "block", "memory.policy_bypass"
        for pattern in SECRET_PATTERNS:
            if re.search(pattern, text):
                return "block", "memory.secret"
        if source not in {"user", "system"}:
            return "quarantine", "memory.untrusted_source"
        if key:
            for record in self.records:
                if (
                    record.get("scope") == scope
                    and record.get("status") == "active"
                    and record.get("key") == key
                    and record.get("text") != text
                ):
                    return "quarantine", "memory.conflict"
        return "allow", None

    def add(
        self,
        scope: str,
        kind: str,
        key: str,
        text: str,
        source: str = "agent",
        confidence: float = 0.5,
        ttl_days: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._expire()
        digest = _hash(text)
        for record in self.records:
            if (
                record.get("scope") == scope
                and record.get("status") == "active"
                and record.get("hash") == digest
            ):
                self._audit("duplicate", record, None)
                return {"status": "duplicate", "record": record}

        decision, rule = self._evaluate(scope, key, text, source, confidence)
        if decision == "block":
            self._audit("block", None, rule)
            return {"status": "block", "rule": rule, "record": None}

        record = {
            "id": f"mem_{digest}",
            "scope": scope,
            "kind": kind,
            "key": key,
            "text": text,
            "source": source,
            "confidence": round(float(confidence), 2),
            "hash": digest,
            "created_at": _now(),
            "expires_at": None,
            "status": "active" if decision == "allow" else "quarantined",
            "reason": rule,
        }
        if extra:
            record.update(extra)
        if ttl_days:
            from datetime import timedelta

            record["expires_at"] = (
                datetime.now(timezone.utc) + timedelta(days=int(ttl_days))
            ).isoformat(timespec="seconds")
        self.records.append(record)
        self._save()
        self._audit("quarantine" if decision == "quarantine" else "add", record, rule)
        return {"status": decision, "rule": rule, "record": record}

    def search(self, scope: str, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        self._expire()
        query_tokens = _tokens(query)
        scored: list[tuple[float, dict[str, Any]]] = []
        for record in self.records:
            if record.get("scope") != scope or record.get("status") != "active":
                continue
            tokens = _tokens(record.get("text", "") + " " + record.get("key", ""))
            score = len(query_tokens & tokens) / max(1, len(query_tokens))
            if score > 0:
                scored.append((score, record))
        scored.sort(key=lambda item: (item[0], item[1].get("confidence", 0)), reverse=True)
        return [record for _, record in scored[:top_k]]

    def list(self, scope: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        self._expire()
        return [
            record
            for record in self.records
            if (scope is None or record.get("scope") == scope)
            and (status is None or record.get("status") == status)
        ]

    def stats(self, scope: str | None = None) -> dict[str, int]:
        records = self.list(scope=scope)
        out = {"total": len(records), "active": 0, "quarantined": 0, "expired": 0}
        for record in records:
            status = record.get("status", "unknown")
            out[status] = out.get(status, 0) + 1
        return out

    def get(self, record_id: str) -> dict[str, Any] | None:
        for record in self.records:
            if record.get("id") == record_id:
                return record
        return None

    def find_by_source(self, source_uri: str) -> dict[str, Any] | None:
        for record in self.records:
            if record.get("viking_source_uri") == source_uri:
                return record
        return None

    def scopes(self) -> list[str]:
        return sorted({str(record.get("scope")) for record in self.records if record.get("scope")})

    def set_status(self, record_id: str, status: str, reason: str | None = None) -> dict[str, Any]:
        if status not in {"active", "quarantined", "rejected", "expired"}:
            raise ValueError(f"invalid status: {status}")
        record = self.get(record_id)
        if record is None:
            raise KeyError(record_id)
        record["status"] = status
        record["reason"] = reason
        self._save()
        action = "approve" if status == "active" else "reject" if status == "rejected" else "status"
        self._audit(action, record, reason)
        return record

    def mark_synced(
        self,
        record_id: str,
        uri: str,
        status: str,
        error: str | None = None,
    ) -> dict[str, Any]:
        record = self.get(record_id)
        if record is None:
            raise KeyError(record_id)
        record["openviking_uri"] = uri or None
        record["sync_status"] = status
        record["sync_error"] = error
        record["synced_at"] = _now()
        self._save()
        self._audit("sync", record, error)
        return record

    def prompt_block(self, scope: str, query: str, top_k: int = 5) -> str:
        records = self.search(scope, query, top_k)
        if not records:
            return ""
        lines = ["<long_term_memory>"]
        for record in records:
            lines.append(
                f"- [{record.get('kind')}] key={record.get('key') or '-'} "
                f"({record.get('source')}, conf={record.get('confidence')}): {record.get('text')}"
            )
        lines.append("</long_term_memory>")
        return "\n".join(lines)
