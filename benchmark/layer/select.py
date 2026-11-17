"""E1 and E2 of `RANKER.md`: better selection, and a better order to select from.

E0 showed that the lexical top 100 contains enough claims for 87,6 % on dev,
while the product returns 63,6 %. The first repair therefore does not need a
model, a vector or a rebuild: it needs a chooser. Two choosers are declared here,
and both are deterministic integer/float arithmetic that the Rust read path can
port without an ADR.

* **`cover`** — greedy set cover over the question's own content terms, weighted
  by the corpus IDF. At each step it takes the claim whose *returned quote* adds
  the most question terms not yet covered. It is the cheapest hypothesis of the
  diagnosis: the ten claims are individually relevant but collectively redundant,
  and the facts are carried by the terms the question already names.
* **`mmr`** — maximal marginal relevance over the same pool: relevance is the
  product's BM25 score, redundancy is the Jaccard overlap of the quotes' token
  sets, with an optional cap on claims per document. It is the conventional
  answer to the same problem, and it is here so E1 is not one idea measured
  against nothing.

E1 plateaus at 71,2 % on dev, sixteen points under the pool's ceiling, so E2 adds
a second *order* over the same pool: cosine between the question and the claim
vectors of `claim_vectors.py`, or the reciprocal rank fusion of that order with
BM25, and the same two selectors applied to it. The pool, the k and the volume do
not move; only the order does. The `query:` prefix is how e5 was trained, and a
`passage:` run is kept as a control because a library with no query prefix cannot
do better than that.

    python3 -m benchmark.layer.select --selection /tmp/layer/corpus/selection.json \\
        --kb /tmp/layer/kb --answers /tmp/layer/runs/ontoskills.answers.jsonl \\
        --split /tmp/layer/runs/split.json --half dev --json /tmp/layer/runs/e1-dev.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.layer import rank  # noqa: E402
from benchmark.layer.answers import _corpus  # noqa: E402
from benchmark.retrieval.metrics import answer_fact_coverage  # noqa: E402

DEPTH = 100
K = 10
LAMBDAS = (0.3, 0.5, 0.7, 0.9)
CAPS = (None, 4, 2)


def _terms(text: str) -> list[str]:
    """The product's own query tokenisation: content words, cut to their stem key."""
    from compiler.documents.ask import _content, _key

    return [_key(term) for term in _content(text)]


def _quote_terms(quote: str) -> set[str]:
    from compiler.documents.ask import _content, _key

    return {_key(term) for term in _content(quote)}


def plain(citations, corpus, question, k=K, **_):
    return list(citations[:k])


def cover(citations, corpus, question, k=K, **_):
    """Greedy: at each step, the claim that adds the most uncovered question terms."""
    terms = _terms(question)
    weights = {}
    for term in terms:
        weights.setdefault(term, corpus._idf(term))
    present = [_quote_terms(citation.quote) for citation in citations]

    picked: list[int] = []
    taken: set[int] = set()
    remaining = dict(weights)
    for _ in range(min(k, len(citations))):
        best, best_gain = None, 0.0
        for index, terms_here in enumerate(present):
            if index in taken:
                continue
            gain = sum(weight for term, weight in remaining.items() if term in terms_here)
            if gain > best_gain:
                best, best_gain = index, gain
        if best is None:
            break
        picked.append(best)
        taken.add(best)
        for term in present[best]:
            remaining.pop(term, None)

    # A pool whose quotes share no question term still answers with the ranker's
    # own order: the chooser must never return fewer than k claims when the pool
    # has them, or it would be rewarded for refusing.
    for index in range(len(citations)):
        if len(picked) >= k:
            break
        if index not in taken:
            picked.append(index)
            taken.add(index)
    return [citations[index] for index in picked]


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def mmr(citations, corpus, question, k=K, lam=0.7, cap=None, **_):
    """Maximal marginal relevance, with an optional per-document cap."""
    if not citations:
        return []
    scores = [citation.score for citation in citations]
    low, high = min(scores), max(scores)
    relevance = [
        (score - low) / (high - low) if high > low else 0.0 for score in scores
    ]
    sets = [_quote_terms(citation.quote) for citation in citations]
    picked: list[int] = []
    taken: set[int] = set()
    per_doc: Counter[str] = Counter()

    for _ in range(min(k, len(citations))):
        best, best_value = None, float("-inf")
        for index, citation in enumerate(citations):
            if index in taken:
                continue
            if cap is not None and per_doc[citation.doc_id] >= cap:
                continue
            similarity = max((_jaccard(sets[index], sets[other]) for other in picked), default=0.0)
            value = lam * relevance[index] - (1 - lam) * similarity
            if value > best_value:
                best, best_value = index, value
        if best is None:
            break
        picked.append(best)
        taken.add(best)
        per_doc[citations[best].doc_id] += 1

    # The cap is a preference, not a refusal: fill the ten from the pool order
    # when every remaining document is at its cap.
    for index in range(len(citations)):
        if len(picked) >= k:
            break
        if index not in taken:
            picked.append(index)
            taken.add(index)
    return [citations[index] for index in picked]


