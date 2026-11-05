from __future__ import annotations

from typing import Any


def gate(
    baseline: dict[str, Any],
    winner: dict[str, Any],
    max_cost_ratio: float = 1.1,
) -> dict[str, Any]:
    """Human-readable, deterministic holdout gate."""
    checks = {
        "pass_not_worse": winner["pass_rate"] >= baseline["pass_rate"],
        "score_not_worse": winner["score"] >= baseline["score"],
        "cost_not_worse": winner["cost_usd"] <= max(0.001, baseline["cost_usd"] * max_cost_ratio),
        "blocked_not_worse": winner["blocked"] <= baseline["blocked"],
    }
    return {
        "adopted": all(checks.values()),
        "checks": checks,
        "baseline": baseline,
        "winner": winner,
    }
