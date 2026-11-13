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
