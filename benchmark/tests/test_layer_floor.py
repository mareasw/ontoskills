"""The floor must be a real floor: cover the corpus and return what it says.

A chunker with a gap in it would make the floor weaker than chunk-and-rank, and
the comparison would flatter every system above it. The tests pin coverage and
the k cap, not quality.
"""

from __future__ import annotations

import json

from benchmark.layer import run_floor


def test_every_character_is_covered_by_some_window():
    text = "".join(f"Sentence {number}. " for number in range(600))
    pieces = run_floor.windows(text)
    rebuilt = [False] * len(text)
    position = 0
    for piece in pieces:
        # Each window starts where its text appears; windows overlap, so the
        # check is coverage, not concatenation.
        start = text.find(piece[:40], 0 if position == 0 else max(0, position - run_floor.OVERLAP))
        assert start >= 0
        for offset in range(len(piece)):
            rebuilt[start + offset] = True
        position = start + len(piece)
    assert all(rebuilt)


def test_a_short_document_is_one_window():
    assert run_floor.windows("short text") == ["short text"]


def test_the_floor_returns_k_chunks_per_question(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    for number in range(3):
        (corpus / f"d{number}.txt").write_text(
            f"Document {number}. The upload limit is {number} MiB. " * 40, encoding="utf-8"
        )
    selection = {
        "corpus_digest": "d" * 64,
        "items": [
            {"qid": "q1", "text": "upload limit", "kind": "basic"},
            {"qid": "q2", "text": "document", "kind": "basic"},
        ],
    }
    (tmp_path / "selection.json").write_text(json.dumps(selection), encoding="utf-8")
    out = tmp_path / "floor.jsonl"

    assert run_floor.main(
        ["--corpus", str(corpus), "--selection", str(tmp_path / "selection.json"), "--out", str(out), "--k", "2"]
    ) == 0

    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert [row["qid"] for row in rows] == ["q1", "q2"]
    assert all(len(row["evidence"]) == 2 for row in rows)
    assert all(row["refused"] is False for row in rows)
    assert rows[0]["documents"] and rows[0]["documents"][0].startswith("d")


def test_the_build_record_says_zero_calls_and_measures_the_chunks(tmp_path):
    """The floor's row is the one whose cost is a fact, not a price."""
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    text = "The upload limit is 3 MiB. " * 30
    (corpus / "d1.txt").write_text(text, encoding="utf-8")
    selection = {"corpus_digest": "d" * 64, "items": [{"qid": "q1", "text": "upload", "kind": "basic"}]}
    (tmp_path / "selection.json").write_text(json.dumps(selection), encoding="utf-8")
    build = tmp_path / "floor.build.json"

    assert run_floor.main(
        [
            "--corpus",
            str(corpus),
            "--selection",
            str(tmp_path / "selection.json"),
            "--out",
            str(tmp_path / "floor.jsonl"),
            "--build",
            str(build),
        ]
    ) == 0

    row = json.loads(build.read_text(encoding="utf-8"))
    assert row["calls"] == 0
    assert row["prompt_tokens"] == row["completion_tokens"] == 0
    assert row["usd"] == 0.0
    assert row["artifact_bytes"] > 0
    assert row["artifact_note"].startswith("in memory")
