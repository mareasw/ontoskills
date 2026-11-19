"""E9: what a claim returns, at an identical character budget.

The selection is the frozen one — dense order, `cover`, budget-determined cut —
and only the *text* of each chosen unit changes. A claim carries a distilled
statement (80 characters median) and the verbatim quotes it was built from (382
characters median): returning the statement fits four to five times more claims
in the same budget, and the question is whether the distillation keeps the tokens
that carry the answer.

Four units are declared, and the same claim path is rendered in each:

* ``quote`` — the first verbatim quotation, the product's current unit;
* ``statement`` — the claim's own sentence;
* ``statement+quote`` — both, statement first;
* ``all-quotes`` — the statement and every quotation the claim carries.

Everything is local: no model is called, no key is used, nothing is spent.

    python3 -m benchmark.layer.e9_rendering --layer .../pilot-work/layer --half dev
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
from benchmark.retrieval.metrics import answer_fact_coverage, answer_fact_support  # noqa: E402

BUDGETS = (2000, 5000, 10000, 14830)
SEED = 20261118
UNITS = ("quote", "statement", "statement+quote", "all-quotes")


def render(claim, unit: str) -> str:
    statement = (claim.get("statement") or "").strip()
    quotes = [q for q in ((e.get("quote") or "").strip() for e in claim.get("evidence") or []) if q]
    if unit == "quote":
        return quotes[0] if quotes else statement
    if unit == "statement":
        return statement
    if unit == "statement+quote":
        return "\n".join(part for part in (statement, quotes[0] if quotes else "") if part)
    if unit == "all-quotes":
        return "\n".join(part for part in [statement, *quotes] if part)
    raise ValueError(unit)


def paired(diff, rng):
    arr = np.asarray(diff, dtype=float)
    means = [arr[rng.integers(0, len(arr), len(arr))].mean() for _ in range(4000)]
    return np.percentile(means, [2.5, 97.5])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--layer", type=Path, default=Path("/tmp/opencode/layer"))
    parser.add_argument("--half", default="dev", choices=("dev", "test", "all"))
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--device", default=None)
    parser.add_argument("--depth", type=int, default=select.DEPTH, help="claim pool depth")
    parser.add_argument(
        "--max-pick", type=int, default=200,
        help="how many claims the greedy may choose; 200 fills 16k of statements",
    )
    args = parser.parse_args(argv)

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

    paths = {}
    for item in items:
        query = encoder.encode_query(item["text"])
        pool = corpus.search(item["text"], limit=args.depth)
        dense = select.dense_order(pool, row_of, matrix, query)
        chosen = select.cover(dense, corpus, item["text"], min(args.max_pick, len(dense)))
        paths[item["qid"]] = [by_id.get(c.claim_id) for c in chosen]

    rng = np.random.default_rng(SEED)
    table = []
    raw: dict[str, dict[str, dict[str, dict[str, float]]]] = {}
    for budget in BUDGETS:
        per_unit = {}
        for unit in UNITS:
            values, supports, chars, counts = {}, {}, [], []
            for item in items:
                rendered = [render(claim, unit) for claim in paths[item["qid"]] if claim]
                kept = prefix_cut(rendered, budget)
                values[item["qid"]] = answer_fact_coverage(item["gold_facts"], kept)
                supports[item["qid"]] = answer_fact_support(item["gold_facts"], kept)
                chars.append(sum(len(k) for k in kept))
                counts.append(len(kept))
            per_unit[unit] = {
                "coverage": round(statistics.mean(values.values()) * 100, 2),
                "support": round(statistics.mean(supports.values()) * 100, 2),
                "characters_median": int(statistics.median(chars)),
                "units_median": int(statistics.median(counts)),
                "values": values,
                "supports": supports,
            }
        base = per_unit["quote"]["values"]
        base_support = per_unit["quote"]["supports"]
        for unit in UNITS:
            if unit == "quote":
                continue
            diff = [per_unit[unit]["values"][q] - base[q] for q in base]
            lo, hi = paired(diff, rng)
            per_unit[unit]["delta"] = round(statistics.mean(diff) * 100, 2)
            per_unit[unit]["ci_low"] = round(float(lo) * 100, 2)
            per_unit[unit]["ci_high"] = round(float(hi) * 100, 2)
            sdiff = [per_unit[unit]["supports"][q] - base_support[q] for q in base_support]
            slo, shi = paired(sdiff, rng)
            per_unit[unit]["support_delta"] = round(statistics.mean(sdiff) * 100, 2)
            per_unit[unit]["support_ci_low"] = round(float(slo) * 100, 2)
            per_unit[unit]["support_ci_high"] = round(float(shi) * 100, 2)

        print(f"--- budget {budget} ---")
        for unit in UNITS:
            row = per_unit[unit]
            extra = (
                f"  d {row['delta']:+6.2f} [{row['ci_low']:+.1f}; {row['ci_high']:+.1f}]"
                if "delta" in row else ""
            )
            support = (
                f"  support {row['support']:6.2f}%  ds {row['support_delta']:+6.2f}"
                f" [{row['support_ci_low']:+.1f}; {row['support_ci_high']:+.1f}]"
                if "support_delta" in row else f"  support {row['support']:6.2f}%"
            )
            print(
                f"  {unit:16s} {row['coverage']:6.2f}%  "
                f"chars {row['characters_median']:5d}  units {row['units_median']:3d}"
                f"{support}{extra}"
            )
        for unit in UNITS:
            raw.setdefault(unit, {})[str(budget)] = {
                "coverage": per_unit[unit]["values"],
                "support": per_unit[unit]["supports"],
            }
        table.append({
            budget: {
                unit: {
                    k: v for k, v in per_unit[unit].items()
                    if k not in ("values", "supports")
                }
                for unit in UNITS
            }
        })

    out = args.json or layer / f"runs/e9-rendering-{args.half}.json"
    out.with_suffix(".values.json").write_text(
        json.dumps({"half": args.half, "seed": SEED, "questions": len(items), "values": raw},
                   indent=1),
        encoding="utf-8",
    )
    out.write_text(json.dumps({"half": args.half, "questions": len(items), "seed": SEED,
                               "rows": table}, indent=1), encoding="utf-8")
    print(f"written {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
