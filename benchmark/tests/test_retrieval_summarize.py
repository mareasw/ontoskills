"""Tests for the Phase-1 summary: the table, the spread, the MDE, the Holm family.

The summary is the only place the protocol's "baseline spread and MDE" become
numbers, so it is tested on artifacts written by hand — no dataset, no network.
"""

from __future__ import annotations

import json

import pytest

from benchmark.retrieval import summarize


def artifact(dataset: str, system: str, values: dict[str, float], n_extra: int = 0) -> dict:
    rows = [{"qid": qid, "kind": "basic", "ndcg@k": value} for qid, value in values.items()]
    for index in range(n_extra):
        rows.append({"qid": f"x{index}", "kind": "basic", "ndcg@k": 0.0})
    mean = sum(row["ndcg@k"] for row in rows) / len(rows)
    return {
        "dataset": dataset,
        "split": "dev",
        "system": system,
        "analysis": "porter-stop",
        "k": 10,
        "questions": len(rows),
        "metrics": {
            "ndcg@k": {"mean": mean, "ci_low": mean - 0.1, "ci_high": mean + 0.1, "n": len(rows)},
            "recall@k": {"mean": mean, "ci_low": mean - 0.1, "ci_high": mean + 0.1, "n": len(rows)},
        },
        "digest": f"{system:0<16}",
        "seconds": 1.0,
        "config": {"retriever": f"{system} (porter-stop)"},
        "per_question": rows,
    }


@pytest.fixture
def artifacts():
    return [
        artifact("scifact", "bm25", {"a": 0.5, "b": 0.4, "c": 0.6}),
        artifact("scifact", "dense", {"a": 0.7, "b": 0.6, "c": 0.8}),
        artifact("scifact", "hybrid", {"a": 0.9, "b": 0.8, "c": 1.0}),
        artifact("qasper", "bm25", {"a": 0.3, "b": 0.2}),
        artifact("qasper", "dense", {"a": 0.1, "b": 0.2}),
    ]


def test_every_system_appears_with_its_own_n_and_digest(artifacts):
    summary = summarize.summarize(artifacts)
    scifact = summary["datasets"]["scifact"]["systems"]
    assert list(scifact) == ["bm25", "dense", "hybrid"]
    assert scifact["bm25"]["n"] == 3
    assert scifact["bm25"]["digest"] == "bm25000000000000"


def test_the_spread_is_the_best_minus_the_worst(artifacts):
    summary = summarize.summarize(artifacts)
    means = {name: value["mean"] for name, value in summary["datasets"]["scifact"]["systems"].items()}
    spread = summary["datasets"]["scifact"]["spread"]
    assert spread == pytest.approx(max(means.values()) - min(means.values()), abs=1e-4)
    assert spread > 0


def test_the_comparison_is_paired_and_reports_an_mde(artifacts):
    summary = summarize.summarize(artifacts)
    comparison = summary["datasets"]["scifact"]["comparisons"]["dense"]
    assert comparison["vs"] == "bm25"
    assert comparison["n"] == 3
    # Every question moved by exactly +0.2 in this fixture.
    assert comparison["mean_difference"] == pytest.approx(0.2, abs=1e-9)
    assert comparison["mde"] == pytest.approx(0.0, abs=1e-9), "zero variance means a zero MDE"
    assert comparison["p_wilcoxon"] <= 1.0


def test_a_losing_system_reports_a_negative_difference(artifacts):
    summary = summarize.summarize(artifacts)
    comparison = summary["datasets"]["qasper"]["comparisons"]["dense"]
    assert comparison["mean_difference"] < 0


def test_only_questions_that_carry_the_metric_are_paired():
    """A metric available on a subset must not be paired with zeros elsewhere."""
    left = artifact("erb", "bm25", {"a": 0.5, "b": 0.4, "c": 0.3})
    right = artifact("erb", "dense", {"a": 0.9, "b": 0.8, "c": 0.7})
    right["per_question"][1].pop("ndcg@k")  # 'b' does not support the metric at all
    summary = summarize.summarize([left, right])
    # Paired on the intersection: one question fewer than either system's n.
    assert summary["datasets"]["erb"]["comparisons"]["dense"]["n"] == 2
    assert summary["datasets"]["erb"]["systems"]["dense"]["n"] == 3


def test_holm_is_applied_across_the_datasets(artifacts):
    summary = summarize.summarize(artifacts)
    for dataset in ("scifact", "qasper"):
        assert "p_holm" in summary["datasets"][dataset]["comparisons"]["dense"]
    # Holm never lowers a p-value.
    for dataset in ("scifact", "qasper"):
        comparison = summary["datasets"][dataset]["comparisons"]["dense"]
        assert comparison["p_holm"] >= comparison["p_wilcoxon"] - 1e-12


def test_a_dataset_with_one_system_has_no_spread_and_no_comparison():
    summary = summarize.summarize([artifact("qasper", "bm25", {"a": 0.3})])
    entry = summary["datasets"]["qasper"]
    assert entry["spread"] is None
    assert entry["comparisons"] == {}


def test_the_table_prints_a_row_per_system(artifacts):
    text = summarize.format_table(summarize.summarize(artifacts))
    system_rows = [line for line in text.splitlines() if line.startswith("| scifact |") and " − " not in line]
    comparison_rows = [line for line in text.splitlines() if line.startswith("| scifact |") and " − " in line]
    assert len(system_rows) == 3, "one row per system"
    assert len(comparison_rows) == 2, "one comparison per non-reference system"
    assert any("MDE" in line for line in text.splitlines())


def test_artifacts_are_discovered_by_split(tmp_path):
    (tmp_path / "scifact-bm25-dev.json").write_text(json.dumps(artifact("scifact", "bm25", {"a": 1.0})), encoding="utf-8")
    (tmp_path / "scifact-bm25-holdout.json").write_text(json.dumps(artifact("scifact", "bm25", {"a": 0.0})), encoding="utf-8")
    found = summarize.load(tmp_path, "dev")
    assert len(found) == 1
    assert found[0]["dataset"] == "scifact"
