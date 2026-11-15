"""The Phase-1 table: every run artifact, one summary, and what Phase 1 exists for.

Phase 1's only permitted outputs are the **baseline spread** and the **MDE** —
the width of the smallest difference this suite can see at this sample size. Both
are properties of the *pairs*, so they are computed from the per-question
receipts every run already writes, using the same `metrics.compare` the rest of
the protocol uses: paired bootstrap, Wilcoxon, Holm across datasets, and the MDE
reported next to each comparison so that "no difference" is a statement about
power rather than about a system.

    python3 benchmark/retrieval/summarize.py --json benchmark/retrieval/artifacts/phase1-summary.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.retrieval import metrics  # noqa: E402

RUNS = Path(__file__).resolve().parent / "runs"
# Lexical first: every comparison in this project is a delta against it.
SYSTEM_ORDER = ("bm25", "dense", "hybrid", "hybrid-rerank")
METRIC = "ndcg@k"


def load(runs: Path, split: str) -> list[dict]:
    artifacts = []
    for path in sorted(runs.glob(f"*-{split}.json")):
        artifact = json.loads(path.read_text(encoding="utf-8"))
        artifact["_path"] = path.name
        artifacts.append(artifact)
    return artifacts


def _values(artifact: dict, metric: str = METRIC) -> dict[str, float]:
    """Per-question values for one metric, by question id, in a stable shape.

    A question that does not support the metric is absent rather than zero: the
    comparison then uses the intersection, which is what a paired test means.
    """
    return {
        row["qid"]: float(row[metric])
        for row in artifact["per_question"]
        if metric in row
    }


def by_dataset(artifacts: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for artifact in artifacts:
        grouped.setdefault(artifact["dataset"], []).append(artifact)
    for rows in grouped.values():
        rows.sort(key=lambda row: SYSTEM_ORDER.index(row["system"]) if row["system"] in SYSTEM_ORDER else 99)
    return grouped


def summarize(artifacts: list[dict], reference: str = "bm25") -> dict:
    """The table, plus one comparison per dataset of its best system against the reference."""
    grouped = by_dataset(artifacts)
    table: dict[str, dict] = {}
    for dataset, rows in grouped.items():
        systems = {}
        for row in rows:
            metric = row["metrics"].get(METRIC)
            if metric is None:
                systems[row["system"]] = {"n": 0, "missing": True}
                continue
            systems[row["system"]] = {
                "n": metric["n"],
                "mean": round(metric["mean"], 4),
                "ci": [round(metric["ci_low"], 4), round(metric["ci_high"], 4)],
                "recall": round(row["metrics"]["recall@k"]["mean"], 4)
                if "recall@k" in row["metrics"]
                else None,
                "digest": row["digest"][:16],
                "seconds": row["seconds"],
                "retriever": row["config"].get("retriever"),
            }
        scored = {name: value for name, value in systems.items() if not value.get("missing")}
        spread = None
        if len(scored) >= 2:
            spread = round(max(v["mean"] for v in scored.values()) - min(v["mean"] for v in scored.values()), 4)
        table[dataset] = {"systems": systems, "spread": spread, "comparisons": {}}

        # Every system against the lexical reference, on the questions both scored.
        base = next((row for row in rows if row["system"] == reference), None)
        if base is None or reference not in scored:
            continue
        base_values = _values(base)
        for row in rows:
            if row["system"] == reference or METRIC not in row["metrics"]:
                continue
            values = _values(row)
            shared = sorted(set(values) & set(base_values))
            if len(shared) < 2:
                continue
            comparison = metrics.compare([values[q] for q in shared], [base_values[q] for q in shared])
            table[dataset]["comparisons"][row["system"]] = {
                "vs": reference,
                "n": comparison.n,
                "mean_difference": round(comparison.mean_difference, 4),
                "ci": [round(comparison.low, 4), round(comparison.high, 4)],
                "p_wilcoxon": comparison.p_wilcoxon,
                "mde": round(comparison.mde, 4),
            }

    # Holm across datasets, one family per competing system, because the datasets
    # are the multiple comparisons a reader would make at once.
    families: dict[str, dict[str, float]] = {}
    for dataset, entry in table.items():
        for system, comparison in entry["comparisons"].items():
            families.setdefault(system, {})[dataset] = comparison["p_wilcoxon"]
    for system, pvalues in families.items():
        adjusted = metrics.holm(pvalues)
        for dataset, value in adjusted.items():
            table[dataset]["comparisons"][system]["p_holm"] = value

    return {"metric": METRIC, "reference": reference, "datasets": table}


def format_table(summary: dict) -> str:
    lines = [
        f"Phase 1 reference table — {summary['metric']} on the dev split",
        "",
        "| dataset | system | n | mean [95% CI] | recall@10 | digest |",
        "|---|---|---|---|---|---|",
    ]
    for dataset, entry in summary["datasets"].items():
        for system, value in entry["systems"].items():
            if value.get("missing"):
                lines.append(f"| {dataset} | {system} | — | not computed | — | — |")
                continue
            lines.append(
                f"| {dataset} | {system} | {value['n']} | {value['mean']:.4f} "
                f"[{value['ci'][0]:.4f}, {value['ci'][1]:.4f}] | {value['recall']:.4f} | `{value['digest']}` |"
            )
    lines += ["", "| dataset | comparison | Δ nDCG@10 [95% CI] | MDE | p (Wilcoxon) | p (Holm) | spread |", "|---|---|---|---|---|---|---|"]
    for dataset, entry in summary["datasets"].items():
        for system, comparison in entry["comparisons"].items():
            lines.append(
                f"| {dataset} | {system} − {comparison['vs']} | {comparison['mean_difference']:+.4f} "
                f"[{comparison['ci'][0]:+.4f}, {comparison['ci'][1]:+.4f}] | {comparison['mde']:.4f} | "
                f"{comparison['p_wilcoxon']:.4f} | {comparison.get('p_holm', float('nan')):.4f} | "
                f"{entry['spread'] if entry['spread'] is not None else '—'} |"
            )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", type=Path, default=RUNS)
    parser.add_argument("--split", default="dev")
    parser.add_argument("--reference", default="bm25")
    parser.add_argument("--json", type=Path, help="write the summary here")
    args = parser.parse_args(argv)

    artifacts = load(args.runs, args.split)
    if not artifacts:
        raise SystemExit(f"no run artifacts in {args.runs} for split {args.split!r}")
    summary = summarize(artifacts, reference=args.reference)
    print(format_table(summary))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(summary, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
