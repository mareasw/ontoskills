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
import heapq
from array import array
import multiprocessing
import os
import re
import sys
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

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

# Lucene's Italian stop words, as `ItalianAnalyzer` loads them: the Snowball
# `italian_stop.txt` that ships with Lucene, plus the analyser's elision articles
# — `ElisionFilter` drops the article of "dell'articolo" and keeps the rest, which
# `[^\W_]+` already does by splitting on the apostrophe, so the articles go in the
# stop set instead. Both lists are copied verbatim and their sizes asserted in a
# test, because a stop list that drifts is a number that drifts.
#   https://raw.githubusercontent.com/apache/lucene/main/lucene/analysis/common/
#   src/resources/org/apache/lucene/analysis/snowball/italian_stop.txt
STOPWORDS_IT = frozenset(
    """
    a abbia abbiamo abbiano abbiate ad agl agli ai al all
    alla alle allo anche avemmo avendo avesse avessero avessi avessimo aveste
    avesti avete aveva avevamo avevano avevate avevi avevo avrai avranno avrebbe
    avrebbero avrei avremmo avremo avreste avresti avrete avrà avrò avuta avute
    avuti avuto c che chi ci coi col come con contro
    cui da dagl dagli dai dal dall dalla dalle dallo degl
    degli dei del dell della delle dello di dov dove e
    ebbe ebbero ebbi ed era erano eravamo eravate eri ero essendo
    faccia facciamo facciano facciate faccio facemmo facendo facesse facessero facessi facessimo
    faceste facesti faceva facevamo facevano facevate facevi facevo fai fanno farai
    faranno farebbe farebbero farei faremmo faremo fareste faresti farete farà farò
    fece fecero feci fosse fossero fossi fossimo foste fosti fu fui
    fummo furono gli ha hai hanno ho i il in io
    l la le lei li lo loro lui ma mi mia
    mie miei mio ne negl negli nei nel nell nella nelle
    nello noi non nostra nostre nostri nostro o per perché più
    quale quanta quante quanti quanto quella quelle quelli quello questa queste
    questi questo sarai saranno sarebbe sarebbero sarei saremmo saremo sareste saresti
    sarete sarà sarò se sei si sia siamo siano siate siete
    sono sta stai stando stanno starai staranno starebbe starebbero starei staremmo
    staremo stareste staresti starete starà starò stava stavamo stavano stavate stavi
    stavo stemmo stesse stessero stessi stessimo steste stesti stette stettero stetti
    stia stiamo stiano stiate sto su sua sue sugl sugli sui
    sul sull sulla sulle sullo suo suoi ti tra tu tua
    tue tuo tuoi tutti tutto un una uno vi voi vostra
    vostre vostri vostro è
    """.split()
)

# `ItalianAnalyzer.DEFAULT_ARTICLES`, verbatim. These are **not** stop words: in
# Lucene they are what `ElisionFilter` strips from `dell'articolo`, and only there.
# Adding them to the stop set instead would also drop the standalone tokens — and
# eight of the twenty-one are not in the 279-word list (`coll`, `pell`, `gl`, `d`,
# `m`, `s`, `t`, `v`), so it would drop tokens Lucene keeps: 0.11% of the tokens in
# a 200,000-passage sample, measured before the fix.
ITALIAN_ARTICLES = (
    "c", "l", "all", "dall", "dell", "nell", "sull", "coll", "pell", "gl",
    "agl", "dagl", "degl", "negl", "sugl", "un", "m", "t", "s", "v", "d",
)

# Longest first, so `dall'` is matched before `d'`.
_ELISION = re.compile(r"\b(?:%s)['\u2019]" % "|".join(sorted(ITALIAN_ARTICLES, key=len, reverse=True)))

LANGUAGES = {
    "english": STOPWORDS,
    "italian": STOPWORDS_IT,
}

# Languages whose analyser carries Lucene's `ElisionFilter`.
ELIDING = frozenset({"italian"})

# Published Anserini BM25 nDCG@10, BEIR Table 2. The tolerance is the Phase-0 gate.
PUBLISHED = {
    "scifact": 0.665,
    "nfcorpus": 0.325,
}

