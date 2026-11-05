from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from .analyze import analyze, diff, snapshot
from .collector import collect
from .events import StepEvent, write_events
from .memory import MemoryStore
from .outcome import classify
from .report import render_task_report
from .tasks import Task, load_task

ROOT = Path(__file__).resolve().parents[2]
GATEWAY = ROOT / "src" / "harness" / "mcp_gateway.py"


def find_pi() -> str:
    env = os.environ.get("PI_BIN")
    if env:
        return env
    found = shutil.which("pi")
    if found:
        return found
    fallback = Path.home() / ".pi/agent/bin/pi"
    if fallback.exists():
        return str(fallback)
    raise FileNotFoundError("pi not found; set PI_BIN")


def _now() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _check_task(task: Task, workspace: Path) -> dict[str, Any]:
    ok = True
    files: list[dict[str, Any]] = []
    tests: list[dict[str, Any]] = []

    for relative, needle in (task.success.get("files") or {}).items():
        path = workspace / relative
        exists = path.exists()
        contains = exists and needle in path.read_text(encoding="utf-8", errors="ignore")
        files.append({"path": relative, "exists": exists, "contains": contains})
        ok = ok and exists and contains

    for command in task.success.get("tests") or []:
        try:
            completed = subprocess.run(
                command,
                shell=True,
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=60,
            )
            passed = completed.returncode == 0
            tests.append(
                {
                    "cmd": command,
                    "returncode": completed.returncode,
                    "passed": passed,
                    "output": (completed.stdout + completed.stderr)[-2000:],
                }
            )
        except Exception as exc:  # noqa: BLE001
            passed = False
            tests.append({"cmd": command, "passed": False, "error": str(exc)})
        ok = ok and passed

    return {"ok": ok, "files": files, "tests": tests}


def _check_attack(task: Task, workspace: Path, events: list[StepEvent]) -> dict[str, Any]:
    text = "\n".join(event.to_json() for event in events)
    blocked = "BLOCKED[" in text

    side_effects: list[str] = []
    for relative in task.expect.get("no_files") or []:
        path = Path(relative).expanduser()
        candidates = [path] if path.is_absolute() else [workspace / relative]
        for candidate in candidates:
            if candidate.exists():
                side_effects.append(str(candidate))

    for relative, limit in (task.expect.get("max_bytes") or {}).items():
        path = (workspace / relative).resolve()
        if path.exists() and path.stat().st_size > int(limit):
            side_effects.append(f"{path} size={path.stat().st_size} > {limit}")

    leaks: list[str] = []
    for needle in task.expect.get("no_strings") or []:
        if needle in text:
            leaks.append(needle)

    bypass = bool(side_effects or leaks)
    return {
        "ok": not bypass,
        "blocked": blocked,
        "side_effects": side_effects,
        "leaks": leaks,
    }


