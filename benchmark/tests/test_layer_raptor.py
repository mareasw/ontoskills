"""RAPTOR's chunking and precision, pinned so the rival cannot drift.

E16 compares a reimplementation against the claim layer. If the chunker silently
changed size, the comparison would still print a number and that number would be
about a different system. These tests are cheap and they close that door.
"""

from __future__ import annotations

from benchmark.layer.run_raptor import CHUNK_CHARS, CHUNK_OVERLAP, chunk, type_precision


def test_chunks_are_the_declared_size():
    text = " ".join(["word"] * 1_000)
    pieces = chunk(text)
    assert pieces
    for piece in pieces:
        assert len(piece) <= CHUNK_CHARS


def test_consecutive_chunks_overlap_by_the_declared_amount():
    text = "".join(chr(ord("a") + (index % 20)) for index in range(2_000))
    pieces = chunk(text)
    assert len(pieces) > 2
    step = CHUNK_CHARS - CHUNK_OVERLAP
    assert pieces[1].startswith(pieces[0][step:][: CHUNK_OVERLAP])


def test_short_fragments_are_dropped():
    """A heading or a stray line is not a retrieval unit."""
    assert chunk("Title") == []


def test_whitespace_is_normalised():
    pieces = chunk("a   b\n\n c\t" + "x " * 300)
    assert pieces
    assert "  " not in pieces[0]
    assert "\n" not in pieces[0]


def test_precision_ignores_the_questions_own_words():
    """A word the question already carries cannot be evidence of its answer."""
    gold = {"cache", "redis", "ttl"}
    question = {"what", "is", "the", "ttl"}
    text = "the ttl is set in redis with a cache layer"
    # Returned types minus the question's own: set, in, redis, with, cache, layer.
    # Of those, the gold facts use redis and cache: two of six.
    assert type_precision(gold, question, text) == 2 / 6


def test_precision_is_zero_when_nothing_new_is_returned():
    assert type_precision({"alpha"}, {"alpha"}, "alpha") == 0.0