# mMARCO Table 2, the Google Translate row, the BM25 column pair: MRR@10 and
# R@1000 on the 6,980-query dev.small set. The paper uses Pyserini without
# stating k1 and b; this measures 0.9/0.4, the same configuration as the BEIR
# gate above, so the two gates are not two different instruments.
PUBLISHED_MARCO = {"italian": {"mrr@10": 0.153, "r@1000": 0.753}}
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
    language: str = "english"

    def __post_init__(self) -> None:
        self._stem = None
        self._stems: dict[str, str] = {}
        if self.language not in LANGUAGES:
            raise ValueError(f"unknown stop-word language {self.language!r}; known: {sorted(LANGUAGES)}")
        self._stopset = LANGUAGES[self.language] if self.stopwords else frozenset()
        self._elide = self.language in ELIDING
        if self.stemmer is not None:
            import snowballstemmer

            self._stem = snowballstemmer.stemmer(self.stemmer)

    def __call__(self, text: str) -> list[str]:
        text = str(text or "").lower()
        if self._elide:
            # Lucene's `ElisionFilter` runs before its lower-case filter, so a
            # sentence-initial `Dell'articolo` keeps its prefix there and loses it
            # here. Declared in PREFLIGHT §14.2; the gate bounds the combined size
            # of this and the two other approximations.
            text = _ELISION.sub("", text)
        tokens = _WORD.findall(text)
        if self._stopset:
            tokens = [token for token in tokens if token not in self._stopset]
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

    def fingerprint(self) -> str:
        """What the cache key is computed from: the analyser's behaviour, not its name.

        `describe()` is a human label, and a label can be true while the code under
        it changes. This is the digest of everything that decides a token — the
        stemmer, the tokeniser, the elision rule and the stop set's *contents* —
        so editing a stop word invalidates the cache instead of silently reusing an
        index built with the old one. A test asserts exactly that.
        """
        material = "\x00".join(
            (
                self.stemmer or "",
                self.language,
                str(self.stopwords),
                _WORD.pattern,
                _ELISION.pattern if self._elide else "",
                "\x01".join(sorted(self._stopset)),
            )
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]

    def describe(self) -> str:
        """The human half of an index's identity — frozen for English.

        Every Phase-0/1 artifact quotes this string, so the English form is kept
        exactly as it was and the language is only named when it is not English.
        The cache key itself is `fingerprint()`, which cannot drift silently.
        """
        if not self.stopwords:
            stops = "none"
        elif self.language == "english":
            stops = "lucene"
        else:
            stops = f"lucene-{self.language}"
        return f"stemmer={self.stemmer or 'none'} stopwords={stops}"


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


def _pack(strings: Sequence[str]) -> np.ndarray:
    r"""Strings as one newline-separated byte blob.

    `np.asarray(strings, dtype=str)` picks the width of the longest string and
    applies it to every one of them: EnterpriseRAG-Bench contains a single
    2,392-character token, which made a 480k-term vocabulary occupy **4.6 GB**
    instead of 17 MB — and every cache load allocated it. Tokens are produced by
    `[^\W_]+` and can never contain a newline, so joining them is lossless.
    """
    return np.frombuffer("\n".join(strings).encode("utf-8"), dtype=np.uint8)


def _unpack(blob: np.ndarray) -> list[str]:
    text = blob.tobytes().decode("utf-8")
    return text.split("\n") if text else []


