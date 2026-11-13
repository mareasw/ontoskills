"""Tests for the section-path cleanup that runs after the replies are cached.

The segmenter keeps every heading it sees, and a PDF running header looks
exactly like a heading. The prompt carries those raw paths on purpose (the
cache fingerprint does not cover them), so the correction happens on the way
out: spans and claims are cleaned once the model has already answered.
"""

from __future__ import annotations

from compiler.documents.sections import apply_sections, clean_sections
from compiler.documents.text import norm

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


def test_a_restated_module_heading_is_kept():
    text = "Security of processing\nThe importer shall act.\n\x0cSecurity of processing\nThe importer shall act again.\n"
    spans = _spans_with([["Security of processing"], ["Security of processing"]])
    assert clean_sections(spans, text)[1]["locator"]["section_path"] == ["Security of processing"]


def test_a_short_repeated_line_is_furniture():
    text = "EN\nThe importer shall act.\n\x0cEN\nThe importer shall act again.\n"
    spans = _spans_with([["Article 5"], ["EN"]])
    assert clean_sections(spans, text)[1]["locator"]["section_path"] == ["Article 5"]


def test_consecutive_duplicate_elements_collapse():
    spans = _spans_with([["Human oversight", "Human oversight"]])
    assert clean_sections(spans, "x")[0]["locator"]["section_path"] == ["Human oversight"]


def test_a_running_date_line_is_furniture():
    text = "February 26, 2024\nThe importer shall act.\n\x0cFebruary 26, 2024\nThe importer shall act again.\n"
    spans = _spans_with([["Article 5"], ["February 26, 2024"]])
    assert clean_sections(spans, text)[1]["locator"]["section_path"] == ["Article 5"]


def test_a_heading_that_mentions_a_year_is_kept():
    spans = _spans_with([["AI RMF 1.0 (January 2023)"]])
    assert clean_sections(spans, "x")[0]["locator"]["section_path"] == ["AI RMF 1.0 (January 2023)"]


def test_a_long_running_header_is_furniture_by_its_position():
    """The Italian corporate header is too long for the short-marker rule."""
    page = "ISO 9001:2015\nN° QMS18180211 - 33.0017\nThe importer shall act.\n"
    text = "\f".join([page] * 5)
    spans = _spans_with([["Article 5"], ["N° QMS18180211 - 33.0017"]])
    assert clean_sections(spans, text)[1]["locator"]["section_path"] == ["Article 5"]


def test_a_heading_restated_on_a_few_pages_is_not_furniture():
    """A module heading lives on the pages of its module, not on four fifths of the file."""
    pages = [
        "Security of processing\nThe importer shall act.\n" if index < 4
        else "Annex\nThe importer shall act.\n"
        for index in range(10)
    ]
    spans = _spans_with([["Security of processing"]])
    assert clean_sections(spans, "\f".join(pages))[0]["locator"]["section_path"] == [
        "Security of processing"
    ]


def test_a_two_page_document_cannot_tell_a_header_from_a_heading():
    """On two pages every repeated line is 100% of the pages: position proves nothing."""
    text = "N° QMS18180211 - 33.0017\nThe importer shall act.\n\fN° QMS18180211 - 33.0017\nThe importer shall act again.\n"
    spans = _spans_with([["N° QMS18180211 - 33.0017"]])
    assert clean_sections(spans, text)[0]["locator"]["section_path"] == [
        "N° QMS18180211 - 33.0017"
    ]


def test_a_footer_joined_into_one_heading_is_furniture():
    """The segmenter joins the footer lines: the element is furniture, not a title."""
    footer = (
        "Riferimenti\nsito www.netcaring.it\nmail: amministrazione@netcaring.it\n"
        "PEC: netcaring@pec.it\nNetwork Partner\nwww.treetechict.com"
    )
    page = f"ISO 9001:2015\nN° QMS18180211 - 33.0017\nThe importer shall act.\n{footer}\n"
    text = "\f".join([page] * 5)
    spans = _spans_with(
        [["Article 5"], ["Riferimenti sito www.netcaring.it mail: amministrazione@netcaring.it"]]
    )
    assert clean_sections(spans, text)[1]["locator"]["section_path"] == ["Article 5"]


def _spans_at(paragraphs, sections, text):
    """Spans whose char_start is where the paragraph really is, as segment() sets it."""
    flat = norm(text)
    spans = []
    cursor = 0
    for index, (paragraph, section) in enumerate(zip(paragraphs, sections), start=1):
        at = flat.find(norm(paragraph), cursor)
        cursor = at + len(norm(paragraph))
        spans.append(
            {
                "span_id": f"S{index:04d}",
                "doc_id": "T1",
                "paragraph": paragraph,
                "locator": {
                    "kind": "text",
                    "section_path": list(section),
                    "char_start": at,
                    "char_end": at + len(norm(paragraph)),
                },
            }
        )
    return spans


LONG_ARTICLE = (
    "DOVERI E RESPONSABILITÀ\n"
    "\n"
    "Articolo 4 - Gestione del personale\n"
    "Il personale opera con diligenza.\n"
    "\n"
    "Articolo 5 - Divieto di detenzione di materiale pornografico\n"
    "Il personale rispetta il divieto.\n"
)


def test_a_long_article_title_is_a_heading_the_segmenter_missed():
    """Nine words is over the segmenter's cap, but the marker is the heading."""
    spans = _spans_at(
        ["Il personale opera con diligenza.", "Il personale rispetta il divieto."],
        [["Articolo 4 - Gestione del personale"], ["Articolo 4 - Gestione del personale"]],
        LONG_ARTICLE,
    )
    path = clean_sections(spans, LONG_ARTICLE)[1]["locator"]["section_path"]
    assert path == ["Articolo 5 - Divieto di detenzione di materiale pornografico"]


def test_an_article_already_on_the_path_is_not_added_twice():
    spans = _spans_at(
        ["Il personale opera con diligenza."],
        [["DOVERI E RESPONSABILITÀ", "Articolo 4 - Gestione del personale"]],
        LONG_ARTICLE,
    )
    assert clean_sections(spans, LONG_ARTICLE)[0]["locator"]["section_path"] == [
        "DOVERI E RESPONSABILITÀ",
        "Articolo 4 - Gestione del personale",
    ]


def test_an_article_is_inserted_above_its_subsection():
    text = (
        "Articolo 4 - Gestione del personale\n"
        "Sezione interna\n"
        "Il personale opera con diligenza.\n"
    )
    spans = _spans_at(["Il personale opera con diligenza."], [["Sezione interna"]], text)
    assert clean_sections(spans, text)[0]["locator"]["section_path"] == [
        "Articolo 4 - Gestione del personale",
        "Sezione interna",
    ]


def test_a_table_of_contents_entry_is_not_the_article_heading():
    """The index repeats the title with a dot leader; the body line is the heading."""
    text = (
        "Indice\n"
        "Articolo 3 - Imparzialità e conflitto di interessi........4\n"
        "\n"
        "Articolo 3 - Imparzialità e conflitto di interessi\n"
        "Il personale agisce con imparzialità.\n"
    )
    spans = _spans_at(["Il personale agisce con imparzialità."], [["Indice"]], text)
    assert clean_sections(spans, text)[0]["locator"]["section_path"] == [
        "Indice",
        "Articolo 3 - Imparzialità e conflitto di interessi",
    ]
