"""The runner is the only place that turns a system into a number, so the tests
here pin the four things it must never do: score a split it cannot verify, score
a document outside a question's scope, report a metric the dataset cannot carry,
or report a different digest for the same ranking.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from benchmark.retrieval import adapters, partition, runner  # noqa: E402

DOCUMENTS = {
    "d1": "the capital of france is paris",
    "d2": "paris is a large city in europe",
    "d3": "the amazon river flows through brazil",
    "d4": "brazil borders argentina and peru",
}


def _questions() -> tuple[adapters.Question, ...]:
    """Eight questions, one of them unanswerable and one unanswerable only in
    name of gold facts. Enough that a 50/50 split leaves both sides non-empty."""
    items = [
        adapters.Question(qid=f"q{index}", text=text, gold_docs=(doc,), kind="basic" if index % 2 else "hard")
        for index, (text, doc) in enumerate(
            [
                ("capital of france", "d1"),
                ("largest city in europe", "d2"),
                ("amazon river", "d3"),
                ("country bordering peru", "d4"),
                ("france capital city", "d1"),
                ("europe city paris", "d2"),
                ("river brazil", "d3"),
                ("argentina border", "d4"),
            ]
        )
    ]
    items.append(
        adapters.Question(qid="abstain", text="population of mars", kind="info_not_found", answerable=False)
    )
    return tuple(items)


def _benchmark() -> adapters.Benchmark:
    return adapters.Benchmark(
        name="stub",
        questions=_questions(),
        documents=lambda: iter(DOCUMENTS.items()),
        citation="a stub, for the runner's tests",
        licence="none",
    )


@pytest.fixture()
def stub(monkeypatch, tmp_path):
    """A registered stub dataset with its partition already committed."""
    monkeypatch.setitem(adapters.ADAPTERS, "stub", _benchmark)
    path = partition.build("stub", _questions()).write(tmp_path / "stub.json")
    return path.parent


def test_a_run_scores_exactly_one_side_of_the_partition(stub):
    committed = partition.verify(stub / "stub.json", _questions())
    result = runner.run("stub", split=partition.DEV, partitions=stub, resamples=200)
    # `questions` is what was scored; the unanswerable ones are named instead, so
    # the two together must be the whole dev side. Asserting only `questions`
    # would let a run that dropped a question look right.
    assert result.questions + len(result.unanswerable) == len(committed.dev)
    assert result.split == partition.DEV
    assert result.partition_digest == committed.digest()
    assert set(result.unanswerable) <= {"abstain"}
    assert sum(1 for question in _questions() if not question.answerable) == 1


def test_the_two_halves_do_not_overlap_and_cover_the_set(stub):
    dev = runner.run("stub", split=partition.DEV, partitions=stub, resamples=100)
    holdout = runner.run("stub", split=partition.HOLDOUT, partitions=stub, resamples=100)
    scored_dev = {row["qid"] for row in dev.per_question}
    scored_holdout = {row["qid"] for row in holdout.per_question}
    assert not scored_dev & scored_holdout
    assert scored_dev | scored_holdout == {
        question.qid for question in _questions() if question.answerable
    }
    # Eight answerable questions and one unanswerable: the unanswerable one is on
    # exactly one side and is named, not scored, so it appears in the union of
    # `unanswerable` and nowhere else.
    assert dev.questions + holdout.questions == 8
    assert len(dev.unanswerable) + len(holdout.unanswerable) == 1


def test_a_missing_partition_stops_the_run_instead_of_guessing(monkeypatch, tmp_path):
    """Scoring an unpartitioned dataset would silently use a split nobody fixed."""
    monkeypatch.setitem(adapters.ADAPTERS, "stub", _benchmark)
    with pytest.raises(SystemExit, match="no committed partition"):
        runner.run("stub", split=partition.DEV, partitions=tmp_path, resamples=10)


def test_a_drifted_partition_stops_the_run_instead_of_rescoring(tmp_path, monkeypatch):
    """A dataset that changed under a committed split must stop the run, not
    quietly score the questions that happen to still be there."""
    partition.build("stub", _questions()).write(tmp_path / "stub.json")
    shrunken = _benchmark()
    trimmed = adapters.Benchmark(
        name=shrunken.name,
        questions=_questions()[:4],
        documents=shrunken.documents,
        citation=shrunken.citation,
        licence=shrunken.licence,
    )
    monkeypatch.setitem(adapters.ADAPTERS, "stub", lambda: trimmed)
    with pytest.raises(SystemExit, match="changed"):
        runner.run("stub", split=partition.DEV, partitions=tmp_path, resamples=10)


def test_a_dataset_without_gold_facts_names_the_metrics_it_skipped(stub):
    result = runner.run("stub", split="all", partitions=stub, resamples=100)
    assert "answer_fact_coverage" in result.missing_metrics
    assert "answer_fact_coverage" not in result.metrics
    # The document-level metrics are still there: skipping one is not skipping all.
    assert {"ndcg@k", "recall@k", "mrr@k", "hit@k"} <= set(result.metrics)


def test_gold_facts_add_the_answer_level_metrics(monkeypatch, tmp_path):
    questions = tuple(
        adapters.Question(
            qid=f"f{index}",
            text="capital of france",
            gold_docs=("d1",),
            gold_facts=("paris is the capital of france",),
            kind="basic",
        )
        for index in range(4)
    )
    monkeypatch.setitem(
        adapters.ADAPTERS,
        "facts",
        lambda: adapters.Benchmark(
            name="facts",
            questions=questions,
            documents=lambda: iter(DOCUMENTS.items()),
            citation="stub",
            licence="none",
        ),
    )
    partition.build("facts", questions).write(tmp_path / "facts.json")
    result = runner.run("facts", split="all", partitions=tmp_path, resamples=100)
    assert "answer_fact_coverage" in result.metrics
    assert result.metrics["answer_fact_coverage"]["mean"] == pytest.approx(1.0)
    assert "answer_fact_coverage" not in result.missing_metrics


def test_a_scoped_question_never_retrieves_outside_its_scope(monkeypatch, tmp_path):
    """The distractor is the single best match for the query; if scope filtering
    is a filter it cannot appear, and a test that only checks the gold is found
    would pass either way."""
    questions = (
        adapters.Question(
            qid="scoped",
            text="the capital of france is paris",
            gold_docs=("d1",),
            kind="basic",
            scope=("d1", "d2"),
        ),
    )
    monkeypatch.setitem(
        adapters.ADAPTERS,
        "scoped",
        lambda: adapters.Benchmark(
            name="scoped",
            questions=questions,
            documents=lambda: iter(DOCUMENTS.items()),
            citation="stub",
            licence="none",
        ),
    )
    partition.build("scoped", questions).write(tmp_path / "scoped.json")
    result = runner.run("scoped", split="all", partitions=tmp_path, resamples=100)
    row = result.per_question[0]
    assert set(row["retrieved"]) <= {"d1", "d2"}
    assert row["ndcg@k"] == pytest.approx(1.0)


def test_the_same_ranking_gives_the_same_digest(stub):
    first = runner.run("stub", split="all", partitions=stub, resamples=100)
    second = runner.run("stub", split="all", partitions=stub, resamples=100)
    assert first.digest == second.digest
    assert first.metrics.keys() == second.metrics.keys()
    for name in first.metrics:
        assert first.metrics[name]["mean"] == second.metrics[name]["mean"]


def test_a_different_ranking_gives_a_different_digest(stub, monkeypatch):
    """The digest must be a function of the ranking the system produced."""
    first = runner.run("stub", split="all", partitions=stub, resamples=100)

    class Inverted:
        """A system that ranks the corpus backwards, so every ranking differs."""

        def __init__(self, documents, analysis=None):
            self._documents = list(documents)

        def scores(self, query):
            return {doc_id: float(len(self._documents) - position) for position, doc_id in enumerate(self._documents)}

    monkeypatch.setitem(runner.SYSTEMS, "inverted", lambda documents, analysis: Inverted(documents, analysis))
    second = runner.run("stub", split="all", system="inverted", partitions=stub, resamples=100)

    assert [row["retrieved"] for row in second.per_question] != [row["retrieved"] for row in first.per_question]
    assert second.digest != first.digest
    # And it must cost something: a backwards ranker that still scores well would
    # mean the metric is not measuring the order.
    assert second.metrics["ndcg@k"]["mean"] <= first.metrics["ndcg@k"]["mean"]


def test_a_limit_truncates_without_changing_the_split(stub):
    full = runner.run("stub", split="all", partitions=stub, resamples=100)
    limited = runner.run("stub", split="all", limit=2, partitions=stub, resamples=100)
    assert limited.questions == 2
    assert limited.partition_digest == full.partition_digest
    assert limited.digest != full.digest


def test_an_unknown_name_is_refused_by_name(stub):
    with pytest.raises(SystemExit, match="unknown dataset"):
        runner.run("not-a-dataset", partitions=stub, resamples=10)
    with pytest.raises(SystemExit, match="unknown system"):
        runner.run("stub", system="not-a-system", partitions=stub, resamples=10)
    with pytest.raises(SystemExit, match="unknown analysis"):
        runner.run("stub", analysis="not-an-analysis", partitions=stub, resamples=10)


def test_the_artifact_carries_every_per_question_value(stub):
    result = runner.run("stub", split="all", partitions=stub, resamples=100)
    payload = result.as_json()
    assert payload["questions"] == len(payload["per_question"])
    for row in payload["per_question"]:
        assert row["qid"] and "retrieved" in row and "gold" in row
        # The aggregate must be recomputable from the rows, or the artifact is
        # a claim rather than a receipt.
        assert row["ndcg@k"] >= 0.0
    recomputed = sum(row["recall@k"] for row in payload["per_question"]) / len(payload["per_question"])
    assert recomputed == pytest.approx(payload["metrics"]["recall@k"]["mean"], abs=1e-6)
