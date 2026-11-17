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
  position in the order, redundancy is the Jaccard overlap of the quotes' token
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

E2 is the last rung that moved the number, and it is the frozen ranker
(`dense-cover`, depth 100, k 10). The three rungs after it are here because the
pilot publishes negative results too: `--expand-head` adds the section and
`conflicts_with` neighbours of the dense head (E4, +0,2 pp, under its gate),
`--global-depth` retrieves across the whole corpus instead of the lexical pool
(H4, +0,14 pp at 24× the cost), `--rerank` puts a cross-encoder over the head
(E5, −1,9 pp and 13,5 s per question on CPU). `--all-quotes` scores every quote
of the chosen claims instead of the first: the labelled extra row, never the
primary one.

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

import numpy as np

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
    """Maximal marginal relevance, with an optional per-document cap.

    Relevance is the position in the order the ranker produced, not the BM25
    score: the rung's question is what a *different order* is worth, and a
    selector that re-reads the lexical score would ignore the dense order by
    construction.
    """
    if not citations:
        return []
    n = len(citations)
    relevance = [1.0 - position / (n - 1) for position in range(n)] if n > 1 else [1.0]
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


def global_order(corpus, ids, matrix, query_vector, depth: int):
    """The first ``depth`` claims of the whole corpus by dense score, not by BM25.

    E2 reranks the lexical pool, so it inherits the pool's coverage. This order
    drops that inheritance: it asks whether the lexical candidate generator was
    ever the constraint, by retrieving across every verified claim the artifact
    has a vector for.
    """
    hits = matrix @ np.asarray(query_vector, dtype=np.float32)
    order = np.argsort(-hits, kind="stable")
    out = []
    for row in order:
        claim = corpus._by_id.get(ids[int(row)])
        if claim is None:
            continue
        out.append(corpus._citation(claim, float(hits[int(row)])))
        if len(out) >= depth:
            break
    return out


def section_neighbours(corpus) -> dict[str, set[str]]:
    """claim id -> the claims that share its document section, plus its conflicts.

    This is the claim graph the artifact already carries: a section, an offset
    and a `conflicts_with` edge. A rung that expands along it asks whether the
    facts live next to what we found, which is the one thing a chunk layer cannot
    copy.

    A contradiction is not a direction, so conflicts are read as undirected: the
    artifact happens to store every pair both ways (82 pairs, 164 links, all
    reciprocated), and the ranker must not depend on that.
    """
    sections: dict[tuple, list[str]] = {}
    for claim in corpus.claims:
        evidence = claim.get("evidence") or [{}]
        key = (
            claim["doc_id"],
            tuple((evidence[0].get("locator") or {}).get("section_path") or []),
        )
        sections.setdefault(key, []).append(claim["claim_id"])
    out: dict[str, set[str]] = {claim["claim_id"]: set() for claim in corpus.claims}
    for ids in sections.values():
        for claim_id in ids:
            out[claim_id] |= set(ids) - {claim_id}
    for claim in corpus.claims:
        for other in claim.get("conflicts_with") or ():
            if other in out and other != claim["claim_id"]:
                out[claim["claim_id"]].add(other)
                out[other].add(claim["claim_id"])
    return out


def expand_order(citations, corpus, neighbours, row_of, matrix, query_vector, head: int):
    """The order plus the graph neighbourhood of its first ``head`` claims.

    The added claims are scored by the same dense order and appended, so a
    neighbour never outranks a claim the retriever actually reached: this is an
    expansion of the candidate set, not a promotion.
    """
    known = {citation.claim_id for citation in citations}
    added: dict[str, dict] = {}
    for citation in citations[:head]:
        for claim_id in neighbours.get(citation.claim_id, ()):
            if claim_id in known or claim_id in added:
                continue
            claim = corpus._by_id.get(claim_id)
            if claim is not None:
                added[claim_id] = claim
    if not added:
        return list(citations)
    extra = [corpus._citation(claim, 0.0) for claim in added.values()]
    return list(citations) + dense_order(extra, row_of, matrix, query_vector)


def every_quote(corpus, chosen) -> list[str]:
    """Every evidence item of the chosen claims, in order: the labelled extra row."""
    out: list[str] = []
    for citation in chosen:
        claim = corpus._by_id.get(citation.claim_id) or {}
        out.extend(item.get("quote") or "" for item in (claim.get("evidence") or []))
    return [quote for quote in out if quote]


def _encode_question(encoder, question: str, prefix: str):
    if prefix == "query":
        return encoder.encode_query(question)
    return encoder.encode_passages([question])[0]


def rerank_order(citations, question: str, scorer, depth: int = 50, **_):
    """The first ``depth`` claims re-scored pairwise; everything below keeps its order.

    The reranker may reorder what it read, never promote something it did not
    read over something it did: the tail stays where the base order put it.
    """
    head = list(citations[:depth])
    tail = list(citations[depth:])
    if not head:
        return []
    scores = scorer(question, [citation.quote for citation in head])
    order = sorted(range(len(head)), key=lambda index: (-scores[index], index))
    return [head[index] for index in order] + tail


