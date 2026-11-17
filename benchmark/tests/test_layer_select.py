"""Selection is arithmetic, so it can be pinned on a corpus whose answer is known.

The quality of a selector is measured on the pilot, not here. These tests pin the
properties a selector must have before its number means anything: it returns the
pool when there is nothing to choose, it never returns fewer than k claims when
the pool has them, a cap is a preference and not a refusal, and lambda = 1 is the
ranker's own order.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np
import pytest

from benchmark.layer import select


def claim(claim_id: str, doc_id: str, quote: str, statement: str = "") -> dict:
    return {
        "claim_id": claim_id,
        "doc_id": doc_id,
        "statement": statement or quote,
        "modality": "fact",
        "evidence": [
            {
                "quote": quote,
                "locator": {"kind": "text", "section_path": ["s"], "url": "u"},
                "role": "supports",
            }
        ],
        "context": {"source": doc_id},
    }


def corpus_of(tmp_path, claims):
    kb = tmp_path / "kb"
    kb.mkdir()
    (kb / "claims.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in claims), encoding="utf-8"
    )
    (kb / "verifier.jsonl").write_text(
        "".join(json.dumps({"claim_id": item["claim_id"], "verdict": "ok"}) + "\n" for item in claims),
        encoding="utf-8",
    )
    (kb / "documents.jsonl").write_text(
        "".join(
            json.dumps({"doc_id": doc_id, "title": doc_id}) + "\n"
            for doc_id in sorted({item["doc_id"] for item in claims})
        ),
        encoding="utf-8",
    )
    return select._corpus(kb, False)


CLAIMS = [
    claim("c1", "a", "alpha beta"),
    claim("c2", "a", "alpha beta gamma"),
    claim("c3", "b", "delta epsilon"),
    claim("c4", "b", "delta zeta"),
    claim("c5", "c", "alpha delta"),
]


def test_plain_is_the_pool_cut_at_k(tmp_path):
    corpus = corpus_of(tmp_path, CLAIMS)
    citations = corpus.search("alpha delta epsilon", limit=100)
    assert [item.claim_id for item in select.plain(citations, corpus, "alpha", k=2)] == [
        item.claim_id for item in citations[:2]
    ]


def test_cover_takes_the_claim_that_adds_the_most_question_terms(tmp_path):
    corpus = corpus_of(tmp_path, CLAIMS)
    citations = corpus.search("alpha delta epsilon", limit=100)
    chosen = [item.claim_id for item in select.cover(citations, corpus, "alpha epsilon", k=2)]
    # "alpha epsilon" is carried whole by no single claim: c1/c2 (alpha) plus c3
    # or c5 (epsilon/alpha) are needed, and the greedy picks the pair that
    # covers both terms rather than two paraphrases of alpha.
    quotes = " ".join(item.quote for item in select.cover(citations, corpus, "alpha epsilon", k=2))
    assert "alpha" in quotes and "epsilon" in quotes
    assert len(chosen) == 2


def test_cover_returns_the_pool_when_no_quote_shares_a_question_term(tmp_path):
    corpus = corpus_of(tmp_path, CLAIMS)
    citations = corpus.search("alpha delta epsilon", limit=100)
    chosen = select.cover(citations, corpus, "unrelated question", k=3)
    assert [item.claim_id for item in chosen] == [item.claim_id for item in citations[:3]]


def test_cover_never_returns_fewer_than_k_when_the_pool_has_them(tmp_path):
    corpus = corpus_of(tmp_path, CLAIMS)
    citations = corpus.search("alpha delta epsilon", limit=100)
    assert len(select.cover(citations, corpus, "alpha", k=10)) == min(10, len(citations))


def test_mmr_with_lambda_one_is_the_ranker_order(tmp_path):
    corpus = corpus_of(tmp_path, CLAIMS)
    citations = corpus.search("alpha delta epsilon", limit=100)
    chosen = [item.claim_id for item in select.mmr(citations, corpus, "alpha", k=3, lam=1.0)]
    assert chosen == [item.claim_id for item in citations[:3]]


def test_a_cap_limits_claims_per_document_until_the_pool_runs_out(tmp_path):
    corpus = corpus_of(tmp_path, CLAIMS)
    citations = corpus.search("alpha delta epsilon", limit=100)
    capped = select.mmr(citations, corpus, "alpha delta epsilon", k=3, lam=0.5, cap=1)
    assert len({item.doc_id for item in capped}) == 3
    # With k larger than the number of documents, the cap cannot be honoured for
    # every slot: the chooser fills rather than returning a short list.
    assert len(select.mmr(citations, corpus, "alpha delta epsilon", k=5, lam=0.5, cap=1)) == 5


def test_section_neighbours_link_a_section_and_a_conflict_but_nothing_else(tmp_path):
    claims = [
        claim("c1", "a", "alpha beta"),
        claim("c2", "a", "alpha gamma"),
        claim("c3", "b", "delta epsilon"),
    ]
    claims[1]["conflicts_with"] = ["c3", "missing"]
    corpus = corpus_of(tmp_path, claims)
    neighbours = select.section_neighbours(corpus)
    assert neighbours["c1"] == {"c2"}
    assert neighbours["c2"] == {"c1", "c3"}
    assert neighbours["c3"] == {"c2"}


def test_expand_appends_neighbours_after_the_order_and_never_duplicates(tmp_path):
    claims = [
        claim("c1", "a", "alpha beta"),
        claim("c2", "a", "alpha gamma delta"),
        claim("c3", "b", "epsilon zeta"),
    ]
    corpus = corpus_of(tmp_path, claims)
    citations = corpus.search("alpha", limit=100)
    neighbours = select.section_neighbours(corpus)
    ids = [item["claim_id"] for item in claims]
    order = select.expand_order(
        citations, corpus, neighbours, {cid: n for n, cid in enumerate(ids)},
        np.eye(len(ids), dtype=np.float32), np.ones(len(ids), dtype=np.float32), head=1,
    )
    assert len({item.claim_id for item in order}) == len(order)
    assert [item.claim_id for item in order[: len(citations)]] == [
        item.claim_id for item in citations
    ]
    assert len(order) >= len(citations)


def test_expand_with_no_neighbours_is_the_order_itself(tmp_path):
    corpus = corpus_of(tmp_path, [claim("c1", "a", "alpha beta")])
    citations = corpus.search("alpha", limit=100)
    order = select.expand_order(
        citations, corpus, {}, {"c1": 0}, np.eye(1, dtype=np.float32),
        np.ones(1, dtype=np.float32), head=10,
    )
    assert [item.claim_id for item in order] == [item.claim_id for item in citations]


def test_global_order_ranks_every_claim_in_the_corpus_and_honours_the_depth(tmp_path):
    corpus = corpus_of(tmp_path, CLAIMS)
    ids = [item["claim_id"] for item in CLAIMS]
    matrix = np.zeros((len(ids), 2), dtype=np.float32)
    matrix[:, 0] = np.arange(len(ids))
    ordered = select.global_order(corpus, ids, matrix, np.array([1.0, 0.0]), depth=3)
    assert [item.claim_id for item in ordered] == ids[::-1][:3]


def test_global_order_skips_an_id_the_corpus_filtered_out(tmp_path):
    corpus = corpus_of(tmp_path, CLAIMS)
    ids = [item["claim_id"] for item in CLAIMS] + ["c9"]
    matrix = np.zeros((len(ids), 2), dtype=np.float32)
    matrix[:, 0] = np.arange(len(ids))
    ordered = select.global_order(corpus, ids, matrix, np.array([1.0, 0.0]), depth=10)
    assert "c9" not in {item.claim_id for item in ordered}
    assert len(ordered) == len(CLAIMS)


def test_every_quote_returns_every_evidence_item_in_order(tmp_path):
    claims = [claim("c1", "a", "alpha beta"), claim("c2", "a", "gamma")]
    claims[0]["evidence"].append({"quote": "second quote"})
    corpus = corpus_of(tmp_path, claims)
    citations = corpus.search("alpha", limit=100)
    quotes = select.every_quote(corpus, citations)
    assert quotes[:2] == ["alpha beta", "second quote"]


def test_the_declared_grid_is_stable_and_named():
    names = list(select.variants())
    assert names[:2] == ["plain", "cover"]
    assert "mmr-l0.7" in names and "mmr-l0.7-c4" in names
    assert names == list(select.variants())


class FakeEncoder:
    """A query encoder that always returns the same unit vector."""

    spec = SimpleNamespace(describe=lambda: "fake")

    def __init__(self, vector):
        self.vector = np.asarray(vector, dtype=np.float32)
        self.queries: list[str] = []
        self.passages: list[str] = []

    def encode_query(self, text):
        self.queries.append(text)
        return self.vector

    def encode_passages(self, texts, batch_size: int = 32):
        self.passages.extend(texts)
        return np.stack([self.vector for _ in texts])


def test_dense_order_sorts_by_the_dot_product_and_keeps_the_pool_open(tmp_path):
    corpus = corpus_of(tmp_path, CLAIMS)
    citations = corpus.search("alpha delta epsilon", limit=100)
    row_of = {item.claim_id: index for index, item in enumerate(citations)}
    matrix = np.eye(len(citations), dtype=np.float32)
    # The vector of the last claim aligns with the query, the others do not.
    matrix[-1] = 0.0
    matrix[-1, -1] = 1.0
    query = np.zeros(len(citations), dtype=np.float32)
    query[-1] = 1.0
    ordered = select.dense_order(citations, row_of, matrix, query)
    assert [item.claim_id for item in ordered] == [citations[-1].claim_id] + [
        item.claim_id for item in citations[:-1]
    ]
    assert len(ordered) == len(citations)


def test_a_claim_without_a_vector_is_kept_at_the_tail_not_dropped(tmp_path):
    corpus = corpus_of(tmp_path, CLAIMS)
    citations = corpus.search("alpha delta epsilon", limit=100)
    row_of = {citations[0].claim_id: 0}
    matrix = np.ones((1, 2), dtype=np.float32)
    ordered = select.dense_order(citations, row_of, matrix, np.ones(2, dtype=np.float32))
    assert ordered[0].claim_id == citations[0].claim_id
    assert {item.claim_id for item in ordered} == {item.claim_id for item in citations}


def test_rrf_keeps_the_claims_that_both_orders_rank_high(tmp_path):
    corpus = corpus_of(tmp_path, CLAIMS)
    citations = corpus.search("alpha delta epsilon", limit=100)
    # The two heads agree; the tails disagree. Fusion must keep the heads.
    dense = citations[:2] + list(reversed(citations[2:]))
    fused = select.rrf_order(citations, dense)
    assert {item.claim_id for item in fused} == {item.claim_id for item in citations}
    assert [item.claim_id for item in fused[:2]] == [
        item.claim_id for item in citations[:2]
    ]


def test_measure_with_vectors_orders_the_same_pool_three_ways(tmp_path):
    corpus_of(tmp_path, CLAIMS)  # writes tmp_path/kb
    kb = tmp_path / "kb"
    selection = tmp_path / "selection.json"
    selection.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "qid": "qst_0001",
                        "kind": "basic",
                        "text": "alpha epsilon",
                        "gold_facts": ["alpha beta"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    answers = tmp_path / "answers.jsonl"
    answers.write_text(json.dumps({"qid": "qst_0001", "evidence": ["alpha"]}) + "\n")
    ids = [item["claim_id"] for item in CLAIMS]
    matrix = np.eye(len(ids), dtype=np.float32)
    report, scores = select.measure(
        selection,
        kb,
        answers,
        half="all",
        k=1,
        vectors=(ids, matrix),
        query_encoder=FakeEncoder(np.eye(len(ids), dtype=np.float32)[0]),
    )
    assert report["vectors"]["claims"] == len(ids)
    assert report["vectors"]["query_prefix"] == "query"
    assert set(report["variants"]) == {
        "plain", "cover", "mmr-l0.5",
        "dense-plain", "dense-cover", "dense-mmr-l0.5",
        "rrf-plain", "rrf-cover", "rrf-mmr-l0.5",
    }
    assert report["variants"]["dense-plain"]["order"] == "dense"
    assert "qst_0001" in {row["qid"] for row in scores["dense-plain"]["per_question"]}


def test_rerank_reorders_only_the_head_it_read(tmp_path):
    corpus = corpus_of(tmp_path, CLAIMS)
    citations = corpus.search("alpha delta epsilon", limit=100)

    def scorer(question, texts):
        # Prefer the shortest quote: a deterministic, order-independent rule.
        return [-len(text) for text in texts]

    ordered = select.rerank_order(citations, "alpha", scorer, depth=2)
    head = ordered[:2]
    assert [len(item.quote) for item in head] == sorted(
        [len(item.quote) for item in citations[:2]]
    )
    assert [item.claim_id for item in ordered[2:]] == [
        item.claim_id for item in citations[2:]
    ]


def test_rerank_without_vectors_is_refused(tmp_path):
    corpus_of(tmp_path, CLAIMS)
    selection = tmp_path / "selection.json"
    selection.write_text(json.dumps({"items": []}), encoding="utf-8")
    answers = tmp_path / "answers.jsonl"
    answers.write_text("", encoding="utf-8")
    with pytest.raises(SystemExit, match="needs claim vectors"):
        select.measure(
            selection, tmp_path / "kb", answers, half="all",
            reranker=lambda question, texts: [0.0 for _ in texts],
        )


def test_measure_with_a_reranker_adds_its_own_order(tmp_path):
    corpus_of(tmp_path, CLAIMS)
    kb = tmp_path / "kb"
    selection = tmp_path / "selection.json"
    selection.write_text(
        json.dumps(
            {"items": [{"qid": "qst_0001", "kind": "basic", "text": "alpha", "gold_facts": ["alpha"]}]}
        ),
        encoding="utf-8",
    )
    answers = tmp_path / "answers.jsonl"
    answers.write_text(json.dumps({"qid": "qst_0001", "evidence": ["alpha"]}) + "\n")
    ids = [item["claim_id"] for item in CLAIMS]
    report, _scores = select.measure(
        selection, kb, answers, half="all", k=2,
        vectors=(ids, np.eye(len(ids), dtype=np.float32)),
        query_encoder=FakeEncoder(np.eye(len(ids), dtype=np.float32)[1]),
        reranker=lambda question, texts: [float(len(text)) for text in texts],
    )
    assert report["variants"]["rerank-plain"]["order"] == "rerank"
    assert report["variants"]["rerank-plain"]["claims_median"] == 2


def test_all_quotes_adds_one_variant_per_selection_with_more_text(tmp_path):
    corpus_of(tmp_path, CLAIMS)
    kb = tmp_path / "kb"
    selection = tmp_path / "selection.json"
    selection.write_text(
        json.dumps(
            {"items": [{"qid": "qst_0001", "kind": "basic", "text": "alpha", "gold_facts": ["alpha"]}]}
        ),
        encoding="utf-8",
    )
    answers = tmp_path / "answers.jsonl"
    answers.write_text(json.dumps({"qid": "qst_0001", "evidence": ["alpha"]}) + "\n")
    ids = [item["claim_id"] for item in CLAIMS]
    report, _scores = select.measure(
        selection, kb, answers, half="all", k=2, all_quotes=True,
    )
    assert report["all_quotes"] is True
    assert "plain-allquotes" in report["variants"]
    assert report["variants"]["plain-allquotes"]["order"] == "bm25"
    assert (
        report["variants"]["plain-allquotes"]["characters_median"]
        >= report["variants"]["plain"]["characters_median"]
    )
    assert len(ids) == len(CLAIMS)


def test_the_query_prefix_is_a_declared_choice_not_an_accident(tmp_path):
    corpus_of(tmp_path, CLAIMS)
    kb = tmp_path / "kb"
    selection = tmp_path / "selection.json"
    selection.write_text(
        json.dumps(
            {"items": [{"qid": "qst_0001", "kind": "basic", "text": "alpha", "gold_facts": ["alpha"]}]}
        ),
        encoding="utf-8",
    )
    answers = tmp_path / "answers.jsonl"
    answers.write_text(json.dumps({"qid": "qst_0001", "evidence": ["alpha"]}) + "\n")
    ids = [item["claim_id"] for item in CLAIMS]
    encoder = FakeEncoder(np.ones(len(ids), dtype=np.float32))
    _report, _scores = select.measure(
        selection, kb, answers, half="all", k=1,
        vectors=(ids, np.eye(len(ids), dtype=np.float32)),
        query_encoder=encoder, query_prefix="passage",
    )
    assert encoder.passages == ["alpha"]
    assert encoder.queries == []


def test_measure_reports_every_variant_and_respects_the_half(tmp_path):
    corpus_dir = tmp_path / "kb"
    corpus_of(tmp_path, CLAIMS)  # writes the knowledge base at tmp_path/kb
    selection = tmp_path / "selection.json"
    selection.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "qid": "qst_0001",
                        "kind": "basic",
                        "text": "alpha epsilon",
                        "gold_facts": ["alpha epsilon"],
                    },
                    {
                        "qid": "qst_0002",
                        "kind": "basic",
                        "text": "delta",
                        "gold_facts": ["delta"],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    split = tmp_path / "split.json"
    split.write_text(json.dumps({"dev": ["qst_0001"], "test": ["qst_0002"]}), encoding="utf-8")
    answers = tmp_path / "answers.jsonl"
    answers.write_text(
        json.dumps({"qid": "qst_0001", "evidence": ["alpha"]})
        + "\n"
        + json.dumps({"qid": "qst_0002", "evidence": ["delta"]})
        + "\n",
        encoding="utf-8",
    )
    out = tmp_path / "scores"
    code = select.main(
        [
            "--selection", str(selection),
            "--kb", str(corpus_dir),
            "--answers", str(answers),
            "--split", str(split),
            "--half", "dev",
            "--json", str(tmp_path / "e1.json"),
            "--scores-dir", str(out),
        ]
    )
    assert code == 0
    report = json.loads((tmp_path / "e1.json").read_text())
    assert report["questions"] == 1
    assert report["half"] == "dev"
    assert set(report["variants"]) == set(select.variants())
    assert report["baseline"] == pytest.approx(0.5)
    score_file = json.loads((out / "cover.score.json").read_text())
    assert [row["qid"] for row in score_file["per_question"]] == ["qst_0001"]
    assert "answer_fact_coverage" in score_file["per_question"][0]
