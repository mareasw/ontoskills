"""The committed fixture is the contract between the Python core and the Rust reader.

`mcp/tests/fixtures/documents/` is a deterministic slice of a real knowledge
base, with the Python answers for 25 questions. The Rust tests compare against
it; these tests keep it honest from the Python side, where the answers were
produced:

* the golden answers are still what `ask()` returns now, so a change to the
  ranking that is not regenerated fails here instead of silently disagreeing
  with the binary;
* every quote in the fixture occurs in its document at the recorded offsets, so
  a reader that trusts the locator is not trusting a stale index;
* the stopword list in `mcp/src/documents/stopwords.rs` is the same list as
  `compiler.documents.text.STOPWORDS`, element for element.

The last one is the only way to catch a list edited on one side: Rust cannot
import the Python module, and a test that only checks `len()` would pass while
the two lists differ.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


from compiler.documents.ask import Corpus, ask
from compiler.documents.store import read_jsonl
from compiler.documents.text import STOPWORDS, norm

FIXTURE = Path(__file__).resolve().parents[2] / "mcp/tests/fixtures/documents"
KB = FIXTURE / "kb"
STOPWORDS_RS = Path(__file__).resolve().parents[2] / "mcp/src/documents/stopwords.rs"


def _golden() -> dict:
    return json.loads((FIXTURE / "golden.json").read_text(encoding="utf-8"))


def _claims() -> list[dict]:
    return read_jsonl(KB / "claims.jsonl")


def _texts() -> dict[str, str]:
    return {
        path.stem: path.read_text(encoding="utf-8")
        for path in (KB / "text").glob("*.txt")
    }


def test_the_fixture_carries_what_the_reader_opens() -> None:
    for name in ("manifest.json", "documents.jsonl", "claims.jsonl", "verifier.jsonl", "graph.ttl"):
        assert (KB / name).is_file(), f"{name} is missing from the fixture"
    texts = _texts()
    documents = read_jsonl(KB / "documents.jsonl")
    assert set(texts) == {document["doc_id"] for document in documents}
    claims = _claims()
    assert claims, "the fixture has no claims"
    assert all(claim["doc_id"] in texts for claim in claims)


def test_every_quote_is_at_its_offsets_in_the_normalised_text() -> None:
    """The gate a reader that follows the locator depends on."""
    texts = {doc_id: norm(text) for doc_id, text in _texts().items()}
    checked = 0
    for claim in _claims():
        source = texts[claim["doc_id"]]
        for item in claim["evidence"]:
            quote = norm(item["quote"])
            locator = item["locator"]
            start, end = locator["char_start"], locator["char_end"]
            assert source[start:end] == quote, (
                f"{claim['claim_id']}: offsets {start}:{end} do not hold the quote"
            )
            checked += 1
    assert checked >= 90


def test_the_golden_answers_are_still_what_the_core_returns() -> None:
    corpus = Corpus(
        read_jsonl(KB / "claims.jsonl"),
        read_jsonl(KB / "documents.jsonl"),
        read_jsonl(KB / "verifier.jsonl"),
    )
    golden = _golden()
    assert len(golden["answers"]) >= 20
    for expected in golden["answers"]:
        answer = ask(expected["question"], corpus, limit=10)
        assert [citation.claim_id for citation in answer.citations] == [
            citation["claim_id"] for citation in expected["citations"]
        ], f"{expected['qid']}: the fixture answer is stale"
        assert answer.documents == expected["documents"]
        assert [
            {"topic": tension.topic, "values": tension.values, "reason": tension.reason}
            for tension in answer.tensions
        ] == expected["tensions"]


def test_the_tokenizer_snapshot_matches_the_core() -> None:
    from compiler.documents.text import tokens

    for doc_id, expected in _golden()["tokenizer"].items():
        assert " ".join(tokens(_texts()[doc_id])) == expected["tokens"], doc_id


def _rust_stopwords() -> list[str]:
    text = STOPWORDS_RS.read_text(encoding="utf-8")
    block = text[text.index("pub static STOPWORDS") :]
    return re.findall(r'^\s*"((?:[^"\\]|\\.)*)",\s*$', block, flags=re.MULTILINE)


def test_the_rust_stopword_list_is_the_python_list() -> None:
    words = _rust_stopwords()
    assert len(words) == len(STOPWORDS)
    assert set(words) == set(STOPWORDS)
    # Sorted, so a regeneration that inserts one word in the middle shows up as
    # a one-line diff instead of a rewritten file.
    assert words == sorted(STOPWORDS)


def test_a_word_cannot_be_a_stopword_in_one_language_only_silently() -> None:
    """The list is generated from `text.py`; nothing here may be hand-edited.

    The check is the file's own header, which names the generator. A list copied
    twice drifts, and the way it drifts is that someone fixes one copy.
    """
    text = STOPWORDS_RS.read_text(encoding="utf-8")
    assert "Generated from `core/src/documents/text.py`" in text
    assert "make_documents_fixture" in text


def test_tie_groups_are_compared_as_sets_and_nothing_else_is() -> None:
    """Gate G1's only tolerance: a last-ULP difference inside equal scores.

    The pilot's ranking is BM25 over doubles accumulated in query order, and two
    implementations can disagree in the last bit. That reorders claims the
    reader cannot tell apart, so a tie group is compared as a set; a different
    claim, or a different order outside a tie group, is still a failure.
    """
    from benchmark.layer.mcp_parity import compare_rankings

    expected = [
        {"claim_id": "a", "score": 1.0},
        {"claim_id": "b", "score": 1.0},
        {"claim_id": "c", "score": 0.5},
    ]
    swapped_tie = [
        {"claim_id": "b", "score": 1.0},
        {"claim_id": "a", "score": 1.0},
        {"claim_id": "c", "score": 0.5},
    ]
    assert compare_rankings(expected, swapped_tie) is None

    reordered = [
        {"claim_id": "c", "score": 0.5},
        {"claim_id": "a", "score": 1.0},
        {"claim_id": "b", "score": 1.0},
    ]
    assert compare_rankings(expected, reordered) is not None

    different = [
        {"claim_id": "a", "score": 1.0},
        {"claim_id": "b", "score": 1.0},
        {"claim_id": "d", "score": 0.5},
    ]
    assert compare_rankings(expected, different) is not None

    assert compare_rankings(expected, expected[:2]) is not None