def variants(lambdas=LAMBDAS, caps=CAPS):
    """The declared grid: one `cover`, plus MMR with every lambda and cap."""
    out = {"plain": lambda cites, corpus, question, k=K: plain(cites, corpus, question, k),
           "cover": lambda cites, corpus, question, k=K: cover(cites, corpus, question, k)}
    for lam in lambdas:
        for cap in caps:
            name = f"mmr-l{lam}" + ("" if cap is None else f"-c{cap}")
            out[name] = (
                lambda cites, corpus, question, k=K, lam=lam, cap=cap: mmr(
                    cites, corpus, question, k, lam, cap
                )
            )
    return out


# E2's shortlist: the two selectors E1 found, plus the plain cut as control.
SELECTORS = {
    "plain": plain,
    "cover": cover,
    "mmr-l0.5": lambda citations, corpus, question, k=K, **_: mmr(
        citations, corpus, question, k, 0.5
    ),
}


def dense_order(citations, row_of: dict[str, int], matrix, query_vector):
    """The same pool, ordered by cosine; claims without a vector keep the tail."""
    scored, unscored = [], []
    for position, citation in enumerate(citations):
        row = row_of.get(citation.claim_id)
        if row is None:
            unscored.append(position)
            continue
        scored.append((float(matrix[row] @ query_vector), position))
    scored.sort(key=lambda pair: (-pair[0], pair[1]))
    return [citations[position] for _score, position in scored] + [
        citations[position] for position in unscored
    ]


def rrf_order(lexical, dense, rrf_k: int = 60):
    """Reciprocal rank fusion of two orders over the same claims."""
    scores: dict[str, float] = {}
    for order in (lexical, dense):
        for rank, citation in enumerate(order):
            scores[citation.claim_id] = scores.get(citation.claim_id, 0.0) + 1.0 / (rrf_k + rank)
    position = {citation.claim_id: index for index, citation in enumerate(lexical)}
    ordered = sorted(scores, key=lambda cid: (-scores[cid], position.get(cid, len(position))))
    by_id = {citation.claim_id: citation for citation in lexical}
    return [by_id[cid] for cid in ordered]


def _encode_question(encoder, question: str, prefix: str):
    if prefix == "query":
        return encoder.encode_query(question)
    return encoder.encode_passages([question])[0]


def _default_encoder(device: str | None = None):
    from benchmark.retrieval.dense import E5_LARGE_V2, SentenceEncoder

    return SentenceEncoder(E5_LARGE_V2, device=device)


