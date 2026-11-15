"""Reference retrievers, and the check that the metric layer is not self-referential.

Every number this project reports is a **delta** against a lexical baseline
measured in this same harness, so the baseline has to be a real one. The Phase-0
gate is that it reproduces a published number within one point: Anserini BM25
scores nDCG@10 = 0.665 on BEIR/SciFact (Thakur et al. 2021, Table 2, k1 = 0.9,
b = 0.4), and an implementation that cannot get within a point of that is not a
baseline, it is a different retriever wearing the name.

The implementation is deliberately plain: one sparse term-document matrix, the
Lucene BM25 weighting, Porter-family stemming. No approximate index, no
parallelism, no tuning per dataset — a tuned baseline flatters our system when it
loses and flatters it differently when it wins.

    python3 benchmark/retrieval/baselines.py --reproduce
"""

from __future__ import annotations

import argparse
import hashlib
import multiprocessing
import os
import re
import sys
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.sparse import csr_matrix

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.retrieval import metrics  # noqa: E402

_WORD = re.compile(r"[^\W_]+", re.UNICODE)

# Lucene's default English stop set, which Pyserini/Anserini apply unless told
# otherwise. Copied rather than derived so that a change upstream cannot move a
# published number silently.
STOPWORDS = frozenset(
    """a an and are as at be but by for if in into is it no not of on or such that the
    their then there these they this to was will with""".split()
)

# Published Anserini BM25 nDCG@10, BEIR Table 2. The tolerance is the Phase-0 gate.
PUBLISHED = {
    "scifact": 0.665,
    "nfcorpus": 0.325,
}
TOLERANCE = 0.01


@dataclass
class Analysis:
    """Tokenisation, optionally stemmed. Named so a run records its own config.

    The stem cache is not a micro-optimisation, it is what makes the baseline
    runnable at all: `snowballstemmer` is pure Python and costs ~76 µs per token,
    so EnterpriseRAG-Bench's 512k documents are about thirteen hours of stemming
    without it. Caching by surface form is exact — the stem of a word does not
    depend on its neighbours — and a test asserts the cached path returns
    byte-identical tokens to the uncached one.
    """

    stemmer: str | None = "porter"
    stopwords: bool = True

    def __post_init__(self) -> None:
        self._stem = None
        self._stems: dict[str, str] = {}
        if self.stemmer is not None:
            import snowballstemmer

            self._stem = snowballstemmer.stemmer(self.stemmer)

    def __call__(self, text: str) -> list[str]:
        tokens = _WORD.findall(str(text or "").lower())
        if self.stopwords:
            tokens = [token for token in tokens if token not in STOPWORDS]
        if self._stem is None:
            return tokens
        stems = self._stems
        stemmed: list[str] = []
        for token in tokens:
            try:
                stemmed.append(stems[token])
            except KeyError:
                stem = self._stem.stemWord(token)
                stems[token] = stem
                stemmed.append(stem)
        return stemmed

    def describe(self) -> str:
        return f"stemmer={self.stemmer or 'none'} stopwords={'lucene' if self.stopwords else 'none'}"


@dataclass(frozen=True)
class BM25Config:
    k1: float = 0.9
    b: float = 0.4

    def describe(self) -> str:
        return f"k1={self.k1} b={self.b}"


# Where a built index may be reused. The key includes a digest of every document,
# so a cached index can never be a stale one; it can only be the right one.
INDEX_CACHE = Path(os.environ.get("ONTOSKILLS_BENCH_CACHE", Path.home() / ".cache" / "ontoskills-bench")) / "index"


def _default_workers() -> int:
    """The pool size, overridable, because a fixed number would be a guess."""
    override = os.environ.get("ONTOSKILLS_BENCH_WORKERS")
    if override:
        return max(1, int(override))
    return min(8, os.cpu_count() or 1)


def _corpus_digest(documents: dict[str, str]) -> str:
    """A digest of the ids and the text, so the cache key is the corpus itself.

    Hashing 2.5 GB costs about ten seconds and the build it guards costs minutes,
    so the exact key is the cheap option: a fingerprint over ids and lengths would
    be faster and would accept an edit that keeps the length.
    """
    digest = hashlib.sha256()
    for doc_id, text in documents.items():
        digest.update(str(doc_id).encode("utf-8"))
        digest.update(b"\x00")
        digest.update(str(text).encode("utf-8"))
        digest.update(b"\x01")
    return digest.hexdigest()


