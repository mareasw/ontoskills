"""The locator checker must pass on the real corpora and fail on a tampered one.

Every test below is either a property of the coordinate space or a deliberate
corruption that the checker has to catch. A checker that only passes is not
evidence of anything: the `test_*_is_caught` cases are what make the pass mean
something.
"""

from __future__ import annotations

import json
import os
import sys
from functools import lru_cache
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from benchmark.retrieval import locator  # noqa: E402

DEMO = ROOT / "examples" / "demo-corpus" / "kb"
PILOT = Path(os.environ.get("ONTOSKILLS_PILOT_CORPUS", ROOT.parent / "pilot" / "kb-final5"))


@lru_cache(maxsize=None)
def released_report(path: Path) -> locator.Report:
    """Load each released corpus once: the demo is 50 MB of sources."""
    return locator.check_corpus(locator.Corpus.load(path))

ALPHA = "The quick brown fox jumps over the lazy dog."
BETA = "Dogs sleep all day and cats sleep all night."
GAMMA = "The third page begins here with more words."

DOC = (
    "Alpha Section\n"
    "\n"
    f"{ALPHA}\n"
    "\n"
    "Beta Section\n"
    "\n"
    f"{BETA}\n"
    "\f"
    "Gamma Section\n"
    "\n"
    f"{GAMMA}\n"
)

SPANS = [
    ("S0001", "Alpha Section", ("Alpha Section",), 1),
    ("S0002", ALPHA, ("Alpha Section",), 1),
    ("S0003", "Beta Section", ("Beta Section",), 1),
    ("S0004", BETA, ("Beta Section",), 1),
    ("S0005", "Gamma Section", ("Gamma Section",), 2),
    ("S0006", GAMMA, ("Gamma Section",), 2),
]

CROSSING_DOC = (
    "Intro text.\n"
    "Alpha Section\n"
    "First alpha paragraph that ends. Beta Section\n"
    "Second beta paragraph.\n"
)

CROSSING_SPANS = [
    ("S0001", "Intro text.", (), 1),
    ("S0002", "Alpha Section", ("Alpha Section",), 1),
    ("S0003", "First alpha paragraph that ends. Beta Section", (), 1),
    ("S0004", "Second beta paragraph.", ("Beta Section",), 1),
]


def collapsed(text: str) -> str:
    return locator.collapse(text).text


def at(text: str, quote: str) -> tuple[int, int]:
    start = collapsed(text).index(quote)
    return start, start + len(collapsed(quote))


def build(tmp_path: Path, text: str, spans, claims) -> locator.Corpus:
    """Write a one-document knowledge base and load it back through the loader."""
    root = tmp_path / "kb"
    (root / "text").mkdir(parents=True)
    (root / "text" / "D.txt").write_text(text, encoding="utf-8")
    with (root / "spans.jsonl").open("w", encoding="utf-8") as handle:
        for span_id, paragraph, path, page in spans:
            start, end = at(text, paragraph)
            handle.write(
                json.dumps(
                    {
                        "span_id": span_id,
                        "doc_id": "D",
                        "paragraph": paragraph,
                        "locator": {
                            "kind": "pdf",
                            "section_path": list(path),
                            "url": "u",
                            "char_start": start,
                            "char_end": end,
                            "page": page,
                        },
                    }
                )
                + "\n"
            )
    with (root / "claims.jsonl").open("w", encoding="utf-8") as handle:
        for claim in claims:
            quote = claim["quote"]
            start, end = at(text, quote)
            handle.write(
                json.dumps(
                    {
                        "claim_id": claim.get("id", "C0001"),
                        "doc_id": "D",
                        "statement": "s",
                        "evidence": [
                            {
                                "quote": claim.get("cited", quote),
                                "locator": {
                                    "kind": "pdf",
                                    "section_path": list(claim.get("section", ())),
                                    "url": "u",
                                    "char_start": start + claim.get("shift", 0),
                                    "char_end": end + claim.get("end_shift", 0),
                                    "page": claim.get("page"),
                                },
                                "role": "supports",
                            }
                        ],
                    }
                )
                + "\n"
            )
    return locator.Corpus.load(root, "synthetic")


def one(tmp_path: Path, quote, section, page, text=DOC, **kwargs):
    """One claim about one quote, with any field of the locator overridden."""
    claim = {"quote": quote, "section": section, "page": page, **kwargs}
    return build(tmp_path, text, SPANS, [claim])


# --- the coordinate space ---------------------------------------------------


def test_collapse_matches_the_compiler_normalisation():
    """The harness reimplements `norm`; the copy must agree with the original."""
    try:
        from compiler.documents.text import norm
    except ImportError:  # the checker is standalone by design
        pytest.skip("compiler not importable")
    texts = [DOC, CROSSING_DOC, "a\u2019b \u201cc\u201d\u2014d\u2013e\t \n\f f"]
    for path in (DEMO, PILOT):
        for source in (path / "text").glob("*.txt"):
            texts.append(source.read_text(encoding="utf-8"))
    for text in texts:
        assert collapsed(text) == norm(text)


def test_collapse_index_points_at_the_original_character():
    text = "  a\u2019b\n\n\fc\u2014d  "
    flat = locator.collapse(text)
    assert flat.text == "a'b c-d"
    for position, raw_index in enumerate(flat.index):
        original = locator._FOLD.get(text[raw_index], text[raw_index])
        assert original == flat.text[position] or (original.isspace() and flat.text[position] == " ")


