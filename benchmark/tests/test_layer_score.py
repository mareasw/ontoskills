"""The scorer: refusals are outcomes, not zeros, and k cannot buy coverage."""

from __future__ import annotations

import pytest

from benchmark.layer.score import read_answers, score_question, summarise


def selection(items: list[dict]) -> dict:
    return {"corpus_digest": "deadbeef" * 4, "items": items}


def item(qid: str, kind: str, facts: tuple[str, ...], docs: tuple[str, ...] = ("d1",)) -> dict:
    return {"qid": qid, "kind": kind, "gold_facts": list(facts), "gold_docs": list(docs)}


def test_read_answers_refuses_a_duplicate(tmp_path):
    path = tmp_path / "a.jsonl"
    path.write_text('{"qid": "q1", "answer": "x"}\n{"qid": "q1", "answer": "y"}\n', encoding="utf-8")
    with pytest.raises(SystemExit):
        read_answers(path)


def test_read_answers_refuses_a_line_without_qid(tmp_path):
    path = tmp_path / "a.jsonl"
    path.write_text('{"answer": "x"}\n', encoding="utf-8")
    with pytest.raises(SystemExit):
        read_answers(path)


def test_read_answers_skips_comments_and_blanks(tmp_path):
    path = tmp_path / "a.jsonl"
    path.write_text('# a note\n\n{"qid": "q1", "answer": "x"}\n', encoding="utf-8")
    assert list(read_answers(path)) == ["q1"]


def test_a_perfect_answer_scores_one():
    outcome = score_question(item("q1", "basic", ("The limit is 10 MiB.",)), {"qid": "q1", "answer": "The limit is 10 MiB."}, "answer", k=10)
    assert outcome["answer_fact_coverage"] == 1.0
    assert outcome["answer_fact_support"] == 1.0
    assert outcome["numeric_congruence"] == 1.0


def test_a_wrong_number_is_not_coverage():
    outcome = score_question(item("q1", "basic", ("The limit is 10 MiB.",)), {"qid": "q1", "answer": "The limit is 20 MiB."}, "answer", k=10)
    assert outcome["answer_fact_coverage"] < 1.0
    assert outcome["numeric_congruence"] == 0.0


def test_a_refusal_is_an_outcome_and_carries_no_quality():
    outcome = score_question(item("q1", "basic", ("a fact",)), {"qid": "q1", "refused": True}, "answer", k=10)
    assert outcome["refused"] is True
    assert "answer_fact_coverage" not in outcome


def test_a_missing_answer_is_recorded_as_missing():
    outcome = score_question(item("q1", "basic", ("a fact",)), None, "answer", k=10)
    assert outcome["missing"] is True
    assert "answer_fact_coverage" not in outcome


def test_refusals_can_be_reread_from_the_text_without_asking_again():
    """A prose run's `refused` flag is derived, so a better reader must be able to replace it.

    A run is paid for once. When the classifier learns a phrasing the model
    actually uses, re-scoring has to apply it to the text already on disk — and it
    must never turn our own structural refusals inside out, which is why the flag
    is honoured for `evidence` and for rows without an `answer`.
    """
    data = selection([item("q1", "basic", ("The limit is 10 MiB.",))])
    answers = {"q1": {"qid": "q1", "answer": "I don\u2019t know \u2014 the data does not state it.", "refused": False}}

    trusted = summarise(data, answers, "answer", k=10, resamples=200)
    rechecked = summarise(data, answers, "answer", k=10, resamples=200, recheck_refusals=True)

    assert trusted["false_refusal_rate"] == 0.0
    assert rechecked["false_refusal_rate"] == 1.0
    assert rechecked["by_kind"]["basic"]["refused"] == 1
    assert "answer_fact_coverage" not in rechecked["per_question"][0]


def test_rechecking_refusals_does_not_touch_the_evidence_modality():
    """Our own row records a refusal structurally, and a citation list is not prose."""
    data = selection([item("q1", "basic", ("The limit is 10 MiB.",))])
    answers = {"q1": {"qid": "q1", "evidence": ["The limit is 10 MiB."], "refused": False}}
    result = summarise(data, answers, "evidence", k=10, resamples=200, recheck_refusals=True)
    assert result["false_refusal_rate"] == 0.0
    assert result["by_kind"]["basic"]["metrics"]["answer_fact_coverage"]["mean"] == 1.0


