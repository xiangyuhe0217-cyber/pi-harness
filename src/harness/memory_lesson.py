from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .memory import MemoryStore


def extract_lesson(
    run_dir: str | Path,
    store: MemoryStore,
    scope: str | None = None,
) -> dict[str, Any]:
    """Turn a failed trace into a quarantined lesson candidate.

    Rule-based on purpose: no extra model call, and the write still goes through
    the normal memory policy (agent source -> quarantine, injection -> block).
    """

    run_dir = Path(run_dir).resolve()
    result = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
    if result.get("kind") == "attack":
        return {"status": "skipped", "reason": "attack_runs_are_not_lessons"}

    outcome = (result.get("outcome") or {}).get("primary", "")
    if result.get("status") == "pass" and outcome in {"FastPass", "SlowPass"}:
        return {"status": "skipped", "reason": "run_passed"}

    summary = result.get("summary") or {}
    watchdog = result.get("watchdog") or {}
    checks = result.get("checks") or {}
    reasons: list[str] = []

    if result.get("timed_out"):
        reasons.append("the run hit its time budget")
    if outcome == "BudgetBlocked":
        reasons.append("the run exceeded a step/token/cost budget")
    if outcome == "CapabilityBlocked":
        reasons.append("the task failed inside its budget")
    if summary.get("blocked"):
        reasons.append(f"{summary['blocked']} tool call(s) were blocked")
    rules = []
    audit = run_dir / "gateway_audit.jsonl"
    if audit.exists():
        for line in audit.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            event = json.loads(line)
            if event.get("decision") == "block" and event.get("rule"):
                rules.append(str(event["rule"]))
    rules = sorted(set(rules))
    if rules:
        reasons.append("blocked rules: " + ", ".join(rules[:5]))
    if watchdog.get("repeated_actions"):
        first = watchdog["repeated_actions"][0]
        reasons.append(f"repeated {first.get('tool')} x{first.get('count')}")
    tests = checks.get("tests") or []
    if any(not test.get("passed") for test in tests):
        reasons.append("a required test failed")
    if not reasons:
        reasons.append("the run did not pass")

    task_id = str(result.get("task_id") or run_dir.name)
    text = (
        f"Lesson from {task_id}: " + "; ".join(reasons) + ". "
        "Next time: read the error, use allowed commands, and run the required tests before finishing."
    )[:480]
    key = f"lesson:{task_id}:{outcome or result.get('status')}"
    memory_scope = scope or result.get("memory_scope") or "default"
    write = store.add(
        scope=memory_scope,
        kind="lesson",
        key=key,
        text=text,
        source="agent",
        confidence=0.6,
    )
    return {
        "status": write.get("status"),
        "rule": write.get("rule"),
        "record": write.get("record"),
        "text": text,
    }
