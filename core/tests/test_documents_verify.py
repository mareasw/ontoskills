"""Tests for the deterministic verifier (ADR 0002 Phase 0 rules)."""

from __future__ import annotations

from compiler.documents.segment import segment
from compiler.documents.verify import SpanIndex, page_containing, summarise, verify

TEXT = (
    "1. Notification\n"
    "1.1 The Supplier shall notify the Buyer within 48 hours of becoming aware of a breach.\n"
    "\f"
    "2. Retention\n"
    "2.1 The Supplier shall retain records for six years after the end of the Contract.\n"
)

DOC = {"doc_id": "T1", "kind": "pdf", "url": "https://example.org/t1"}


def _spans():
    return segment(TEXT, DOC)


def _claim(span, statement):
    return {
        "claim_id": "T1-0001",
        "doc_id": "T1",
        "statement": statement,
        "modality": "obligation",
        "evidence": [
            {"quote": span["paragraph"], "locator": dict(span["locator"]), "role": "supports"}
        ],
    }


def test_a_faithful_claim_passes():
    spans = _spans()
    span = next(s for s in spans if "48 hours" in s["paragraph"])
    claim = _claim(span, "The Supplier shall notify the Buyer within 48 hours of a breach.")
    result = verify(claim, SpanIndex(spans), {"T1": TEXT})
    assert result["verdict"] == "ok", result


def test_a_quote_absent_from_the_source_is_a_failure():
    spans = _spans()
    span = next(s for s in spans if "48 hours" in s["paragraph"])
    claim = _claim(span, "The Supplier shall notify the Buyer within 48 hours of a breach.")
    claim["evidence"][0]["quote"] = "The Supplier shall notify within 24 hours."
    result = verify(claim, SpanIndex(spans), {"T1": TEXT})
    assert result["verdict"] == "no"
    assert any("not in the source" in reason for reason in result["reasons"])


def test_a_wrong_page_is_a_failure():
    spans = _spans()
    span = next(s for s in spans if "six years" in s["paragraph"])
    claim = _claim(span, "The Supplier shall retain records for six years after the end of the Contract.")
    claim["evidence"][0]["locator"]["page"] = 1  # the quote is on page 2
    result = verify(claim, SpanIndex(spans), {"T1": TEXT})
    assert result["verdict"] == "no"
    assert any("declared page" in reason for reason in result["reasons"])


def test_a_number_absent_from_the_evidence_is_a_failure():
    spans = _spans()
    span = next(s for s in spans if "48 hours" in s["paragraph"])
    claim = _claim(span, "The Supplier shall notify the Buyer within 72 hours of a breach.")
    result = verify(claim, SpanIndex(spans), {"T1": TEXT})
    assert result["verdict"] == "no"
    assert any("numbers not in the evidence" in reason for reason in result["reasons"])


def test_a_paraphrase_beyond_tolerance_is_weak():
    spans = _spans()
    span = next(s for s in spans if "48 hours" in s["paragraph"])
    claim = _claim(
        span,
        "Suppliers must escalate severe incidents to regulators and affected customers promptly.",
    )
    result = verify(claim, SpanIndex(spans), {"T1": TEXT})
    assert result["verdict"] == "weak", result
    assert result["reasons"]


def test_modality_is_a_note_not_a_verdict():
    spans = _spans()
    span = next(s for s in spans if "48 hours" in s["paragraph"])
    claim = _claim(span, "The Supplier may notify the Buyer within 48 hours of a breach.")
    result = verify(claim, SpanIndex(spans), {"T1": TEXT})
    assert result["verdict"] in {"ok", "weak"}
    assert any("modality note" in note for note in result["notes"])


def test_page_containing_prefers_the_declared_page_when_it_is_true():
    source = "same quote\fother\fsame quote"
    assert page_containing(source, "same quote", 3) == 3
    assert page_containing(source, "same quote", 2) == 1
    assert page_containing(source, "absent", 1) is None


def test_summarise_groups_failures_by_document():
    rows = [
        {"claim_id": "T1-0001", "doc_id": "T1", "verdict": "ok", "reasons": [], "notes": []},
        {"claim_id": "T1-0002", "doc_id": "T1", "verdict": "weak", "reasons": ["x"], "notes": []},
        {"claim_id": "T2-0001", "doc_id": "T2", "verdict": "no", "reasons": ["y"], "notes": []},
    ]
    report = summarise(rows)
    assert report["claims"] == 3
    assert report["by_verdict"] == {"ok": 1, "weak": 1, "no": 1}
    assert len(report["failures"]) == 2
    assert report["by_doc"]["T1"] == {"ok": 1, "weak": 1}