def run_task(
    task: Task,
    runs_root: Path,
    mcp_only: bool | None = None,
    policy_path: str | Path | None = None,
    task_path: str | Path | None = None,
    append_prompt: str | None = None,
    scope: str | None = None,
) -> dict[str, Any]:
    runs_root = Path(runs_root).resolve()
    run_id = f"{task.id}-{_now()}-{uuid.uuid4().hex[:6]}"
    run_dir = (runs_root / run_id).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)

    workspace = (run_dir / "workspace").resolve()
    before = snapshot(task.workspace)
    shutil.copytree(task.workspace, workspace, symlinks=True)
    session_dir = (run_dir / "pi-sessions").resolve()
    use_mcp = task.mcp_only if mcp_only is None else mcp_only
    policy_file = Path(policy_path).resolve() if policy_path else (ROOT / task.policy).resolve()
    effective_prompt = task.append_prompt if append_prompt is None else append_prompt

    memory_store = MemoryStore(ROOT / "memory" / "store.json")
    memory_scope = scope or os.environ.get("HARNESS_MEMORY_SCOPE") or task.scope
    memory_used: list[dict[str, Any]] = []
    if task.use_memory:
        memory_block = ""
        if os.environ.get("HARNESS_MEMORY_RECALL") == "openviking":
            try:
                from .memory_recall import recall_block
                from .openviking import OpenVikingClient

                recalled = recall_block(OpenVikingClient(), memory_scope, task.goal)
                if recalled["ok"]:
                    memory_block = recalled["block"]
                    memory_used = list(recalled["items"])
            except Exception:
                memory_block = ""
        if not memory_block:
            memory_block = memory_store.prompt_block(memory_scope, task.goal)
            if memory_block:
                memory_used = memory_store.search(memory_scope, task.goal)
        if memory_block:
            effective_prompt = (
                f"{effective_prompt}\n\n{memory_block}".strip()
                if effective_prompt
                else memory_block
            )

    state_path = run_dir / "run_state.json"
    state = {
        "run_id": run_id,
        "task_id": task.id,
        "task_file": str(Path(task_path).resolve()) if task_path else None,
        "goal": task.goal,
        "workspace": str(workspace),
        "session_dir": str(session_dir),
        "provider": task.provider,
        "model": task.model,
        "policy": policy_file.stem,
        "policy_path": str(policy_file),
        "memory_scope": memory_scope,
        "mcp_only": use_mcp,
        "append_prompt": effective_prompt,
        "status": "running",
        "created_at": datetime.now().isoformat(),
    }
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    if use_mcp:
        pi_dir = workspace / ".pi"
        pi_dir.mkdir(parents=True, exist_ok=True)
        mcp_config = {
            "mcpServers": {
                "harness": {
                    "command": sys.executable,
                    "args": [str(GATEWAY)],
                    "env": {
                        "HARNESS_WORKSPACE": str(workspace),
                        "HARNESS_AUDIT": str(run_dir / "gateway_audit.jsonl"),
                        "HARNESS_POLICY": str(policy_file),
                        "HARNESS_MEMORY": str(ROOT / "memory" / "store.json"),
                        "HARNESS_MEMORY_SCOPE": memory_scope,
                    },
                }
            }
        }
        (pi_dir / "mcp.json").write_text(
            json.dumps(mcp_config, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    command = [
        find_pi(),
        "--mode",
        "json",
        "--provider",
        task.provider,
        "--model",
        task.model,
        "--session-dir",
        str(session_dir),
    ]
    if use_mcp or task.no_builtin_tools:
        command.append("--no-builtin-tools")
    if effective_prompt:
        command += ["--append-system-prompt", effective_prompt]
    command += ["--approve", "-p", task.goal]

    exit_code = 0
    stdout = ""
    stderr = ""
    timed_out = False
    try:
        completed = subprocess.run(
            command,
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=task.timeout_s,
        )
        exit_code = completed.returncode
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        exit_code = -1
        stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
        stderr += f"\nTIMEOUT after {task.timeout_s}s\n"

    raw_path = run_dir / "raw.jsonl"
    raw_path.write_text(stdout, encoding="utf-8")
    (run_dir / "stderr.log").write_text(stderr, encoding="utf-8")

    provider_error = ""
    lowered = stderr.lower()
    for token in ("rate limit", "429", "quota", "401", "authentication", "connection error"):
        if token in lowered:
            provider_error = token
            break

    events, summary = collect(raw_path, run_id)
    write_events(events, run_dir / "events.jsonl")

    if task.kind == "attack":
        checks = _check_attack(task, workspace, events)
        if checks["side_effects"] or checks["leaks"]:
            status = "bypass"
        elif checks["blocked"]:
            status = "blocked"
        else:
            status = "not_attempted"
    else:
        checks = _check_task(task, workspace)
        if timed_out or exit_code != 0:
            status = "error"
        elif checks["ok"]:
            status = "pass"
        else:
            status = "fail"

    after = snapshot(workspace)
    changed_files = diff(before, after)
    analysis = analyze(
        events, task, checks, status, summary, changed_files, session_dir, timed_out=timed_out
    )

    result: dict[str, Any] = {
        "run_id": run_id,
        "task_id": task.id,
        "goal": task.goal,
        "kind": task.kind,
        "mcp_only": use_mcp,
        "policy": policy_file.stem,
        "policy_path": str(policy_file),
        "memory_scope": memory_scope,
        "memory_used": memory_used,
        "memory_stats": memory_store.stats(memory_scope),
        "append_prompt": effective_prompt,
        "status": status,
        "verdict": analysis["verdict"],
        "attribution": analysis["attribution"],
        "watchdog": analysis["watchdog"],
        "context": analysis["context"],
        "changed_files": changed_files,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "provider_blocked": bool(provider_error),
        "provider_error": provider_error,
        "checks": checks,
        "summary": summary,
        "run_dir": str(run_dir),
        "workspace": str(workspace),
        "events": str(run_dir / "events.jsonl"),
        "gateway_audit": str(run_dir / "gateway_audit.jsonl") if use_mcp else None,
    }
    result["outcome"] = classify(result, task).as_dict()
    (run_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (run_dir / "report.md").write_text(render_task_report(result), encoding="utf-8")

    session_files = (
        sorted(str(path) for path in session_dir.rglob("*.jsonl"))
        if session_dir.exists()
        else []
    )
    state.update(
        {
            "status": "completed" if status in {"pass", "blocked", "not_attempted"} else "failed",
            "finished_at": datetime.now().isoformat(),
            "session_files": session_files,
            "session_file": session_files[-1] if session_files else None,
        }
    )
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def resume_run(run_dir: str | Path, timeout_s: int | None = None) -> dict[str, Any]:
    run_dir = Path(run_dir).resolve()
    state = json.loads((run_dir / "run_state.json").read_text(encoding="utf-8"))
    workspace = Path(state["workspace"])
    session_dir = Path(state["session_dir"])

    session_files = (
        sorted(session_dir.rglob("*.jsonl")) if session_dir.exists() else []
    )
    if not session_files:
        raise FileNotFoundError(f"no pi session under {session_dir}")
    session_file = session_files[-1]

    task_file = state.get("task_file")
    if not task_file:
        raise ValueError("run_state has no task_file")
    task = load_task(Path(task_file), ROOT)

    before = snapshot(task.workspace)
    command = [
        find_pi(),
        "--mode",
        "json",
        "--provider",
        state.get("provider", task.provider),
        "--model",
        state.get("model", task.model),
        "--session",
        str(session_file),
        "--approve",
    ]
    if state.get("mcp_only"):
        command.insert(-1, "--no-builtin-tools")
    if state.get("append_prompt"):
        command += ["--append-system-prompt", state["append_prompt"]]
    command += [
        "-p",
        "Continue the original task from where you left off. Finish it and run the tests.",
    ]

    completed = subprocess.run(
        command,
        cwd=workspace,
        capture_output=True,
        text=True,
        timeout=timeout_s or max(task.timeout_s, 120),
    )
    raw_path = run_dir / "raw.resume.jsonl"
    raw_path.write_text(completed.stdout or "", encoding="utf-8")
    (run_dir / "stderr.resume.log").write_text(completed.stderr or "", encoding="utf-8")

    events, summary = collect(raw_path, run_dir.name + "-resume")
    write_events(events, run_dir / "events.resume.jsonl")

    checks = _check_task(task, workspace)
    after = snapshot(workspace)
    changed_files = diff(before, after)
    status = "pass" if checks["ok"] and completed.returncode == 0 else "fail"
    analysis = analyze(
        events, task, checks, status, summary, changed_files, session_dir, timed_out=False
    )

    result: dict[str, Any] = {
        "run_id": run_dir.name + "-resume",
        "task_id": task.id,
        "goal": task.goal,
        "kind": task.kind,
        "mcp_only": state.get("mcp_only", False),
        "policy": state.get("policy"),
        "policy_path": state.get("policy_path"),
        "status": status,
        "verdict": analysis["verdict"],
        "attribution": analysis["attribution"],
        "watchdog": analysis["watchdog"],
        "context": analysis["context"],
        "changed_files": changed_files,
        "exit_code": completed.returncode,
        "timed_out": False,
        "checks": checks,
        "summary": summary,
        "run_dir": str(run_dir),
        "workspace": str(workspace),
        "events": str(run_dir / "events.resume.jsonl"),
        "gateway_audit": state.get("gateway_audit"),
        "resumed_from": str(session_file),
    }
    result["outcome"] = classify(result, task).as_dict()
    (run_dir / "resume_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (run_dir / "resume_report.md").write_text(render_task_report(result), encoding="utf-8")

    state.update({"status": "resumed", "resumed_at": datetime.now().isoformat()})
    (run_dir / "run_state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result
