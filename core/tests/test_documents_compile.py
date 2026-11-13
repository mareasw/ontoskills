"""Tests for claim construction, repair, dedupe and row claims.

No model is called: the compiler's job here is to refuse to write a quote and
to copy it from the span instead. That is the guarantee these tests pin down.
"""

from __future__ import annotations

from pathlib import Path

from compiler.documents.compile import (
    CompileOptions,
    build_claim,
    compile_document,
    dedupe_claims,
    parse_claims,
    repair_json_array,
    row_claims,
)
from compiler.documents.model import Document


def _doc() -> Document:
    return Document(
        doc_id="T1",
        path=Path("t1.txt"),
        title="Test",
        kind="text",
        url="https://example.org/t1",
        doc_type="contract",
    )


def _span(span_id: str, text: str, **extra) -> dict:
    span = {
        "span_id": span_id,
        "doc_id": "T1",
        "paragraph": text,
        "locator": {
            "kind": "text",
            "section_path": ["2. Notification"],
            "char_start": 10,
            "char_end": 10 + len(text),
            "url": "https://example.org/t1",
        },
    }
    span.update(extra)
    return span


def test_build_claim_copies_the_quote_from_the_span():
    span = _span("S0001", "The Supplier shall notify within 48 hours.")
    claim = build_claim(
        {
            "span_ids": ["S0001"],
            "statement": "The Supplier must notify within 48 hours.",
            "modality": "obligation",
        },
        {"S0001": span},
        _doc(),
        1,
    )
    assert claim is not None
    assert claim["claim_id"] == "T1-0001"
    assert claim["evidence"][0]["quote"] == span["paragraph"]
    assert claim["evidence"][0]["locator"] == span["locator"]
    assert claim["context"]["doc_type"] == "contract"


def test_build_claim_rejects_unknown_span_ids():
    assert build_claim(
        {"span_ids": ["S9999"], "statement": "A statement long enough to pass."},
        {},
        _doc(),
        1,
    ) is None


def test_build_claim_rejects_a_statement_too_short():
    span = _span("S0001", "A rule.")
    assert build_claim({"span_ids": ["S0001"], "statement": "Too short"}, {"S0001": span}, _doc(), 1) is None


def test_unknown_modality_rule_becomes_definition():
    span = _span("S0001", "The Supplier shall keep records.")
    claim = build_claim(
        {"span_ids": ["S0001"], "statement": "The Supplier shall keep records.", "modality": "rule"},
        {"S0001": span},
        _doc(),
        1,
    )
    assert claim is not None
    assert claim["modality"] == "definition"


def test_duplicate_evidence_quotes_are_merged():
    span = _span("S0001", "The Supplier shall keep records for six years.")
    claim = build_claim(
        {"span_ids": ["S0001", "S0001"], "statement": "The Supplier shall keep records for six years."},
        {"S0001": span},
        _doc(),
        1,
    )
    assert claim is not None
    assert len(claim["evidence"]) == 1


def test_dedupe_merges_paraphrases_and_keeps_evidence():
    left = {
        "doc_id": "T1",
        "statement": "The Supplier shall notify the Buyer within 48 hours of a breach.",
        "evidence": [{"quote": "a", "locator": {}, "role": "supports"}],
        "conditions": [],
    }
    right = {
        "doc_id": "T1",
        "statement": "The Supplier must notify the Buyer within 48 hours of a breach.",
        "evidence": [{"quote": "b", "locator": {}, "role": "supports"}],
        "conditions": [],
    }
    kept, merged = dedupe_claims([left, right])
    assert merged == 1
    assert len(kept) == 1
    assert {item["quote"] for item in kept[0]["evidence"]} == {"a", "b"}


def test_dedupe_keeps_distinct_rules():
    left = {"doc_id": "T1", "statement": "The Supplier must notify within 48 hours.", "evidence": [], "conditions": []}
    right = {"doc_id": "T1", "statement": "The Buyer may audit the Supplier once a year.", "evidence": [], "conditions": []}
    kept, merged = dedupe_claims([left, right])
    assert merged == 0
    assert len(kept) == 2


