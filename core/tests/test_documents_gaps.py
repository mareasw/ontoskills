"""Tests for the lead-in the segmenter dropped between two spans.

The segmenter drops a heading printed at a page break, and the sentence printed
under the heading goes with it: `sections` gives the heading to the spans below,
but nothing can quote the sentence. This repair runs on the span list, before
the prompt, and gives the block a span of its own.
"""

from __future__ import annotations

from compiler.documents.gaps import raw_offsets, recover_lead_ins
from compiler.documents.sections import clean_sections
from compiler.documents.segment import lead_ins
from compiler.documents.text import norm

META = {"doc_id": "T1", "kind": "pdf", "url": "https://example.test/doc"}

TEXT = """\
Devono essere garantiti il rispetto delle disposizioni di legge.

RESPONSABILITA' DI OSSERVANZA E ATTUAZIONE
L'osservanza e l'attuazione delle policy sono responsabilità di:

• tutto il personale che collabora con l'azienda.
"""

FLAT = norm(TEXT)
BEFORE = "Devono essere garantiti il rispetto delle disposizioni di legge."
AFTER = "tutto il personale che collabora con l'azienda."
LEAD = "L'osservanza e l'attuazione delle policy sono responsabilità di:"
HEADING = "RESPONSABILITA' DI OSSERVANZA E ATTUAZIONE"
RECOVERED = f"{HEADING} {LEAD}"


def _spans(paragraphs, page=1):
    spans = []
    cursor = 0
    for index, paragraph in enumerate(paragraphs, start=1):
        at = FLAT.find(paragraph, cursor)
        assert at >= 0, paragraph
        cursor = at + len(paragraph)
        spans.append(
            {
                "span_id": f"S{index:04d}",
                "doc_id": "T1",
                "paragraph": paragraph,
                "locator": {
                    "kind": "pdf",
                    "page": page,
                    "section_path": ["POLICY SICUREZZA DELLE INFORMAZIONI"],
                    "url": "https://example.test/doc",
                    "char_start": at,
                    "char_end": cursor,
                },
            }
        )
    return spans


def test_the_offset_map_has_one_entry_per_normalised_character():
    text = "  Uno\n\nDue   tre.  \n"
    raw = raw_offsets(text)
    assert norm(text) == "Uno Due tre."
    assert len(raw) == len(norm(text))
    assert text[raw[0]] == "U"
    assert text[raw[3]].isspace()
    assert text[raw[4]] == "D"
    assert text[raw[-1]] == "."


def test_a_dropped_heading_and_its_lead_in_become_a_span():
    spans = _spans([BEFORE, AFTER])
    recovered = recover_lead_ins(spans, TEXT, META)
    assert [span["span_id"] for span in recovered] == ["S0001", "S0002", "S0003"]
    assert [span["paragraph"] for span in recovered] == [BEFORE, RECOVERED, AFTER]


def test_the_recovered_span_is_located_where_the_sentence_starts():
    spans = _spans([BEFORE, AFTER])
    recovered = recover_lead_ins(spans, TEXT, META)[1]
    locator = recovered["locator"]
    assert FLAT[locator["char_start"]: locator["char_end"]] == RECOVERED
    assert locator["page"] == 1
    assert locator["kind"] == "pdf"
    assert locator["url"] == META["url"]


def test_the_recovered_span_declares_no_path_and_takes_the_band_above():
    spans = _spans([BEFORE, AFTER])
    recovered = recover_lead_ins(spans, TEXT, META)
    assert recovered[1]["locator"]["section_path"] == []
    cleaned = clean_sections(recovered, TEXT)
    assert cleaned[1]["locator"]["section_path"] == [
        "POLICY SICUREZZA DELLE INFORMAZIONI",
        "RESPONSABILITA' DI OSSERVANZA E ATTUAZIONE",
    ]


def test_the_spans_below_keep_the_heading_they_had():
    spans = _spans([BEFORE, AFTER])
    cleaned = clean_sections(recover_lead_ins(spans, TEXT, META), TEXT)
    assert cleaned[2]["locator"]["section_path"][-1] == (
        "RESPONSABILITA' DI OSSERVANZA E ATTUAZIONE"
    )


