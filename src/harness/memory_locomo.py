from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class Case:
    case_id: str
    messages: list[dict[str, Any]]
    question: str
    answer: str
    evidence: list[str]


def load_cases(path: str | Path) -> list[Case]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = data.get("cases") if isinstance(data, dict) else data
    cases: list[Case] = []
    for index, row in enumerate(rows or []):
        evidence = row.get("evidence") or row.get("evidence_text") or []
        if isinstance(evidence, str):
            evidence = [evidence]
        cases.append(
            Case(
                case_id=str(row.get("id") or row.get("case_id") or index),
                messages=list(row.get("messages") or row.get("conversation") or []),
                question=str(row.get("question") or ""),
                answer=str(row.get("answer") or ""),
                evidence=[str(item) for item in evidence],
            )
        )
    return cases


def score_retrieval(
    cases: list[Case],
    search: Callable[[str], list[dict[str, Any]]],
    top_k: int = 5,
) -> dict[str, Any]:
    rows = []
    for case in cases:
        results = search(case.question)
        texts = [
            str(item.get("content") or item.get("text") or item.get("abstract") or "")
            for item in results[:top_k]
        ]
        blob = "\n".join(texts)
        needles = [case.answer, *case.evidence]
        matched = any(needle and needle in blob for needle in needles)
        rows.append(
            {
                "case_id": case.case_id,
                "question": case.question,
                "matched": matched,
                "results": len(results),
            }
        )
    hits = sum(1 for row in rows if row["matched"])
    return {
        "cases": len(rows),
        "hits": hits,
        "recall_at_k": hits / len(rows) if rows else 0.0,
        "rows": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score normalized LoCoMo-style retrieval")
    parser.add_argument("--cases", required=True)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--out", default="memory/eval/locomo-report.json")
    args = parser.parse_args(argv)
    cases = load_cases(args.cases)
    raise SystemExit(
        "This CLI needs a configured search function; import score_retrieval in a script."
    )


if __name__ == "__main__":
    raise SystemExit(main())
