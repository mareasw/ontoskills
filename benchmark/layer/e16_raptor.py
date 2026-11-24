"""E16: RAPTOR against the claim layer, paired on the question.

The protocol in `E6-PROTOCOL.md` §E16 fixes the comparison before the build ran:
same 200 questions, same gold facts, same character budgets, same cut, same
metric. This file only does the arithmetic — it reads the rows E14 and RAPTOR
already wrote and pairs them question by question, so no number here can be
produced by choosing a subset after the fact.

    python3 -m benchmark.layer.e16_raptor --layer .../pilot-work/layer
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
BUDGETS = (2000, 5000, 10000, 14830)
BOOTSTRAP = 4000


def raptor_by_budget(runs: Path) -> dict[str, dict[str, float]]:
    """RAPTOR's per-question coverage, one dict per budget."""
    out: dict[str, dict[str, float]] = {}
    for half in ("dev", "test"):
        payload = json.loads((runs / f"raptor-score-{half}.json").read_text(encoding="utf-8"))
        for budget, block in payload["per_question"].items():
            out.setdefault(budget, {}).update(block["coverage"])
    return out


def e14_by_name(runs: Path) -> dict[str, dict[str, float]]:
    """E14's per-question recall, keyed by the system name it published."""
    out: dict[str, dict[str, float]] = {}
    for half in ("dev", "test"):
        payload = json.loads((runs / f"e14-pareto-{half}.json").read_text(encoding="utf-8"))
        for name, rows in payload["per_question"].items():
            out.setdefault(name, {}).update({row["qid"]: row["recall"] for row in rows})
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
    raptor = raptor_by_budget(runs)
    systems = e14_by_name(runs)
    rng = np.random.default_rng(SEED)

    rivals = ["ours-statement", "ours-quote", "sentences", "floor"]
    table = []
    print(f"{'budget':>7} {'raptor':>8} " + " ".join(f"{name:>22}" for name in rivals))
    for budget in BUDGETS:
        key = str(budget)
        row = {
            "budget": budget,
            "raptor": round(statistics.mean(raptor[key].values()) * 100, 2),
            "comparisons": {},
        }
        cells = []
        for name in rivals:
            series = systems.get(f"{name}@{budget}")
            if series is None:
                cells.append(f"{'-':>22}")
                continue
            n, diff, low, high = paired(raptor[key], series, rng)
            row["comparisons"][name] = {
                "n": n,
                "other": round(statistics.mean(series[q] for q in raptor[key]) * 100, 2),
                "delta": round(diff, 2),
                "ci": [round(low, 2), round(high, 2)],
            }
            cells.append(f"{diff:+7.2f} [{low:+5.1f};{high:+5.1f}]")
        table.append(row)
        print(f"{budget:7d} {row['raptor']:7.2f}% " + " ".join(cells))

    out = args.json or runs / "e16-raptor-comparison.json"
    out.write_text(json.dumps({"seed": SEED, "rows": table}, indent=1), encoding="utf-8")
    print(f"written {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