def test_the_list_item_takes_the_recovered_lead_in_as_its_context():
    spans = _spans([BEFORE, AFTER])
    cleaned = clean_sections(recover_lead_ins(spans, TEXT, META), TEXT)
    contexts = lead_ins(cleaned)
    assert contexts["S0003"]["span_id"] == "S0002"


def test_a_gap_with_only_a_running_header_adds_nothing():
    text = BEFORE + "\n\nManuale SGSD\n\n" + AFTER
    flat = norm(text)
    spans = [
        {"span_id": "S0001", "doc_id": "T1", "paragraph": BEFORE,
         "locator": {"kind": "pdf", "page": 1, "section_path": [],
                     "char_start": 0, "char_end": len(BEFORE)}},
        {"span_id": "S0002", "doc_id": "T1", "paragraph": AFTER,
         "locator": {"kind": "pdf", "page": 2, "section_path": [],
                     "char_start": flat.find(AFTER),
                     "char_end": flat.find(AFTER) + len(AFTER)}},
    ]
    assert recover_lead_ins(spans, text, META) == spans


def test_a_gap_whose_line_is_a_fragment_adds_nothing():
    # The line under the heading starts mid-sentence: it is the tail of the
    # paragraph above, which already has a span.
    text = (
        "Devono essere garantiti il rispetto delle disposizioni\n"
        "\n"
        "RESPONSABILITA' DI OSSERVANZA E ATTUAZIONE\n"
        "di legge e di regolamento.\n"
        "\n"
        "tutto il personale che collabora con l'azienda.\n"
    )
    flat = norm(text)
    before = "Devono essere garantiti il rispetto delle disposizioni"
    after = "tutto il personale che collabora con l'azienda."
    spans = [
        {"span_id": "S0001", "doc_id": "T1", "paragraph": before,
         "locator": {"kind": "pdf", "page": 1, "section_path": [],
                     "char_start": 0, "char_end": len(before)}},
        {"span_id": "S0002", "doc_id": "T1", "paragraph": after,
         "locator": {"kind": "pdf", "page": 1, "section_path": [],
                     "char_start": flat.find(after),
                     "char_end": flat.find(after) + len(after)}},
    ]
    assert recover_lead_ins(spans, text, META) == spans


def test_a_heading_above_a_list_item_adds_nothing():
    # The item starts in lower case, so the gap holds no sentence of its own:
    # the heading is what `sections` already hands down to the spans below.
    text = BEFORE + "\n\nRESPONSABILITA' DI OSSERVANZA E ATTUAZIONE\n\n• " + AFTER
    flat = norm(text)
    spans = [
        {"span_id": "S0001", "doc_id": "T1", "paragraph": BEFORE,
         "locator": {"kind": "pdf", "page": 1, "section_path": [],
                     "char_start": 0, "char_end": len(BEFORE)}},
        {"span_id": "S0002", "doc_id": "T1", "paragraph": AFTER,
         "locator": {"kind": "pdf", "page": 1, "section_path": [],
                     "char_start": flat.find(AFTER),
                     "char_end": flat.find(AFTER) + len(AFTER)}},
    ]
    assert recover_lead_ins(spans, text, META) == spans


def test_the_page_is_the_one_the_heading_is_printed_on():
    text = BEFORE + "\n\x0c\n" + HEADING + "\n" + LEAD + "\n\n" + AFTER
    flat = norm(text)
    spans = [
        {"span_id": "S0001", "doc_id": "T1", "paragraph": BEFORE,
         "locator": {"kind": "pdf", "page": 1, "section_path": [],
                     "char_start": 0, "char_end": len(BEFORE)}},
        {"span_id": "S0002", "doc_id": "T1", "paragraph": AFTER,
         "locator": {"kind": "pdf", "page": 2, "section_path": [],
                     "char_start": flat.find(AFTER),
                     "char_end": flat.find(AFTER) + len(AFTER)}},
    ]
    recovered = recover_lead_ins(spans, text, META)
    assert recovered[1]["locator"]["page"] == 2


def test_spans_without_offsets_are_left_alone():
    spans = _spans([BEFORE, AFTER])
    for span in spans:
        span["locator"].pop("char_start")
        span["locator"].pop("char_end")
    assert recover_lead_ins(spans, TEXT, META) == spans


def test_one_span_is_not_enough_to_have_a_gap():
    spans = _spans([BEFORE])
    assert recover_lead_ins(spans, TEXT, META) == spans
