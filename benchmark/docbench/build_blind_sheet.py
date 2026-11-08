#!/usr/bin/env python3
"""Build a blind re-score sheet from a DocBench run.

Strips the condition label and any condition-revealing field (claim_ids),
assigns an opaque case id, and writes one sheet per document so independent
reviewers can score without knowing which baseline produced the answer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path

FIELDS_KEPT = ("question_id", "doc_id", "answer", "citation")


def opaque_id(seed: str) -> str:
    return "C" + hashlib.sha256(seed.encode()).hexdigest()[:8]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True, help="run directory with answers.jsonl")
    ap.add_argument("--gold", required=True, help="questions.jsonl")
    ap.add_argument("--out", required=True, help="output directory for sheets")
    ap.add_argument("--seed", default="docbench-blind-2026")
    args = ap.parse_args()

    run = Path(args.run)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    answers = [json.loads(line) for line in (run / "answers.jsonl").read_text().splitlines() if line.strip()]
    gold = {
        row["question_id"]: row
        for row in (json.loads(line) for line in Path(args.gold).read_text().splitlines() if line.strip())
    }

    rng = random.Random(args.seed)
    cases = []
    for row in answers:
        g = gold[row["question_id"]]
        case = {k: row[k] for k in FIELDS_KEPT}
        case["case_id"] = opaque_id(f"{args.seed}:{row['condition']}:{row['question_id']}")
        case["question"] = g["question"]
        case["question_type"] = g.get("type", "")
        case["gold_answer"] = g["gold_answer"]
        cases.append(case)

    rng.shuffle(cases)

    # Per-document sheets, ordered by case id (already shuffled) so nothing
    # about the original grouping leaks.
    by_doc: dict[str, list[dict]] = {}
    for case in cases:
        by_doc.setdefault(case["doc_id"], []).append(case)

    for doc_id, rows in sorted(by_doc.items()):
        path = out / f"cases_{doc_id}.jsonl"
        with path.open("w") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"{path}: {len(rows)} cases")

    with (out / "cases_all.jsonl").open("w") as fh:
        for row in cases:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"{out / 'cases_all.jsonl'}: {len(cases)} cases")

    # The key that unblinds afterwards. Never handed to a reviewer.
    key = {}
    for row in answers:
        key[opaque_id(f"{args.seed}:{row['condition']}:{row['question_id']}")] = {
            "condition": row["condition"],
            "question_id": row["question_id"],
        }
    (out / "key.json").write_text(json.dumps(key, indent=1, sort_keys=True))
    print(f"{out / 'key.json'}: {len(key)} entries (do not share)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
