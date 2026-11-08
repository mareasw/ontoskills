#!/usr/bin/env python3
"""Score a DocBench baseline run.

Automatic metrics are deliberately conservative heuristics; they are meant to
triage, not to replace blind human scoring. The CSV includes empty manual_*
columns for the final judgement.

Usage:
    python benchmark/docbench/score.py [--run DIR]
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import re
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from claims_model import quotes  # noqa: E402
GOLD = ROOT / "gold"
RUNS = ROOT / "runs" / "baselines"
PRIVATE = ROOT / "private"

SOURCES = {
    "D1": PRIVATE / "D1.txt",
    "D2": PRIVATE / "D2.txt",
    "D3": PRIVATE / "D3.txt",
    "D4": PRIVATE / "D4.txt",
}

STOP = set(
    "a an the of to in on for and or is are was were be been being that this these those "
    "with by as at from it its their they them we you your our not no if then than which who "
    "whom whose what when where why how".split()
)


def norm(text: str) -> str:
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    return re.sub(r"\s+", " ", text).strip().lower()


def content(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", norm(text)) if t not in STOP and len(t) > 1}


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def latest_run() -> Path:
    runs = sorted([p for p in RUNS.iterdir() if p.is_dir() and (p / "answers.jsonl").exists()])
    if not runs:
        raise SystemExit("no run with answers.jsonl found")
    return runs[-1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="", help="Run directory; defaults to the latest with answers")
    args = ap.parse_args()

    run = Path(args.run) if args.run else latest_run()
    answers = load_jsonl(run / "answers.jsonl")
    questions = {q["question_id"]: q for q in load_jsonl(GOLD / "questions.jsonl")}
    claims = {c["claim_id"]: c for c in load_jsonl(GOLD / "claims.jsonl")}
    sources = {d: p.read_text(encoding="utf-8", errors="ignore") for d, p in SOURCES.items()}

    rows = []
    for a in answers:
        q = questions[a["question_id"]]
        answer_norm = norm(a.get("answer", ""))
        abstained = answer_norm == "unknown" or answer_norm.startswith("unknown")
        gold_content = content(q.get("gold_answer", ""))
        answer_content = content(a.get("answer", ""))
        recall = len(gold_content & answer_content) / max(len(gold_content), 1) if gold_content else 0.0

        citation = a.get("citation", "")
        citation_norm = norm(citation)
        citation_present = bool(citation.strip())
        citation_supported = bool(citation_norm) and citation_norm in norm(sources[a["doc_id"]])

        gold_cites = [quote for cid in q.get("gold_claim_ids", []) if cid in claims for quote in quotes(claims[cid])]
        if set(a.get("claim_ids", [])) & set(q.get("gold_claim_ids", [])):
            citation_matches_gold = True
        elif citation_norm and gold_cites:
            citation_matches_gold = any(
                citation_norm in norm(g) or norm(g) in citation_norm for g in gold_cites
            )
        else:
            citation_matches_gold = False

        abstention_correct = abstained if q["type"] == "unanswerable" else not abstained

        rows.append({
            "condition": a["condition"],
            "question_id": a["question_id"],
            "doc_id": a["doc_id"],
            "type": q["type"],
            "question": q["question"],
            "gold_answer": q["gold_answer"],
            "answer": a.get("answer", ""),
            "citation": citation,
            "claim_ids": ",".join(a.get("claim_ids", [])),
            "abstained": abstained,
            "abstention_correct": abstention_correct,
            "answer_recall": round(recall, 3),
            "citation_present": citation_present,
            "citation_supported": citation_supported,
            "citation_matches_gold": citation_matches_gold,
            "input_tokens": a.get("input_tokens", 0),
            "output_tokens": a.get("output_tokens", 0),
            "reasoning_tokens": a.get("reasoning_tokens", 0),
            "latency_ms": a.get("latency_ms", 0),
            "manual_correct": "",
            "manual_citation": "",
            "notes": "",
        })

    out_csv = run / "scores.csv"
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    summary = {}
    for condition in sorted({r["condition"] for r in rows}):
        subset = [r for r in rows if r["condition"] == condition]
        answerable = [r for r in subset if r["type"] != "unanswerable"]
        summary[condition] = {
            "n": len(subset),
            "answer_recall_mean": round(statistics.mean([r["answer_recall"] for r in answerable]), 3) if answerable else 0.0,
            "citation_present_rate": round(sum(r["citation_present"] for r in subset) / len(subset), 3),
            "citation_supported_rate": round(sum(r["citation_supported"] for r in subset) / len(subset), 3),
            "citation_matches_gold_rate": round(sum(r["citation_matches_gold"] for r in subset) / len(subset), 3),
            "abstention_correct_rate": round(sum(r["abstention_correct"] for r in subset) / len(subset), 3),
            "avg_input_tokens": round(statistics.mean([r["input_tokens"] for r in subset]), 1),
            "avg_output_tokens": round(statistics.mean([r["output_tokens"] for r in subset]), 1),
            "avg_reasoning_tokens": round(statistics.mean([r["reasoning_tokens"] for r in subset]), 1),
            "avg_latency_ms": round(statistics.mean([r["latency_ms"] for r in subset]), 1),
        }

    (run / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    md = ["# DocBench run", "", f"Run: `{run.name}`", "", "| Condition | n | answer recall | citation present | citation supported | citation matches gold | abstention correct | input tok | output tok | reasoning tok | latency ms |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for condition, s in summary.items():
        md.append(
            f"| {condition} | {s['n']} | {s['answer_recall_mean']:.1%} | {s['citation_present_rate']:.1%} | "
            f"{s['citation_supported_rate']:.1%} | {s['citation_matches_gold_rate']:.1%} | "
            f"{s['abstention_correct_rate']:.1%} | {s['avg_input_tokens']:.0f} | {s['avg_output_tokens']:.0f} | "
            f"{s['avg_reasoning_tokens']:.0f} | {s['avg_latency_ms']:.0f} |"
        )
    md += ["", "Automatic metrics are triage only. Fill the `manual_*` columns in `scores.csv` before deciding.", ""]
    (run / "summary.md").write_text("\n".join(md), encoding="utf-8")

    print((run / "summary.md").read_text(encoding="utf-8"))
    print(f"wrote {out_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