def test_parse_claims_repairs_missing_commas():
    reply = '[{"span_ids":["S1"],"statement":"a"}{"span_ids":["S2"],"statement":"b"}]'
    claims = parse_claims(reply)
    assert [claim["span_ids"] for claim in claims] == [["S1"], ["S2"]]


def test_repair_json_array_salvages_a_truncated_reply():
    reply = '[{"a": 1}, {"b": 2}, {"c":'
    assert repair_json_array(reply) == [{"a": 1}, {"b": 2}]


def test_parse_claims_returns_empty_on_prose():
    assert parse_claims("I cannot answer that.") == []


def test_row_claims_quote_the_printed_label_and_value():
    span = _span("S0001", "Retention period: six years after the contract ends")
    span["row"] = {"label": "Retention period", "value": "six years after the contract ends"}
    claims = row_claims([span], _doc(), start=3)
    assert len(claims) == 1
    assert claims[0]["claim_id"] == "T1-0003"
    assert claims[0]["statement"].startswith("Retention period: six years")
    assert claims[0]["evidence"][0]["quote"] == span["paragraph"]


def test_compile_document_dry_run_makes_no_call():
    spans = [_span("S0001", "The Supplier shall notify within 48 hours.")]
    result = compile_document(_doc(), "text", spans, CompileOptions(dry_run=True))
    assert result.claims == []
    assert result.stats.calls == 0
    assert result.spans == spans


def test_conflict_pass_uses_its_own_system_prompt(monkeypatch):
    from compiler.documents.compile import CompileStats, _link_conflicts

    captured = {}

    def fake_one_chunk(prompt, fingerprint, cache_path, options, system=""):
        captured["system"] = system
        return '[["T1-0001", "T1-0002"]]', {}, "stop", False

    monkeypatch.setattr("compiler.documents.compile._one_chunk", fake_one_chunk)
    claims = [
        {"claim_id": "T1-0001", "statement": "The Supplier must notify within 48 hours."},
        {"claim_id": "T1-0002", "statement": "The Supplier must notify within 72 hours."},
    ]
    _link_conflicts(_doc(), claims, CompileOptions(model="stub"), CompileStats(), None)
    assert captured["system"].startswith("You are given the claims compiled from ONE document")
    assert claims[0]["conflicts_with"] == ["T1-0002"]
    assert claims[1]["conflicts_with"] == ["T1-0001"]


def test_a_cached_chunk_still_reports_what_it_cost(tmp_path):
    """A resumed build must not look free: the cache keeps the billed usage."""
    from compiler.documents.compile import _one_chunk, _write_cache

    path = tmp_path / "T1" / "00000.json"
    _write_cache(path, "fp", "[{}]", {"input_tokens": 100, "output_tokens": 50}, "stop")
    reply, usage, finish, cached = _one_chunk(
        "prompt", "fp", path, CompileOptions(model="stub", cache_dir=tmp_path, resume=True)
    )
    assert cached is True
    assert reply == "[{}]"
    assert usage == {"input_tokens": 100, "output_tokens": 50}
    assert finish == "stop"


def test_a_list_item_claim_declares_its_lead_in_as_context():
    lead = _span("S0001", "The binding corporate rules shall specify at least:")
    item = _span("S0002", "(k) the mechanisms for reporting and recording changes to the rules.")
    raw = {
        "statement": "The binding corporate rules shall specify at least the mechanisms for reporting changes.",
        "span_ids": ["S0002"],
        "modality": "obligation",
    }
    claim = build_claim(raw, {"S0001": lead, "S0002": item}, _doc(), 1, {"S0002": lead})
    assert claim is not None
    assert [item["role"] for item in claim["evidence"]] == ["supports", "context"]
    assert claim["evidence"][0]["quote"] == item["paragraph"]
    assert claim["evidence"][1]["quote"] == lead["paragraph"]
    assert claim["evidence"][1]["locator"] == lead["locator"]


def test_without_a_lead_in_the_claim_has_one_evidence_item():
    span = _span("S0001", "Natural persons shall be enabled to decide.")
    raw = {"statement": "Natural persons shall be enabled to decide.", "span_ids": ["S0001"]}
    claim = build_claim(raw, {"S0001": span}, _doc(), 1, {})
    assert [item["role"] for item in claim["evidence"]] == ["supports"]


