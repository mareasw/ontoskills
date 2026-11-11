"""Tests for the product segmenter, including parity with the DocBench copy.

The benchmark keeps its own frozen segmenter so the Phase 0/1 artifacts stay
reproducible. The product copy must not drift on the structure it claims to
share: same spans, same ids, same locators, on the same text.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from compiler.documents.model import Document
from compiler.documents.segment import chunk, record_key_lines, segment

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