def _chunk_size(total: int, workers: int) -> int:
    """Documents per chunk: four chunks per worker, so the pool can rebalance.

    A minimum keeps the per-chunk overhead from dominating a small corpus, and it
    is the same number for one worker, so the serial path is the same code.
    """
    if total <= 0:
        return 1
    return max(256, -(-total // max(1, workers * 4)))


def _chunk_postings(payload: tuple[str | None, bool, str, list[str]]) -> dict:
    """Tokenise one chunk into a CSR fragment with its own local vocabulary.

    Runs in a worker process, so it rebuilds the Analysis rather than receiving
    it: a stem cache is a per-process object, and sending one over a pipe would
    cost more than filling it. The language travels with the payload, because a
    worker that rebuilt the analyser without it would silently index Italian with
    the English stop list, and the serial and parallel builds would disagree.
    """
    stemmer, stopwords, language, chunk = payload
    analysis = Analysis(stemmer=stemmer, stopwords=stopwords, language=language)
    vocab: dict[str, int] = {}
    # `array` rather than `list`: a Python list holds a pointer and a boxed object
    # per posting (36 bytes), the typed array holds 4. On the largest corpus a
    # chunk is tens of millions of postings, and eight chunks are alive at once,
    # which is where the peak memory went.
    indices = array("i")
    data = array("f")
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
        "indices": indices,
        "data": data,
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
    # Preallocated and filled in place. `np.concatenate` would need a second copy
    # of every posting while all the fragments are still alive, which on a corpus
    # of hundreds of millions of postings is the difference between fitting and
    # swapping.
    postings = sum(len(partial["indices"]) for partial in partials)
    documents = sum(len(partial["lengths"]) for partial in partials)
    indices = np.empty(postings, dtype=np.int32)
    data = np.empty(postings, dtype=np.float32)
    indptr = np.zeros(documents + 1, dtype=np.int64)
    lengths = np.empty(documents, dtype=np.float32)
    cursor = 0
    document_cursor = 0
    total = 0
    for partial in partials:
        terms = partial["terms"]
        lookup = np.fromiter(
            (vocab.setdefault(term, len(vocab)) for term in terms), dtype=np.int64, count=len(terms)
        )
        count = len(partial["indices"])
        if count:
            # `np.frombuffer` reads the worker's typed array without copying it.
            local = np.frombuffer(partial["indices"], dtype=np.int32)
            indices[cursor : cursor + count] = lookup[local] if len(terms) else local
            data[cursor : cursor + count] = partial["data"]
        tail = partial["indptr"][1:]
        indptr[document_cursor + 1 : document_cursor + 1 + len(tail)] = tail + total
        lengths[document_cursor : document_cursor + len(tail)] = partial["lengths"]
        cursor += count
        document_cursor += len(tail)
        total += int(partial["indptr"][-1])
    return vocab, {"indices": indices, "data": data, "indptr": indptr, "lengths": lengths}


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
        self.lengths = matrix["lengths"]
        # Document-major, then transposed once to term-major for scoring. The
        # transpose is the only place two copies of the postings are alive at the
        # same time, so the dict and the tuple are dropped as early as they can be.
        self.matrix = csr_matrix(
            (matrix["data"], matrix["indices"], matrix["indptr"]),
            shape=(len(self.ids), len(self.vocab)),
        ).tocsc()
        del matrix, payload
        document_frequency = np.diff(self.matrix.indptr).astype(np.float32)
        total = np.float32(len(self.ids))
        self.idf = np.log1p((total - document_frequency + 0.5) / (document_frequency + 0.5)).astype(np.float32)
        self.average_length = float(self.lengths.mean()) or 1.0

    def _build_payload(self, documents: dict[str, str], workers: int | None) -> tuple[dict[str, int], dict]:
        """The postings, from the cache if it holds exactly this corpus."""
        # `k1` and `b` are scoring parameters, not index parameters: the postings
        # are the same for every value, so they are deliberately not in the key.
        # A sensitivity probe over them therefore reuses the index instead of
        # rebuilding fifteen minutes of it per value.
        key = hashlib.sha256(
            f"{self.analysis.fingerprint()}|{_corpus_digest(documents)}".encode("utf-8")
        ).hexdigest()
        self.cache_key = key
        self._buffer: np.ndarray | None = None
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
            (
                self.analysis.stemmer,
                self.analysis.stopwords,
                self.analysis.language,
                texts[start : start + chunks],
            )
            for start in range(0, len(texts), chunks)
        ]
        if workers == 1 or len(payload) <= 1 or len(texts) < self.PARALLEL_FROM:
            partials = [_chunk_postings(item) for item in payload]
        else:
            context = multiprocessing.get_context("fork")
            with context.Pool(processes=min(workers, len(payload))) as pool:
                partials = pool.map(_chunk_postings, payload, chunksize=1)
        built = _merge(partials)
        # The fragments and the merged arrays are the same size; dropping the
        # fragments before the cache write halves the peak on a large corpus.
        del partials
        if self.cache is not None:
            self._write_cache(Path(self.cache) / f"{key}.npz", *built)
        return built

    def _read_cache(self, path: Path) -> tuple[dict[str, int], dict] | None:
        if not path.exists():
            return None
        try:
            with np.load(path, allow_pickle=False) as saved:
                if "ids_blob" in saved.files:
                    ids = _unpack(saved["ids_blob"])
                else:
                    ids = [str(value) for value in saved["ids"]]
                if ids != self.ids:
                    return None
                if "terms" in saved.files:
                    # The original format: a fixed-width unicode array. Reading it
                    # is kept so a cache built before the change is still a hit.
                    terms = [str(value) for value in saved["terms"]]
                else:
                    terms = _unpack(saved["terms_blob"])
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
                ids_blob=_pack(self.ids),
                terms_blob=_pack(list(vocab)),
                **matrix,
            )
            temporary.replace(path)
        except OSError:
            # A cache that cannot be written is not a failure of the run.
            pass

    def _accumulate(self, query: str, accumulated: np.ndarray) -> bool:
        """Add this query's contribution into `accumulated`, in place.

        One copy of the scoring formula, because two copies are two definitions of
        the score and the second one is always the one that drifts.
        """
        terms = {self.vocab[token] for token in self.analysis(query) if token in self.vocab}
        if not terms:
            return False
        k1, b = self.config.k1, self.config.b
        for term in terms:
            start, end = self.matrix.indptr[term], self.matrix.indptr[term + 1]
            rows = self.matrix.indices[start:end]
            frequency = self.matrix.data[start:end]
            denominator = frequency + k1 * (
                1.0 - b + b * self.lengths[rows] / self.average_length
            )
            accumulated[rows] += self.idf[term] * frequency * (k1 + 1.0) / denominator
        return True

    def scores(self, query: str) -> dict[str, float]:
        """BM25 score per document, for the documents the query touches."""
        accumulated = np.zeros(len(self.ids), dtype=np.float32)
        if not self._accumulate(query, accumulated):
            return {}
        touched = np.flatnonzero(accumulated)
        return {self.ids[row]: float(accumulated[row]) for row in touched}

    def top_ids(self, query: str, k: int) -> tuple[tuple[str, ...], float]:
        """The top `k` under `metrics.rank`'s ordering, without materialising a dict.

        On 8.8M passages a query touches about a million documents, and building a
        million-entry dict per query — 6,980 times — is what makes the Italian
        corpus unaffordable. This keeps the same answer: the cutoff is found with
        `np.partition`, the documents strictly above it are ordered by score, and
        the boundary ties are resolved by id, exactly as `metrics.rank` does.
        """
        if k <= 0:
            raise ValueError("k must be positive")
        if self._buffer is None or len(self._buffer) != len(self.ids):
            self._buffer = np.zeros(len(self.ids), dtype=np.float32)
        accumulated = self._buffer
        accumulated.fill(0)
        if not self._accumulate(query, accumulated):
            return (), 0.0

        rows = np.flatnonzero(accumulated)
        values = accumulated[rows]
        if len(rows) > k:
            cutoff = float(np.partition(values, len(values) - k)[len(values) - k])
            above = values > cutoff
            head_rows, head_values = rows[above], values[above]
            need = k - int(above.sum())
            # `head_rows` is strictly above the cutoff, so it holds at most k - 1.
            ties = rows[values == cutoff]
            if need > 0 and len(ties):
                smallest = heapq.nsmallest(need, ties.tolist(), key=self.ids.__getitem__)
                head_rows = np.concatenate([head_rows, np.asarray(smallest, dtype=rows.dtype)])
                head_values = np.concatenate([head_values, np.full(len(smallest), cutoff, dtype=values.dtype)])
        else:
            head_rows, head_values = rows, values

        order = sorted(range(len(head_rows)), key=lambda position: (-head_values[position], self.ids[head_rows[position]]))
        chosen = [int(head_rows[position]) for position in order[:k]]
        return tuple(self.ids[row] for row in chosen), float(head_values[order[0]]) if chosen else 0.0

    def search(self, query: str, top_k: int = 100) -> tuple[str, ...]:
        """Ranked ids, ties broken by id so two runs are bit-identical."""
        return metrics.rank(self.scores(query), top_k=top_k)

    def describe(self) -> str:
        return f"{self.analysis.describe()} {self.config.describe()} documents={len(self.ids)}"


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


