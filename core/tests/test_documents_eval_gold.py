"""The eval's arithmetic, on a fixture, with no knowledge base and no model."""

from __future__ import annotations

import json

from compiler.documents.eval import evaluate, load_gold, score


def test_a_question_scores_hit_recall_and_reciprocal_rank():
    gold = [{"id": "q1", "question": "retention", "expected": [
        {"doc_id": "T1", "quote": "six years after the end of the contract"},
        {"doc_id": "T2", "quote": "two years after the end of the contract"},
    ]}]
    ranked = {
        "q1": [
            {"claim_id": "T2-0001", "doc_id": "T2", "quote": "two years after the end of the contract"},
            {"claim_id": "T1-0009", "doc_id": "T1", "quote": "six years after the end of the contract"},
        ]
    }
    row = score(gold[0], ranked["q1"])
    assert row["hit"] is True
    assert row["recall"] == 1.0
    assert row["rr"] == 1.0


def test_a_missing_expected_claim_lowers_recall_without_a_hit():
    gold = {"id": "q2", "question": "audit", "expected": [
        {"doc_id": "T1", "quote": "the authority may audit the supplier"},
    ]}
    row = score(gold, [{"claim_id": "T9-0001", "doc_id": "T9", "quote": "unrelated text"}])
    assert row["hit"] is False
    assert row["recall"] == 0.0
    assert row["rr"] == 0.0


def test_load_gold_rejects_a_question_with_no_expectation(tmp_path):
    path = tmp_path / "questions.jsonl"
    path.write_text(json.dumps({"id": "q1", "question": "x", "expected": []}) + "\n")
    try:
        load_gold(path)
    except ValueError as exc:
        assert "no expected" in str(exc)
    else:
        raise AssertionError("a question with no expectation must be refused")


def test_the_gate_needs_both_hit_rate_and_recall():
    rows = [{"hit": True, "recall": 1.0, "rr": 1.0}] * 18 + [{"hit": False, "recall": 0.0, "rr": 0.0}] * 2
    summary = evaluate(rows)
    assert summary["hit_rate"] == 0.9
    assert summary["gate"] is True
