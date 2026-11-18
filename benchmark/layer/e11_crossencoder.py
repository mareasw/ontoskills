"""E11: a reranker trained for relevance, over the same pool and the same budget.

The frozen order is a bi-encoder's: question and claim embedded apart, compared
by cosine. A cross-encoder reads the pair together, and the one already tried in
the pilot (`ms-marco-MiniLM-L-6-v2`) lost 1,9 pp because it was trained on web
search passages. This rung uses `BAAI/bge-reranker-v2-m3`, a 0,6 B multilingual
reranker, run locally at a declared precision.

Two texts per candidate are scored, because the product can return either: the
claim's statement and its first quote. Each gets its own order and its own budget
curve. The tail beyond the reranked head keeps the frozen order, so a reranker
never promotes a claim it did not read.

The work is split in two phases. The first one touches the GPU and is expensive;
it writes one row per question, flushed before the next call, and a resumed run
never rescores a question already on disk. The second one is arithmetic over
those rows — the same `prefix_cut` the floor is scored with — and can be rerun as
often as a table changes.

Everything is local: one model, no key, no API spend.

    python3 -m benchmark.layer.e11_crossencoder --layer .../pilot-work/layer --half dev
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.layer import claim_vectors, select  # noqa: E402
from benchmark.layer.budget import prefix_cut  # noqa: E402
from benchmark.retrieval.dense import E5_LARGE_V2, SentenceEncoder  # noqa: E402
from benchmark.retrieval.metrics import answer_fact_coverage  # noqa: E402

MODEL_ID = "BAAI/bge-reranker-v2-m3"
BUDGETS = (2000, 5000, 10000, 14830)
SEED = 20261118
UNITS = ("quote", "statement")
MAX_LENGTH = 256


def render(claim, unit: str) -> str:
    statement = (claim.get("statement") or "").strip()
    quotes = [q for q in ((e.get("quote") or "").strip() for e in claim.get("evidence") or []) if q]
    if unit == "quote":
        return quotes[0] if quotes else statement
    if unit == "statement":
        return statement
    raise ValueError(unit)


def paired(diff, rng):
    arr = np.asarray(diff, dtype=float)
    means = [arr[rng.integers(0, len(arr), len(arr))].mean() for _ in range(4000)]
    return np.percentile(means, [2.5, 97.5])


def model_revision(model_id: str) -> str:
    """The commit the weights came from, not the name someone typed."""
    try:
        from huggingface_hub import snapshot_download

        path = snapshot_download(model_id, local_files_only=True)
        return Path(path).name
    except Exception:
        return "unresolved"


def read_rows(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    rows: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        rows[row["qid"]] = row
    return rows


def append_row(path: Path, row: dict) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def tables(rows: list[dict], items: list[dict], rng) -> list[dict]:
    """Every unit, every budget, paired against the frozen order on the same pool."""
    table = []
    for unit in UNITS:
        for budget in BUDGETS:
            per_order = {}
            for name in ("cover", "ce"):
                values, chars, counts = {}, [], []
                for item in items:
                    order = rows[item["qid"]][name][unit]
                    kept = prefix_cut(order, budget)
                    values[item["qid"]] = answer_fact_coverage(item["gold_facts"], kept)
                    chars.append(sum(len(k) for k in kept))
                    counts.append(len(kept))
                per_order[name] = {
                    "coverage": round(statistics.mean(values.values()) * 100, 2),
                    "characters_median": int(statistics.median(chars)),
                    "units_median": int(statistics.median(counts)),
                    "values": values,
                }
            base = per_order["cover"]["values"]
            diff = [per_order["ce"]["values"][q] - base[q] for q in base]
            lo, hi = paired(diff, rng)
            per_order["ce"]["delta"] = round(statistics.mean(diff) * 100, 2)
            per_order["ce"]["ci_low"] = round(float(lo) * 100, 2)
            per_order["ce"]["ci_high"] = round(float(hi) * 100, 2)
            print(f"--- {unit} @ {budget} ---")
            for name, row in per_order.items():
                extra = (
                    f"  d {row['delta']:+6.2f} [{row['ci_low']:+.1f}; {row['ci_high']:+.1f}]"
                    if "delta" in row else ""
                )
                print(
                    f"  {name:6s} {row['coverage']:6.2f}%  chars {row['characters_median']:5d}"
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
    return table


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--layer", type=Path, required=True)
    parser.add_argument("--half", default="dev", choices=("dev", "test", "all"))
    parser.add_argument("--model", default=MODEL_ID)
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--device", default=None)
    parser.add_argument("--precision", default="fp32", choices=("fp32", "fp16"))
    parser.add_argument("--limit", type=int, default=0, help="questions; 0 is all")
    parser.add_argument("--fresh", action="store_true", help="rescore what is already on disk")
    parser.add_argument("--score-only", action="store_true", help="rebuild the table from rows")
    args = parser.parse_args(argv)

    import gc

    import torch
    from sentence_transformers import CrossEncoder

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

    orders_path = layer / f"runs/e11-orders.{args.half}.jsonl"
    if args.fresh and orders_path.exists():
        orders_path.unlink()
    done = {} if args.score_only else read_rows(orders_path)
    todo = [item for item in items if item["qid"] not in done]
    if done:
        print(f"{len(done)} questions already scored, {len(todo)} to go", file=sys.stderr)

    corpus = select._corpus(layer / "kb", False)
    by_id = {claim["claim_id"]: claim for claim in corpus.claims}
    ids, matrix = claim_vectors.read(layer / "runs/claim-vectors.npz")
    row_of = {claim_id: index for index, claim_id in enumerate(ids)}

    if todo:
        # One card, two models, and they never share it. The query encoder runs
        # first at the frozen precision its claim vectors were built with — fp32,
        # same model, same text — because a query encoded differently would move
        # the baseline every paired difference is measured against. Its vectors
        # are kept, the model is dropped, the card is emptied, and only then the
        # reranker loads. Its precision is declared, not chosen per run.
        gpu = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
        dtype = torch.float32 if args.precision == "fp32" else torch.float16
        encoder = SentenceEncoder(E5_LARGE_V2, device=gpu)
        queries = {item["qid"]: encoder.encode_query(item["text"]) for item in todo}
        del encoder
        gc.collect()
        if gpu == "cuda":
            torch.cuda.empty_cache()
        scorer = CrossEncoder(
            args.model,
            max_length=MAX_LENGTH,
            device=gpu,
            model_kwargs={"dtype": dtype} if gpu == "cuda" else None,
        )

        started = time.time()
        for position, item in enumerate(todo, 1):
            query = queries[item["qid"]]
            pool = corpus.search(item["text"], limit=select.DEPTH)
            dense = select.dense_order(pool, row_of, matrix, query)
            base = select.cover(dense, corpus, item["text"], len(dense))
            claims = [by_id.get(c.claim_id) for c in dense]
            base_claims = [by_id.get(c.claim_id) for c in base]
            row = {"qid": item["qid"], "cover": {}, "ce": {}}
            for unit in UNITS:
                row["cover"][unit] = [render(claim, unit) for claim in base_claims if claim]
                texts = [render(claim, unit) for claim in claims if claim]
                logits = scorer.predict(
                    [(item["text"], text) for text in texts],
                    batch_size=16,
                    show_progress_bar=False,
                )
                order = sorted(range(len(texts)), key=lambda i: (-float(logits[i]), i))
                row["ce"][unit] = [texts[i] for i in order]
            append_row(orders_path, row)
            print(
                f"{position:3d}/{len(todo)} {item['qid']}  {time.time() - started:7.1f}s",
                file=sys.stderr,
                flush=True,
            )
        del scorer
        gc.collect()
        if gpu == "cuda":
            torch.cuda.empty_cache()

    rows = read_rows(orders_path)
    missing = [item["qid"] for item in items if item["qid"] not in rows]
    if missing:
        raise SystemExit(f"{len(missing)} questions have no row: run without --score-only")

    table = tables(rows, items, np.random.default_rng(SEED))
    out = args.json or layer / f"runs/e11-crossencoder-{args.half}.json"
    out.write_text(
        json.dumps(
            {
                "half": args.half,
                "questions": len(items),
                "seed": SEED,
                "model": args.model,
                "revision": model_revision(args.model),
                "precision": args.precision,
                "max_length": MAX_LENGTH,
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
