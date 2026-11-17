"""The answer file is a contract with the scorer: pin it.

`score.py` reads three things from each row — `qid`, `evidence`, `refused` — and
scores whatever they say. A harness that quietly switched from quotes to
restated statements, or that reported a refusal as an empty list without saying
so, would change every number downstream without changing a line of the metric
code. These tests hold the contract still.
"""

from __future__ import annotations

import json
from pathlib import Path

from benchmark.layer import answers


class Cite:
    def __init__(self, claim_id: str, doc_id: str, quote: str, statement: str = "a statement"):
        self.claim_id = claim_id
        self.doc_id = doc_id
        self.quote = quote
        self.statement = statement
        self.page = None
        self.section_path = []
        self.url = ""
        self.score = 1.5
        self.verdict = "ok"


class Result:
    def __init__(self, citations):
        self.citations = citations

    @property
    def documents(self):
        return list(dict.fromkeys(citation.doc_id for citation in self.citations))


def selection(*qids: str) -> dict:
    return {
        "corpus_digest": "d" * 64,
        "items": [{"qid": qid, "text": f"question {qid}", "kind": "basic"} for qid in qids],
    }


def test_evidence_is_the_verbatim_quote_not_the_statement(monkeypatch):
    cite = Cite("d1-0001", "d1", "The limit is 10 MiB.", statement="The cap is ten mebibytes.")
    monkeypatch.setattr("benchmark.layer.answers._corpus", lambda *a, **k: object())
    monkeypatch.setattr("compiler.documents.ask.ask", lambda *a, **k: Result([cite]))

    [row] = list(answers.answer_rows(Path("kb"), selection("q1"), limit=10))
    assert row["qid"] == "q1"
    assert row["evidence"] == ["The limit is 10 MiB."]
    assert row["refused"] is False
    assert row["documents"] == ["d1"]
    # The restated statement is recorded for a human reader and never scored as
    # evidence: scoring it would credit a claim for text it does not show.
    assert row["citations"][0]["quote"] == "The limit is 10 MiB."
    assert "The cap is ten mebibytes." in row["answer"]
    assert "The cap is ten mebibytes." not in row["evidence"]


def test_no_citation_is_a_refusal_not_an_empty_answer(monkeypatch):
    monkeypatch.setattr("benchmark.layer.answers._corpus", lambda *a, **k: object())
    monkeypatch.setattr("compiler.documents.ask.ask", lambda *a, **k: Result([]))

    [row] = list(answers.answer_rows(Path("kb"), selection("q1"), limit=10))
    assert row["refused"] is True
    assert row["evidence"] == []
    assert row["documents"] == []


def test_rows_follow_the_selection_order(monkeypatch):
    monkeypatch.setattr("benchmark.layer.answers._corpus", lambda *a, **k: object())
    monkeypatch.setattr("compiler.documents.ask.ask", lambda *a, **k: Result([]))

    rows = list(answers.answer_rows(Path("kb"), selection("q3", "q1", "q2"), limit=10))
    assert [row["qid"] for row in rows] == ["q3", "q1", "q2"]


def test_one_line_per_question_round_trips_as_json(tmp_path, monkeypatch):
    monkeypatch.setattr("benchmark.layer.answers._corpus", lambda *a, **k: object())
    monkeypatch.setattr(
        "compiler.documents.ask.ask",
        lambda *a, **k: Result([Cite("d1-0001", "d1", "quoted text")]),
    )
    sel = selection("q1", "q2")
    (tmp_path / "selection.json").write_text(json.dumps(sel), encoding="utf-8")
    out = tmp_path / "answers.jsonl"

    assert answers.main(
        ["--kb", str(tmp_path), "--selection", str(tmp_path / "selection.json"), "--out", str(out)]
    ) == 0

    lines = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert [line["qid"] for line in lines] == ["q1", "q2"]
    assert all(line["evidence"] == ["quoted text"] for line in lines)