def test_k_caps_the_evidence_a_system_can_be_credited_for():
    row = {"qid": "q1", "evidence": ["irrelevant words here", "The limit is 10 MiB."]}
    generous = score_question(item("q1", "basic", ("The limit is 10 MiB.",)), row, "evidence", k=10)
    capped = score_question(item("q1", "basic", ("The limit is 10 MiB.",)), row, "evidence", k=1)
    assert generous["answer_fact_support"] == 1.0
    assert capped["answer_fact_support"] < 1.0


def test_summarise_separates_refusal_from_quality():
    data = selection(
        [
            item("q1", "basic", ("The limit is 10 MiB.",)),
            item("q2", "basic", ("The cap is 50 MiB.",), docs=("d2",)),
            item("q3", "info_not_found", (), docs=()),
        ]
    )
    answers = {
        "q1": {"qid": "q1", "answer": "The limit is 10 MiB."},
        "q2": {"qid": "q2", "refused": True},
        "q3": {"qid": "q3", "refused": True},
    }
    result = summarise(data, answers, "answer", k=10, resamples=200)
    assert result["selection_digest"] == "deadbeef" * 4
    assert result["answered"] == 3
    assert result["missing"] == []
    assert result["false_refusal_rate"] == 0.5  # one of the two answerable questions refused
    assert result["abstention_rate"] == 1.0
    basic = result["by_kind"]["basic"]
    assert basic["questions"] == 2
    assert basic["refused"] == 1
    assert basic["metrics"]["answer_fact_coverage"]["n"] == 1
    assert basic["metrics"]["answer_fact_coverage"]["mean"] == 1.0


def test_summarise_lists_facts_only_where_the_dataset_has_them():
    # high_level carries facts and no document; info_not_found carries neither.
    data = selection(
        [
            item("q1", "high_level", ("an aggregate fact",), docs=()),
            item("q2", "info_not_found", (), docs=()),
        ]
    )
    answers = {"q1": {"qid": "q1", "answer": "an aggregate fact"}, "q2": {"qid": "q2", "refused": True}}
    result = summarise(data, answers, "answer", k=10, resamples=200)
    assert result["by_kind"]["high_level"]["metrics"]["answer_fact_coverage"]["mean"] == 1.0
    assert result["by_kind"]["info_not_found"]["metrics"] == {}
    assert result["abstention_rate"] == 1.0
    assert result["false_refusal_rate"] == 0.0


def test_a_character_budget_equalises_volume_not_only_k():
    """Lexical coverage rises with characters returned, so volume is capped too."""
    long_passage = "filler " * 200
    row = {"qid": "q1", "evidence": [long_passage, "The limit is 10 MiB."]}
    full = score_question(item("q1", "basic", ("The limit is 10 MiB.",)), row, "evidence", k=10)
    tight = score_question(
        item("q1", "basic", ("The limit is 10 MiB.",)), row, "evidence", k=10, max_chars=10
    )
    assert full["answer_fact_support"] == 1.0
    # The budget cannot afford the second passage, and the first one is kept
    # whole rather than cut mid-sentence.
    assert tight["answer_fact_support"] < 1.0
    assert tight["chars"] == len(long_passage)


def test_the_budget_keeps_the_first_passage_even_when_it_is_too_big():
    """A budget is a ceiling on the extras, not a licence to truncate a quote."""
    row = {"qid": "q1", "evidence": ["x" * 500]}
    outcome = score_question(item("q1", "basic", ("nothing",)), row, "evidence", k=10, max_chars=1)
    assert outcome["chars"] == 500


def test_the_summary_reports_the_median_characters_returned():
    data = selection([item("q1", "basic", ("The limit is 10 MiB.",))])
    answers = {"q1": {"qid": "q1", "answer": "The limit is 10 MiB."}}
    result = summarise(data, answers, "answer", k=10, resamples=200)
    assert result["median_chars"] == len("The limit is 10 MiB.")
    assert result["max_chars"] is None
    assert "median chars" in __import__("benchmark.layer.score", fromlist=["format_score"]).format_score(result)
