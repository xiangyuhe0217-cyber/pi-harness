from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class StepEvent:
    """统一的 step 事件，后续 verdict/归因都读它。"""

    run_id: str
    seq: int
    step: int
    kind: str
    ts: str
    source: str = "pi"
    tool: str | None = None
    tool_call_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    verdict: str = "ok"
    metrics: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


def write_events(events: list[StepEvent], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for event in events:
            fh.write(event.to_json() + "\n")
