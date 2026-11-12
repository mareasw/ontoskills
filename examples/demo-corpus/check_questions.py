#!/usr/bin/env python3
"""Check the demo's exit criterion on a compiled knowledge base.

The criterion is structural, not a score: each question must answer with claims
from **at least two documents**, and every citation must name the document.
Run it after `ontocore ingest`; it exits non-zero if any question is answered by
a single document, so the check can gate a release.

Usage:
    python examples/demo-corpus/check_questions.py --kb examples/demo-corpus/kb
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb", type=Path, default=HERE / "kb", help="Compiled knowledge base")
    ap.add_argument(
        "--questions", type=Path, default=HERE / "questions.txt", help="One question per line"
    )
    ap.add_argument("--limit", type=int, default=12, help="Max citations per question")
    ap.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    args = ap.parse_args()

    from compiler.documents.ask import Corpus, ask
    from compiler.documents.store import KnowledgeBase

    kb = KnowledgeBase(args.kb)
    claims = kb.claims()
    if not claims:
        print(f"{args.kb}: no claims.jsonl; run `ontocore ingest` first", file=sys.stderr)
        return 2

    questions = [
        line.strip()
        for line in args.questions.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    corpus = Corpus(claims, kb.documents())

    rows = []
    for question in questions:
        answer = ask(question, corpus, limit=args.limit)
        rows.append(
            {
                "question": question,
                "documents": answer.documents,
                "citations": len(answer.citations),
                "claims": [
                    {
                        "claim_id": citation.claim_id,
                        "doc_id": citation.doc_id,
                        "page": citation.page,
                        "section": citation.section_path,
                        "url": citation.url,
                    }
                    for citation in answer.citations
                ],
                "tensions": [
                    {
                        "topic": tension.topic,
                        "values": [value for value, _ in tension.values],
                    }
                    for tension in answer.tensions
                ],
                "ok": len(answer.documents) >= 2,
            }
        )

    passed = all(row["ok"] for row in rows)

    if args.json:
        print(json.dumps({"ok": passed, "questions": rows}, ensure_ascii=False, indent=1))
        return 0 if passed else 1

    for row in rows:
        mark = "ok  " if row["ok"] else "FAIL"
        print(f"{mark} {row['question']}")
        print(
            f"     {row['citations']} claim(s) from {len(row['documents'])} document(s): "
            + ", ".join(row["documents"])
        )
        for tension in row["tensions"]:
            print(f"     tension on {tension['topic']}: " + " vs ".join(tension["values"]))
    print()
    print(
        f"{len(rows)} question(s): "
        + ("all cite at least two documents" if passed else "some cite a single document")
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
