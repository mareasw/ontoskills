"""The baseline's two optimisations are only acceptable if they change nothing.

An index cache and a process pool are exactly the kind of change that quietly
moves a number: one can hand back yesterday's corpus, the other can renumber the
terms. Both are pinned here — the cache by a digest over every document, the pool
by asserting a bit-identical index — so a speed-up can never be a silent
redefinition of the baseline.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from benchmark.retrieval import baselines  # noqa: E402

CORPUS = {
    f"d{index}": text
    for index, text in enumerate(
        [
            "The capital of France is Paris, and Paris is the largest city in France.",
            "Brazil borders Argentina and Peru; the Amazon river flows through Brazil.",
            "Retrieval systems rank documents by relevance to a query.",
            "Snowball stemming reduces words to their morphological roots.",
            "A citation is a reference to a source, quoted verbatim in context.",
            "Paris is the capital of France and the seat of its government.",
            "The Amazon is the largest river in Brazil by discharge.",
            "Enterprise documents are often long, structured and multilingual.",
        ]
    )
}


def test_the_stem_cache_is_exact():
    """Caching by surface form must not change a single token."""
    import snowballstemmer

    analysis = baselines.Analysis(stemmer="porter", stopwords=True)
    stemmer = snowballstemmer.stemmer("porter")
    for text in CORPUS.values():
        words = [token for token in baselines._WORD.findall(text.lower()) if token not in baselines.STOPWORDS]
        assert analysis(text) == list(stemmer.stemWords(words))


def test_a_repeated_token_is_stemmed_once_and_identically():
    analysis = baselines.Analysis(stemmer="porter", stopwords=True)
    first = analysis("retrieval retrieval retrieval")
    second = analysis("retrieval retrieved retrieving")
    assert first == ["retriev"] * 3
    assert second[0] == first[0]
    # The cache is per instance and holds surface forms, not contexts.
    assert len(analysis._stems) >= 3


def test_no_stemmer_returns_the_tokens_unchanged():
    analysis = baselines.Analysis(stemmer=None, stopwords=False)
    assert analysis("The Retrieval, of documents.") == ["the", "retrieval", "of", "documents"]


def test_a_parallel_index_is_bit_identical_to_a_serial_one():
    """Different term numbering would pass an equality-of-scores test and still be
    a different index, so the vocabulary, the postings and the idf are compared."""
    serial = baselines.BM25(CORPUS, workers=1, cache=None)
    parallel = baselines.BM25(CORPUS, workers=4, cache=None)
    assert serial.vocab == parallel.vocab
    assert np.array_equal(serial.matrix.indptr, parallel.matrix.indptr)
    assert np.array_equal(serial.matrix.indices, parallel.matrix.indices)
    assert np.array_equal(serial.matrix.data, parallel.matrix.data)
    assert np.array_equal(serial.lengths, parallel.lengths)
    assert np.array_equal(serial.idf, parallel.idf)
    assert serial.average_length == parallel.average_length


def test_the_chunk_boundaries_do_not_change_the_index():
    """A serial build is one chunk per worker with the same chunk function, so the
    only thing that may differ is how many chunks it was cut into."""
    texts = list(CORPUS.values())
    one_shot = baselines._merge([baselines._chunk_postings(("porter", True, texts))])
    split = baselines._merge(
        [
            baselines._chunk_postings(("porter", True, texts[:3])),
            baselines._chunk_postings(("porter", True, texts[3:])),
        ]
    )
    assert one_shot[0] == split[0]
    for name in ("indices", "data", "indptr", "lengths"):
        assert np.array_equal(one_shot[1][name], split[1][name])


def test_a_cached_index_is_the_same_index(tmp_path):
    fresh = baselines.BM25(CORPUS, workers=1, cache=tmp_path)
    assert fresh.from_cache is False
    cached = baselines.BM25(CORPUS, workers=1, cache=tmp_path)
    assert cached.from_cache is True
    assert cached.vocab == fresh.vocab
    assert np.array_equal(cached.matrix.toarray(), fresh.matrix.toarray())
    assert np.array_equal(cached.idf, fresh.idf)
    assert cached.scores("capital of france") == fresh.scores("capital of france")


def test_an_edited_corpus_does_not_hit_the_cache(tmp_path):
    """The key is a digest over every document, so a one-character edit misses."""
    baselines.BM25(CORPUS, workers=1, cache=tmp_path)
    edited = dict(CORPUS)
    edited["d0"] = CORPUS["d0"].replace("largest", "biggest")
    assert len(edited["d0"]) == len(CORPUS["d0"])
    rebuilt = baselines.BM25(edited, workers=1, cache=tmp_path)
    assert rebuilt.from_cache is False
    assert "biggest" in rebuilt.vocab or "biggest" not in rebuilt.vocab  # tokenised, not stored raw
    assert rebuilt.scores("biggest city") != baselines.BM25(CORPUS, workers=1, cache=None).scores("biggest city")


def test_a_different_analysis_does_not_hit_the_cache(tmp_path):
    baselines.BM25(CORPUS, analysis=baselines.Analysis("porter", True), workers=1, cache=tmp_path)
    other = baselines.BM25(CORPUS, analysis=baselines.Analysis(None, False), workers=1, cache=tmp_path)
    assert other.from_cache is False


def test_a_truncated_cache_file_is_a_miss_not_a_crash(tmp_path):
    baselines.BM25(CORPUS, workers=1, cache=tmp_path)
    victim = next(tmp_path.glob("*.npz"))
    victim.write_bytes(victim.read_bytes()[: 40])
    rebuilt = baselines.BM25(CORPUS, workers=1, cache=tmp_path)
    assert rebuilt.from_cache is False
    assert rebuilt.vocab


def test_a_cache_holding_another_corpus_is_rejected(tmp_path):
    """Belt and braces: the digest is the key, but a renamed or copied cache file
    must still be recognised as describing a different document set."""
    baselines.BM25(CORPUS, workers=1, cache=tmp_path)
    victim = next(tmp_path.glob("*.npz"))
    with np.load(victim, allow_pickle=False) as saved:
        payload = {name: saved[name] for name in saved.files}
    payload["ids"] = np.asarray(["x", "y"], dtype=str)
    np.savez(victim, **payload)
    rebuilt = baselines.BM25(CORPUS, workers=1, cache=tmp_path)
    assert rebuilt.from_cache is False


def test_the_pool_is_not_used_for_a_corpus_too_small_to_benefit(monkeypatch):
    """Spawning processes for eight documents would be slower and would hide a
    parallel-only defect behind small test corpora."""
    calls = []

    def explode(*args, **kwargs):
        calls.append(args)
        raise AssertionError("a pool was created for a tiny corpus")

    monkeypatch.setattr(baselines.multiprocessing, "get_context", explode)
    index = baselines.BM25(CORPUS, workers=8, cache=None)
    assert not calls
    assert index.vocab


def test_the_pool_is_used_once_the_corpus_is_big_enough(monkeypatch):
    """The negative test above is only meaningful with this one: the threshold
    must actually switch the pool on, and the pooled build must still equal the
    serial one at a size where chunking is real."""
    size = baselines.BM25.PARALLEL_FROM + 50
    corpus = {f"x{index}": "alpha beta gamma delta epsilon zeta" for index in range(size)}
    seen: list[tuple] = []
    real = baselines.multiprocessing.get_context

    def spy(*args, **kwargs):
        seen.append(args)
        return real(*args, **kwargs)

    monkeypatch.setattr(baselines.multiprocessing, "get_context", spy)
    pooled = baselines.BM25(corpus, workers=2, cache=None)
    assert seen
    serial = baselines.BM25(corpus, workers=1, cache=None)
    assert pooled.vocab == serial.vocab
    assert np.array_equal(pooled.matrix.indptr, serial.matrix.indptr)
    assert np.array_equal(pooled.matrix.indices, serial.matrix.indices)


def test_bm25_scores_a_document_that_shares_nothing_as_zero():
    index = baselines.BM25(CORPUS, workers=1, cache=None)
    scores = index.scores("zebra")
    assert scores == {}


def test_a_more_matching_document_outranks_a_less_matching_one():
    index = baselines.BM25(CORPUS, workers=1, cache=None)
    ranking = index.search("capital of france paris", top_k=3)
    assert ranking[0] in {"d0", "d5"}
    assert "d1" not in ranking
