"""The GraphRAG runner, tested for the only thing that costs money: not asking twice.

The index is never loaded here — `load_index` and the search function are
replaced — because what is under test is the file discipline of a run that pays
for every answer, not GraphRAG itself. A question that is on disk has been paid
for; a question still in memory has not.
"""

from __future__ import annotations

import argparse
import asyncio
import json

from benchmark.layer import run_graphrag

QUESTIONS = ["q1", "q2", "q3"]


def make_selection(tmp_path, qids=QUESTIONS, kinds=None):
    kinds = kinds or {}
    items = [
        {"qid": qid, "text": f"question {qid}", "kind": kinds.get(qid, "fact")}
        for qid in qids
    ]
    path = tmp_path / "selection.json"
    path.write_text(json.dumps({"items": items}), encoding="utf-8")
    return path


def make_args(tmp_path, selection, resume=False, kinds="", limit=None, out=None):
    return argparse.Namespace(
        root=tmp_path / "graphrag",
        selection=selection,
        out=out or tmp_path / "runs" / "graphrag.jsonl",
        method="local",
        kinds=kinds,
        limit=limit,
        resume=resume,
    )


def fake_index(monkeypatch):
    monkeypatch.setattr(run_graphrag, "load_index", lambda root: (object(), {}))


def fake_answers(monkeypatch, out, seen=None):
    """An `ask_local` that records what was already on disk when it was called."""

    async def ask(config, tables, question):
        if seen is not None:
            on_disk = []
            if out.exists():
                on_disk = [
                    json.loads(line)["qid"]
                    for line in out.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
            seen.append(on_disk)
        return f"answer to {question}"

    monkeypatch.setattr(run_graphrag, "ask_local", ask)


def answered(qid, answer=None):
    return {
        "qid": qid,
        "system": "graphrag",
        "method": "local",
        "answer": answer or f"answer to {qid}",
        "refused": False,
        "seconds": 1.0,
    }


def write_rows(path, rows, tail=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    path.write_text(body + tail, encoding="utf-8")


def qids_on_disk(path):
    return [
        json.loads(line)["qid"]
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_an_answer_is_on_disk_before_the_next_question_is_paid_for(tmp_path, monkeypatch):
    out = tmp_path / "runs" / "graphrag.jsonl"
    seen = []
    fake_index(monkeypatch)
    fake_answers(monkeypatch, out, seen)

    asyncio.run(run_graphrag.run(make_args(tmp_path, make_selection(tmp_path))))

    # Before each question, the answers already paid for are readable; the one
    # being asked is not there yet. A kill at any point loses at most the
    # question in flight.
    assert seen == [[], ["q1"], ["q1", "q2"]]
    assert qids_on_disk(out) == QUESTIONS


def test_resume_asks_only_the_questions_not_yet_paid_for(tmp_path, monkeypatch):
    out = tmp_path / "runs" / "graphrag.jsonl"
    write_rows(out, [answered("q1"), answered("q3")])
    asked = []

    async def ask(config, tables, question):
        asked.append(question)
        return f"answer to {question}"

    fake_index(monkeypatch)
    monkeypatch.setattr(run_graphrag, "ask_local", ask)

    asyncio.run(run_graphrag.run(make_args(tmp_path, make_selection(tmp_path), resume=True)))

    assert asked == ["question q2"]
    # Nothing is asked twice and nothing is lost.
    assert sorted(qids_on_disk(out)) == QUESTIONS


def test_a_run_killed_mid_line_keeps_its_readable_rows_and_rewrites_the_file(
    tmp_path, monkeypatch
):
    out = tmp_path / "runs" / "graphrag.jsonl"
    # The last write of a killed run: a truncated JSON object, no closing brace.
    write_rows(out, [answered("q1")], tail='{"qid": "q2", "answer": "half wri')
    asked = []

    async def ask(config, tables, question):
        asked.append(question)
        return f"answer to {question}"

    fake_index(monkeypatch)
    monkeypatch.setattr(run_graphrag, "ask_local", ask)

    asyncio.run(run_graphrag.run(make_args(tmp_path, make_selection(tmp_path), resume=True)))

    # The unreadable tail names no question, so q2 cannot be trusted as paid:
    # only q1 is skipped. The corrupt line is gone from the published file.
    assert asked == ["question q2", "question q3"]
    assert qids_on_disk(out) == QUESTIONS
    assert all("refused" in json.loads(line) for line in out.read_text().splitlines())


def test_a_failed_question_is_asked_again_on_resume_and_the_file_keeps_one_row(
    tmp_path, monkeypatch, capsys
):
    out = tmp_path / "runs" / "graphrag.jsonl"
    broken_row = answered("q2")
    broken_row["answer"] = "ERROR: RuntimeError: gateway fell over"
    write_rows(out, [answered("q1"), broken_row, answered("q3")])
    asked = []

    async def ask(config, tables, question):
        asked.append(question)
        return f"answer to {question}"

    fake_index(monkeypatch)
    monkeypatch.setattr(run_graphrag, "ask_local", ask)

    asyncio.run(run_graphrag.run(make_args(tmp_path, make_selection(tmp_path), resume=True)))

    # A failed call is paid for but it is not an answer: only that question is
    # asked again, and the file ends with one row per question and no error.
    assert asked == ["question q2"]
    rows = [json.loads(line) for line in out.read_text().splitlines() if line.strip()]
    assert [row["qid"] for row in rows] == QUESTIONS
    assert not any(row["answer"].startswith("ERROR:") for row in rows)
    summary = json.loads(capsys.readouterr().out)
    assert summary["retried"] == 1
    assert summary["resumed"] == 2
    assert summary["asked"] == 1


def test_resume_without_a_file_asks_everything(tmp_path, monkeypatch):
    out = tmp_path / "runs" / "graphrag.jsonl"
    asked = []

    async def ask(config, tables, question):
        asked.append(question)
        return f"answer to {question}"

    fake_index(monkeypatch)
    monkeypatch.setattr(run_graphrag, "ask_local", ask)

    asyncio.run(run_graphrag.run(make_args(tmp_path, make_selection(tmp_path), resume=True)))

    assert len(asked) == len(QUESTIONS)
    assert qids_on_disk(out) == QUESTIONS


def test_without_resume_a_previous_file_is_replaced_not_appended(tmp_path, monkeypatch):
    out = tmp_path / "runs" / "graphrag.jsonl"
    write_rows(out, [answered("q1"), answered("q2"), answered("q3")])
    fake_index(monkeypatch)
    fake_answers(monkeypatch, out)

    asyncio.run(run_graphrag.run(make_args(tmp_path, make_selection(tmp_path))))

    # A fresh, non-resumed run is a fresh measurement: three rows, not six.
    assert qids_on_disk(out) == QUESTIONS


def test_a_failed_question_is_recorded_as_data_and_the_run_continues(tmp_path, monkeypatch):
    out = tmp_path / "runs" / "graphrag.jsonl"

    async def ask(config, tables, question):
        if question.endswith("q2"):
            raise RuntimeError("gateway fell over")
        return f"answer to {question}"

    fake_index(monkeypatch)
    monkeypatch.setattr(run_graphrag, "ask_local", ask)

    asyncio.run(run_graphrag.run(make_args(tmp_path, make_selection(tmp_path))))

    rows = {row["qid"]: row for row in map(json.loads, out.read_text().splitlines())}
    assert sorted(rows) == QUESTIONS
    assert rows["q2"]["answer"] == "ERROR: RuntimeError: gateway fell over"


def test_the_summary_counts_what_was_resumed_and_what_was_asked(tmp_path, monkeypatch, capsys):
    out = tmp_path / "runs" / "graphrag.jsonl"
    write_rows(out, [answered("q1")])
    fake_index(monkeypatch)
    fake_answers(monkeypatch, out)

    asyncio.run(run_graphrag.run(make_args(tmp_path, make_selection(tmp_path), resume=True)))

    summary = json.loads(capsys.readouterr().out)
    assert summary["questions"] == 3
    assert summary["resumed"] == 1
    assert summary["asked"] == 2
    assert summary["unreadable_lines"] == 0
    assert summary["errors"] == 0


def test_kinds_and_limit_still_select_the_questions(tmp_path, monkeypatch):
    selection = make_selection(
        tmp_path,
        qids=QUESTIONS,
        kinds={"q1": "fact", "q2": "completeness", "q3": "completeness"},
    )
    asked = []

    async def ask(config, tables, question):
        asked.append(question)
        return "an answer"

    fake_index(monkeypatch)
    monkeypatch.setattr(run_graphrag, "ask_local", ask)

    asyncio.run(
        run_graphrag.run(
            make_args(tmp_path, selection, kinds="completeness", limit=1),
        )
    )

    assert asked == ["question q2"]
