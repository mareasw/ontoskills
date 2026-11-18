"""E11: a reranker trained for relevance, over the same pool and the same budget.

The frozen order is a bi-encoder's: question and claim embedded apart, compared
by cosine. A cross-encoder reads the pair together, and the one already tried in
the pilot (`ms-marco-MiniLM-L-6-v2`) lost 1,9 pp because it was trained on web
search passages. This rung uses `BAAI/bge-reranker-v2-m3`, a 0,6 B multilingual
reranker, pinned by revision and run locally.

Two texts per candidate are scored, because the product can return either: the
claim's statement and its first quote. Each gets its own order and its own
budget curve. The tail beyond the reranked head keeps the frozen order, so a
reranker never promotes a claim it did not read.

Everything is local: one model, no key, no API spend.

    python3 -m benchmark.layer.e11_crossencoder --layer .../pilot-work/layer --half dev
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.layer import claim_vectors, select  # noqa: E402
from benchmark.retrieval.dense import E5_LARGE_V2, SentenceEncoder  # noqa: E402
from benchmark.retrieval.metrics import answer_fact_coverage  # noqa: E402

MODEL_ID = "BAAI/bge-reranker-v2-m3"
BUDGETS = (2000, 5000, 10000, 14830)
SEED = 20261118
UNITS = ("quote", "statement")
DEPTHS = (60, 100)


def render(claim, unit: str) -> str:
    statement = (claim.get("statement") or "").strip()
    quotes = [q for q in ((e.get("quote") or "").strip() for e in claim.get("evidence") or []) if q]
    if unit == "quote":
        return quotes[0] if quotes else statement
    if unit == "statement":
        return statement
    raise ValueError(unit)


def fill(units, budget):
    total, kept = 0, []
    for text in units:
        if not text:
            continue
        if total + len(text) > budget:
            if kept:
                continue
            return [text]
        kept.append(text)
        total += len(text)
    return kept


def paired(diff, rng):
    arr = np.asarray(diff, dtype=float)
    means = [arr[rng.integers(0, len(arr), len(arr))].mean() for _ in range(4000)]
    return np.percentile(means, [2.5, 97.5])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--layer", type=Path, default=Path("/tmp/opencode/layer"))
    parser.add_argument("--half", default="dev", choices=("dev", "test", "all"))
    parser.add_argument("--model", default=MODEL_ID)
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--device", default=None)
    parser.add_argument("--precision", default="fp32", choices=("fp32", "fp16"))
    parser.add_argument("--limit", type=int, default=0, help="questions; 0 is all")
    args = parser.parse_args(argv)

    from sentence_transformers import CrossEncoder

    import torch

    layer = args.layer
    selection = json.loads((layer / "corpus/selection.json").read_text(encoding="utf-8"))
    split = json.loads((layer / "runs/split.json").read_text(encoding="utf-8"))
    wanted = None if args.half == "all" else set(split[args.half])
    items = [
        i for i in selection["items"]
        if (wanted is None or i["qid"] in wanted) and i.get("gold_facts")
    ]
    if args.limit:
        items = items[: args.limit]

    corpus = select._corpus(layer / "kb", False)
    by_id = {claim["claim_id"]: claim for claim in corpus.claims}
    ids, matrix = claim_vectors.read(layer / "runs/claim-vectors.npz")
    row_of = {claim_id: index for index, claim_id in enumerate(ids)}
    # One card, two models, and they never share it. The query encoder runs first
    # at the frozen precision its claim vectors were built with — fp32, the same
    # text and the same model — because a query encoded differently would move the
    # baseline every paired difference is measured against. Its vectors are kept,
    # the model is dropped, the card is emptied, and only then the reranker loads.
    # Precision of the reranker is declared, not chosen per run.
    gpu = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    dtype = torch.float32 if args.precision == "fp32" else torch.float16
    encoder = SentenceEncoder(E5_LARGE_V2, device=gpu)
    queries = {
        item["qid"]: encoder.encode_query(item["text"])
        for item in items
    }
    del encoder
    import gc

    gc.collect()
    if gpu == "cuda":
        torch.cuda.empty_cache()
    scorer = CrossEncoder(
        args.model,
        max_length=256,
        device=gpu,
        model_kwargs={"torch_dtype": dtype} if gpu == "cuda" else None,
    )

    started = time.time()
    results: dict[str, dict[str, dict[str, float]]] = {}
    for position, item in enumerate(items, 1):
        query = queries[item["qid"]]
        pool = corpus.search(item["text"], limit=select.DEPTH)
        dense = select.dense_order(pool, row_of, matrix, query)
        base = select.cover(dense, corpus, item["text"], len(dense))
        results[item["qid"]] = {"cover": {unit: [by_id.get(c.claim_id) for c in base]
                                         for unit in UNITS}}
        for depth in DEPTHS:
            head = list(dense[:depth])
            for unit in UNITS:
                texts = [(by_id.get(c.claim_id) or {}) for c in head]
                logits = scorer.predict(
                    [(item["text"], render(claim, unit)) for claim in texts],
                    batch_size=16,
                    show_progress_bar=False,
                )
                order = sorted(range(len(head)), key=lambda i: (-float(logits[i]), i))
                ordered = [head[i] for i in order] + list(dense[depth:])
                results[item["qid"]][f"ce{depth}"] = (
                    results[item["qid"]].get(f"ce{depth}") or {}
                )
                results[item["qid"]][f"ce{depth}"][unit] = [
                    by_id.get(c.claim_id) for c in ordered
                ]
        print(f"{position:3d}/{len(items)} {item['qid']}  {time.time() - started:6.1f}s",
              file=sys.stderr, flush=True)

    rng = np.random.default_rng(SEED)
    table = []
    for unit in UNITS:
        for budget in BUDGETS:
            per_order = {}
            for name in results[items[0]["qid"]]:
                values, chars, counts = {}, [], []
                for item in items:
                    claims = results[item["qid"]][name][unit]
                    kept = fill([render(claim, unit) for claim in claims if claim], budget)
                    values[item["qid"]] = answer_fact_coverage(item["gold_facts"], kept)
                    chars.append(sum(len(k) for k in kept))
                    counts.append(len(kept))
                per_order[name] = {
                    "coverage": round(statistics.mean(values.values()) * 100, 2),
                    "characters_median": int(statistics.median(chars)),
                    "units_median": int(statistics.median(counts)),
                    "values": values,
                }
            base_values = per_order["cover"]["values"]
            for name, row in per_order.items():
                if name == "cover":
                    continue
                diff = [row["values"][q] - base_values[q] for q in base_values]
                lo, hi = paired(diff, rng)
                row["delta"] = round(statistics.mean(diff) * 100, 2)
                row["ci_low"] = round(float(lo) * 100, 2)
                row["ci_high"] = round(float(hi) * 100, 2)
            print(f"--- {unit} @ {budget} ---")
            for name in per_order:
                row = per_order[name]
                extra = (
                    f"  d {row['delta']:+6.2f} [{row['ci_low']:+.1f}; {row['ci_high']:+.1f}]"
                    if "delta" in row else ""
                )
                print(
                    f"  {name:10s} {row['coverage']:6.2f}%  chars {row['characters_median']:5d}"
                    f"  units {row['units_median']:3d}{extra}"
                )
            table.append({
                "unit": unit,
                "budget": budget,
                "orders": {
                    name: {k: v for k, v in row.items() if k != "values"}
                    for name, row in per_order.items()
                },
            })

    out = args.json or layer / f"runs/e11-crossencoder-{args.half}.json"
    out.write_text(
        json.dumps(
            {
                "half": args.half,
                "questions": len(items),
                "seed": SEED,
                "model": args.model,
                "precision": args.precision,
                "depth": list(DEPTHS),
                "seconds": round(time.time() - started, 1),
                "rows": table,
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"written {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
