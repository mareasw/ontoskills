#!/usr/bin/env python3
"""Measure retrieval on the demo gold set.

    python3 examples/demo-corpus/eval_retrieval.py --kb examples/demo-corpus/kb
    python3 examples/demo-corpus/eval_retrieval.py --kb kb --semantic --vectors kb

--validate checks that every expected fragment is quoted by at least one claim;
an expectation no claim can satisfy is a broken gold row, not a retrieval miss.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from compiler.documents.ask import Corpus, ask
from compiler.documents.eval import HIT_GATE, RECALL_GATE, evaluate, load_gold, score
from compiler.documents.text import norm
from compiler.documents.store import KnowledgeBase


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kb", type=Path, default=Path("examples/demo-corpus/kb"))
    parser.add_argument("--gold", type=Path, default=Path("examples/demo-corpus/gold/questions.jsonl"))
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--validate", action="store_true", help="only check the gold set against the KB")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--semantic", action="store_true")
    parser.add_argument(
        "--force-semantic",
        action="store_true",
        help="fuse the embedding ranking even when the corpus is not in a language the model knows",
    )
    parser.add_argument(
        "--min-hits",
        type=int,
        default=None,
        help="report the gate against an absolute number of hits instead of the demo's rate",
    )
    parser.add_argument("--recall-gate", type=float, default=RECALL_GATE)
    args = parser.parse_args()

    kb = KnowledgeBase(args.kb)
    claims = kb.claims()
    gold = load_gold(args.gold)

    if args.validate:
        bad = 0
        for row in gold:
            for expected in row["expected"]:
                fragment = norm(expected["quote"])
                # The metric reads the citation's quote, which is evidence[0]:
                # a fragment only the context item carries cannot score.
                hit = any(
                    expected["doc_id"] == claim["doc_id"]
                    and fragment in norm((claim["evidence"] or [{}])[0].get("quote") or "")
                    for claim in claims
                )
                if not hit:
                    bad += 1
                    print(f"{row['id']}: no claim quotes {expected['quote'][:70]!r}")
        print(f"{len(gold)} question(s), {bad} unsatisfiable expectation(s)")
        return 0 if bad == 0 else 1

    corpus = Corpus(claims, kb.documents(), verdicts=kb.verifier())
    if args.semantic or args.force_semantic:
        from compiler.documents.vector import embedder_for

        languages = set((kb.manifest().get("languages") or {}).values())
        enabled = corpus.enable_semantic(
            kb.vectors(), embedder_for(kb), None if args.force_semantic else languages
        )
        if not enabled:
            print("semantic ranking skipped: the corpus language is not one the model knows")

    rows = []
    for row in gold:
        result = ask(row["question"], corpus, limit=args.limit)
        ranked = [citation.__dict__ for citation in result.citations]
        rows.append(score(row, ranked))

    hit_gate = HIT_GATE if args.min_hits is None else args.min_hits / (len(rows) or 1)
    summary = evaluate(rows, hit_gate=hit_gate, recall_gate=args.recall_gate)
    if args.json:
        print(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=1))
    else:
        for row in rows:
            flag = "ok  " if row["hit"] else "MISS"
            print(f"{flag} {row['id']} hit={int(row['hit'])} recall={row['recall']:.2f} rr={row['rr']:.2f}  {row['question'][:70]}")
            for missed in row["missed"]:
                print(f"       missed: {missed}")
        bar = (
            f" (bar {args.min_hits})" if args.min_hits is not None else ""
        )
        print(
            f"{summary['hits']}/{summary['questions']} hit@12{bar}, "
            f"recall@12 {summary['mean_recall']:.3f}, MRR@12 {summary['mrr']:.3f} "
            f"-> gate {'PASS' if summary['gate'] else 'FAIL'}"
        )
    return 0 if summary["gate"] else 1


if __name__ == "__main__":
    sys.exit(main())
