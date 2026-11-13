"""Retrieval quality: a small gold set, three numbers, one pre-registered gate.

The gold set is grounded in the corpus, not in what the retriever returned: an
expectation is a (document, verbatim fragment) pair that any correct claim must
quote. A claim matches when the fragment is a substring of its quote, so the
metric survives re-segmentation, and it cannot be gamed by ranking.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from compiler.documents.text import norm

MIN_FRAGMENT = 40
HIT_GATE = 0.90  # 18 of 20
RECALL_GATE = 0.60


def load_gold(path: Path) -> list[dict]:
    rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    for row in rows:
        if not row.get("expected"):
            raise ValueError(f"{row.get('id')}: no expected claim")
        for item in row["expected"]:
            if len(norm(item.get("quote", ""))) < MIN_FRAGMENT:
                raise ValueError(f"{row.get('id')}: fragment too short to identify a claim")
    return rows


def _matches(expected: dict, citation: dict) -> bool:
    return citation.get("doc_id") == expected["doc_id"] and norm(expected["quote"]) in norm(
        citation.get("quote", "")
    )


def score(gold: dict, ranked: Iterable[dict]) -> dict:
    ranked = list(ranked)
    found: list[int] = []
    for expected in gold["expected"]:
        rank = next(
            (index for index, citation in enumerate(ranked, start=1) if _matches(expected, citation)),
            None,
        )
        if rank is not None:
            found.append(rank)
    return {
        "id": gold["id"],
        "question": gold["question"],
        "hit": bool(found),
        "recall": len(found) / len(gold["expected"]),
        "rr": (1.0 / min(found)) if found else 0.0,
        "missed": [
            expected["quote"][:60]
            for expected in gold["expected"]
            if not any(_matches(expected, citation) for citation in ranked)
        ],
    }


def evaluate(rows: list[dict], hit_gate: float = HIT_GATE, recall_gate: float = RECALL_GATE) -> dict:
    """Summarise the rows against a gate the caller names.

    The defaults are the demo corpus gate. The pilot corpus has a bar of its own,
    pre-registered before the measurement began, and a tool that printed someone
    else's bar would report the wrong verdict in both directions.
    """
    total = len(rows) or 1
    hit_rate = sum(1 for row in rows if row["hit"]) / total
    mean_recall = sum(row["recall"] for row in rows) / total
    mrr = sum(row["rr"] for row in rows) / total
    return {
        "questions": len(rows),
        "hit_rate": round(hit_rate, 3),
        "mean_recall": round(mean_recall, 3),
        "mrr": round(mrr, 3),
        "gate": hit_rate >= hit_gate and mean_recall >= recall_gate,
        "hits": sum(1 for row in rows if row["hit"]),
        "hit_gate": hit_gate,
        "recall_gate": recall_gate,
    }
