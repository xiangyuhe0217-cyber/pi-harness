from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Policy:
    version: str
    allowed_bin: set[str]
    deny_patterns: list[str]
    sensitive_markers: list[str]
    max_write_bytes: int
    allow_stderr_merge: bool = False
    deny_modules: list[str] = field(default_factory=list)
    injection_patterns: list[str] = field(default_factory=list)
    secret_patterns: list[str] = field(default_factory=list)


def load_policy(path: str | Path | None = None) -> Policy:
    if path is None:
        path = Path(__file__).resolve().parents[2] / "policies" / "p1.json"
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return Policy(
        version=str(data["version"]),
        allowed_bin=set(data.get("allowed_bin") or []),
        deny_patterns=list(data.get("deny_patterns") or []),
        sensitive_markers=list(data.get("sensitive_markers") or []),
        max_write_bytes=int(data.get("max_write_bytes") or 200000),
        allow_stderr_merge=bool(data.get("allow_stderr_merge", False)),
        deny_modules=list(data.get("deny_modules") or []),
        injection_patterns=list(data.get("injection_patterns") or []),
        secret_patterns=list(data.get("secret_patterns") or []),
    )
