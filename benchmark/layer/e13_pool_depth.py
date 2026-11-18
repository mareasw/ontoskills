"""E13: how deep the claim pool has to be before the statement row stops binding.

The statement row exhausts itself at 9 524 characters: one hundred claims at
eighty characters each, and more budget cannot buy a hundred-and-first claim. So
the losses at ten and fourteen thousand characters were measured against a pool
that had already run out, while the sentence floor had thirty thousand units to
spend. That is a defect of the rung, not a property of the layer, and this script
separates the two.

The pool comes from the lexical search over the claims; its depth is the knob.
At each depth the frozen order is rebuilt (`dense_order`), `cover` orders the pool
and the character budget cuts the prefix — exactly the pipeline the product runs,
with one number changed.

Everything is local: no model is called, no key is used, nothing is spent.

    python3 -m benchmark.layer.e13_pool_depth --layer .../pilot-work/layer --half dev
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.layer import claim_vectors, select  # noqa: E402
from benchmark.layer.budget import prefix_cut  # noqa: E402
from benchmark.retrieval.dense import E5_LARGE_V2, SentenceEncoder  # noqa: E402
from benchmark.retrieval.metrics import answer_fact_coverage, answer_fact_support  # noqa: E402

BUDGETS = (2000, 5000, 10000, 14830)
DEPTHS = (100, 200, 400, 800)
SEED = 20261118
UNITS = ("quote", "statement")
# Two hundred claims fit sixteen thousand characters of statements; asking the
# greedy for more than the budget can hold is work that cannot change a number.
MAX_PICK = 200


def render(claim, unit: str) -> str:
    statement = (claim.get("statement") or "").strip()
    quotes = [q for q in ((e.get("quote") or "").strip() for e in claim.get("evidence") or []) if q]
    if unit == "quote":
        return quotes[0] if quotes else statement
    if unit == "statement":
        return statement
    raise ValueError(unit)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--layer", type=Path, required=True)
    parser.add_argument("--half", default="dev", choices=("dev", "test", "all"))
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--device", default=None)
    parser.add_argument(
        "--depths", default="", help="comma-separated override, for the single-config test read"
    )
    args = parser.parse_args(argv)
    depths = tuple(int(d) for d in args.depths.split(",") if d.strip()) or DEPTHS

    layer = args.layer
    selection = json.loads((layer / "corpus/selection.json").read_text(encoding="utf-8"))
    split = json.loads((layer / "runs/split.json").read_text(encoding="utf-8"))
    wanted = None if args.half == "all" else set(split[args.half])
    items = [
        i for i in selection["items"]
        if (wanted is None or i["qid"] in wanted) and i.get("gold_facts")
    ]

    corpus = select._corpus(layer / "kb", False)
    by_id = {claim["claim_id"]: claim for claim in corpus.claims}
    ids, matrix = claim_vectors.read(layer / "runs/claim-vectors.npz")
    row_of = {claim_id: index for index, claim_id in enumerate(ids)}
    encoder = SentenceEncoder(E5_LARGE_V2, device=args.device)

    paths: dict[int, dict[str, dict[str, list[str]]]] = {}
    for item in items:
        query = encoder.encode_query(item["text"])
        paths[item["qid"]] = {}
        for depth in depths:
            pool = corpus.search(item["text"], limit=depth)
            dense = select.dense_order(pool, row_of, matrix, query)
            chosen = select.cover(dense, corpus, item["text"], min(MAX_PICK, len(dense)))
            paths[item["qid"]][depth] = {
                unit: [render(by_id.get(c.claim_id), unit) for c in chosen if by_id.get(c.claim_id)]
                for unit in UNITS
            }

    raw: dict[str, dict[str, dict[str, dict[str, dict[str, float]]]]] = {}
    table = []
    for unit in UNITS:
        for depth in depths:
            for budget in BUDGETS:
                values, supports, chars, counts = {}, {}, [], []
                for item in items:
                    kept = prefix_cut(paths[item["qid"]][depth][unit], budget)
                    values[item["qid"]] = answer_fact_coverage(item["gold_facts"], kept)
                    supports[item["qid"]] = answer_fact_support(item["gold_facts"], kept)
                    chars.append(sum(len(k) for k in kept))
                    counts.append(len(kept))
                row = {
                    "unit": unit,
                    "depth": depth,
                    "budget": budget,
                    "coverage": round(statistics.mean(values.values()) * 100, 2),
                    "support": round(statistics.mean(supports.values()) * 100, 2),
                    "characters_median": int(statistics.median(chars)),
                    "units_median": int(statistics.median(counts)),
                }
                table.append(row)
                raw.setdefault(unit, {}).setdefault(str(depth), {})[str(budget)] = {
                    "coverage": values,
                    "support": supports,
                }
            print(
                f"{unit:9s} depth {depth:4d}  budget {budget:6d}  "
                f"{row['coverage']:6.2f}% (support {row['support']:5.2f}%)  "
                f"chars {row['characters_median']:5d}  units {row['units_median']:3d}",
                flush=True,
            )

    out = args.json or layer / f"runs/e13-pool-depth-{args.half}.json"
    out.write_text(
        json.dumps(
            {
                "half": args.half,
                "questions": len(items),
                "seed": SEED,
                "depths": list(depths),
                "max_pick": MAX_PICK,
                "rows": table,
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    out.with_suffix(".values.json").write_text(
        json.dumps({"half": args.half, "seed": SEED, "questions": len(items), "values": raw},
                   indent=1),
        encoding="utf-8",
    )
    print(f"written {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
