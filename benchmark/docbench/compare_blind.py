#!/usr/bin/env python3
"""Compare a blind re-score against the original manual scoring.

Reads the unblinding key, joins the independent verdicts to the original
scores.csv, and reports agreement plus every disagreement with its evidence.
The key is only read here, after the reviewers have finished.

Usage:
    python benchmark/docbench/compare_blind.py [--run DIR] [--blind DIR]
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_RUN = ROOT / "runs" / "baselines" / "20261107T140843Z"

# Known defects in the gold set. The blind reviewer had no way to know, so these
# cases are excluded from the comparison instead of counted for or against it.
DEFECTS = {"D4-Q10"}


def norm(value: str) -> str:
    return "yes" if value.startswith("yes") else "no"


def cit_norm(value: str) -> str:
    """Map the v1 vocabulary (yes/partial/none) onto the blind one (yes/partial/no)."""
    if value.startswith("yes"):
        return "yes"
    if value.startswith("partial"):
        return "partial"
    return "no"


def load_verdicts(blind: Path) -> dict[str, dict]:
    verdicts = {}
    for path in sorted(blind.glob("verdicts_D*.jsonl")):
        for line in path.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                verdicts[row["case_id"]] = row
    return verdicts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default=str(DEFAULT_RUN), help="Run directory with scores.csv")
    ap.add_argument("--blind", default="", help="Blind directory (default: <run>/blind)")
    args = ap.parse_args()

    run = Path(args.run)
    blind = Path(args.blind) if args.blind else run / "blind"

    key = json.loads((blind / "key.json").read_text())
    verdicts = load_verdicts(blind)
    missing = [c for c in key if c not in verdicts]
    if missing:
        raise SystemExit(f"missing verdicts for {len(missing)} cases: {missing[:5]}")

    original = {}
    with (run / "scores.csv").open() as fh:
        for row in csv.DictReader(fh):
            original[(row["condition"], row["question_id"])] = row

    agreement: Counter = Counter()
    flips = []
    by_cond: dict[str, Counter] = defaultdict(Counter)

    for case_id, meta in key.items():
        cond, qid = meta["condition"], meta["question_id"]
        orig = original[(cond, qid)]
        verdict = verdicts[case_id]

        o_correct = "excluded" if orig["manual_correct"] == "excluded" else norm(orig["manual_correct"])
        o_cit = "excluded" if o_correct == "excluded" else cit_norm(orig["manual_citation"])
        n_correct = verdict["answer_correct"]
        n_cit = verdict["citation"]

        if qid in DEFECTS:
            agreement["defect_excluded"] += 1
            continue

        if o_correct == n_correct:
            agreement["same_correct"] += 1
        else:
            agreement["diff_correct"] += 1

        if o_cit == n_cit:
            agreement["same_citation"] += 1
        elif not orig["citation"].strip() and o_correct == "yes" and orig["type"] == "unanswerable":
            # A correct abstention has nothing to cite. The original pass scored
            # that as "none"; the blind pass scored it "yes". Convention, not a
            # disagreement about the answer.
            agreement["convention_citation"] += 1
        else:
            agreement["real_diff_citation"] += 1

        by_cond[cond]["n"] += 1
        by_cond[cond]["blind_correct"] += n_correct == "yes"
        by_cond[cond]["blind_cit_yes"] += n_cit == "yes"
        by_cond[cond]["blind_unsupported"] += verdict["unsupported"] == "yes"

        if o_correct != n_correct:
            flips.append({
                "case": case_id, "cond": cond, "qid": qid,
                "axis": "answer", "original": o_correct, "blind": n_correct,
                "note": verdict["note"], "answer": orig["answer"][:300],
                "gold": orig["gold_answer"][:200],
            })
        if o_cit != n_cit and not (not orig["citation"].strip() and o_correct == "yes" and orig["type"] == "unanswerable"):
            flips.append({
                "case": case_id, "cond": cond, "qid": qid,
                "axis": "citation", "original": o_cit, "blind": n_cit,
                "note": verdict["note"], "citation": orig["citation"][:300],
            })

    print("=== agreement with original manual scoring (39 scored questions x 3) ===")
    for key_name in ("same_correct", "diff_correct", "same_citation", "convention_citation",
                     "real_diff_citation", "defect_excluded"):
        print(f"{key_name}: {agreement[key_name]}")

    print("\n=== blind results by condition (excluding D4-Q10) ===")
    print(f"{'cond':4} {'n':>3} {'correct':>8} {'cit=yes':>8} {'unsupported':>12}")
    for cond in ("B0", "B1", "B2"):
        c = by_cond[cond]
        print(f"{cond:4} {c['n']:>3} {c['blind_correct']:>5}/{c['n']:<2} {c['blind_cit_yes']:>5}/{c['n']:<2} "
              f"{c['blind_unsupported']:>12}")

    print(f"\n=== {len(flips)} disagreements ===")
    for flip in flips:
        print(json.dumps(flip, ensure_ascii=False))

    out = run / "blind_review.json"
    out.write_text(json.dumps({
        "agreement": dict(agreement),
        "by_condition": {k: dict(v) for k, v in by_cond.items()},
        "disagreements": flips,
        "excluded": sorted(DEFECTS),
        "convention": "citation on answered questions only; empty citation on a correct abstention is not a failure",
    }, indent=1))
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