def test_build_claim_rejects_a_statement_with_an_unattested_quantity():
    span = _span("S0001", "the controller shall notify the supervisory authority")
    raw = {"statement": "The controller shall notify within 8.2 days.", "span_ids": ["S0001"]}
    assert build_claim(raw, {"S0001": span}, _doc(), 1) is None


def test_build_claim_keeps_a_statement_whose_quantity_is_quoted():
    span = _span("S0001", "the controller shall notify within 72 hours")
    raw = {"statement": "The controller shall notify within 72 hours.", "span_ids": ["S0001"]}
    assert build_claim(raw, {"S0001": span}, _doc(), 1) is not None


def test_build_claim_keeps_a_structural_reference():
    span = _span("S0001", "Paragraphs 1, 2 and 3 shall not apply where the data subject has the information.")
    raw = {
        "statement": "Paragraphs 1, 2 and 3 of Article 13 shall not apply.",
        "span_ids": ["S0001"],
    }
    assert build_claim(raw, {"S0001": span}, _doc(), 1) is not None


def _four_spans() -> list[dict]:
    return [
        _span("S0001", "The Supplier shall keep its records."),
        _span("S0002", "The Buyer shall keep its records."),
        _span("S0003", "The Supplier shall notify the Buyer."),
        _span("S0004", "The Buyer shall notify the Supplier."),
    ]


def test_a_truncated_reply_is_split_and_the_tail_recovered(monkeypatch):
    """A reply cut at the ceiling is incomplete: the halves are asked again."""
    calls: list[str] = []

    def fake_one_chunk(prompt, fingerprint, cache_path, options, system=""):
        calls.append(prompt)
        if len(calls) == 1:
            return '[{"span_ids": ["S0001"], "statement": "The Supplier shall kee', (
                {"input_tokens": 10, "output_tokens": 10000}
            ), "length", False
        if "[S0003]" in prompt:
            statement, span_id = "The Buyer shall notify the Supplier.", "S0004"
        else:
            statement, span_id = "The Supplier shall keep its records.", "S0001"
        return (
            f'[{{"span_ids": ["{span_id}"], "statement": "{statement}"}}]',
            {"input_tokens": 5, "output_tokens": 20},
            "stop",
            False,
        )

    monkeypatch.setattr("compiler.documents.compile._one_chunk", fake_one_chunk)
    result = compile_document(
        _doc(),
        "text",
        _four_spans(),
        CompileOptions(model="stub", conflicts=False),
    )
    assert result.stats.retried == 1
    assert result.stats.truncated == 0
    assert result.stats.calls == 3
    assert len(calls) == 3
    assert {claim["statement"] for claim in result.claims} == {
        "The Supplier shall keep its records.",
        "The Buyer shall notify the Supplier.",
    }


def test_truncation_is_reported_when_splitting_is_off(monkeypatch):
    def fake_one_chunk(prompt, fingerprint, cache_path, options, system=""):
        return "", {"input_tokens": 10, "output_tokens": 10000}, "length", False

    monkeypatch.setattr("compiler.documents.compile._one_chunk", fake_one_chunk)
    result = compile_document(
        _doc(),
        "text",
        _four_spans(),
        CompileOptions(model="stub", conflicts=False, split_truncated=False),
    )
    assert result.stats.truncated == 1
    assert result.stats.retried == 0
    assert result.stats.calls == 1
    assert result.claims == []


def test_a_single_span_block_cannot_be_split(monkeypatch):
    calls: list[str] = []

    def fake_one_chunk(prompt, fingerprint, cache_path, options, system=""):
        calls.append(prompt)
        return "", {"input_tokens": 10, "output_tokens": 10000}, "length", False

    monkeypatch.setattr("compiler.documents.compile._one_chunk", fake_one_chunk)
    result = compile_document(
        _doc(),
        "text",
        [_span("S0001", "The Supplier shall keep its records.")],
        CompileOptions(model="stub", conflicts=False),
    )
    assert result.stats.truncated == 1
    assert result.stats.retried == 0
    assert len(calls) == 1
