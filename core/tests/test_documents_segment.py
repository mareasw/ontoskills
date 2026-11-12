"""Tests for the product segmenter, including parity with the DocBench copy.

The benchmark keeps its own frozen segmenter so the Phase 0/1 artifacts stay
reproducible. The product copy must not drift on the structure it claims to
share: same spans, same ids, same locators, on the same text.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from compiler.documents.model import Document
from compiler.documents.segment import chunk, lead_ins, record_key_lines, segment

REPO = Path(__file__).resolve().parents[2]
BENCH = REPO / "benchmark" / "docbench" / "compile_claims.py"

CONTRACT = """\
1. Definitions and interpretation

1.1 "Personal Data" means any information relating to an identified natural person.

1.2 "Data Protection Legislation" means the GDPR and any legislation replacing it.

2. Notification of a Personal Data Breach

2.1 The Supplier shall notify the Buyer without undue delay and in any event within 48 hours of becoming aware of a Personal Data Breach.

2.2 The notification shall describe the nature of the breach and the likely consequences.

3. Retention and deletion

3.1 The Supplier shall retain Personal Data for six years after the end of the Contract and shall delete it at the written direction of the Buyer.
"""


def _product_doc() -> Document:
    return Document(
        doc_id="T1",
        path=Path("t1.txt"),
        title="Test contract",
        kind="text",
        url="https://example.org/t1",
    )


def _bench_module():
    spec = importlib.util.spec_from_file_location("docbench_compile_claims", BENCH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    module.DOCS["T1"] = {"file": "T1.txt", "kind": "text", "url": "https://example.org/t1"}
    return module


def test_segment_emits_spans_with_verbatim_text_and_locators():
    doc = _product_doc()
    spans = segment(CONTRACT, doc.segment_meta())
    assert spans
    for span in spans:
        assert span["doc_id"] == "T1"
        assert span["span_id"].startswith("S")
        assert span["paragraph"] in CONTRACT.replace("\n", " ")
        locator = span["locator"]
        assert locator["kind"] == "text"
        assert locator["url"] == "https://example.org/t1"
        assert locator["char_start"] >= 0
        assert locator["char_end"] > locator["char_start"]


def test_span_ids_are_sequential():
    spans = segment(CONTRACT, _product_doc().segment_meta())
    assert [span["span_id"] for span in spans] == [
        f"S{index:04d}" for index in range(1, len(spans) + 1)
    ]


def test_section_path_is_attached_to_the_rule():
    spans = segment(CONTRACT, _product_doc().segment_meta())
    breach = [s for s in spans if "48 hours" in s["paragraph"]]
    assert breach
    path = breach[0]["locator"]["section_path"]
    assert any("Notification" in part for part in path)


def test_headings_are_not_emitted_as_claims():
    spans = segment(CONTRACT, _product_doc().segment_meta())
    assert all(span["paragraph"].strip() != "1. Definitions and interpretation" for span in spans)


def test_chunk_overlaps_and_covers_every_span():
    spans = segment(CONTRACT, _product_doc().segment_meta())
    chunks = chunk(spans, size=2, overlap=1)
    assert chunks[0] == spans[:2]
    assert chunks[1][0] == spans[1]
    covered = {span["span_id"] for block in chunks for span in block}
    assert covered == {span["span_id"] for span in spans}


def test_empty_text_yields_no_spans():
    assert segment("", _product_doc().segment_meta()) == []


def test_record_key_detector_ignores_section_numbering():
    sectioned = "1. Introduction\n1.1 The rule applies.\n1.2 The exception does not.\n"
    assert record_key_lines(sectioned) == []


def test_record_key_detector_finds_flat_item_keys():
    table = (
        "Contents\n001\nAlpha record\nDestroy 2 years\n"
        "010\nBeta record\nDestroy 5 years\n"
        "012\nGamma record\nDestroy 7 years\n"
    )
    assert record_key_lines(table) == [1, 4, 7]


def test_parity_with_docbench_segmenter():
    """The product copy equals the frozen bench on identical input."""
    doc = _product_doc()
    ours = segment(CONTRACT, doc.segment_meta())
    bench = _bench_module().segment(CONTRACT, "T1", min_chars=60)
    # Page is removed later by ``strip_pages`` for unpaginated formats; the
    # segmenter itself is expected to agree on every field.
    assert ours == bench


def _plain_span(span_id, paragraph, start, section=("Article 5",)):
    return {
        "span_id": span_id,
        "doc_id": "T1",
        "paragraph": paragraph,
        "locator": {"kind": "text", "section_path": list(section), "char_start": start, "char_end": start + len(paragraph), "url": "u"},
    }


def test_lead_ins_gives_a_list_item_its_introduction():
    spans = [
        _plain_span("S0001", "The binding corporate rules shall specify at least:", 0),
        _plain_span("S0002", "(k) the mechanisms for reporting and recording changes to the rules.", 57),
    ]
    assert lead_ins(spans)["S0002"]["span_id"] == "S0001"


def test_lead_ins_gives_a_lowercase_continuation_its_previous_span():
    spans = [
        _plain_span("S0001", "The Commission shall engage relevant stakeholders in", 0),
        _plain_span("S0002", "(c) engage relevant stakeholders in discussion and activities.", 49),
    ]
    assert lead_ins(spans)["S0002"]["span_id"] == "S0001"


def test_lead_ins_gives_an_anaphoric_sentence_its_previous_span():
    spans = [
        _plain_span("S0001", "Measures to reply to a request may be adopted.", 0),
        _plain_span("S0002", "Such measures may include the transmission of relevant information.", 47),
    ]
    assert lead_ins(spans)["S0002"]["span_id"] == "S0001"


def test_lead_ins_ignores_a_self_contained_sentence():
    spans = [
        _plain_span("S0001", "This Regulation applies to providers.", 0),
        _plain_span("S0002", "Natural persons shall be enabled to decide.", 40),
    ]
    assert lead_ins(spans) == {}


def test_lead_ins_does_not_cross_a_section_boundary():
    spans = [
        _plain_span("S0001", "The controller shall specify at least:", 0, ("Article 5",)),
        _plain_span("S0002", "(k) the mechanisms for reporting changes.", 38, ("Article 6",)),
    ]
    assert lead_ins(spans) == {}


def test_a_list_item_after_another_item_gets_the_opener():
    spans = [
        _plain_span("S0001", "The documentation shall contain at least:", 0),
        _plain_span("S0002", "(i) a general description of the system;", 45),
        _plain_span("S0003", "(k) the mechanisms for reporting changes.", 90),
    ]
    assert lead_ins(spans)["S0003"]["span_id"] == "S0001"


def test_a_lowercase_continuation_gets_the_sentence_before_it():
    spans = [
        _plain_span("S0001", "The Commission shall engage stakeholders in", 0),
        _plain_span("S0002", "compliance with the obligations laid down in this Regulation.", 45),
    ]
    assert lead_ins(spans)["S0002"]["span_id"] == "S0001"


def test_a_run_without_an_opener_gets_no_context():
    spans = [_plain_span(f"S{i:04d}", f"({chr(96 + i)}) item number {i} of the list.", i * 40) for i in range(1, 9)]
    assert lead_ins(spans) == {}


def _paged(span_id, paragraph, start, page):
    span = _plain_span(span_id, paragraph, start)
    span["locator"].update(kind="pdf", page=page)
    return span


def test_a_page_header_between_items_is_not_a_lead_in():
    """A PDF puts its header between the spans of one list; the walk passes over it."""
    header = "Official Journal of the European Union 4.5.2016"
    spans = [
        _paged("S0001", header, 0, 1),
        _paged("S0002", "The controller shall specify at least:", 47, 1),
        _paged("S0003", "(i) the first item;", 90, 2),
        _paged("S0004", header, 110, 3),
        _paged("S0005", "(k) the last item.", 157, 4),
    ]
    assert lead_ins(spans)["S0005"]["span_id"] == "S0002"


def test_a_continuation_split_twice_gets_the_span_before_it():
    """The sentence was split over three spans: the antecedent is the span just above."""
    spans = [
        _plain_span("S0001", "The measures shall reflect demographic", 0),
        _plain_span("S0002", "capacities for establishing context.", 45),
        _plain_span("S0003", "technology are understood and documented. MAP 1.4:", 88),
    ]
    assert lead_ins(spans)["S0003"]["span_id"] == "S0002"


def test_a_list_item_after_the_tail_of_another_item_gets_the_opener():
    spans = [
        _plain_span("S0001", "The rules shall specify at least:", 0),
        _plain_span("S0002", "(g) how the information is published;", 37),
        _plain_span("S0003", "the complaint procedures; (j)", 80),
        _plain_span("S0004", "(k) the mechanisms for reporting changes.", 112),
    ]
    assert lead_ins(spans)["S0004"]["span_id"] == "S0001"


def test_a_numbered_paragraph_is_the_opener_not_an_item():
    """A clause number is not a list marker: "1. Any distributor …" opens the list."""
    spans = [
        _plain_span("S0001", "1. Any distributor shall be considered a provider if they:", 0),
        _plain_span("S0002", "(a) place the system on the market;", 63),
        _plain_span("S0003", "(b) modify the system substantially.", 100),
    ]
    assert lead_ins(spans)["S0003"]["span_id"] == "S0001"