def test_page_at_counts_form_feeds():
    flat = locator.collapse(DOC)
    assert flat.page_at(flat.text.index(ALPHA), DOC) == 1
    assert flat.page_at(flat.text.index(GAMMA), DOC) == 2


# --- the four things that can be wrong --------------------------------------


def test_a_correct_locator_passes(tmp_path):
    report = locator.check_corpus(one(tmp_path, ALPHA, ("Alpha Section",), 1))
    assert report.ok
    assert report.classes == {locator.OK: 1}
    assert report.offset_valid == report.page_valid == report.section_valid == 1


def test_shifted_offset_is_caught(tmp_path):
    report = locator.check_corpus(one(tmp_path, ALPHA, ("Alpha Section",), 1, shift=1))
    assert not report.ok
    assert locator.OFFSET_MISMATCH in report.classes
    assert report.anomalies[0].verdict == locator.OFFSET_MISMATCH


def test_edited_quote_is_caught(tmp_path):
    report = locator.check_corpus(one(tmp_path, ALPHA, ("Alpha Section",), 1, cited=ALPHA + " (edited)"))
    assert not report.ok
    assert locator.QUOTE_ABSENT in report.classes


def test_wrong_page_is_caught(tmp_path):
    report = locator.check_corpus(one(tmp_path, ALPHA, ("Alpha Section",), 2))
    assert not report.ok
    assert locator.PAGE_MISMATCH in report.classes
    assert report.section_valid == 1, "a page defect must not hide a correct section"


def test_wrong_section_is_caught(tmp_path):
    report = locator.check_corpus(one(tmp_path, GAMMA, ("Beta Section",), 2))
    assert not report.ok
    assert locator.SECTION_MISMATCH in report.classes
    assert report.offset_valid == report.page_valid == 1


def test_a_range_that_is_not_a_span_is_caught(tmp_path):
    report = locator.check_corpus(one(tmp_path, ALPHA[:20], ("Alpha Section",), 1))
    assert not report.ok
    assert locator.SPAN_MISSING in report.classes


def test_a_page_on_a_pageless_document_is_caught(tmp_path):
    corpus = one(tmp_path, ALPHA, ("Alpha Section",), 1, text=DOC.replace("\f", ""))
    assert locator.PAGE_ON_PAGELESS in locator.check_corpus(corpus).classes


def test_a_missing_page_on_a_pageable_document_is_caught(tmp_path):
    report = locator.check_corpus(one(tmp_path, ALPHA, ("Alpha Section",), None))
    assert not report.ok
    assert locator.PAGE_MISSING in report.classes


def test_a_pageless_document_needs_no_page(tmp_path):
    text = DOC.replace("\f", "")
    report = locator.check_corpus(one(tmp_path, ALPHA, ("Alpha Section",), None, text=text))
    assert report.ok


# --- the case with no single right answer -----------------------------------


@pytest.mark.parametrize("declared", [("Alpha Section",), ("Beta Section",)])
def test_a_quote_across_a_heading_is_enumerated_not_hidden(tmp_path, declared):
    span = CROSSING_SPANS[2][1]
    report = locator.check_corpus(
        build(tmp_path, CROSSING_DOC, CROSSING_SPANS, [{"quote": span, "section": declared, "page": None}])
    )
    assert report.ok, "a heading crossing is a compile defect, not a broken citation"
    assert report.classes == {locator.HEADING_CROSSING: 1}
    assert report.crossing_spans == {("D", "S0003"): {("Alpha Section",), ("Beta Section",)}}


def test_a_heading_crossing_with_a_third_section_is_a_mismatch(tmp_path):
    span = CROSSING_SPANS[2][1]
    report = locator.check_corpus(
        build(tmp_path, CROSSING_DOC, CROSSING_SPANS, [{"quote": span, "section": ("Nope",), "page": None}])
    )
    assert not report.ok
    assert locator.SECTION_MISMATCH in report.classes


# --- the artifact as released ----------------------------------------------


@pytest.mark.parametrize("path", [DEMO, PILOT], ids=["demo", "pilot"])
def test_the_released_corpora_are_fully_valid(path):
    if not path.exists():
        pytest.skip(f"{path} not present")
    report = released_report(path)
    assert report.ok
    assert report.offset_valid == report.evidence
    assert report.section_valid == report.evidence
    assert report.page_valid == report.pages_checked
    assert not report.anomalies


def test_the_released_corpora_are_the_size_the_protocol_states():
    if not DEMO.exists() or not PILOT.exists():
        pytest.skip("corpora not present")
    demo, pilot = released_report(DEMO), released_report(PILOT)
    assert (demo.claims, pilot.claims) == (5680, 298)
    assert demo.claims + pilot.claims == 5978
    assert demo.evidence + pilot.evidence == 6845
    # Two spans in the pilot contain a heading that opens the next section; six
    # claims cite them. Enumerated here so a change in the compiler is noticed.
    assert pilot.heading_crossings == 6
    assert len(pilot.crossing_spans) == 2
    assert demo.heading_crossings == 0


def test_the_audit_is_json_serialisable(tmp_path):
    report = locator.check_corpus(one(tmp_path, ALPHA, ("Alpha Section",), 1))
    payload = json.loads(json.dumps(report.as_json()))
    assert payload["offset_validity"] == 1.0
    assert payload["page_validity"] == 1.0
    assert payload["section_validity"] == 1.0
