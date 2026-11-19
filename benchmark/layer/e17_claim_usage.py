"""E17: where the build money goes, and how much of the index a context ever reads.

The pilot knows what the build cost — 4,11 $ for 9 295 claims — and what a budget
returns. It does not know the join of the two: **how many of those claims any
answer ever uses**, and therefore how much of the bill bought text no context
will ever hold.

This is not a cost-optimisation experiment. It measures what the bill bought and
sorts every claim into one of three tiers:

* **unreachable** — never inside any question's candidate pool, so no ranker at
  this depth could have returned it for this workload;
* **reachable but unused** — inside a pool at least once, never chosen at any
  budget up to 14 830 characters;
* **used** — chosen and kept at some budget.

The cost of a document is read from the compiler's own cache, one usage record
per chunk call plus the conflict pass, priced at the declared table. A claim is
charged its document's cost divided by that document's claim count: the compiler
bills per document, so within a document there is no better attribution than
"these claims came out of this bill".

Everything is local: the encoder runs on the GPU, no model is called, nothing is
spent.

    python3 -m benchmark.layer.e17_claim_usage --layer .../pilot-work/layer
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.layer import claim_vectors, select  # noqa: E402
from benchmark.retrieval.dense import E5_LARGE_V2, SentenceEncoder  # noqa: E402

BUDGETS = (2000, 5000, 10000, 14830)
SEED = 20261118
DEPTH = 400
MAX_PICK = 200
PRICE_IN, PRICE_OUT = 0.15, 0.60
ENRICHMENT = 99999


def document_costs(layer: Path) -> dict[str, dict[str, float]]:
    """Per document, the metered bill split into extraction and conflict pass."""
    root = layer / "kb" / "cache"
    out: dict[str, dict[str, float]] = {}
    for folder in sorted(root.iterdir()):
        if not folder.is_dir():
            continue
        chunks = pairs = 0.0
        prompt = completion = 0
        for path in sorted(folder.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            usage = payload.get("usage") or {}
            tokens_in = int(usage.get("input_tokens") or 0)
            tokens_out = int(usage.get("output_tokens") or 0)
            prompt += tokens_in
            completion += tokens_out
            cost = tokens_in / 1e6 * PRICE_IN + tokens_out / 1e6 * PRICE_OUT
            if path.stem == str(ENRICHMENT):
                pairs += cost
            else:
                chunks += cost
        out[folder.name] = {
            "chunks_usd": round(chunks, 6),
            "conflicts_usd": round(pairs, 6),
            "usd": round(chunks + pairs, 6),
            "prompt_tokens": prompt,
            "completion_tokens": completion,
        }
    return out


def render(claim) -> str:
    return (claim.get("statement") or "").strip()


def kept_indices(texts: list[str], budget: int) -> list[int]:
    """`prefix_cut`'s decision, with the positions, so a kept claim stays a claim.

    Reading the kept count off `len(prefix_cut(...))` would misattribute every
    unit that follows a blank statement: the cut skips blanks without spending
    the budget, so positions and lengths drift apart. This mirrors the cut line
    for line and returns which claims were actually kept.
    """
    kept: list[int] = []
    used = 0
    for index, text in enumerate(texts):
        if not text:
            continue
        if kept and used + len(text) > budget:
            break
        kept.append(index)
        used += len(text)
    return kept


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--layer", type=Path, required=True)
    parser.add_argument("--half", default="all", choices=("dev", "test", "all"))
    parser.add_argument("--device", default=None)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)

    layer = args.layer
    selection = json.loads((layer / "corpus/selection.json").read_text(encoding="utf-8"))
    split = json.loads((layer / "runs/split.json").read_text(encoding="utf-8"))
    wanted = None if args.half == "all" else set(split[args.half])
    items = [
        item
        for item in selection["items"]
        if (wanted is None or item["qid"] in wanted) and item.get("gold_facts")
    ]

    corpus = select._corpus(layer / "kb", False)
    by_id = {claim["claim_id"]: claim for claim in corpus.claims}
    ids, matrix = claim_vectors.read(layer / "runs/claim-vectors.npz")
    row_of = {claim_id: index for index, claim_id in enumerate(ids)}
    encoder = SentenceEncoder(E5_LARGE_V2, device=args.device)

    pools: Counter[str] = Counter()
    used: dict[int, set[str]] = {budget: set() for budget in BUDGETS}
    chosen_per_question: dict[str, int] = {}

    for position, item in enumerate(items, 1):
        query = encoder.encode_query(item["text"])
        pool = corpus.search(item["text"], limit=DEPTH)
        for candidate in pool:
            pools[candidate.claim_id] += 1
        dense = select.dense_order(pool, row_of, matrix, query)
        chosen = select.cover(dense, corpus, item["text"], min(MAX_PICK, len(dense)))
        chosen_per_question[item["qid"]] = len(chosen)
        ordered = [(c.claim_id, render(by_id[c.claim_id])) for c in chosen if c.claim_id in by_id]
        texts = [text for _, text in ordered]
        for budget in BUDGETS:
            for index in kept_indices(texts, budget):
                used[budget].add(ordered[index][0])
        if position % 32 == 0:
            print(f"{position}/{len(items)}", flush=True)

    all_claims = set(by_id)
    ever_used = set().union(*used.values())
    reachable = set(pools)

    costs = document_costs(layer)
    per_doc_claims = Counter(claim["doc_id"] for claim in corpus.claims)
    cost_of_claim: dict[str, float] = {}
    for claim in corpus.claims:
        doc = claim["doc_id"]
        total = costs.get(doc, {}).get("usd", 0.0)
        count = per_doc_claims.get(doc, 0)
        cost_of_claim[claim["claim_id"]] = total / count if count else 0.0

    total_cost = sum(row["usd"] for row in costs.values())
    # The manifest bills the build, not the cache: a replayed chunk was paid for
    # and produced the claims already on disk. Attribution per claim therefore
    # uses the cache, and the replay is reported separately rather than smeared
    # across claims it did not create.
    manifest = json.loads((layer / "kb" / "manifest.json").read_text(encoding="utf-8"))
    billed = float(manifest.get("cost_usd") or 0.0)

    def spend(subset: set[str]) -> float:
        return sum(cost_of_claim.get(claim_id, 0.0) for claim_id in subset)

    # Documents that paid for a build and produced no verified claim: the money
    # is in the bill and belongs to no claim, so it cannot appear in any tier.
    paid_docs = set(costs)
    orphan_docs = paid_docs - {claim["doc_id"] for claim in corpus.claims}
    orphan_usd = sum(costs[doc]["usd"] for doc in orphan_docs)

    tiers = {
        "unreachable": all_claims - reachable,
        "reachable_unused": reachable - ever_used,
        "used": ever_used,
    }

    # Where the unused money sits: thin and uniform across the corpus, or piled
    # on documents no question ever reads. The two imply different levers, so the
    # per-document profile is recorded rather than summarised away.
    per_document = []
    for doc in sorted({claim["doc_id"] for claim in corpus.claims}):
        owned = [claim["claim_id"] for claim in corpus.claims if claim["doc_id"] == doc]
        per_document.append(
            {
                "doc": doc,
                "claims": len(owned),
                "used_5000": sum(1 for claim_id in owned if claim_id in used[5000]),
                "used_14830": sum(1 for claim_id in owned if claim_id in used[14830]),
                "usd": round(costs.get(doc, {}).get("usd", 0.0), 6),
            }
        )
    dead_docs = [row for row in per_document if row["used_14830"] == 0]

    print()
    print(f"questions {len(items)}  claims {len(all_claims)}  "
          f"documents {len(per_doc_claims)}  cache $ {total_cost:.4f}  "
          f"first pass $ {billed:.4f}  replay $ {max(0.0, total_cost - billed):.4f}")
    print(f"chosen per question, median {int(statistics.median(chosen_per_question.values()))}")
    print()
    print(f"{'budget':>7} {'used':>6} {'share':>7} {'docs':>5} {'$ used':>8}")
    for budget in BUDGETS:
        docs = {by_id[claim_id]["doc_id"] for claim_id in used[budget]}
        print(
            f"{budget:7d} {len(used[budget]):6d} "
            f"{len(used[budget]) / len(all_claims) * 100:6.2f}% {len(docs):5d} "
            f"{spend(used[budget]):8.4f}"
        )
    print()
    for name, subset in tiers.items():
        print(
            f"{name:20s} {len(subset):5d} claims  "
            f"{len(subset) / len(all_claims) * 100:6.2f}%  $ {spend(subset):.4f}"
        )
    print(
        f"{'no verified claim':20s} {len(orphan_docs):5d} docs    "
        f"{'':6s}   $ {orphan_usd:.4f}"
    )
    print(
        f"{'never used at 14.8k':20s} {len(dead_docs):5d} docs    "
        f"{'':6s}   $ {sum(row['usd'] for row in dead_docs):.4f}"
    )


    payload = {
        "questions": len(items),
        "seed": SEED,
        "depth": DEPTH,
        "max_pick": MAX_PICK,
        "claims": len(all_claims),
        "documents": len(per_doc_claims),
        "build_usd_attributed": round(total_cost, 4),
        "build_usd_billed": round(billed, 4),
        "build_usd_replay": round(max(0.0, total_cost - billed), 4),
        "build_usd_chunks": round(sum(row["chunks_usd"] for row in costs.values()), 4),
        "build_usd_conflicts": round(sum(row["conflicts_usd"] for row in costs.values()), 4),
        "chosen_median": int(statistics.median(chosen_per_question.values())),
        "by_budget": {
            str(budget): {
                "claims": len(used[budget]),
                "share": round(len(used[budget]) / len(all_claims) * 100, 2),
                "share_of_build": round(spend(used[budget]) / total_cost * 100, 2),
                "documents": len({by_id[claim_id]["doc_id"] for claim_id in used[budget]}),
                "usd_attributed": round(spend(used[budget]), 4),
            }
            for budget in BUDGETS
        },
        "tiers": {
            name: {
                "claims": len(subset),
                "share": round(len(subset) / len(all_claims) * 100, 2),
                "usd_attributed": round(spend(subset), 4),
            }
            for name, subset in tiers.items()
        },
        "documents_never_used": len(dead_docs),
        "usd_documents_never_used": round(sum(row["usd"] for row in dead_docs), 4),
        "per_document": per_document,
        "documents_paid": len(paid_docs),
        "documents_without_claim": len(orphan_docs),
        "usd_documents_without_claim": round(orphan_usd, 4),
        "usd_per_claim_mean": round(total_cost / len(all_claims), 6),
        "pool_visits_top": pools.most_common(10),
    }
    (layer / f"runs/e17-used-{args.half}.json").write_text(
        json.dumps({str(budget): sorted(used[budget]) for budget in BUDGETS}),
        encoding="utf-8",
    )
    out = args.json or layer / f"runs/e17-claim-usage-{args.half}.json"
    out.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(f"\nwritten {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
