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
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from benchmark.retrieval import adapters, baselines, metrics  # noqa: E402
from benchmark.retrieval.adapters import Question as _Question  # noqa: E402

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
    one_shot = baselines._merge([baselines._chunk_postings(("porter", True, "english", texts))])
    split = baselines._merge(
        [
            baselines._chunk_postings(("porter", True, "english", texts[:3])),
            baselines._chunk_postings(("porter", True, "english", texts[3:])),
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
    payload["ids_blob"] = baselines._pack(["x", "y"])
    np.savez(victim, **payload)
    rebuilt = baselines.BM25(CORPUS, workers=1, cache=tmp_path)
    assert rebuilt.from_cache is False


def test_a_cache_written_in_the_original_format_is_still_read(tmp_path):
    """The vocabulary used to be stored as a fixed-width unicode array. A storage
    change that cannot change the index must not invalidate a cache, because the
    rebuild it would force is ten minutes on the largest corpus."""
    fresh = baselines.BM25(CORPUS, workers=1, cache=None)
    path = tmp_path / f"{fresh.cache_key}.npz"
    # The cache holds the document-major payload, not the term-major matrix the
    # scorer uses, so the old file is written from the build itself.
    vocab, matrix = baselines._merge([baselines._chunk_postings(("porter", True, "english", list(CORPUS.values())))])
    assert vocab == fresh.vocab
    np.savez(path, ids=np.asarray(fresh.ids, dtype=str), terms=np.asarray(list(vocab), dtype=str), **matrix)
    cached = baselines.BM25(CORPUS, workers=1, cache=tmp_path)
    assert cached.from_cache is True
    assert cached.vocab == fresh.vocab
    assert np.array_equal(cached.matrix.toarray(), fresh.matrix.toarray())


def test_one_long_token_does_not_inflate_the_cache(tmp_path):
    """EnterpriseRAG-Bench contains a 2,392-character token. Stored as a fixed-width
    unicode array it made a 480k-term vocabulary occupy 4.6 GB instead of 17 MB —
    allocated on every load, for one string."""
    corpus = {"d1": "alpha beta", "d2": ("a" * 2000) + " gamma delta"}
    index = baselines.BM25(corpus, workers=1, cache=tmp_path)
    size = sum(path.stat().st_size for path in tmp_path.glob("*.npz"))
    assert size < 200_000, f"the cache grew to {size} bytes around one long token"
    assert max(len(term) for term in index.vocab) >= 2000, "the token is kept, only its storage changed"

    reloaded = baselines.BM25(corpus, workers=1, cache=tmp_path)
    assert reloaded.from_cache is True
    assert reloaded.vocab == index.vocab


def test_top_ids_returns_exactly_what_rank_returns():
    """The fast path exists for the 8.8M-passage corpus, and it must not be a
    second definition of the ranking."""
    index = baselines.BM25(CORPUS, workers=1, cache=None)
    for query in ("capital of france", "largest city in the country", "alpha", "nothing matches here"):
        for k in (1, 3, 10, 100):
            expected = metrics.rank(index.scores(query), top_k=k)
            ranked, top = index.top_ids(query, k)
            assert ranked == expected
            if expected:
                assert top == pytest.approx(index.scores(query)[expected[0]])


def test_top_ids_breaks_a_boundary_tie_by_id():
    """Two documents with the same score: the smaller id wins the slot, as it does
    in `metrics.rank`, and it must win it when k exactly cuts the tie too."""
    corpus = {"b": "alpha beta", "a": "alpha beta", "c": "gamma"}
    index = baselines.BM25(corpus, workers=1, cache=None)
    assert metrics.rank(index.scores("alpha"))[:2] == ("a", "b")
    ranked, _ = index.top_ids("alpha", 1)
    assert ranked == ("a",), "a tie at the cutoff must be resolved by id, not by array order"


def test_top_ids_handles_a_query_longer_than_the_corpus_and_an_empty_one():
    index = baselines.BM25(CORPUS, workers=1, cache=None)
    ranked, top = index.top_ids("capital", 1000)
    assert ranked and top > 0
    assert index.top_ids("zzz-nonexistent", 5) == ((), 0.0)
    with pytest.raises(ValueError):
        index.top_ids("capital", 0)


def test_the_italian_analyser_uses_the_italian_stop_list():
    italian = baselines.Analysis(stemmer="italian", language="italian")
    tokens = italian("Il gatto dell'articolo è sul tavolo, ma il cane non c'è")
    assert "il" not in tokens and "tavolo" not in tokens, "stop words and elided articles are dropped"
    assert "gatt" in tokens and "tavol" in tokens


def test_the_stop_lists_are_the_published_ones():
    """A stop list that drifts is a number that drifts, and nobody would notice."""
    assert len(baselines.STOPWORDS_IT) == 279, "Lucene's italian_stop.txt"
    assert len(baselines.ITALIAN_ARTICLES) == 21, "ItalianAnalyzer.DEFAULT_ARTICLES"
    assert "perché" in baselines.STOPWORDS_IT
    assert "sull" in baselines.ITALIAN_ARTICLES


def test_the_english_description_is_frozen_because_it_keys_the_cache():
    """Every built index is cached under this string; renaming it silently rebuilds
    ten minutes of work per corpus."""
    assert baselines.Analysis().describe() == "stemmer=porter stopwords=lucene"
    assert baselines.Analysis(stemmer=None, stopwords=False).describe() == "stemmer=none stopwords=none"
    assert baselines.Analysis(stemmer="italian", language="italian").describe() == "stemmer=italian stopwords=lucene-italian"


def test_an_unknown_stop_word_language_is_refused():
    with pytest.raises(ValueError, match="unknown stop-word language"):
        baselines.Analysis(language="klingon")


def test_the_worker_is_told_which_language_it_is_indexing():
    """A worker rebuilds the analyser from the payload. If the language does not
    travel with it, the worker indexes Italian with the English stop list and the
    serial and parallel builds disagree — silently, in a number nobody re-derives."""
    italian = baselines._chunk_postings(("italian", True, "italian", ["Il gatto del vicino"]))
    assert "il" not in italian["terms"] and "gatt" in italian["terms"]
    english = baselines._chunk_postings(("italian", True, "english", ["Il gatto del vicino"]))
    assert "il" in english["terms"], "the language must reach the worker, not be assumed"


def test_an_italian_index_is_the_same_serial_and_parallel():
    corpus = {f"d{i}": f"Il gatto del vicino e sul tavolo numero {i}" for i in range(2100)}
    analysis = baselines.Analysis(stemmer="italian", language="italian")
    serial = baselines.BM25(corpus, analysis=analysis, workers=1, cache=None)
    parallel = baselines.BM25(corpus, analysis=analysis, workers=2, cache=None)
    assert parallel.vocab == serial.vocab
    assert "il" not in serial.vocab, "the italian stop list reaches the build, not the english one"
    for name in ("indices", "data", "indptr"):
        assert np.array_equal(getattr(parallel.matrix, name), getattr(serial.matrix, name))
    assert np.array_equal(parallel.lengths, serial.lengths)


ITALIAN_CORPUS = {
    "d1": "Il gatto dorme sul tavolo della cucina",
    "d2": "Il cane corre nel parco con il pallone",
    "d3": "La macchina rossa va molto veloce in autostrada",
    "d4": "Il tavolo del giardino e di legno scuro",
}


def test_the_marco_scorer_agrees_with_the_generic_ranking():
    """MRR@10 and R@1000 must be cut from the ranking `metrics.rank` produces:
    the fast path is a speed-up, not a second definition of retrieval."""
    index = baselines.BM25(ITALIAN_CORPUS, workers=1, cache=None)
    questions = [
        _Question(qid="q1", text="gatto tavolo", gold_docs=("d1",)),
        _Question(qid="q2", text="cane parco pallone", gold_docs=("d2",)),
        _Question(qid="q3", text="autostrada veloce", gold_docs=("d3",)),
    ]
    result = baselines.evaluate_marco(index, questions)

    def generic(question):
        ranking = metrics.rank(index.scores(question.text), top_k=1000)
        return (
            metrics.mrr_at(ranking, question.gold_docs, 10),
            metrics.recall_at(ranking, question.gold_docs, 1000),
            metrics.ndcg_at(ranking, question.gold_docs, 10),
        )

    expected = [generic(question) for question in questions]
    assert result["queries"] == 3
    assert result["mrr@10"] == pytest.approx(sum(row[0] for row in expected) / 3)
    assert result["r@1000"] == pytest.approx(sum(row[1] for row in expected) / 3)
    assert result["ndcg@10"] == pytest.approx(sum(row[2] for row in expected) / 3)


def test_the_marco_gate_is_reproducible_and_can_fail(monkeypatch):
    """The gate must be a gate: it passes on the published numbers and fails on a
    corpus that is not the one they were measured on, without pretending."""
    benchmark = adapters.Benchmark(
        name="mmarco-it",
        questions=(
            _Question(qid="q1", text="gatto tavolo", gold_docs=("d1",)),
            _Question(qid="q2", text="cane parco", gold_docs=("d2",)),
        ),
        documents=lambda: iter(ITALIAN_CORPUS.items()),
        citation="fake",
        licence="fake",
    )
    monkeypatch.setattr(adapters, "mmarco_it", lambda collection=False, limit=None: benchmark)

    first = baselines.reproduce_marco(workers=1)
    assert first["documents"] == len(ITALIAN_CORPUS)
    assert first["queries"] == 2
    assert "stemmer=italian" in first["config"] and "lucene-italian" in first["config"]
    assert first["within_tolerance"] is False, "four documents are not the published corpus"
    assert first["ranking_digest"]

    second = baselines.reproduce_marco(workers=1)
    assert second["ranking_digest"] == first["ranking_digest"], "same index, same ranking"

    monkeypatch.setitem(
        baselines.PUBLISHED_MARCO,
        "italian",
        {"mrr@10": first["mrr@10"], "r@1000": first["r@1000"]},
    )
    assert baselines.reproduce_marco(workers=1)["within_tolerance"] is True


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
