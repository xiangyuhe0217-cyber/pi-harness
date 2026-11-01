from __future__ import annotations

from collections import Counter
from typing import Any

from .study import render_study


def _fmt_cost(value: Any) -> str:
    return f"${float(value or 0):.6f}"


def render_task_report(result: dict[str, Any]) -> str:
    summary = result.get("summary") or {}
    checks = result.get("checks") or {}
    lines = [
        f"# {result['task_id']}",
        "",
        f"- kind: {result.get('kind', 'task')}",
        f"- status: **{result['status']}**",
        f"- mcp_only: {result.get('mcp_only', False)}",
        f"- outcome: {(result.get('outcome') or {}).get('primary')} "
        f"(valid={(result.get('outcome') or {}).get('valid')}, "
        f"reason={(result.get('outcome') or {}).get('reason')})",
        f"- goal: {result['goal']}",
        f"- steps: {summary.get('steps', 0)}",
        f"- tool_calls: {summary.get('tool_calls', 0)}",
        f"- blocked: {summary.get('blocked', 0)}",
        f"- tokens: {summary.get('tokens', 0)}",
        f"- cost: {_fmt_cost(summary.get('cost_usd'))}",
        f"- duration_ms: {summary.get('duration_ms', 0)}",
        f"- run_dir: `{result['run_dir']}`",
        "",
        "## checks",
        "",
    ]
    for item in checks.get("files") or []:
        lines.append(
            f"- file `{item['path']}`: exists={item['exists']}, contains={item['contains']}"
        )
    for item in checks.get("tests") or []:
        lines.append(f"- test `{item['cmd']}`: passed={item.get('passed')}")
    if result.get("kind") == "attack":
        lines.append(f"- blocked: {checks.get('blocked')}")
        lines.append(f"- side_effects: {checks.get('side_effects')}")
        lines.append(f"- leaks: {checks.get('leaks')}")
    lines += [
        "## verdict",
        "",
        f"- verdict: **{result.get('verdict')}**",
        f"- attribution: {result.get('attribution')}",
        f"- changed_files: {result.get('changed_files')}",
        "",
    ]
    watchdog = result.get("watchdog") or {}
    lines += [
        "## watchdog",
        "",
        f"- max_repeat: {watchdog.get('max_repeat')}",
        f"- failed_calls: {watchdog.get('failed_calls')}",
        f"- blocked_calls: {watchdog.get('blocked_calls')}",
        f"- no_progress: {watchdog.get('no_progress')}",
        f"- decay_ratio: {watchdog.get('decay_ratio')}",
        f"- loop: {watchdog.get('loop')}",
        "",
    ]
    context = result.get("context") or {}
    lines += [
        "## context",
        "",
        f"- max_input_tokens: {context.get('max_input_tokens')}",
        f"- context_window: {context.get('context_window')}",
        f"- utilization: {context.get('utilization')}",
        f"- anxiety: {context.get('anxiety')}",
        f"- compaction_count: {context.get('compaction_count')}",
        f"- compactions: {context.get('compactions')}",
        "",
    ]
    study = render_study(result["task_id"])
    if study:
        lines += ["", study]
    lines.append("")
    return "\n".join(lines)


def render_baseline(results: list[dict[str, Any]]) -> str:
    benign = [result for result in results if result.get("kind", "task") != "attack"]
    attacks = [result for result in results if result.get("kind") == "attack"]
    verdicts = Counter(result.get("verdict") for result in results)
    attributions = Counter(result.get("attribution") for result in results)
    lines = [
        "# Baseline",
        "",
        "- verdicts: " + ", ".join(f"{key}={value}" for key, value in verdicts.items()),
        "- attributions: " + ", ".join(f"{key}={value}" for key, value in attributions.items()),
        "",
    ]

    if benign:
        total = len(benign) or 1
        passed = sum(1 for result in benign if result.get("status") == "pass")
        lines += [
            f"- tasks: {len(benign)}",
            f"- pass@1: {passed}/{len(benign)} = {passed / total:.2f}",
            "",
            "| task | status | verdict | attr | steps | tools | blocked | tokens | cost | util |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]
        for result in benign:
            summary = result.get("summary") or {}
            context = result.get("context") or {}
            lines.append(
                f"| {result['task_id']} | {result['status']} | {result.get('verdict')} | "
                f"{result.get('attribution')} | {summary.get('steps', 0)} | "
                f"{summary.get('tool_calls', 0)} | {summary.get('blocked', 0)} | "
                f"{summary.get('tokens', 0)} | {_fmt_cost(summary.get('cost_usd'))} | "
                f"{context.get('utilization')} |"
            )
        lines.append("")

    if attacks:
        total = len(attacks) or 1
        bypassed = sum(1 for result in attacks if result.get("status") == "bypass")
        blocked = sum(1 for result in attacks if result.get("status") == "blocked")
        lines += [
            f"- attacks: {len(attacks)}",
            f"- ASR (bypass): {bypassed}/{len(attacks)} = {bypassed / total:.2f}",
            f"- blocked: {blocked}/{len(attacks)}",
            "",
            "| attack | status | verdict | attr | blocked | side_effects | steps | tools |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for result in attacks:
            summary = result.get("summary") or {}
            checks = result.get("checks") or {}
            lines.append(
                f"| {result['task_id']} | {result['status']} | {result.get('verdict')} | "
                f"{result.get('attribution')} | {checks.get('blocked')} | "
                f"{len(checks.get('side_effects') or [])} | {summary.get('steps', 0)} | "
                f"{summary.get('tool_calls', 0)} |"
            )
        lines.append("")

    return "\n".join(lines)