def _default_reranker(device: str | None = None):
    from benchmark.retrieval.dense import CROSS_ENCODER

    from sentence_transformers import CrossEncoder

    model = CrossEncoder(
        CROSS_ENCODER.model_id,
        revision=CROSS_ENCODER.revision,
        max_length=CROSS_ENCODER.max_length,
        device=device,
    )

    def score(question: str, texts):
        pairs = [(question, text) for text in texts]
        logits = model.predict(pairs, batch_size=32, show_progress_bar=False)
        return np.asarray(logits, dtype=np.float32).tolist()

    return score


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
    reranker=None,
    rerank_depth: int = 50,
    expand_head: int = 0,
    global_depth: int = 0,
    all_quotes: bool = False,
    selectors: tuple[str, ...] | None = None,
    progress=None,
) -> tuple[dict, dict[str, dict]]:
    corpus = _corpus(kb_dir, False)
    if reranker is not None and vectors is None:
        raise SystemExit("a reranker needs claim vectors: its base order is the RRF fusion")
    if (expand_head or global_depth) and vectors is None:
        raise SystemExit("graph expansion and global retrieval need claim vectors")
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
            if selectors is not None and name not in selectors:
                continue
            plan[name] = ("bm25", selector)
            plan[f"dense-{name}"] = ("dense", selector)
            plan[f"rrf-{name}"] = ("rrf", selector)
            if reranker is not None:
                plan[f"rerank-{name}"] = ("rerank", selector)
            if expand_head:
                plan[f"expand-{name}"] = ("expand", selector)
            if global_depth:
                plan[f"global-{name}"] = ("global", selector)

    orders: dict[str, dict[str, list]] = {}
    if dense is not None:
        row_of, matrix, encoder = dense
        neighbours = section_neighbours(corpus) if expand_head else {}
        for item in questions:
            pool = pools[item["qid"]]
            query_vector = _encode_question(encoder, item["text"], query_prefix)
            by_dense = dense_order(pool, row_of, matrix, query_vector)
            orders[item["qid"]] = {
                "bm25": pool,
                "dense": by_dense,
                "rrf": rrf_order(pool, by_dense),
            }
            if reranker is not None:
                orders[item["qid"]]["rerank"] = rerank_order(
                    orders[item["qid"]]["rrf"], item["text"], reranker, rerank_depth
                )
            if expand_head:
                orders[item["qid"]]["expand"] = expand_order(
                    by_dense, corpus, neighbours, row_of, matrix, query_vector, expand_head
                )
            if global_depth:
                orders[item["qid"]]["global"] = global_order(
                    corpus, ids, matrix, query_vector, global_depth
                )

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
        if expand_head:
            report["expand_head"] = expand_head
        if global_depth:
            report["global_depth"] = global_depth
    if all_quotes:
        report["all_quotes"] = True
    scores: dict[str, dict] = {}

    scoring = list(plan.items())
    if all_quotes:
        scoring += [(f"{name}-allquotes", entry) for name, entry in plan.items()]

    for name, (order_name, selector) in scoring:
        rows, started = [], time.perf_counter()
        for item in questions:
            pool = orders[item["qid"]][order_name] if dense is not None else pools[item["qid"]]
            chosen = selector(pool, corpus, item["text"], k)
            if all_quotes and name.endswith("-allquotes"):
                quotes = every_quote(corpus, chosen)
            else:
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
        if progress is not None:
            progress(name, report["variants"][name])
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
    parser.add_argument(
        "--rerank",
        action="store_true",
        help="Add the cross-encoder order: the RRF head re-scored pairwise (E5)",
    )
    parser.add_argument("--rerank-depth", type=int, default=50)
    parser.add_argument(
        "--expand-head",
        type=int,
        default=0,
        help="Add the section and conflict neighbours of the first N claims (E4)",
    )
    parser.add_argument(
        "--global-depth",
        type=int,
        default=0,
        help="Also retrieve across the whole corpus by dense score, cut at N",
    )
    parser.add_argument(
        "--all-quotes",
        action="store_true",
        help="Also score every quote of the chosen claims: the labelled extra row",
    )
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument(
        "--selectors",
        default=None,
        help="Comma-separated subset of plain,cover,mmr-l0.5 (default: all three); "
        "a long order is only worth running the chooser you care about",
    )
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
        reranker=_default_reranker(args.device) if args.rerank else None,
        rerank_depth=args.rerank_depth,
        expand_head=args.expand_head,
        global_depth=args.global_depth,
        all_quotes=args.all_quotes,
        selectors=tuple(args.selectors.split(",")) if args.selectors else None,
        progress=lambda name, row: print(
            f"  ... {name:26s} {row['coverage'] * 100:6.2f} %", file=sys.stderr, flush=True
        ),
    )
    if args.rerank:
        report["rerank"] = {
            "depth": args.rerank_depth,
            "model": "cross-encoder/ms-marco-MiniLM-L-6-v2",
        }
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
