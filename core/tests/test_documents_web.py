"""Tests for the static HTML view."""

from __future__ import annotations

from compiler.documents.ask import Citation, Answer, Tension
from compiler.documents.store import KnowledgeBase
from compiler.documents.web import render_view


def _kb(tmp_path) -> KnowledgeBase:
    documents = [
        {
            "doc_id": "T1",
            "title": "Test <contract>",
            "kind": "pdf",
            "url": "https://example.org/t1",
            "licence": "CC0",
            "sha256": "a" * 64,
        }
    ]
    claims = [
        {
            "claim_id": "T1-0001",
            "doc_id": "T1",
            "statement": 'The Supplier shall notify within 48 hours of a "<breach>".',
            "modality": "obligation",
            "evidence": [
                {
                    "quote": "The Supplier shall notify within 48 hours.",
                    "locator": {
                        "kind": "pdf",
                        "page": 4,
                        "section_path": ["2. Notification"],
                        "url": "https://example.org/t1",
                    },
                    "role": "supports",
                }
            ],
        }
    ]
    kb = KnowledgeBase(tmp_path)
    kb.write(
        manifest={"name": "Demo <corpus>", "model": "test-model", "created": "2026-01-01T00:00:00Z"},
        documents=documents,
        spans=[],
        claims=claims,
        verifier_rows=[{"claim_id": "T1-0001", "doc_id": "T1", "verdict": "ok", "reasons": [], "notes": []}],
    )
    return kb


def test_view_contains_claim_quote_and_locator(tmp_path):
    kb = _kb(tmp_path)
    html = render_view(kb)
    assert "T1-0001" in html
    assert "The Supplier shall notify within 48 hours." in html
    assert "p.&nbsp;4" in html
    assert "2. Notification" in html
    assert "https://example.org/t1" in html


def test_view_escapes_document_and_statement_text(tmp_path):
    kb = _kb(tmp_path)
    html = render_view(kb)
    assert "Test &lt;contract&gt;" in html
    assert "Demo &lt;corpus&gt;" in html
    assert '&lt;breach&gt;' in html
    assert "<breach>" not in html


def test_view_has_copy_citation_button_with_a_full_citation(tmp_path):
    kb = _kb(tmp_path)
    html = render_view(kb)
    assert 'class="copy"' in html
    assert "copy citation" in html
    assert "T1-0001" in html.split('data-citation="', 1)[1]


def test_view_renders_answers_and_tensions(tmp_path):
    kb = _kb(tmp_path)
    citation = Citation(
        claim_id="T1-0001",
        doc_id="T1",
        title="Test <contract>",
        statement="The Supplier shall notify within 48 hours.",
        quote="The Supplier shall notify within 48 hours.",
        page=4,
        section_path=["2. Notification"],
        url="https://example.org/t1",
    )
    answer = Answer(
        question="How fast must a breach be notified?",
        citations=[citation],
        tensions=[
            Tension(topic="breach_notification", values=[("48 hours", "T1-0001")], reason="two periods")
        ],
    )
    html = render_view(kb, answers=[answer])
    assert "How fast must a breach be notified?" in html
    assert "Documents answering" not in html
    assert "breach notification" in html
    assert "two periods" in html


def test_view_is_read_only_no_editing_controls(tmp_path):
    kb = _kb(tmp_path)
    html = render_view(kb).lower()
    assert "<textarea" not in html
    assert "contenteditable" not in html
    assert "accept suggestion" not in html
