"""Local sentence embeddings, cosine, and rank fusion.

No network at query time and no paid call: the model is MiniLM, pinned by id
and revision, loaded from the local Hugging Face cache. Every function here is
deterministic, and every caller must work without it — the knowledge base
answers from BM25 alone when the optional runtime is absent.
"""

from __future__ import annotations

import math

MODEL = "sentence-transformers/all-MiniLM-L6-v2"
REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
DIM = 384
RRF_K = 60

# The model is trained on English. On a corpus in another language its cosine
# ranking is not a second opinion but a guess, and it measured worse than the
# words themselves on the Italian pilot: hit@12 8 of 10 against 9, MRR 0.326
# against 0.431, with two questions that the lexical pass answered first pushed
# out of the top twelve. So the fusion is applied only to the languages the
# model was trained on. A knowledge base that does not declare its language
# keeps the fusion: there is nothing to compare against it.
LANGUAGES = frozenset({"en"})


def supports(languages) -> bool:
    """True when at least one of the corpus languages is one the model knows."""
    known = {language for language in (languages or ()) if language}
    return not known or bool(known & LANGUAGES)



def cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError("vectors of different length")
    dot = sum(a * b for a, b in zip(left, right))
    norm_left = math.sqrt(sum(a * a for a in left))
    norm_right = math.sqrt(sum(b * b for b in right))
    if not norm_left or not norm_right:
        return 0.0
    return dot / (norm_left * norm_right)


def fuse(rankings: list[list[str]], k: int = RRF_K) -> list[tuple[str, float]]:
    """Reciprocal Rank Fusion: ranks only, so there is no weight to tune."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, claim_id in enumerate(ranking, start=1):
            scores[claim_id] = scores.get(claim_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


class Embedder:
    """The model, wrapped so the rest of the code never imports torch."""

    def __init__(self, model) -> None:
        self.model = model

    @classmethod
    def load(cls) -> "Embedder":
        from sentence_transformers import SentenceTransformer  # optional dependency

        # ``local_files_only`` is the promise this module makes: the pinned
        # revision is already in the cache, so a query never reaches the network.
        return cls(
            SentenceTransformer(
                MODEL, revision=REVISION, device="cpu", local_files_only=True
            )
        )

    def encode(self, texts: list[str]) -> list[list[float]]:
        vectors = self.model.encode(
            texts, batch_size=32, normalize_embeddings=False, show_progress_bar=False
        )
        return [[round(float(value), 6) for value in vector] for vector in vectors]

    def encode_one(self, text: str) -> list[float]:
        return self.encode([text])[0]


def embedder_for(kb) -> Embedder:
    """Load the embedder for a KB, refusing a different model's vectors."""
    header = kb.vectors_header()
    if header.get("model") not in (None, MODEL):
        raise ValueError(f"{kb.root}: vectors were built with {header['model']}, not {MODEL}")
    return Embedder.load()
