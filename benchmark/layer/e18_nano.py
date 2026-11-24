"""E18: Nano-GraphRAG against the rows already on the table, paired by question.

The protocol fixed the modes, the corpus, the model and the metric before the
build ran. This file only does the arithmetic, so no number here can be produced
by choosing a subset after the fact.

Two things it deliberately does *not* do:

* it does not cut Nano's answer to a character budget — a generated answer has no
  budget dimension, exactly like the GraphRAG row, and its length is its own;
* it does not pool `local` and `naive` into one score. They are different query
  shapes, and a mixed number would describe neither.

    python3 -m benchmark.layer.e18_nano --layer .../pilot-work/layer
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

SEED = 20261118
BOOTSTRAP = 4000
RIVALS = ("graphrag", "ours-statement@5000", "floor@5000", "sentences@5000")


def nano_rows(runs: Path, mode: str) -> dict[str, dict]:
    payload = json.loads((runs / f"nanographrag-score-{mode}-all.json").read_text(encoding="utf-8"))
    return {row["qid"]: row for row in payload["per_question"]}


def e14_rows(runs: Path) -> dict[str, dict[str, dict]]:
    """Every E14 system, keyed by name, with each question's row."""
    out: dict[str, dict[str, dict]] = {}
    for half in ("dev", "test"):
        payload = json.loads((runs / f"e14-pareto-{half}.json").read_text(encoding="utf-8"))
        for name, rows in payload["per_question"].items():
            block = out.setdefault(name, {})
            for row in rows:
                block[row["qid"]] = row
    return out


def paired(a: dict[str, float], b: dict[str, float], rng) -> tuple[int, float, float, float]:
    common = sorted(set(a) & set(b))
    diff = np.array([a[q] - b[q] for q in common])
    draws = [diff[rng.integers(0, len(diff), len(diff))].mean() for _ in range(BOOTSTRAP)]
    low, high = np.percentile(draws, [2.5, 97.5])
    return len(common), diff.mean() * 100, float(low) * 100, float(high) * 100


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--layer", type=Path, required=True)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)

    runs = args.layer / "runs"
    systems = e14_rows(runs)
    rng = np.random.default_rng(SEED)

    table = []
    print(f"{'mode':7s} {'recall':>7} {'strict':>7} {'prec':>6} {'F1':>6} {'ref%':>6} {'tok':>6}  rivals")
    for mode in ("local", "global", "naive"):
        if not (runs / f"nanographrag-score-{mode}-all.json").exists():
            continue
        rows = nano_rows(runs, mode)
        recall = {qid: row["recall"] for qid, row in rows.items()}
        refused = sum(1 for row in rows.values() if row["refused"])
        answered = [row for row in rows.values() if not row["refused"]]
        entry = {
            "mode": mode,
            "questions": len(rows),
            "recall_answered": round(statistics.mean(r["recall"] for r in answered) * 100, 2)
            if answered
            else 0.0,
            "recall_strict": round(statistics.mean(recall.values()) * 100, 2),
            "precision_strict": round(statistics.mean(r["precision"] for r in rows.values()) * 100, 2),
            "f1_strict": round(statistics.mean(r["f1"] for r in rows.values()) * 100, 2),
            "refusal_rate": round(refused / len(rows) * 100, 2),
            "tokens_median": int(statistics.median(r["tokens"] for r in answered)) if answered else 0,
            "comparisons": {},
        }
        cells = []
        for name in RIVALS:
            rival = systems.get(name)
            if not rival:
                continue
            other = {qid: row["recall"] for qid, row in rival.items()}
            n, diff, low, high = paired(recall, other, rng)
            entry["comparisons"][name] = {
                "n": n,
                "other": round(statistics.mean(other[q] for q in recall) * 100, 2),
                "delta": round(diff, 2),
                "ci": [round(low, 2), round(high, 2)],
            }
            cells.append(f"{name.split('@')[0]} {diff:+6.2f} [{low:+5.1f};{high:+5.1f}]")
        table.append(entry)
        print(
            f"{mode:7s} {entry['recall_answered']:7.2f} {entry['recall_strict']:7.2f} "
            f"{entry['precision_strict']:6.2f} {entry['f1_strict']:6.2f} "
            f"{entry['refusal_rate']:6.2f} {entry['tokens_median']:6d}  " + "  ".join(cells)
        )

    out = args.json or runs / "e18-nano-comparison.json"
    out.write_text(json.dumps({"seed": SEED, "rows": table}, indent=1), encoding="utf-8")
    print(f"written {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