def measure(
    selection: Path,
    kb_dir: Path,
    answers: Path,
    split_path: Path | None = None,
    half: str = "all",
    depth: int = DEPTH,
    k: int = K,
    vectors: tuple[list[str], object] | None = None,
    query_encoder=None,
    query_prefix: str = "query",
) -> tuple[dict, dict[str, dict]]:
    corpus = _corpus(kb_dir, False)
    items = json.loads(selection.read_text(encoding="utf-8"))["items"]
    wanted = rank.read_split(split_path, half) if split_path else None
    items = [item for item in items if wanted is None or item["qid"] in wanted]
    questions = [item for item in items if item.get("gold_facts")]
    by_qid = {item["qid"]: item for item in items}

    pools: dict[str, list] = {}
    pool_ms: list[float] = []
    for item in questions:
        started = time.perf_counter()
        pools[item["qid"]] = corpus.search(item["text"], limit=depth)
        pool_ms.append((time.perf_counter() - started) * 1000)

    if vectors is None:
        plan = {name: ("bm25", selector) for name, selector in variants().items()}
        dense = None
    else:
        ids, matrix = vectors
        row_of = {claim_id: index for index, claim_id in enumerate(ids)}
        dense = (row_of, matrix, query_encoder or _default_encoder())
        plan = {}
        for name, selector in SELECTORS.items():
            plan[name] = ("bm25", selector)
            plan[f"dense-{name}"] = ("dense", selector)
            plan[f"rrf-{name}"] = ("rrf", selector)

    orders: dict[str, dict[str, list]] = {}
    if dense is not None:
        row_of, matrix, encoder = dense
        for item in questions:
            pool = pools[item["qid"]]
            query_vector = _encode_question(encoder, item["text"], query_prefix)
            by_dense = dense_order(pool, row_of, matrix, query_vector)
            orders[item["qid"]] = {
                "bm25": pool,
                "dense": by_dense,
                "rrf": rrf_order(pool, by_dense),
            }

    report: dict = {
        "questions": len(questions),
        "claims": len(corpus.claims),
        "half": half,
        "depth": depth,
        "k": k,
        "baseline": round(rank.published_coverage(answers, by_qid), 6),
        "pool_ms_median": round(sorted(pool_ms)[len(pool_ms) // 2], 1),
        "variants": {},
    }
    if dense is not None:
        report["vectors"] = {
            "claims": len(vectors[0]),
            "dim": int(vectors[1].shape[1]),
            "query_prefix": query_prefix,
        }
    scores: dict[str, dict] = {}

    for name, (order_name, selector) in plan.items():
        rows, started = [], time.perf_counter()
        for item in questions:
            pool = orders[item["qid"]][order_name] if dense is not None else pools[item["qid"]]
            chosen = selector(pool, corpus, item["text"], k)
            quotes = [citation.quote for citation in chosen if citation.quote]
            rows.append(
                {
                    "qid": item["qid"],
                    "answer_fact_coverage": answer_fact_coverage(item["gold_facts"], quotes),
                    "claims": len(chosen),
                    "characters": sum(len(quote) for quote in quotes),
                }
            )
        seconds = time.perf_counter() - started
        report["variants"][name] = {
            "order": order_name,
            "coverage": round(sum(row["answer_fact_coverage"] for row in rows) / len(rows), 6),
            "characters_median": sorted(row["characters"] for row in rows)[len(rows) // 2],
            "claims_median": sorted(row["claims"] for row in rows)[len(rows) // 2],
            "select_ms_per_question": round(seconds / len(rows) * 1000, 2),
        }
        scores[name] = {"per_question": rows}
    return report, scores


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--kb", type=Path, required=True)
    parser.add_argument("--answers", type=Path, required=True)
    parser.add_argument("--split", type=Path, default=None)
    parser.add_argument("--half", default="all", choices=("all", "dev", "test"))
    parser.add_argument("--depth", type=int, default=DEPTH)
    parser.add_argument("--k", type=int, default=K)
    parser.add_argument(
        "--vectors",
        type=Path,
        default=None,
        help="Claim vectors from `claim_vectors.py`; adds the dense and RRF orders",
    )
    parser.add_argument(
        "--query-prefix",
        default="query",
        choices=("query", "passage"),
        help="`query` is how e5 was trained; `passage` is the control a library with "
        "no query prefix is stuck with",
    )
    parser.add_argument("--device", default=None, help="cpu or cuda for the query encoder")
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument(
        "--scores-dir",
        type=Path,
        default=None,
        help="Write one score file per variant, for `interval.py --score`",
    )
    args = parser.parse_args(argv)
    if args.half != "all" and args.split is None:
        parser.error("--half dev/test needs --split")

    vectors = None
    if args.vectors is not None:
        from benchmark.layer import claim_vectors

        vectors = claim_vectors.read(args.vectors)
        vectors = (vectors[0], vectors[1])

    report, scores = measure(
        args.selection,
        args.kb,
        args.answers,
        args.split,
        args.half,
        args.depth,
        args.k,
        vectors=vectors,
        query_encoder=_default_encoder(args.device) if vectors is not None else None,
        query_prefix=args.query_prefix,
    )
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=1), encoding="utf-8")
    if args.scores_dir:
        args.scores_dir.mkdir(parents=True, exist_ok=True)
        for name, payload in scores.items():
            (args.scores_dir / f"{name}.score.json").write_text(
                json.dumps(payload, indent=1), encoding="utf-8"
            )

    print(
        f"questions {report['questions']}, claims {report['claims']}, half {report['half']}, "
        f"depth {report['depth']}, k {report['k']}"
    )
    if "vectors" in report:
        print(
            f"vectors {report['vectors']['claims']} x {report['vectors']['dim']}, "
            f"query prefix {report['vectors']['query_prefix']!r}"
        )
    print(f"published baseline   {report['baseline'] * 100:6.2f} %")
    ordered = sorted(report["variants"].items(), key=lambda pair: -pair[1]["coverage"])
    for name, row in ordered:
        print(
            f"{name:18s} {row['coverage'] * 100:6.2f} %  "
            f"chars {row['characters_median']:5d}  "
            f"select {row['select_ms_per_question']:5.1f} ms/q"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