def evaluate_marco(index: BM25, questions: Sequence, depth: int = 1000) -> dict:
    """MRR@10, R@1000, nDCG@10 and a digest, scored through `top_ids`.

    `scores()` builds a dict of every document the query touches — around a
    million of them on 8.8M passages — and 6,980 of those is the difference
    between twelve minutes and an afternoon. The metrics are cut from the same
    ranked list `metrics.rank` would produce, and a test asserts the two agree.
    """
    if depth < 1000:
        raise ValueError("R@1000 needs a ranking of at least 1000")
    mrr: list[float] = []
    recall: list[float] = []
    ndcg: list[float] = []
    digest = hashlib.sha256()
    for question in questions:
        ranking, _ = index.top_ids(question.text, depth)
        mrr.append(metrics.mrr_at(ranking, question.gold_docs, 10))
        recall.append(metrics.recall_at(ranking, question.gold_docs, 1000))
        ndcg.append(metrics.ndcg_at(ranking, question.gold_docs, 10))
        digest.update(metrics.ranking_digest(ranking[:10]).encode("ascii"))
    return {
        "queries": len(questions),
        "mrr@10": float(np.mean(mrr)) if mrr else 0.0,
        "r@1000": float(np.mean(recall)) if recall else 0.0,
        "ndcg@10": float(np.mean(ndcg)) if ndcg else 0.0,
        "ranking_digest": digest.hexdigest()[:16],
    }


