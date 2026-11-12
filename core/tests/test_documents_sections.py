"""Tests for the section-path cleanup that runs after the replies are cached.

The segmenter keeps every heading it sees, and a PDF running header looks
exactly like a heading. The prompt carries those raw paths on purpose (the
cache fingerprint does not cover them), so the correction happens on the way
out: spans and claims are cleaned once the model has already answered.
"""

from __future__ import annotations

from compiler.documents.sections import apply_sections, clean_sections

PAGE = """\
The Commission shall engage relevant stakeholders.
\x0c
L 119/29
The Commission shall engage relevant stakeholders.
\x0c
Article 50
The Commission shall engage relevant stakeholders.
\x0c
L 119/31
The Commission shall engage relevant stakeholders.
"""


def _spans_with(sections):
    return [
        {"span_id": f"S{i:04d}", "doc_id": "T1", "paragraph": "text",
         "locator": {"kind": "pdf", "page": i, "section_path": list(section), "char_start": i * 10}}
        for i, section in enumerate(sections, start=1)
    ]


def test_a_page_label_is_not_a_section():
    spans = _spans_with([["Article 50"], ["L 119/29"]])
    cleaned = clean_sections(spans, PAGE)
    assert cleaned[1]["locator"]["section_path"] == ["Article 50"]


def test_a_repeated_running_header_is_not_a_section():
    text = "Official Journal of the European Union\nThe Commission shall act.\n\x0cOfficial Journal of the European Union\nThe Commission shall act again.\n"
    spans = _spans_with([["ANNEX IV"], ["Official Journal of the European Union"]])
    assert clean_sections(spans, text)[1]["locator"]["section_path"] == ["ANNEX IV"]


def test_a_real_heading_is_kept():
    spans = _spans_with([["Article 50"]])
    assert clean_sections(spans, PAGE)[0]["locator"]["section_path"] == ["Article 50"]


def test_the_first_span_with_only_furniture_gets_an_empty_path():
    spans = _spans_with([["L 119/29"]])
    assert clean_sections(spans, PAGE)[0]["locator"]["section_path"] == []


def test_cleaning_touches_the_path_only():
    spans = _spans_with([["L 119/29"]])
    cleaned = clean_sections(spans, PAGE)
    assert cleaned[0]["span_id"] == spans[0]["span_id"]
    assert cleaned[0]["paragraph"] == spans[0]["paragraph"]
    assert cleaned[0]["locator"]["page"] == spans[0]["locator"]["page"]
    assert spans[0]["locator"]["section_path"] == ["L 119/29"]   # input not mutated


def test_claims_take_the_cleaned_path_by_span_id():
    spans = _spans_with([["L 119/29"]])
    claim = {"claim_id": "T1-0001", "doc_id": "T1", "statement": "x",
             "evidence": [{"quote": "text", "locator": {"span_id": "S0001", "section_path": ["L 119/29"]}}]}
    cleaned = clean_sections(spans, PAGE)
    apply_sections([claim], cleaned)
    assert claim["evidence"][0]["locator"]["section_path"] == []
