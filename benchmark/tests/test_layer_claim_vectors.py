"""The vector artifact must be readable back as exactly what was embedded."""

from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np
import pytest

from benchmark.layer import claim_vectors


class FakeEncoder:
    """Stands in for the pinned model: no torch, no download, same interface."""

    spec = SimpleNamespace(describe=lambda: "fake-e5 dim=2")

    def __init__(self, dim: int = 2):
        self.dim = dim
        self.seen: list[str] = []

    def encode_passages(self, texts, batch_size: int = 32):
        self.seen.extend(texts)
        return np.zeros((len(texts), self.dim), dtype=np.float32)


def claim(claim_id: str, statement: str, quote: str) -> dict:
    return {
        "claim_id": claim_id,
        "doc_id": "doc",
        "statement": statement,
        "evidence": [{"quote": quote}],
    }


def test_the_embedded_text_is_the_statement_and_the_first_quote():
    item = {
        "claim_id": "c1",
        "statement": "The limit is 10 MiB.",
        "evidence": [{"quote": "max_file_size is 10 MiB"}, {"quote": "ignored"}],
    }
    assert claim_vectors.claim_text(item) == "The limit is 10 MiB. max_file_size is 10 MiB"


def test_build_keeps_the_claim_order_and_the_spec():
    claims = [claim("c1", "one", "q1"), claim("c2", "two", "q2")]
    built = claim_vectors.build(claims, FakeEncoder())
    assert built["claim_ids"] == ["c1", "c2"]
    assert built["matrix"].shape == (2, 2)
    assert built["spec"] == "fake-e5 dim=2"


def test_the_file_round_trips_ids_and_matrix(tmp_path):
    claims = [claim("c1", "one", "q1"), claim("c2", "two", "q2"), claim("c3", "three", "q3")]
    path = tmp_path / "vectors.npz"
    claim_vectors.write(path, claim_vectors.build(claims, FakeEncoder()))
    ids, matrix = claim_vectors.read(path)
    assert ids == ["c1", "c2", "c3"]
    assert matrix.shape == (3, 2)
    assert matrix.dtype == np.float32


def test_a_matrix_with_the_wrong_number_of_rows_is_refused(tmp_path):
    path = tmp_path / "broken.npz"
    np.savez(
        path,
        claim_ids=np.array(json.dumps(["c1", "c2"])),
        matrix=np.zeros((1, 2), dtype=np.float32),
        spec=np.array("fake"),
        seconds=np.array(0.0),
    )
    with pytest.raises(ValueError, match="1 vectors for 2 ids"):
        claim_vectors.read(path)


def test_build_refuses_an_encoder_that_returns_a_different_count():
    class Short(FakeEncoder):
        def encode_passages(self, texts, batch_size: int = 32):
            return np.zeros((len(texts) - 1, 2), dtype=np.float32)

    with pytest.raises(ValueError, match="vectors for"):
        claim_vectors.build([claim("c1", "one", "q1"), claim("c2", "two", "q2")], Short())
