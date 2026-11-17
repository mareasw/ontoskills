"""The depth curve has two known endpoints; these tests pin both.

At the ranker's own k the pool is exactly what it returns, so the curve must
equal its plain coverage. At every claim the pool is the oracle's ceiling. A
curve that misses either end is measuring something else.
"""

from __future__ import annotations

import json

import pytest

from benchmark.layer import oracle, rank
from benchmark.retrieval.metrics import answer_fact_coverage


def claim(claim_id: str, quote: str) -> dict:
    return {
        "claim_id": claim_id,
        "doc_id": "doc",
        "statement": "",
        "modality": "fact",
        "evidence": [{"quote": quote}],
    }


def write_kb(tmp_path, claims):
    kb = tmp_path / "kb"
    kb.mkdir()
    (kb / "claims.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in claims), encoding="utf-8"
    )
    (kb / "verifier.jsonl").write_text("", encoding="utf-8")
    return kb


def write_selection(tmp_path, items):
    path = tmp_path / "selection.json"
    path.write_text(json.dumps({"items": items}), encoding="utf-8")
    return path


def write_answers(tmp_path, rows):
    path = tmp_path / "answers.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return path


def corpus(tmp_path):
    claims = [
        claim("c1", "alpha beta gamma"),
        claim("c2", "alpha delta"),
        claim("c3", "epsilon zeta"),
        claim("c4", "eta theta"),
    ] + [claim(f"f{number}", f"filler{number} noise") for number in range(1, 10)]
    kb = write_kb(tmp_path, claims)
    selection = write_selection(
        tmp_path,
        [{"qid": "qst_0001", "kind": "basic", "text": "alpha", "gold_facts": ["alpha beta epsilon"]}],
    )
    return kb, selection, claims


def test_at_depth_k_the_curve_is_what_the_ranker_returns(tmp_path):
    kb, selection, claims = corpus(tmp_path)
    matrix, vocab = oracle.build(claims, oracle.TEXTS["statement+quote"])
    pool = oracle.bm25(matrix, vocab, "alpha", k=rank.K)
    vectors = oracle.fact_vectors(["alpha beta epsilon"], vocab)
    covered, _reachable = rank.pool_ceiling(matrix, vectors, pool)

    returned = [oracle.first_quote(claims[index]) for index in pool]
    assert covered == pytest.approx(answer_fact_coverage(["alpha beta epsilon"], returned))


def test_at_depth_all_the_curve_is_the_oracle_ceiling(tmp_path):
    kb, selection, claims = corpus(tmp_path)
    matrix, vocab = oracle.build(claims, oracle.TEXTS["statement+quote"])
    vectors = oracle.fact_vectors(["alpha beta epsilon"], vocab)
    covered, reachable = rank.pool_ceiling(matrix, vectors, list(range(len(claims))))
    _single, ten = oracle.ceiling(matrix, vectors)
    assert covered == pytest.approx(ten)
    assert reachable == 1.0


def test_the_curve_never_falls_as_the_pool_grows(tmp_path):
    kb, selection, claims = corpus(tmp_path)
    matrix, vocab = oracle.build(claims, oracle.TEXTS["statement+quote"])
    vectors = oracle.fact_vectors(["alpha beta epsilon"], vocab)
    ceiling, reachable = [], []
    for depth in (1, 2, 4, 8, len(claims)):
        pool = oracle.bm25(matrix, vocab, "alpha", k=depth)
        covered, reach = rank.pool_ceiling(matrix, vectors, pool)
        ceiling.append(covered)
        reachable.append(reach)
    assert ceiling == sorted(ceiling)
    assert reachable == sorted(reachable)


def test_an_empty_pool_is_zero_not_an_exception(tmp_path):
    kb, selection, claims = corpus(tmp_path)
    matrix, vocab = oracle.build(claims, oracle.TEXTS["statement+quote"])
    vectors = oracle.fact_vectors(["alpha"], vocab)
    assert rank.pool_ceiling(matrix, vectors, []) == (0.0, 0.0)


def test_a_document_cap_keeps_the_pool_size_and_skips_the_crowded_document():
    pool = [0, 1, 2, 3]
    doc_of = ["a", "a", "b", "b"]
    assert rank.doc_capped(pool, doc_of, 1, 4) == [0, 2]
    assert rank.doc_capped(pool, doc_of, 1, 1) == [0]
    assert rank.doc_capped(pool, doc_of, 2, 4) == [0, 1, 2, 3]
    assert rank.doc_capped(pool, doc_of, 1, 10) == [0, 2]


def test_read_split_all_means_no_filter_and_a_missing_half_is_refused(tmp_path):
    path = tmp_path / "split.json"
    path.write_text(json.dumps({"dev": ["qst_0001"], "test": ["qst_0002"]}), encoding="utf-8")
    assert rank.read_split(path, "all") is None
    assert rank.read_split(path, "dev") == {"qst_0001"}
    with pytest.raises(SystemExit):
        rank.read_split(path, "nope")


def test_published_coverage_scores_the_quotes_the_row_returned(tmp_path):
    answers = write_answers(
        tmp_path,
        [
            {"qid": "qst_0001", "evidence": ["alpha beta gamma", "epsilon"]},
            {"qid": "qst_0002", "evidence": []},
        ],
    )
    items = {
        "qst_0001": {"gold_facts": ["alpha beta epsilon"]},
        "qst_0002": {"gold_facts": ["alpha"]},
    }
    assert rank.published_coverage(answers, items) == pytest.approx((1.0 + 0.0) / 2)


def test_the_measurement_only_counts_questions_with_gold_facts_and_respects_the_half(tmp_path):
    kb, selection, _claims = corpus(tmp_path)
    record = json.loads(selection.read_text())
    record["items"].append({"qid": "qst_0002", "kind": "basic", "text": "alpha", "gold_facts": []})
    record["items"].append({"qid": "qst_0003", "kind": "basic", "text": "alpha", "gold_facts": ["alpha"]})
    selection.write_text(json.dumps(record), encoding="utf-8")
    answers = write_answers(
        tmp_path,
        [
            {"qid": "qst_0001", "evidence": ["alpha beta gamma"]},
            {"qid": "qst_0003", "evidence": ["alpha"]},
        ],
    )
    split = tmp_path / "split.json"
    split.write_text(json.dumps({"dev": ["qst_0001"], "test": ["qst_0002", "qst_0003"]}),
                     encoding="utf-8")
    report = rank.measure(selection, kb, answers, split, "dev", depths=(10,))
    assert report["questions"] == 1
    assert report["half"] == "dev"
    assert report["baseline"] == pytest.approx(2 / 3)


def test_the_cli_writes_the_curve_it_printed(tmp_path, capsys):
    kb, selection, _claims = corpus(tmp_path)
    answers = write_answers(tmp_path, [{"qid": "qst_0001", "evidence": ["alpha beta"]}])
    out = tmp_path / "e0.json"
    code = rank.main(
        [
            "--selection", str(selection),
            "--kb", str(kb),
            "--answers", str(answers),
            "--json", str(out),
        ]
    )
    assert code == 0
    report = json.loads(out.read_text())
    assert report["questions"] == 1
    assert set(report["curve"]) == {str(depth) for depth in rank.DEPTHS} | {"all"} | {
        f"div-{cap}" for cap in rank.DIVERSE
    }
    assert 0.0 <= report["pool"]["gold_document_present"] <= 1.0
    assert report["curve"]["all"]["ceiling"] >= report["baseline"]
    printed = capsys.readouterr().out
    assert "published baseline" in printed
    assert "ceiling" in printed
