"""The ceiling decides the diagnosis, so these tests pin the arithmetic first.

The corpus is small enough that the answer is known by hand: a fact one claim
carries exactly, a fact split across two claims, a claim the verifier refused.
If the ceiling were wrong here, every conclusion drawn from it on the pilot
would be wrong in the same direction.
"""

from __future__ import annotations

import json

from benchmark.layer import oracle


def claim(claim_id: str, quote: str) -> dict:
    return {
        "claim_id": claim_id,
        "doc_id": "doc",
        "statement": "",
        "modality": "fact",
        "evidence": [{"quote": quote}],
    }


def write_kb(tmp_path, claims, verdicts=None):
    kb = tmp_path / "kb"
    kb.mkdir()
    (kb / "claims.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in claims), encoding="utf-8"
    )
    (kb / "verifier.jsonl").write_text(
        "".join(
            json.dumps({"claim_id": cid, "verdict": verdict}) + "\n"
            for cid, verdict in (verdicts or {}).items()
        ),
        encoding="utf-8",
    )
    return kb


def write_selection(tmp_path, items):
    path = tmp_path / "selection.json"
    path.write_text(json.dumps({"items": items}), encoding="utf-8")
    return path


def one_question(tmp_path, facts, text="alpha epsilon"):
    return write_selection(
        tmp_path, [{"qid": "qst_0001", "kind": "basic", "text": text, "gold_facts": facts}]
    )


def test_a_fact_one_claim_carries_is_one_for_that_claim_alone():
    claims = [claim("c1", "alpha beta gamma"), claim("c2", "epsilon zeta")]
    matrix, vocab = oracle.build(claims, oracle.first_quote)
    vectors = oracle.fact_vectors(["alpha beta gamma"], vocab)
    single, ten = oracle.ceiling(matrix, vectors)
    assert single == 1.0
    assert ten == 1.0


def test_a_fact_split_across_claims_needs_the_greedy_choice_of_two():
    claims = [claim("c1", "alpha beta gamma"), claim("c2", "epsilon zeta")]
    matrix, vocab = oracle.build(claims, oracle.first_quote)
    # The fact has two tokens, and no single claim carries both: the best one
    # reaches half, and only the pair reaches the whole fact.
    vectors = oracle.fact_vectors(["alpha epsilon"], vocab)
    single, ten = oracle.ceiling(matrix, vectors)
    assert single == 0.5
    assert ten == 1.0


def test_the_greedy_ceiling_is_never_below_the_best_single_claim():
    claims = [
        claim("c1", "alpha beta"),
        claim("c2", "gamma delta"),
        claim("c3", "epsilon zeta"),
        claim("c4", "eta theta"),
    ]
    matrix, vocab = oracle.build(claims, oracle.first_quote)
    vectors = oracle.fact_vectors(
        ["alpha gamma epsilon", "beta delta eta theta", "nothing indexed here"], vocab
    )
    for vector in vectors:
        single, ten = oracle.ceiling(matrix, [vector])
        assert single <= ten


def test_a_fact_no_claim_can_touch_counts_as_zero_not_as_skipped():
    claims = [claim("c1", "alpha beta")]
    matrix, vocab = oracle.build(claims, oracle.first_quote)
    single, ten = oracle.ceiling(matrix, oracle.fact_vectors(["lambda"], vocab))
    assert single == 0.0
    assert ten == 0.0


def test_a_claim_the_verifier_refused_is_not_a_candidate(tmp_path):
    kb = write_kb(
        tmp_path,
        [claim("c1", "alpha beta"), claim("c2", "alpha beta")],
        {"c1": "ok", "c2": "no"},
    )
    kept = oracle.verified_claims(kb)
    assert [item["claim_id"] for item in kept] == ["c1"]


def test_a_claim_without_evidence_is_not_a_candidate(tmp_path):
    silent = claim("c2", "")
    silent["evidence"] = []
    kb = write_kb(tmp_path, [claim("c1", "alpha beta"), silent])
    assert [item["claim_id"] for item in oracle.verified_claims(kb)] == ["c1"]


def test_the_quotes_variant_reads_every_evidence_item_and_quote_only_the_first():
    item = {
        "claim_id": "c1",
        "evidence": [{"quote": "first"}, {"quote": "second"}],
    }
    assert oracle.first_quote(item) == "first"
    assert oracle.all_quotes(item) == "first second"


def test_bm25_ranks_the_claim_carrying_the_question_token_first_and_cuts_at_k():
    filler = [claim(f"c{number}", f"filler{number} common") for number in range(1, 12)]
    claims = [claim("target", "alpha beta gamma")] + filler
    matrix, vocab = oracle.build(claims, oracle.first_quote)
    ranked = oracle.bm25(matrix, vocab, "alpha")
    assert ranked[0] == 0
    assert len(ranked) == oracle.K


def test_the_measurement_is_deterministic(tmp_path):
    kb = write_kb(tmp_path, [claim("c1", "alpha beta gamma"), claim("c2", "epsilon zeta")])
    selection = one_question(tmp_path, ["alpha epsilon"], text="alpha")
    first = oracle.measure(selection, kb)
    second = oracle.measure(selection, kb)
    assert first == second


def test_the_cli_writes_the_report_it_printed(tmp_path, capsys):
    kb = write_kb(tmp_path, [claim("c1", "alpha beta gamma"), claim("c2", "epsilon zeta")])
    selection = one_question(tmp_path, ["alpha epsilon"], text="alpha")
    out = tmp_path / "oracle.json"
    assert oracle.main(["--selection", str(selection), "--kb", str(kb), "--json", str(out)]) == 0

    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["questions"] == 1
    assert report["claims"] == 2
    assert report["k"] == oracle.K
    assert report["ceiling"]["quote"]["greedy_ten"] == 1.0
    assert report["ceiling"]["quote"]["best_single_claim"] == 0.5
    # Ten returned claims is the whole two-claim corpus, so the ranker reaches
    # both facts' tokens here: the truncation it suffers on the pilot is not
    # exercised by a corpus this small, and the greedy ceiling above is.
    assert report["lexical"]["quote"] == 1.0

    printed = capsys.readouterr().out
    assert "greedy ten" in printed
    assert "bm25" in printed


def test_a_question_without_gold_facts_is_not_counted(tmp_path):
    kb = write_kb(tmp_path, [claim("c1", "alpha beta")])
    selection = write_selection(
        tmp_path,
        [
            {"qid": "qst_0001", "kind": "basic", "text": "alpha", "gold_facts": []},
            {"qid": "qst_0002", "kind": "basic", "text": "alpha", "gold_facts": ["alpha"]},
        ],
    )
    assert oracle.measure(selection, kb)["questions"] == 1
