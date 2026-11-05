"""LoCoMo retrieval baseline: session-level BM25 over the public conversations.

This is a reproducible retrieval baseline for the memory chain. It does not
claim to be an end-to-end OpenViking memory benchmark; the OpenViking session
extraction path is evaluated separately.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from pathlib import Path


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9_]+", text.lower())


def load_documents(path: str | Path) -> tuple[list[dict], list[dict]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    docs: list[dict] = []
    cases: list[dict] = []
    for sample in data:
        sample_id = str(sample.get("sample_id"))
        conversation = sample.get("conversation") or {}
        evidence_to_session: dict[str, str] = {}
        for key, value in conversation.items():
            if not key.startswith("session_") or key.endswith("_date_time"):
                continue
            if not isinstance(value, list):
                continue
            session = key
            date = conversation.get(f"{key}_date_time", "")
            lines = []
            for dialogue in value:
                dia_id = str(dialogue.get("dia_id") or "")
                if dia_id:
                    evidence_to_session[dia_id] = session
                lines.append(f"{dialogue.get('speaker', '')}: {dialogue.get('text', '')}")
            docs.append(
                {
                    "id": f"{sample_id}:{session}",
                    "sample_id": sample_id,
                    "session": session,
                    "text": f"{date} " + "\n".join(lines),
                }
            )
        for qa in sample.get("qa") or []:
            targets = {
                evidence_to_session[e]
                for e in qa.get("evidence") or []
                if e in evidence_to_session
            }
            if not targets:
                continue
            cases.append(
                {
                    "id": f"{sample_id}:{len(cases)}",
                    "sample_id": sample_id,
                    "question": str(qa.get("question") or ""),
                    "answer": qa.get("answer"),
                    "target_sessions": targets,
                }
            )
    return docs, cases


def bm25_rank(query: str, docs: list[dict], top_k: int = 5) -> list[str]:
    query_tokens = _tokens(query)
    if not query_tokens:
        return []
    doc_tokens = [_tokens(doc["text"]) for doc in docs]
    lengths = [len(tokens) for tokens in doc_tokens]
    avg = sum(lengths) / max(1, len(lengths))
    df = Counter()
    for tokens in doc_tokens:
        for token in set(tokens):
            df[token] += 1
    scores = []
    for index, tokens in enumerate(doc_tokens):
        counts = Counter(tokens)
        score = 0.0
        for token in query_tokens:
            if counts[token] == 0:
                continue
            idf = math.log(1 + (len(docs) - df[token] + 0.5) / (df[token] + 0.5))
            tf = counts[token]
            denom = tf + 1.5 * (1 - 0.75 + 0.75 * lengths[index] / max(avg, 1e-9))
            score += idf * (tf * 2.5) / denom
        scores.append((score, docs[index]["id"]))
    scores.sort(reverse=True)
    return [doc_id for _, doc_id in scores[:top_k]]


def evaluate(path: str | Path, limit: int | None = None, top_k: int = 5) -> dict:
    docs, cases = load_documents(path)
    if limit:
        cases = cases[:limit]
    ranks = []
    hits = {k: 0 for k in (1, 3, 5, 10)}
    rows = []
    for case in cases:
        ranked = bm25_rank(case["question"], docs, top_k=max(10, top_k))
        target_ids = {f"{case['sample_id']}:{session}" for session in case["target_sessions"]}
        rank = next(
            (index + 1 for index, doc_id in enumerate(ranked) if doc_id in target_ids),
            None,
        )
        ranks.append(rank or 999)
        for k in hits:
            if rank is not None and rank <= k:
                hits[k] += 1
        rows.append(
            {
                "id": case["id"],
                "question": case["question"],
                "target_sessions": sorted(case["target_sessions"]),
                "rank": rank,
                "top": ranked[:top_k],
            }
        )
    total = len(cases)
    return {
        "documents": len(docs),
        "cases": total,
        "hit_at": {str(k): round(hits[k] / total, 4) if total else 0 for k in hits},
        "mrr": round(sum(1.0 / rank for rank in ranks) / total, 4) if total else 0.0,
        "rows": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="memory/eval/locomo10.json")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--out", default="memory/eval/locomo-report.json")
    args = parser.parse_args(argv)
    result = evaluate(args.data, args.limit, args.top_k)
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {key: result[key] for key in ("documents", "cases", "hit_at", "mrr")},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
