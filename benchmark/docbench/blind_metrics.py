#!/usr/bin/env python3
"""Recompute DocBench metrics under a single, explicit citation convention.

The original manual pass scored an empty citation as "none", which mixes two
different things: a missing citation on an answered question (a failure) and a
correct abstention that has nothing to cite (not a failure). This script
separates them so the blind verdicts and the original verdicts can be compared
on the same basis.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_RUN = ROOT / "runs" / "baselines" / "20261107T140843Z"

ap = argparse.ArgumentParser()
ap.add_argument("--run", default=str(DEFAULT_RUN), help="Run directory")
ap.add_argument("--blind", default="", help="Blind directory (default: <run>/blind)")
args = ap.parse_args()

RUN = Path(args.run)
BLIND = Path(args.blind) if args.blind else RUN / "blind"

key = json.loads((BLIND / "key.json").read_text())
verdicts = {}
for path in sorted(BLIND.glob("verdicts_D*.jsonl")):
    for line in path.read_text().splitlines():
        if line.strip():
            row = json.loads(line)
            verdicts[row["case_id"]] = row

gold = {}
for line in (ROOT / "gold" / "questions.jsonl").read_text().splitlines():
    if line.strip():
        row = json.loads(line)
        gold[row["question_id"]] = row

DEFECTS = {"D4-Q10"}
UNANSWERABLE = {qid for qid, row in gold.items() if row.get("type") == "unanswerable"}

stats = defaultdict(Counter)
for case_id, meta in key.items():
    qid, cond = meta["question_id"], meta["condition"]
    if qid in DEFECTS:
        continue
    v = verdicts[case_id]
    s = stats[cond]
    s["n"] += 1
    s["correct"] += v["answer_correct"] == "yes"
    s["unsupported"] += v["unsupported"] == "yes"
    if qid in UNANSWERABLE:
        s["unanswerable"] += 1
        s["unanswerable_correct"] += v["answer_correct"] == "yes"
        continue
    # Answerable question: a citation is required.
    s["answerable"] += 1
    s["cit_yes"] += v["citation"] == "yes"
    s["cit_partial"] += v["citation"] == "partial"
    s["cit_no"] += v["citation"] == "no"

# Only report the conditions this run actually contains: a single-condition
# run (e.g. B2 with compiled claims) has no B0/B1 to compare against.
present = [cond for cond in ("B0", "B1", "B2") if stats.get(cond) and stats[cond]["n"]]

print(f"{'cond':4} {'n':>3} {'correct':>9} {'unsup':>6} {'ans':>4} {'cit_yes':>8} {'cit%':>6} {'partial':>8} {'no':>3}")
for cond in present:
    s = stats[cond]
    pct = 100 * s["cit_yes"] / s["answerable"] if s["answerable"] else 0.0
    print(f"{cond:4} {s['n']:>3} {s['correct']:>4}/{s['n']:<4} {s['unsupported']:>6} "
          f"{s['answerable']:>4} {s['cit_yes']:>4}/{s['answerable']:<3} {pct:>5.1f}% {s['cit_partial']:>8} {s['cit_no']:>3}")

print("\nunanswerable questions (correct abstention / total)")
for cond in present:
    s = stats[cond]
    print(f"  {cond}: {s['unanswerable_correct']}/{s['unanswerable']}")

p = lambda cond, field: 100 * cond[field] / cond["answerable"]
if "B2" in present:
    print("\ndeltas on citation quality (answerable questions only)")
    for other in ("B1", "B0"):
        if other in present:
            print(f"  B2 - {other}: {p(stats['B2'],'cit_yes') - p(stats[other],'cit_yes'):+.1f} pp")

out = RUN / "blind_summary.json"
out.write_text(json.dumps({
    "convention": "citation scored only on answerable questions; empty citation on a correct abstention is not a failure",
    "by_condition": {k: dict(v) for k, v in stats.items()},
    "excluded": sorted(DEFECTS),
}, indent=1))
print(f"\nwrote {out}")
