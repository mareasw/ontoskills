"""E10: one slot per aspect, instead of a greedy walk over the question's terms.

The diagnosis behind this rung: a question has 4,03 gold facts, the ten claims
`cover` picks touch 3,38 of them, and 0,66 facts are missed *entirely* — no
chosen claim carries a single token of them. `cover` asks which claim adds the
most question terms, and question terms are shared across aspects, so it can
spend all ten slots on one aspect of a question whose facts sit in two.

Four orders are declared here, each of them a full ordering of the pool (so the
character budget, not the ranker, decides how many units are returned), and the
same claim path is rendered as the quote or as the statement:

* ``cover`` — the frozen baseline, unchanged, kept for the paired difference;
* ``aspectN`` — the top sixty candidates clustered into N groups by their claim
  vectors (spherical k-means, fixed seed), then read round-robin: the best of
  every cluster first, then the second of every cluster, and so on. One slot per
  aspect before any aspect gets two;
* ``doc-round`` — the same round-robin with the document as the aspect. Cheaper
  than clustering and blind to paraphrase, but a section is a real aspect;
* ``aspectN-cover`` — the cluster order recomputed inside each round by the
  baseline's own greedy, so the diversity is the cluster's and the relevance is
  still the question's terms.

Everything is local. No model is called, no key is used, nothing is spent.

    python3 -m benchmark.layer.e10_aspect --layer .../pilot-work/layer --half dev
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

BUDGETS = (2000, 5000, 10000, 14830)
SEED = 20261118
UNITS = ("quote", "statement")
CLUSTERS = (8, 10, 20)
HEAD = 60


def render(claim, unit: str) -> str:
    statement = (claim.get("statement") or "").strip()
    quotes = [q for q in ((e.get("quote") or "").strip() for e in claim.get("evidence") or []) if q]
    if unit == "quote":
        return quotes[0] if quotes else statement
    if unit == "statement":
        return statement
    raise ValueError(unit)


def spherical_kmeans(matrix: np.ndarray, n_clusters: int, rng) -> np.ndarray:
    """Cosine k-means with k-means++ seeding; deterministic for a fixed rng."""
    n = matrix.shape[0]
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    unit = matrix / np.maximum(norms, 1e-12)

    chosen = [int(rng.integers(0, n))]
    for _ in range(1, min(n_clusters, n)):
        similarity = np.max(unit[chosen] @ unit.T, axis=0)
        weight = np.maximum(1.0 - similarity, 0.0) ** 2
        total = weight.sum()
        if total <= 0:
            free = [index for index in range(n) if index not in chosen]
            pick = int(free[0]) if free else chosen[0]
        else:
            pick = int(rng.choice(n, p=weight / total))
        chosen.append(pick)
    centres = unit[chosen].copy()

    labels = np.zeros(n, dtype=int)
    for _ in range(12):
        scores = unit @ centres.T
        labels = np.argmax(scores, axis=1)
        for cluster in range(centres.shape[0]):
            members = unit[labels == cluster]
            if len(members):
                centres[cluster] = members.mean(axis=0) / max(
                    np.linalg.norm(members.mean(axis=0)), 1e-12
                )
    return labels


def round_robin(groups: list[list[int]]) -> list[int]:
    """Best of every group, then the second of every group, and so on."""
    out: list[int] = []
    rounds = max((len(group) for group in groups), default=0)
    for depth in range(rounds):
        for group in groups:
            if depth < len(group):
                out.append(group[depth])
    return out


def order_aspect(citations, matrix, row_of, clusters, head=HEAD, cover_first=False, corpus=None,
                 question=""):
    """Cluster the head, then interleave: one slot per aspect before a second."""
    n = min(head, len(citations))
    if n == 0:
        return []
    rows, present = [], []
    for index in range(n):
        row = row_of.get(citations[index].claim_id)
        if row is None:
            continue
        rows.append(index)
        present.append(row)
    if len(set(present)) < clusters:
        clusters = max(2, len(set(present)))
    labels = spherical_kmeans(matrix[np.asarray(present)], clusters, np.random.default_rng(SEED))

    grouped: dict[int, list[int]] = {}
    for position, label in zip(rows, labels):
        grouped.setdefault(int(label), []).append(position)
    groups = sorted(grouped.values(), key=lambda group: group[0])
    if cover_first and corpus is not None:
        ordered = []
        for group in groups:
            position_of = {citations[index].claim_id: index for index in group}
            picked = select.cover(
                [citations[index] for index in group], corpus, question, k=len(group)
            )
            ordered.append([position_of[citation.claim_id] for citation in picked])
        groups = ordered
    return [citations[i] for i in round_robin(groups)] + [
        citations[i] for i in range(n, len(citations))
    ]


def order_doc(citations, head=HEAD):
    """Round-robin over documents: a section is an aspect nobody had to infer."""
    n = min(head, len(citations))
    grouped: dict[str, list[int]] = {}
    for index in range(n):
        grouped.setdefault(citations[index].doc_id, []).append(index)
    groups = sorted(grouped.values(), key=lambda group: group[0])
    return [citations[i] for i in round_robin(groups)] + [
        citations[i] for i in range(n, len(citations))
    ]


def paired(diff, rng):
    arr = np.asarray(diff, dtype=float)
    means = [arr[rng.integers(0, len(arr), len(arr))].mean() for _ in range(4000)]
    return np.percentile(means, [2.5, 97.5])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--layer", type=Path, required=True)
    parser.add_argument("--half", default="dev", choices=("dev", "test", "all"))
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--device", default=None)
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

    orders: dict[str, dict[str, list]] = {}
    for item in items:
        query = encoder.encode_query(item["text"])
        pool = corpus.search(item["text"], limit=select.DEPTH)
        dense = select.dense_order(pool, row_of, matrix, query)
        base = select.cover(dense, corpus, item["text"], len(dense))
        plan = {"cover": base}
        for clusters in CLUSTERS:
            plan[f"aspect{clusters}"] = order_aspect(dense, matrix, row_of, clusters)
            plan[f"aspect{clusters}-cover"] = order_aspect(
                dense, matrix, row_of, clusters, cover_first=True, corpus=corpus,
                question=item["text"],
            )
        plan["doc-round"] = order_doc(dense)
        orders[item["qid"]] = plan

    rng = np.random.default_rng(SEED)
    table = []
    for unit in UNITS:
        for budget in BUDGETS:
            per_order = {}
            for name in orders[items[0]["qid"]]:
                values, chars, counts = {}, [], []
                for item in items:
                    rendered = [render(by_id.get(c.claim_id), unit)
                                for c in orders[item["qid"]][name] if by_id.get(c.claim_id)]
                    kept = prefix_cut(rendered, budget)
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
                    f"  {name:18s} {row['coverage']:6.2f}%  chars {row['characters_median']:5d}"
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

    out = args.json or layer / f"runs/e10-aspect-{args.half}.json"
    out.write_text(
        json.dumps({"half": args.half, "questions": len(items), "seed": SEED, "rows": table},
                   indent=1),
        encoding="utf-8",
    )
    print(f"written {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
