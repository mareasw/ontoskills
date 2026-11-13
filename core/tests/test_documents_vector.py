"""Rank fusion and vector arithmetic: no model, no network."""

from __future__ import annotations

import pytest

from compiler.documents.vector import cosine, fuse


def test_cosine_of_identical_vectors_is_one():
    assert cosine([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == 1.0


def test_cosine_of_orthogonal_vectors_is_zero():
    assert cosine([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_cosine_of_a_zero_vector_is_zero_instead_of_a_division_error():
    # A claim whose text carries no signal must not crash a query.
    assert cosine([0.0, 0.0], [1.0, 0.0]) == 0.0


def test_cosine_refuses_vectors_of_different_length():
    with pytest.raises(ValueError):
        cosine([1.0, 2.0], [1.0])


def test_fuse_puts_a_claim_two_rankers_agree_on_first():
    bm25 = ["A", "B", "C"]
    semantic = ["C", "A", "D"]
    assert [claim for claim, _ in fuse([bm25, semantic])][0] == "A"


def test_fuse_raises_a_claim_only_one_ranker_found():
    # The Q2 case: the counterpoint is lexically unreachable (rank 448 in BM25)
    # but semantically first. Fusion must bring it into the result.
    bm25 = [f"lex{i}" for i in range(12)] + ["counterpoint"]
    semantic = ["counterpoint"] + [f"sem{i}" for i in range(3)]
    order = [claim for claim, _ in fuse([bm25, semantic])]
    assert order.index("counterpoint") < 6


def test_fuse_is_deterministic_on_ties():
    assert fuse([["B", "A"]]) == fuse([["B", "A"]])


@pytest.mark.integration
def test_the_local_model_encodes_deterministically():
    from compiler.documents.vector import Embedder

    embedder = Embedder.load()
    first = embedder.encode_one("a retention period")
    second = embedder.encode_one("a retention period")
    assert first == second
    assert len(first) == 384
