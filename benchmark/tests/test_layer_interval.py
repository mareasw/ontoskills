from __future__ import annotations

import json

import pytest

from benchmark.layer import interval


def test_a_constant_has_no_spread():
    ci = interval.mean_ci([0.5] * 20)
    assert ci["mean"] == ci["low"] == ci["high"] == 0.5
    assert ci["n"] == 20


def test_the_interval_is_a_property_of_the_data_not_of_the_invocation():
    values = [0.0, 0.25, 0.5, 0.75, 1.0, 0.4, 0.6, 0.2]
    assert interval.mean_ci(values) == interval.mean_ci(values)


def test_the_interval_brackets_the_mean_and_tightens_with_n():
    small = interval.mean_ci([1.0, 0.0])
    large = interval.mean_ci([1.0, 0.0] * 100)
    for ci in (small, large):
        assert ci["low"] <= ci["mean"] <= ci["high"]
    assert (large["high"] - large["low"]) < (small["high"] - small["low"])


def test_an_empty_series_is_not_a_zero():
    assert interval.mean_ci([]) == {"n": 0, "mean": None, "low": None, "high": None}


def test_a_paired_difference_keeps_the_questions_paired():
    # Same mean on both sides, but every question differs: a paired test sees it.
    left = [1.0, 0.0, 1.0, 0.0]
    right = [0.0, 1.0, 0.0, 1.0]
    result = interval.paired_difference(left, right)
    assert result["mean"] == 0.0
    assert result["low"] <= 0.0 <= result["high"]


def test_a_paired_difference_refuses_unequal_lengths():
    with pytest.raises(ValueError, match="same questions"):
        interval.paired_difference([1.0, 0.0], [1.0])


def test_identical_systems_differ_by_zero():
    values = [0.1, 0.9, 0.4, 0.6]
    result = interval.paired_difference(values, values)
    assert result["mean"] == result["low"] == result["high"] == 0.0


def test_only_the_questions_both_sides_answered_are_compared():
    left = {
        "q1": {"answer_fact_coverage": 1.0},
        "q2": {"answer_fact_coverage": 0.5},
        "q3": {},  # the info_not_found question: no gold facts to cover
    }
    right = {
        "q1": {"answer_fact_coverage": 0.5},
        "q2": {"answer_fact_coverage": 0.0},
        "q3": {"answer_fact_coverage": 1.0},
    }
    result = interval.paired_metric(left, right, "answer_fact_coverage")
    assert result["n"] == 2
    assert result["mean"] == pytest.approx(0.5)


def test_the_command_writes_what_it_printed(tmp_path):
    left = tmp_path / "left.score.json"
    right = tmp_path / "right.score.json"
    left.write_text(
        json.dumps(
            {
                "per_question": [
                    {"qid": "q1", "answer_fact_coverage": 1.0},
                    {"qid": "q2", "answer_fact_coverage": 0.0},
                ]
            }
        ),
        encoding="utf-8",
    )
    right.write_text(
        json.dumps(
            {
                "per_question": [
                    {"qid": "q1", "answer_fact_coverage": 0.0},
                    {"qid": "q2", "answer_fact_coverage": 0.0},
                ]
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "intervals.json"
    code = interval.main(
        [
            "--score",
            str(left),
            "--score",
            str(right),
            "--metric",
            "answer_fact_coverage",
            "--json",
            str(out),
        ]
    )
    assert code == 0
    rows = json.loads(out.read_text(encoding="utf-8"))
    assert [row["kind"] for row in rows] == ["mean", "mean", "paired"]
    assert rows[2]["mean"] == 0.5
