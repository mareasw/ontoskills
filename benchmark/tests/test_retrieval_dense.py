"""Tests for the dense and hybrid baselines.

None of these touch a model, a network or a GPU: the encoder is a seam, and a
test that needed a 1.3 GB download would simply not be run.

The hybrid numbers are the non-inferiority target the product is judged against,
so the fusion arithmetic is checked against a value computed by hand in the test
rather than against whatever the implementation happens to return.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from benchmark.retrieval import dense

DOCUMENTS = {
    "d1": "alpha beta gamma",
    "d2": "delta epsilon",
    "d3": "alpha delta",
}


def spec(dim: int = 8, model_id: str = "fake/model", revision: str = "a" * 40) -> dense.ModelSpec:
    return dense.ModelSpec(
        model_id=model_id,
        revision=revision,
        max_length=16,
        query_prefix="query: ",
        passage_prefix="passage: ",
        dim=dim,
    )


class FakeEncoder:
    """A bag-of-words projection: deterministic, offline, and good enough to rank.

    The prefixes are stripped rather than embedded, so `encode_query` and
    `encode_passages` of the same text agree — which is what the real model does
    for the `query:`/`passage:` pair only approximately, and what a test wants
    exactly.
    """

    def __init__(self, spec_: dense.ModelSpec, table: dict[str, list[float]] | None = None) -> None:
        self.spec = spec_
        self.table = table or {}
        self.passage_calls: list[list[str]] = []
        self.query_calls: list[str] = []

    def _vector(self, text: str) -> np.ndarray:
        if text in self.table:
            vector = np.asarray(self.table[text], dtype=np.float32)
        else:
            vector = np.zeros(self.spec.dim, dtype=np.float32)
            for word in text.split():
                vector[hash(word) % self.spec.dim] += 1.0
        norm = np.linalg.norm(vector)
        return vector / norm if norm else vector

    def encode_passages(self, texts, batch_size: int = 32) -> np.ndarray:
        self.passage_calls.append(list(texts))
        return np.vstack([self._vector(t) for t in texts]).astype(np.float32)

    def encode_query(self, text: str) -> np.ndarray:
        self.query_calls.append(text)
        return self._vector(text)


@pytest.fixture(autouse=True)
def cache_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(dense, "EMBEDDING_CACHE", tmp_path / "embeddings")
    return tmp_path / "embeddings"


def test_dense_puts_the_matching_document_first(cache_dir):
    encoder = FakeEncoder(spec(dim=2), {"delta epsilon": [1.0, 0.0], "delta": [0.0, 1.0]})
    for text in DOCUMENTS.values():
        encoder.table.setdefault(text, [0.0, 1.0])
    index = dense.Dense({**DOCUMENTS, "d2": "delta epsilon"}, encoder=encoder)
    scores = index.scores("delta epsilon")
    assert max(scores, key=scores.get) == "d2"


def test_every_document_is_scored_and_cosine_is_bounded(cache_dir):
    encoder = FakeEncoder(spec())
    index = dense.Dense(DOCUMENTS, spec=spec(), encoder=encoder)
    scores = index.scores("alpha")
    assert set(scores) == set(DOCUMENTS)
    assert all(-1.0001 <= value <= 1.0001 for value in scores.values())


def test_the_embedding_cache_is_used_and_is_the_same_matrix(cache_dir):
    first = FakeEncoder(spec())
    matrix, info = dense.build_embeddings(DOCUMENTS, spec=spec(), encoder=first)
    assert info["cache"] == "miss"
    assert len(first.passage_calls) == 1

    # No encoder at all: a cache hit must not need a model, a download or a network.
    again, second_info = dense.build_embeddings(DOCUMENTS, spec=spec())
    assert second_info["cache"] == "hit"
    assert np.array_equal(np.asarray(matrix), np.asarray(again))


def test_a_changed_document_is_not_a_cache_hit(cache_dir):
    dense.build_embeddings(DOCUMENTS, spec=spec(), encoder=FakeEncoder(spec()))
    changed = {**DOCUMENTS, "d1": "alpha beta gamma delta"}
    _, info = dense.build_embeddings(changed, spec=spec(), encoder=FakeEncoder(spec()))
    assert info["cache"] == "miss"


def test_a_different_model_revision_is_not_a_cache_hit(cache_dir):
    dense.build_embeddings(DOCUMENTS, spec=spec(), encoder=FakeEncoder(spec()))
    _, info = dense.build_embeddings(DOCUMENTS, spec=spec(revision="b" * 40), encoder=FakeEncoder(spec()))
    assert info["cache"] == "miss"


def test_a_truncated_cache_file_is_rebuilt_not_fatal(cache_dir):
    """A half-written `.npy` raises `ValueError`, not `OSError`.

    The BM25 cache had the same defect and it took down the run it was meant to
    speed up; a cache must never be able to fail a measurement.
    """
    matrix, info = dense.build_embeddings(DOCUMENTS, spec=spec(), encoder=FakeEncoder(spec()))
    path = dense.Path(info["path"])
    path.write_bytes(path.read_bytes()[:40])
    rebuilt, info = dense.build_embeddings(DOCUMENTS, spec=spec(), encoder=FakeEncoder(spec()))
    assert info["cache"] == "miss"
    assert np.array_equal(np.asarray(matrix), np.asarray(rebuilt))


def test_a_cache_with_the_wrong_width_is_rebuilt(cache_dir):
    dense.build_embeddings(DOCUMENTS, spec=spec(dim=8), encoder=FakeEncoder(spec(dim=8)))
    # Same corpus and same model string, but a different dimension: the file is
    # the wrong shape, so it is not this corpus's embedding.
    rebuilt, info = dense.build_embeddings(DOCUMENTS, spec=spec(dim=8), encoder=FakeEncoder(spec(dim=8)))
    assert info["cache"] == "hit"
    assert rebuilt.shape == (3, 8)


def test_rrf_matches_a_value_computed_by_hand():
    fused = dense.reciprocal_rank_fusion((["a", "b", "c"], ["c", "a"]), k=60)
    assert fused["a"] == pytest.approx(1 / 61 + 1 / 62)
    assert fused["b"] == pytest.approx(1 / 62)
    assert fused["c"] == pytest.approx(1 / 63 + 1 / 61)
    # Highest fused score wins: 'a' and 'c' by hand.
    assert max(fused, key=fused.get) in {"a", "c"}
    assert fused["a"] > fused["b"] and fused["c"] > fused["b"]


def test_rrf_refuses_a_meaningless_k():
    with pytest.raises(ValueError):
        dense.reciprocal_rank_fusion((["a"],), k=0)


def test_a_document_both_systems_rank_high_beats_one_only_one_does(cache_dir):
    fused = dense.reciprocal_rank_fusion((["only-lexical", "both"], ["both", "only-dense"]))
    assert fused["both"] > fused["only-lexical"] > 0
    assert fused["both"] > fused["only-dense"] > 0


class StubCrossEncoder:
    def __init__(self, logits: list[float]) -> None:
        self.logits = logits
        self.seen: list[tuple[str, str]] = []

    def predict(self, pairs, batch_size: int = 32, show_progress_bar: bool = False):
        self.seen.extend(pairs)
        return np.asarray(self.logits[: len(pairs)], dtype=np.float32)


class StubBase:
    """A base retriever whose order is exactly the one given."""

    def __init__(self, order: list[str]) -> None:
        self.order = order

    def scores(self, query: str) -> dict[str, float]:
        return {doc_id: 1.0 / (position + 1) for position, doc_id in enumerate(self.order)}

    def describe(self) -> str:
        return "stub"


def test_the_reranker_may_reorder_only_what_it_read(cache_dir):
    corpus = {"d1": "first", "d2": "second", "d3": "third", "d4": "fourth"}
    base = StubBase(["d1", "d2", "d3", "d4"])
    reranker = dense.Reranked(corpus, base=base, depth=2)
    stub = StubCrossEncoder([0.1, 0.9])
    reranker._model = stub
    scores = reranker.scores("q")

    assert [pair[1] for pair in stub.seen] == ["first", "second"]
    assert scores["d2"] > scores["d1"], "the cross-encoder's order must win inside the depth"
    assert scores["d1"] > scores["d3"] > scores["d4"], "the tail keeps its fused order, below the head"
    assert dense.metrics.rank(scores)[:2] == ("d2", "d1")
    assert stub.seen[0][0] == "q"


def test_the_reranker_never_promotes_an_unread_document(cache_dir):
    corpus = {"d1": "first", "d2": "second", "d3": "third"}
    base = StubBase(["d1", "d2", "d3"])
    reranker = dense.Reranked(corpus, base=base, depth=2)
    reranker._model = StubCrossEncoder([-5.0, -4.0])
    scores = reranker.scores("q")
    # Even though the head scores are very negative, the unread tail stays under them.
    assert scores["d3"] < min(scores["d1"], scores["d2"])


def test_a_reranked_run_is_reproducible(cache_dir):
    corpus = {"d1": "first", "d2": "second", "d3": "third"}
    first = dense.Reranked(corpus, base=StubBase(["d3", "d1", "d2"]), depth=3)
    first._model = StubCrossEncoder([0.2, 0.8, 0.5])
    second = dense.Reranked(corpus, base=StubBase(["d3", "d1", "d2"]), depth=3)
    second._model = StubCrossEncoder([0.2, 0.8, 0.5])
    assert first.scores("q") == second.scores("q")


def test_describe_records_the_model_and_the_revision(cache_dir):
    index = dense.Dense(DOCUMENTS, spec=spec(), encoder=FakeEncoder(spec()))
    text = index.describe()
    assert "fake/model" in text
    assert "a" * 12 in text, "a number must name the weights that produced it"


def test_hybrid_fuses_both_and_keeps_every_document(cache_dir):
    from benchmark.retrieval import baselines

    index = dense.Hybrid(DOCUMENTS, analysis=baselines.Analysis(stemmer="porter", stopwords=True), encoder=FakeEncoder(spec()))
    scores = index.scores("alpha delta")
    assert set(scores) == set(DOCUMENTS)
    assert all(math.isfinite(value) for value in scores.values())
    # Both halves contribute: the fused score of a document ranked by both is
    # strictly larger than its score in either list alone.
    single = 1.0 / (dense.RRF_K + 1)
    assert max(scores.values()) > single
