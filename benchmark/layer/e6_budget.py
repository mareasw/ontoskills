"""E6: the same ranker and the floor at an identical character cap.

The budget is a rendering, not a selector: the frozen ranker orders the same
claim path and this cuts the prefix that fits, exactly as `score.py` cuts the
floor's passages. The floor's rows are the already
measured `floor.budget-*.score.json`, restricted to the same half. Differences
are paired per question, with a percentile bootstrap over questions.

The whole curve is published, on every budget, and no budget is chosen after the
fact: a family read once, not five looks.

    python3 -m benchmark.layer.e6_budget --layer .../pilot-work/layer --half test
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.layer import claim_vectors, select  # noqa: E402
from benchmark.layer.budget import prefix_cut  # noqa: E402
from benchmark.retrieval.dense import E5_LARGE_V2, SentenceEncoder  # noqa: E402
from benchmark.retrieval.metrics import answer_fact_coverage  # noqa: E402

BUDGETS = (5000, 10000, 14830, 20000, 45000)
SEED = 20261118


def floor_rows(score, half_set):
    out = {}
    for row in score["per_question"]:
        if row["qid"] in half_set and row.get("answer_fact_coverage") is not None:
            out[row["qid"]] = row["answer_fact_coverage"]
    return out


def boot(diff, rng):
    arr = np.asarray(diff, dtype=float)
    means = [arr[rng.integers(0, len(arr), len(arr))].mean() for _ in range(4000)]
    return np.percentile(means, [2.5, 97.5])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--layer", type=Path, default=Path("/tmp/opencode/layer"))
    parser.add_argument("--half", default="test", choices=("dev", "test"))
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--device", default=None)
    args = parser.parse_args(argv)

    layer = args.layer
    selection = json.loads((layer / "corpus/selection.json").read_text(encoding="utf-8"))
    split = json.loads((layer / "runs/split.json").read_text(encoding="utf-8"))
    half = set(split[args.half])
    items = [i for i in selection["items"] if i["qid"] in half and i.get("gold_facts")]

    corpus = select._corpus(layer / "kb", False)
    ids, matrix = claim_vectors.read(layer / "runs/claim-vectors.npz")
    row_of = {claim_id: index for index, claim_id in enumerate(ids)}
    encoder = SentenceEncoder(E5_LARGE_V2, device=args.device)

    floors = {
        budget: floor_rows(
            json.loads((layer / f"runs/floor.budget-{budget}.score.json").read_text()), half
        )
        for budget in BUDGETS
    }

    # The path is computed once per question: a curve over five budgets is one
    # ordering cut five times, not five rankers.
    paths: dict[str, list[str]] = {}
    for item in items:
        query = encoder.encode_query(item["text"])
        pool = corpus.search(item["text"], limit=select.DEPTH)
        dense = select.dense_order(pool, row_of, matrix, query)
        chosen = select.cover(dense, corpus, item["text"], 100)
        paths[item["qid"]] = [c.quote or "" for c in chosen]

    rng = np.random.default_rng(SEED)
    table = []
    for budget in BUDGETS:
        values, chars = {}, []
        for item in items:
            quotes = prefix_cut(paths[item["qid"]], budget)
            values[item["qid"]] = answer_fact_coverage(item["gold_facts"], quotes)
            chars.append(sum(len(q) for q in quotes))
        floor = floors[budget]
        diff = [values[q] - floor[q] for q in values if q in floor]
        lo, hi = boot(diff, rng)
        row = {
            "budget": budget,
            "questions": len(values),
            "coverage": round(statistics.mean(values.values()) * 100, 2),
            "characters_median": int(statistics.median(chars)),
            "floor_coverage": round(statistics.mean(floor.values()) * 100, 2),
            "floor_characters_median": int(
                statistics.median(
                    r["chars"] for r in json.loads(
                        (layer / f"runs/floor.budget-{budget}.score.json").read_text()
                    )["per_question"] if r["qid"] in half
                )
            ),
            "paired_diff": round(statistics.mean(diff) * 100, 2),
            "ci_low": round(float(lo) * 100, 2),
            "ci_high": round(float(hi) * 100, 2),
        }
        table.append(row)
        print(
            f"budget {budget:6d}  ours {row['coverage']:6.2f}% ({row['characters_median']} ch)  "
            f"floor {row['floor_coverage']:6.2f}% ({row['floor_characters_median']} ch)  "
            f"d {row['paired_diff']:+6.2f} [{row['ci_low']:+.1f}; {row['ci_high']:+.1f}]",
            flush=True,
        )

    payload = {"half": args.half, "questions": len(items), "seed": SEED, "rows": table}
    out = args.json or layer / f"runs/e6-budget-{args.half}.json"
    out.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(f"written {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
