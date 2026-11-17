"""Dense and hybrid baselines: B2, B3, B4 from the protocol.

The lexical baseline answers "is the claim layer better than keyword search". It
does not answer "is it better than the strong hybrid everyone compares against",
and that second question is the one the product's README implicitly claims. So
the table needs a dense retriever and a fusion of the two, measured on the same
corpus, the same queries and the same k as BM25.

Three decisions are made here and recorded in `PREFLIGHT.md` §13 before any of
these numbers existed, because each of them can be tuned to flatter a system:

* **The model.** §6 allows "BGE-M3 or E5-large, pinned". BGE-M3 is 568M
  parameters and multi-vector; on the 4 GB card this harness runs on it is not
  practical at 512k documents, and a model that cannot cover the corpus is not a
  baseline. `intfloat/e5-large-v2` at a pinned revision is the choice, with its
  required `query:` / `passage:` prefixes applied — omitting them is a silent
  several-point loss that looks like the dense model being weak.
* **The cut.** 512 tokens, the model's own maximum. EnterpriseRAG-Bench carries
  long documents, so truncation is measured and reported rather than assumed
  away: a dense baseline that silently reads the first 512 tokens of a 3,000
  token contract is being handicapped, and the artifact says by how much.
* **The fusion.** Reciprocal rank fusion with k = 60, the value from Cormack et
  al. 2009, not a value tuned on these datasets.

The reranker is B4: fusion, then a cross-encoder over the fused top 50. Its depth
is fixed here too.

Everything is deterministic on one machine and one library build; unlike BM25
this is not claimed to be bit-identical across machines, because float matmul is
not. `--digest` re-runs the ranking and prints the digest so a rerun can be
checked rather than trusted.

    python3 benchmark/retrieval/dense.py --dataset scifact --build
    python3 benchmark/retrieval/dense.py --dataset scifact --stats
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.retrieval import baselines, metrics  # noqa: E402

CACHE_ROOT = Path(os.environ.get("ONTOSKILLS_BENCH_CACHE", Path.home() / ".cache" / "ontoskills-bench"))
EMBEDDING_CACHE = CACHE_ROOT / "embeddings"


@dataclass(frozen=True)
class ModelSpec:
    """What produced an embedding, recorded with the number it produced.

    The revision is a commit hash, not a tag: a tag can move, and a benchmark
    whose model can move underneath it is not a benchmark.
    """

    model_id: str
    revision: str
    max_length: int
    query_prefix: str
    passage_prefix: str
    dim: int

    def describe(self) -> str:
        return f"{self.model_id}@{self.revision[:12]} max={self.max_length}"


# The pinned pair, both resolved 2026-11-15 before the first dense run.
E5_LARGE_V2 = ModelSpec(
    model_id="intfloat/e5-large-v2",
    revision="f169b11e22de13617baa190a028a32f3493550b6",
    max_length=512,
    query_prefix="query: ",
    passage_prefix="passage: ",
    dim=1024,
)
CROSS_ENCODER = ModelSpec(
    model_id="cross-encoder/ms-marco-MiniLM-L-6-v2",
    revision="233902d25c440f23af6f7d6e94d2946bac0bee0a",
    max_length=512,
    query_prefix="",
    passage_prefix="",
    dim=1,
)

DEFAULT_MODEL = E5_LARGE_V2
RRF_K = 60
RERANK_DEPTH = 50


class Encoder(Protocol):
    """The seam that makes every test below runnable without a download."""

    spec: ModelSpec

    def encode_passages(self, texts: Sequence[str], batch_size: int = 32) -> np.ndarray: ...

    def encode_query(self, text: str) -> np.ndarray: ...


class SentenceEncoder:
    """A pinned SentenceTransformers model, normalized and on the GPU if present."""

    def __init__(self, spec: ModelSpec, device: str | None = None, batch_size: int = 32) -> None:
        from sentence_transformers import SentenceTransformer  # imported lazily: tests must not need torch

        self.spec = spec
        self.batch_size = batch_size
        self.model = SentenceTransformer(spec.model_id, revision=spec.revision, device=device)
        self.model.max_seq_length = spec.max_length

    def _encode(self, texts: Sequence[str], prefix: str) -> np.ndarray:
        import torch

        payload = [prefix + text for text in texts]
        with torch.inference_mode():
            matrix = self.model.encode(
                payload,
                batch_size=self.batch_size,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
        return np.asarray(matrix, dtype=np.float32)

    def encode_passages(self, texts: Sequence[str], batch_size: int = 32) -> np.ndarray:
        return self._encode(texts, self.spec.passage_prefix)

    def encode_query(self, text: str) -> np.ndarray:
        return self._encode([text], self.spec.query_prefix)[0]

    def over_length(self, texts: Sequence[str]) -> float:
        """Share of documents longer than the cut, measured rather than assumed.

        Determined on a deterministic sample: encoding a whole 512k corpus twice
        to count tokens is a cost this number does not justify.
        """
        tokenizer = self.model.tokenizer
        sample = _sample(texts)
        if not sample:
            return 0.0
        lengths = [len(tokenizer(self.spec.passage_prefix + text, truncation=False)["input_ids"]) for text in sample]
        return sum(1 for length in lengths if length > self.spec.max_length) / len(lengths)


def _sample(texts: Sequence[str], wanted: int = 500) -> list[str]:
    """Every n-th document, by position, so the sample is not the short ones.

    Taking the first 500 would measure the shortest documents in a corpus that
    is usually sorted by source, and would understate truncation.
    """
    if not texts:
        return []
    step = max(1, len(texts) // wanted)
    return list(texts[::step][:wanted])


# --- the embedding cache ----------------------------------------------------


def _cache_path(spec: ModelSpec, documents: dict[str, str]) -> Path:
    """Content-addressed: the key is the model revision, the cut and the corpus.

    Hashing the corpus costs seconds; encoding it costs hours. What must not
    happen is a cache hit for a different corpus, so the key is the text itself
    rather than a fingerprint of its size.
    """
    digest = hashlib.sha256()
    digest.update(spec.describe().encode("utf-8"))
    digest.update(b"\x00")
    digest.update(str(len(documents)).encode("utf-8"))
    digest.update(b"\x00")
    digest.update(baselines._corpus_digest(documents).encode("utf-8"))
    return EMBEDDING_CACHE / f"{digest.hexdigest()[:32]}.npy"


def _ids_path(path: Path) -> Path:
    return path.with_suffix(".ids.json")


def _load(path: Path, expected_ids: Sequence[str], dim: int) -> np.ndarray | None:
    """A cache entry, or None if it cannot be the right one.

    A truncated `.npy` raises `ValueError`/`EOFError` rather than an `OSError`,
    and a partial write must not take down the run it exists to speed up — the
    same defect the BM25 cache had, fixed the same way.
    """
    if not path.exists():
        return None
    try:
        matrix = np.load(path, mmap_mode="r")
        ids = json.loads(_ids_path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, EOFError, json.JSONDecodeError):
        return None
    if matrix.ndim != 2 or matrix.shape != (len(expected_ids), dim):
        return None
    if list(expected_ids) != ids:
        return None
    return matrix


def build_embeddings(
    documents: dict[str, str],
    spec: ModelSpec = DEFAULT_MODEL,
    encoder: Encoder | None = None,
    batch_size: int = 32,
    cache: bool = True,
    progress: bool = False,
) -> tuple[np.ndarray, dict]:
    """Embed a corpus once, in id order, and reuse it.

    Batches are a fixed slice of a fixed order, so the matrix is the same on a
    rerun of the same corpus on the same machine. That is the determinism this
    layer claims: same machine, same library; `metrics.ranking_digest` is what
    makes a rerun checkable.
    """
    path = _cache_path(spec, documents)
    cached = _load(path, list(documents), spec.dim) if cache else None
    if cached is not None:
        return cached, {"cache": "hit", "path": str(path)}

    encoder = encoder or SentenceEncoder(spec, batch_size=batch_size)
    ids = list(documents)
    texts = [documents[doc_id] for doc_id in ids]
    chunks: list[np.ndarray] = []
    for start in range(0, len(texts), 2048):
        chunks.append(encoder.encode_passages(texts[start : start + 2048], batch_size=batch_size))
        if progress:
            print(f"  encoded {min(start + 2048, len(texts))}/{len(texts)}", file=sys.stderr, flush=True)
    matrix = np.vstack(chunks) if chunks else np.zeros((0, spec.dim), dtype=np.float32)
    if matrix.shape[1] != spec.dim:
        raise SystemExit(f"{spec.model_id}: expected {spec.dim} dimensions, got {matrix.shape[1]}")

    info: dict = {"cache": "miss", "path": str(path), "documents": len(ids)}
    if cache:
        EMBEDDING_CACHE.mkdir(parents=True, exist_ok=True)
        staged = path.with_suffix(".part")
        # Through a handle: `np.save` appends `.npy` to a name that lacks it, and
        # a staged file called `<key>.part.npy` never replaces `<key>.npy`.
        with staged.open("wb") as handle:
            np.save(handle, matrix)
        staged.replace(path)
        _ids_path(path).write_text(json.dumps(ids), encoding="utf-8")
    return matrix, info


# --- the retrievers ---------------------------------------------------------


class Dense:
    """B2: cosine over a pinned bi-encoder, no lexical component."""

    def __init__(
        self,
        documents: dict[str, str],
        spec: ModelSpec = DEFAULT_MODEL,
        encoder: Encoder | None = None,
        cache: bool = True,
        batch_size: int = 32,
    ) -> None:
        # The encoder carries the model it was built from, and a test encoder that
        # disagrees with the declared spec is a mistake, not a configuration.
        self.spec = getattr(encoder, "spec", None) or spec
        self.ids = list(documents)
        self.matrix, self.build_info = build_embeddings(
            documents, spec=self.spec, encoder=encoder, cache=cache, batch_size=batch_size
        )
        self._encoder = encoder

    def _encoder_for_queries(self) -> Encoder:
        if self._encoder is None:
            self._encoder = SentenceEncoder(self.spec)
        return self._encoder

    def scores(self, query: str) -> dict[str, float]:
        vector = self._encoder_for_queries().encode_query(query)
        # Chunked so a 512k x 1024 corpus does not need a second copy of itself.
        best = np.empty(len(self.ids), dtype=np.float32)
        for start in range(0, len(self.ids), 100_000):
            best[start : start + 100_000] = np.asarray(self.matrix[start : start + 100_000]) @ vector
        return dict(zip(self.ids, best.tolist(), strict=True))

    def describe(self) -> str:
        return f"dense ({self.spec.describe()})"


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[str]], k: int = RRF_K
) -> dict[str, float]:
    """RRF: sum of 1/(k + rank), ranks one-based, Cormack et al. 2009.

    Written out and unit-tested rather than taken from a library, because the
    fused order *is* the B3 number and a convenience function that quietly
    changes its normalisation would move it.
    """
    if k <= 0:
        raise ValueError("RRF k must be positive")
    fused: dict[str, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            fused[doc_id] = fused.get(doc_id, 0.0) + 1.0 / (k + rank)
    return fused


class Hybrid:
    """B3: BM25 and B2 fused by rank — the non-inferiority target."""

    def __init__(
        self,
        documents: dict[str, str],
        analysis: baselines.Analysis | None = None,
        spec: ModelSpec = DEFAULT_MODEL,
        encoder: Encoder | None = None,
        cache: bool = True,
    ) -> None:
        self.documents = documents
        self.lexical = baselines.BM25(documents, analysis=analysis)
        self.dense = Dense(documents, spec=spec, encoder=encoder, cache=cache)

    def scores(self, query: str) -> dict[str, float]:
        lexical = metrics.rank(self.lexical.scores(query))
        dense = metrics.rank(self.dense.scores(query))
        return reciprocal_rank_fusion((lexical, dense))

    def describe(self) -> str:
        return f"bm25+{self.dense.describe()} rrf(k={RRF_K})"


class Reranked:
    """B4: B3's fused top 50, reordered by a cross-encoder.

    Documents below the depth keep their fused order, mapped strictly under the
    reranked block: the reranker is allowed to reorder what it read, never to
    promote something it did not read over something it did.
    """

    def __init__(
        self,
        documents: dict[str, str],
        base,
        spec: ModelSpec = CROSS_ENCODER,
        depth: int = RERANK_DEPTH,
        batch_size: int = 32,
    ) -> None:
        self.documents = documents
        self.base = base
        self.spec = spec
        self.depth = depth
        self.batch_size = batch_size
        self._model = None

    def _cross_encoder(self):
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self.spec.model_id, revision=self.spec.revision, max_length=self.spec.max_length)
        return self._model

    def scores(self, query: str) -> dict[str, float]:
        fused = self.base.scores(query)
        ordered = metrics.rank(fused)
        head = list(ordered[: self.depth])
        tail = list(ordered[self.depth :])
        if not head:
            return fused

        model = self._cross_encoder()
        pairs = [(query, text) for text in self._texts(head)]
        logits = np.asarray(model.predict(pairs, batch_size=self.batch_size, show_progress_bar=False), dtype=np.float32)

        scores: dict[str, float] = dict(zip(head, logits.tolist(), strict=True))
        floor = float(logits.min()) - 1.0
        for position, doc_id in enumerate(tail):
            scores[doc_id] = floor - position * 1e-6
        return scores

    def _texts(self, ids: Sequence[str]) -> list[str]:
        return [self.documents[doc_id] for doc_id in ids]

    def describe(self) -> str:
        return f"{self.base.describe()} + rerank({self.spec.describe()}, depth={self.depth})"


def hybrid(documents: dict[str, str], analysis: baselines.Analysis | None = None) -> Hybrid:
    """The registry entry for B3."""
    return Hybrid(documents, analysis=analysis)


def hybrid_rerank(documents: dict[str, str], analysis: baselines.Analysis | None = None) -> Reranked:
    """The registry entry for B4."""
    return Reranked(documents, base=Hybrid(documents, analysis=analysis))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--build", action="store_true", help="embed the corpus and cache it")
    parser.add_argument("--stats", action="store_true", help="report the truncation share")
    parser.add_argument("--device", default=None)
    args = parser.parse_args(argv)

    from benchmark.retrieval import adapters

    benchmark = adapters.ADAPTERS[args.dataset]()
    documents = dict(benchmark.documents())
    if not documents:
        raise SystemExit(f"{args.dataset}: the adapter returned no documents")

    encoder = SentenceEncoder(DEFAULT_MODEL, device=args.device)
    if args.build:
        matrix, info = build_embeddings(documents, encoder=encoder, progress=True)
        print(json.dumps({**info, "shape": list(matrix.shape)}, indent=2))
    if args.stats:
        share = encoder.over_length([documents[doc_id] for doc_id in documents])
        print(
            json.dumps(
                {
                    "model": DEFAULT_MODEL.describe(),
                    "documents": len(documents),
                    "max_length": DEFAULT_MODEL.max_length,
                    "truncated_share": round(share, 4),
                    "sampled": len(_sample(list(documents.values()))),
                },
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