def _chunk_size(total: int, workers: int) -> int:
    """Documents per chunk: four chunks per worker, so the pool can rebalance.

    A minimum keeps the per-chunk overhead from dominating a small corpus, and it
    is the same number for one worker, so the serial path is the same code.
    """
    if total <= 0:
        return 1
    return max(256, -(-total // max(1, workers * 4)))


def _chunk_postings(payload: tuple[str | None, bool, list[str]]) -> dict:
    """Tokenise one chunk into a CSR fragment with its own local vocabulary.

    Runs in a worker process, so it rebuilds the Analysis rather than receiving
    it: a stem cache is a per-process object, and sending one over a pipe would
    cost more than filling it.
    """
    stemmer, stopwords, chunk = payload
    analysis = Analysis(stemmer=stemmer, stopwords=stopwords)
    vocab: dict[str, int] = {}
    indices: list[int] = []
    data: list[float] = []
    indptr: list[int] = [0]
    lengths = np.zeros(len(chunk), dtype=np.float32)
    for position, text in enumerate(chunk):
        counts: dict[str, int] = {}
        for token in analysis(text):
            counts[token] = counts.get(token, 0) + 1
        lengths[position] = sum(counts.values())
        for token, frequency in counts.items():
            term = vocab.get(token)
            if term is None:
                term = len(vocab)
                vocab[token] = term
            indices.append(term)
            data.append(float(frequency))
        indptr.append(len(indices))
    return {
        "terms": list(vocab),
        "indices": np.asarray(indices, dtype=np.int32),
        "data": np.asarray(data, dtype=np.float32),
        "indptr": np.asarray(indptr, dtype=np.int64),
        "lengths": lengths,
    }


def _merge(partials: list[dict]) -> tuple[dict[str, int], dict]:
    """Concatenate chunk fragments, renumbering terms in document order.

    Merging in chunk order is what makes the term numbering identical to a serial
    build's: each chunk contributes its terms in the order they first appear in
    that chunk, and the chunks are contiguous and ordered.
    """
    vocab: dict[str, int] = {}
    indices = []
    data = []
    indptr = [np.zeros(1, dtype=np.int64)]
    lengths = []
    total = 0
    for partial in partials:
        terms = partial["terms"]
        lookup = np.fromiter(
            (vocab.setdefault(term, len(vocab)) for term in terms), dtype=np.int64, count=len(terms)
        )
        indices.append(lookup[partial["indices"]].astype(np.int32) if len(terms) else partial["indices"])
        data.append(partial["data"])
        indptr.append(partial["indptr"][1:] + total)
        total += int(partial["indptr"][-1])
        lengths.append(partial["lengths"])
    return vocab, {
        "indices": np.concatenate(indices) if indices else np.zeros(0, dtype=np.int32),
        "data": np.concatenate(data) if data else np.zeros(0, dtype=np.float32),
        "indptr": np.concatenate(indptr),
        "lengths": np.concatenate(lengths) if lengths else np.zeros(0, dtype=np.float32),
    }


class BM25:
    """Okapi BM25 over one sparse term-document matrix.

    Scoring follows Lucene's `BM25Similarity`: idf = log(1 + (N - df + 0.5)/(df + 0.5))
    and tf saturated by k1 with length normalisation b. The whole index is held
    in memory as CSR; at 500k documents that is a few hundred megabytes, which is
    why this is not an approximate index.

    Building the index is one code path over chunks of documents; the chunks run
    in a process pool when there are enough of them to pay for it. Two properties
    are tested rather than assumed: `workers=4` produces a bit-identical index to
    `workers=1`, and a cached index is the same index as a freshly built one.
    Workers keep their own vocabulary, and the parent merges them in document
    order, so the global term numbering is the same as a serial build's — which
    is what makes the parallel result identical rather than merely equivalent.
    """

    # Below this, the process pool costs more than it saves.
    PARALLEL_FROM = 2_000

    def __init__(
        self,
        documents: dict[str, str],
        analysis: Analysis | None = None,
        config: BM25Config | None = None,
        workers: int | None = None,
        cache: Path | None = INDEX_CACHE,
    ) -> None:
        self.config = config or BM25Config()
        self.analysis = analysis or Analysis()
        self.workers = workers
        self.cache = cache
        self.ids = list(documents)
        payload = self._build_payload(documents, workers)
        self.vocab, matrix = payload
        self.matrix = csr_matrix(
            (matrix["data"], matrix["indices"], matrix["indptr"]),
            shape=(len(self.ids), len(self.vocab)),
        ).tocsc()
        self.lengths = matrix["lengths"]
        document_frequency = np.diff(self.matrix.indptr).astype(np.float32)
        total = np.float32(len(self.ids))
        self.idf = np.log1p((total - document_frequency + 0.5) / (document_frequency + 0.5)).astype(np.float32)
        self.average_length = float(self.lengths.mean()) or 1.0

    def _build_payload(self, documents: dict[str, str], workers: int | None) -> tuple[dict[str, int], dict]:
        """The postings, from the cache if it holds exactly this corpus."""
        key = hashlib.sha256(
            f"{self.analysis.describe()}|{self.config.describe()}|{_corpus_digest(documents)}".encode("utf-8")
        ).hexdigest()
        self.cache_key = key
        if self.cache is not None:
            cached = self._read_cache(Path(self.cache) / f"{key}.npz")
            if cached is not None:
                self.from_cache = True
                return cached
        self.from_cache = False

        texts = [documents[doc_id] for doc_id in self.ids]
        workers = _default_workers() if workers is None else max(1, workers)
        chunks = _chunk_size(len(texts), workers)
        payload = [
            (self.analysis.stemmer, self.analysis.stopwords, texts[start : start + chunks])
            for start in range(0, len(texts), chunks)
        ]
        if workers == 1 or len(payload) <= 1 or len(texts) < self.PARALLEL_FROM:
            partials = [_chunk_postings(item) for item in payload]
        else:
            context = multiprocessing.get_context("fork")
            with context.Pool(processes=min(workers, len(payload))) as pool:
                partials = pool.map(_chunk_postings, payload, chunksize=1)
        built = _merge(partials)
        if self.cache is not None:
            self._write_cache(Path(self.cache) / f"{key}.npz", *built)
        return built

    def _read_cache(self, path: Path) -> tuple[dict[str, int], dict] | None:
        if not path.exists():
            return None
        try:
            with np.load(path, allow_pickle=False) as saved:
                ids = [str(value) for value in saved["ids"]]
                if ids != self.ids:
                    return None
                terms = [str(value) for value in saved["terms"]]
                matrix = {name: saved[name] for name in ("indices", "data", "indptr", "lengths")}
        except (OSError, KeyError, ValueError, zipfile.BadZipFile):
            # A truncated, half-written or older-format cache is a miss, not an
            # error: the worst thing a cache may do is cost time. `BadZipFile` is
            # caught explicitly because it is not an `OSError` and a corrupt cache
            # would otherwise take down a run it was meant to speed up.
            return None
        if len(matrix["indptr"]) - 1 != len(ids) or (len(matrix["indices"]) and int(matrix["indices"].max()) >= len(terms)):
            return None
        return {term: position for position, term in enumerate(terms)}, matrix

    def _write_cache(self, path: Path, vocab: dict[str, int], matrix: dict) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp.npz")
            np.savez(
                temporary,
                ids=np.asarray(self.ids, dtype=str),
                terms=np.asarray(list(vocab), dtype=str),
                **matrix,
            )
            temporary.replace(path)
        except OSError:
            # A cache that cannot be written is not a failure of the run.
            pass

    def scores(self, query: str) -> dict[str, float]:
        """BM25 score per document, for the documents the query touches."""
        terms = {self.vocab[token] for token in self.analysis(query) if token in self.vocab}
        if not terms:
            return {}
        k1, b = self.config.k1, self.config.b
        accumulated = np.zeros(len(self.ids), dtype=np.float32)
        for term in terms:
            start, end = self.matrix.indptr[term], self.matrix.indptr[term + 1]
            rows = self.matrix.indices[start:end]
            frequency = self.matrix.data[start:end]
            denominator = frequency + k1 * (
                1.0 - b + b * self.lengths[rows] / self.average_length
            )
            accumulated[rows] += self.idf[term] * frequency * (k1 + 1.0) / denominator
        touched = np.flatnonzero(accumulated)
        return {self.ids[row]: float(accumulated[row]) for row in touched}

    def search(self, query: str, top_k: int = 100) -> tuple[str, ...]:
        """Ranked ids, ties broken by id so two runs are bit-identical."""
        return metrics.rank(self.scores(query), top_k=top_k)


class MultiFieldBM25:
    """One BM25 index per field, scores summed — the BEIR/Anserini setup.

    BEIR indexes the title and the passage as separate fields and sums the two
    BM25 scores, which is why the published number is a little below a
    single-field run of the same code. Reproducing the reference means
    reproducing its field layout, not just its k1 and b.
    """

    def __init__(
        self,
        fields: dict[str, dict[str, str]],
        analysis: Analysis | None = None,
        config: BM25Config | None = None,
        workers: int | None = None,
        cache: Path | None = INDEX_CACHE,
    ) -> None:
        if not fields:
            raise ValueError("a multi-field index needs at least one field")
        self.analysis = analysis or Analysis()
        self.config = config or BM25Config()
        self.fields = {
            name: BM25(documents, self.analysis, self.config, workers=workers, cache=cache)
            for name, documents in fields.items()
        }

    def scores(self, query: str) -> dict[str, float]:
        merged: dict[str, float] = {}
        for index in self.fields.values():
            for doc_id, score in index.scores(query).items():
                merged[doc_id] = merged.get(doc_id, 0.0) + score
        return merged

    def search(self, query: str, top_k: int = 100) -> tuple[str, ...]:
        return metrics.rank(self.scores(query), top_k=top_k)

    def describe(self) -> str:
        return f"fields={sorted(self.fields)} {self.analysis.describe()} {self.config.describe()}"


# --- published-number reproduction -----------------------------------------


def _load_beir(name: str) -> tuple[dict[str, dict[str, str]], dict[str, str], dict[str, set[str]]]:
    """Fields, queries and test qrels for a BEIR dataset, streamed from HF.

    Title and text stay separate because BEIR indexes them separately; joining
    them here and calling the result BM25 would quietly change what is compared.
    """
    from datasets import load_dataset

    fields: dict[str, dict[str, str]] = {"title": {}, "text": {}}
    for row in load_dataset(f"BeIR/{name}", "corpus", split="corpus", streaming=True):
        doc_id = str(row["_id"])
        fields["title"][doc_id] = str(row.get("title") or "").strip()
        fields["text"][doc_id] = str(row.get("text") or "").strip()
    queries = {}
    for row in load_dataset(f"BeIR/{name}", "queries", split="queries", streaming=True):
        queries[str(row["_id"])] = str(row["text"])
    qrels: dict[str, set[str]] = {}
    for split in ("test", "train", "dev"):
        try:
            rows = load_dataset(f"BeIR/{name}-qrels", split=split, streaming=True)
        except Exception:
            continue
        for row in rows:
            qrels.setdefault(str(row["query-id"]), set()).add(str(row["corpus-id"]))
        break
    return fields, queries, qrels


def reproduce(name: str, analysis: Analysis, depth: int = 100, limit: int | None = None) -> dict:
    """Index a BEIR dataset, retrieve, score nDCG@10, compare with the paper."""
    started = time.time()
    fields, queries, qrels = _load_beir(name)
    judged = [(qid, text) for qid, text in queries.items() if qrels.get(qid)]
    if limit is not None:
        judged = judged[:limit]
    index = MultiFieldBM25(fields, analysis=analysis)
    scores = []
    for qid, text in judged:
        scores.append(metrics.ndcg_at(index.search(text, top_k=depth), qrels[qid], 10))
    observed = float(np.mean(scores))
    published = PUBLISHED.get(name)
    return {
        "dataset": name,
        "documents": len(fields["text"]),
        "queries": len(judged),
        "config": index.describe(),
        "ndcg@10": observed,
        "published": published,
        "difference": None if published is None else observed - published,
        "within_tolerance": None if published is None else abs(observed - published) <= TOLERANCE,
        "seconds": round(time.time() - started, 1),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--reproduce", action="store_true", help="the Phase-0 instrument gate")
    parser.add_argument("--dataset", default="scifact", help="BEIR dataset name")
    parser.add_argument("--stemmer", default="porter", help="snowball algorithm, or 'none'")
    parser.add_argument("--no-stopwords", action="store_true")
    parser.add_argument("--limit", type=int, default=None, help="debug: score only the first N queries")
    parser.add_argument("--json", type=Path, help="write the result as an artifact")
    args = parser.parse_args(argv)
    if not args.reproduce:
        parser.print_help()
        return 0

    analysis = Analysis(
        stemmer=None if args.stemmer in ("none", "") else args.stemmer,
        stopwords=not args.no_stopwords,
    )
    result = reproduce(args.dataset, analysis, limit=args.limit)
    for key in ("dataset", "documents", "queries", "config", "seconds"):
        print(f"{key:12s} {result[key]}")
    print(f"{'ndcg@10':12s} {result['ndcg@10']:.4f}")
    if result["published"] is not None:
        print(f"{'published':12s} {result['published']:.3f} (BEIR Table 2, Anserini BM25)")
        print(f"{'difference':12s} {result['difference']:+.4f}")
        print(f"{'gate':12s} {'PASS' if result['within_tolerance'] else 'FAIL'} (|difference| <= {TOLERANCE})")
        if args.json:
            import json

            args.json.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
            print(f"wrote {args.json}")
        return 0 if result["within_tolerance"] else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