def reproduce_marco(
    analysis: Analysis | None = None,
    limit: int | None = None,
    depth: int = 1000,
    workers: int | None = None,
    config: BM25Config | None = None,
) -> dict:
    """Index the Italian collection, retrieve, and compare with the published row.

    This is the gate for the Italian analyser: the corpus is the translation the
    paper measured, so the only thing that can differ is our instrument. Both
    numbers must land within `TOLERANCE`, because a stemmer that helps MRR and
    hurts recall (or the reverse) is a stemmer that has not been reproduced, only
    reached once.
    """
    from benchmark.retrieval import adapters

    started = time.time()
    analysis = analysis or Analysis(stemmer="italian", language="italian")
    benchmark = adapters.mmarco_it(collection=True, limit=limit)
    documents = dict(benchmark.documents())
    loaded = time.time()
    index = BM25(documents, analysis=analysis, config=config, workers=workers)
    built = time.time()
    del documents
    scores = evaluate_marco(index, benchmark.questions, depth=depth)
    scored = time.time()

    published = PUBLISHED_MARCO["italian"]
    observed = {"mrr@10": scores["mrr@10"], "r@1000": scores["r@1000"]}
    return {
        "dataset": "mmarco-it",
        "documents": len(index.ids),
        "queries": scores["queries"],
        "config": f"{index.describe()} depth={depth}",
        "mrr@10": scores["mrr@10"],
        "r@1000": scores["r@1000"],
        "ndcg@10": scores["ndcg@10"],
        "published": published,
        "difference": {name: observed[name] - value for name, value in published.items()},
        "within_tolerance": all(
            abs(observed[name] - value) <= TOLERANCE for name, value in published.items()
        ),
        "ranking_digest": scores["ranking_digest"],
        "seconds": {
            "load": round(loaded - started, 1),
            "index": round(built - loaded, 1),
            "score": round(scored - built, 1),
            "total": round(scored - started, 1),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--reproduce", action="store_true", help="the Phase-0 instrument gate")
    parser.add_argument(
        "--reproduce-marco",
        action="store_true",
        help="the Italian instrument gate: mMARCO BM25, MRR@10 and R@1000",
    )
    parser.add_argument("--dataset", default="scifact", help="BEIR dataset name")
    parser.add_argument("--stemmer", default="porter", help="snowball algorithm, or 'none'")
    parser.add_argument("--no-stopwords", action="store_true")
    parser.add_argument("--limit", type=int, default=None, help="debug: score only the first N queries")
    parser.add_argument("--json", type=Path, help="write the result as an artifact")
    parser.add_argument("--workers", type=int, default=None, help="index build processes")
    parser.add_argument("--k1", type=float, default=0.9, help="BM25 term saturation (scoring only)")
    parser.add_argument("--b", type=float, default=0.4, help="BM25 length normalisation (scoring only)")
    args = parser.parse_args(argv)
    if not args.reproduce and not args.reproduce_marco:
        parser.print_help()
        return 0

    if args.reproduce_marco:
        result = reproduce_marco(
            limit=args.limit,
            workers=args.workers,
            config=BM25Config(k1=args.k1, b=args.b),
        )
        for key in ("dataset", "documents", "queries", "config", "ranking_digest"):
            print(f"{key:14s} {result[key]}")
        for key in ("mrr@10", "r@1000", "ndcg@10"):
            print(f"{key:14s} {result[key]:.4f}")
        for name, value in result["published"].items():
            print(f"{'published ' + name:14s} {value:.3f} (mMARCO Table 2, Google Translate)")
        for name, value in result["difference"].items():
            print(f"{'diff ' + name:14s} {value:+.4f}")
        print(f"{'gate':14s} {'PASS' if result['within_tolerance'] else 'FAIL'} (|difference| <= {TOLERANCE})")
        print(f"{'seconds':14s} {result['seconds']}")
        if args.json:
            import json

            args.json.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
            print(f"wrote {args.json}")
        return 0 if result["within_tolerance"] else 1

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
