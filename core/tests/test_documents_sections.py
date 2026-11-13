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
    # The contents page is not a parent section: the article is the section.
    assert clean_sections(spans, text)[0]["locator"]["section_path"] == [
        "Articolo 3 - Imparzialità e conflitto di interessi",
    ]


WRAPPED_TITLE = (
    "Articolo 30 - Entrata in vigore, coordinamento, efficacia, aggiornamento e\n"
    "modifiche\n"
    "Il presente Codice è stato adottato.\n"
)


def test_a_wrapped_article_title_is_completed():
    """The extractor prints the wrap on its own line; the title is one heading."""
    spans = _spans_at(["Il presente Codice è stato adottato."], [[]], WRAPPED_TITLE)
    assert clean_sections(spans, WRAPPED_TITLE)[0]["locator"]["section_path"] == [
        "Articolo 30 - Entrata in vigore, coordinamento, efficacia, aggiornamento e modifiche",
    ]


LONG_WRAPPED_TITLE = (
    "Articolo 8 - Riciclaggio, ricettazione e impiego di denaro, beni o utilità di\n"
    "provenienza illecita\n"
    "NETCARING S.r.l. vieta al proprio personale di acquistare denaro.\n"
)


def test_a_wrapped_title_may_be_longer_than_one_line():
    """The ceiling tells a heading from a paragraph, and the wrap is two lines."""
    text = LONG_WRAPPED_TITLE
    spans = _spans_at(
        ["NETCARING S.r.l. vieta al proprio personale di acquistare denaro."], [[]], text
    )
    path = clean_sections(spans, text)[0]["locator"]["section_path"]
    assert path == [
        "Articolo 8 - Riciclaggio, ricettazione e impiego di denaro, beni o utilità "
        "di provenienza illecita",
    ]
    assert len(path[0]) > 90


POLICY_PAGE = (
    "La Direzione verifica l'efficacia del Sistema di Gestione.\n"
    "RIESAME\n"
    "Il Responsabile ha la responsabilità del riesame della politica.\n"
    "\x0c"
    "Manuale SGSD\n"
    "Allegato n. 1\n"
    "(ISO/IEC 27001:2022)\n"
    "Ed. 01 Rev. 00\n"
    "\n"
    "Il riesame dovrà verificare lo stato delle azioni correttive.\n"
    "IMPEGNO DELLA DIREZIONE\n"
    "La direzione sostiene attivamente la sicurezza.\n"
)


def test_a_heading_at_the_page_break_is_the_section():
    """``RIESAME`` ends its page; the segmenter folds it into the next paragraph."""
    spans = _spans_at(
        [
            "RIESAME Il Responsabile ha la responsabilità del riesame della politica.",
            "Il riesame dovrà verificare lo stato delle azioni correttive.",
            "La direzione sostiene attivamente la sicurezza.",
        ],
        [
            ["POLICY SICUREZZA DELLE INFORMAZIONI"],
            ["POLICY SICUREZZA DELLE INFORMAZIONI"],
            ["IMPEGNO DELLA DIREZIONE"],
        ],
        POLICY_PAGE,
    )
    cleaned = clean_sections(spans, POLICY_PAGE)
    assert cleaned[0]["locator"]["section_path"] == [
        "POLICY SICUREZZA DELLE INFORMAZIONI",
        "RIESAME",
    ]
    # The page break does not end the section: the next span keeps it.
    assert cleaned[1]["locator"]["section_path"] == [
        "POLICY SICUREZZA DELLE INFORMAZIONI",
        "RIESAME",
    ]
    # A heading the segmenter did record ends it.
    assert cleaned[2]["locator"]["section_path"] == ["IMPEGNO DELLA DIREZIONE"]


def test_a_legal_name_is_not_a_heading_at_the_start_of_a_paragraph():
    """``NETCARING S.R.L. Via …`` opens with capitals and is not a section."""
    text = (
        "NETCARING S.R.L. Via Giovanni Porzio, 4 - Napoli.\n"
        "\x0c"
        "EA 33 (NACE 62) Certificato N°: I787.\n"
    )
    spans = _spans_at(
        ["NETCARING S.R.L. Via Giovanni Porzio, 4 - Napoli."],
        [["Sede Legale"]],
        text,
    )
    assert clean_sections(spans, text)[0]["locator"]["section_path"] == ["Sede Legale"]


def test_a_span_of_capitals_with_no_sentence_is_not_a_heading():
    """A span that is all capitals has no sentence under it: nothing says it is a heading."""
    text = "RIESAME E ALTRO\n\nIl riesame dovrà verificare lo stato delle azioni.\n"
    spans = _spans_at(
        ["RIESAME E ALTRO", "Il riesame dovrà verificare lo stato delle azioni."],
        [[], []],
        text,
    )
    cleaned = clean_sections(spans, text)
    assert cleaned[0]["locator"]["section_path"] == []
    assert cleaned[1]["locator"]["section_path"] == []


INLINE_HEADING = (
    "Il Sistema di Gestione definisce le linee guida aziendali.\n"
    "SCOPO E OBIETTIVI\n"
    "La Direzione ha definito la politica per la sicurezza.\n"
    "Il riesame dovrà verificare lo stato delle azioni correttive.\n"
)


def test_a_heading_printed_inside_a_paragraph_is_the_section_below_it():
    """The extractor joins a page into one block: the heading is not its first line."""
    spans = _spans_at(
        [
            "Il Sistema di Gestione definisce le linee guida aziendali. SCOPO E OBIETTIVI "
            "La Direzione ha definito la politica per la sicurezza.",
            "Il riesame dovrà verificare lo stato delle azioni correttive.",
        ],
        [[], []],
        INLINE_HEADING,
    )
    cleaned = clean_sections(spans, INLINE_HEADING)
    # The text before the heading sits in the band above, so the span keeps it.
    assert cleaned[0]["locator"]["section_path"] == []
    # What comes below the heading inherits it, across the span boundary.
    assert cleaned[1]["locator"]["section_path"] == ["SCOPO E OBIETTIVI"]


SIBLING_HEADINGS = (
    "RIESAME\n"
    "Il Responsabile ha la responsabilità del riesame.\n"
    "La direzione sostiene attivamente la sicurezza.\n"
    "IMPEGNO DELLA DIREZIONE\n"
    "La direzione definisce gli obiettivi per la sicurezza.\n"
    "La direzione riesamina gli obiettivi ogni anno.\n"
)


def test_two_headings_of_the_same_document_are_siblings_not_parent_and_child():
    """A section that follows another is not its subsection."""
    spans = _spans_at(
        [
            "RIESAME Il Responsabile ha la responsabilità del riesame.",
            "La direzione sostiene attivamente la sicurezza. IMPEGNO DELLA DIREZIONE "
            "La direzione definisce gli obiettivi per la sicurezza.",
            "La direzione riesamina gli obiettivi ogni anno.",
        ],
        [[], [], []],
        SIBLING_HEADINGS,
    )
    cleaned = clean_sections(spans, SIBLING_HEADINGS)
    assert cleaned[0]["locator"]["section_path"] == ["RIESAME"]
    # The second span holds the last text of ``RIESAME`` and the first text of
    # ``IMPEGNO DELLA DIREZIONE``, so it declares only what the two share; the
    # claims below it carry the section each one belongs to.
    assert cleaned[1]["locator"]["section_path"] == []
    assert cleaned[2]["locator"]["section_path"] == ["IMPEGNO DELLA DIREZIONE"]


def test_a_claim_that_quotes_below_an_inline_heading_gets_that_section():
    """The section of a claim is the last heading printed above the text it quotes."""
    text = (
        "Il Sistema di Gestione definisce le linee guida aziendali.\n"
        "SCOPO E OBIETTIVI\n"
        "La Direzione ha definito la politica per la sicurezza.\n"
    )
    paragraph = (
        "Il Sistema di Gestione definisce le linee guida aziendali. SCOPO E OBIETTIVI "
        "La Direzione ha definito la politica per la sicurezza."
    )
    spans = _spans_at([paragraph], [[]], text)
    breaks: dict = {}
    cleaned = clean_sections(spans, text, breaks)
    before = "Il Sistema di Gestione definisce le linee guida aziendali."
    after = "La Direzione ha definito la politica per la sicurezza."
    locator = {"span_id": "S0001", "char_start": 0, "char_end": len(paragraph)}
    claims = [
        {"claim_id": "T1-0001", "doc_id": "T1", "statement": before,
         "evidence": [{"quote": before, "locator": dict(locator)}]},
        {"claim_id": "T1-0002", "doc_id": "T1", "statement": after,
         "evidence": [{"quote": after, "locator": dict(locator)}]},
    ]
    apply_sections(claims, cleaned, breaks, text)
    assert claims[0]["evidence"][0]["locator"]["section_path"] == []
    assert claims[1]["evidence"][0]["locator"]["section_path"] == ["SCOPO E OBIETTIVI"]


def test_a_quote_that_runs_across_a_heading_does_not_place_the_claim():
    """A block-level quote is as wide as the block: the statement says which side."""
    text = (
        "La presente Politica viene diffusa a tutto il personale.\n"
        "CAMPO DI APPLICAZIONE\n"
        "La presente politica si applica a tutti gli organi dell'Azienda.\n"
    )
    paragraph = (
        "La presente Politica viene diffusa a tutto il personale. "
        "CAMPO DI APPLICAZIONE La presente politica si applica a tutti gli organi dell'Azienda."
    )
    spans = _spans_at([paragraph], [[]], text)
    breaks: dict = {}
    cleaned = clean_sections(spans, text, breaks)
    statement = "La presente politica si applica a tutti gli organi dell'Azienda."
    locator = {"span_id": "S0001", "char_start": 0, "char_end": len(paragraph)}
    claims = [
        {
            "claim_id": "T1-0001",
            "doc_id": "T1",
            "statement": statement,
            # The model quoted the whole page block, not the sentence it states.
            "evidence": [{"quote": paragraph, "locator": dict(locator)}],
        }
    ]
    apply_sections(claims, cleaned, breaks, text)
    assert claims[0]["evidence"][0]["locator"]["section_path"] == ["CAMPO DI APPLICAZIONE"]


SIBLING_IN_ONE_SPAN = (
    "RIESAME\n"
    "Il Responsabile verifica l'efficacia del Sistema.\n"
    "La direzione sostiene il Sistema di Gestione.\n"
    "IMPEGNO DELLA DIREZIONE\n"
    "La direzione definisce gli obiettivi per la sicurezza.\n"
)


def test_a_span_that_holds_two_sibling_sections_declares_what_they_share():
    """The band above and the heading below are siblings: the span is their base.

    A claim below the heading then resolves back to a span that declares the
    section it names, instead of one that declares the band above it.
    """
    span_one = "RIESAME Il Responsabile verifica l'efficacia del Sistema."
    span_two = (
        "La direzione sostiene il Sistema di Gestione. IMPEGNO DELLA DIREZIONE "
        "La direzione definisce gli obiettivi per la sicurezza."
    )
    spans = _spans_at([span_one, span_two], [[], []], SIBLING_IN_ONE_SPAN)
    breaks: dict = {}
    cleaned = clean_sections(spans, SIBLING_IN_ONE_SPAN, breaks)
    assert cleaned[0]["locator"]["section_path"] == ["RIESAME"]
    # The band above and ``IMPEGNO DELLA DIREZIONE`` share no heading.
    assert cleaned[1]["locator"]["section_path"] == []

    above = "La direzione sostiene il Sistema di Gestione."
    below = "La direzione definisce gli obiettivi per la sicurezza."
    locator = {
        "span_id": "S0002",
        "char_start": cleaned[1]["locator"]["char_start"],
        "char_end": cleaned[1]["locator"]["char_end"],
    }
    claims = [
        {"claim_id": "T1-0001", "doc_id": "T1", "statement": above,
         "evidence": [{"quote": above, "locator": dict(locator)}]},
        {"claim_id": "T1-0002", "doc_id": "T1", "statement": below,
         "evidence": [{"quote": below, "locator": dict(locator)}]},
    ]
    apply_sections(claims, cleaned, breaks, SIBLING_IN_ONE_SPAN)
    assert claims[0]["evidence"][0]["locator"]["section_path"] == ["RIESAME"]
    assert claims[1]["evidence"][0]["locator"]["section_path"] == ["IMPEGNO DELLA DIREZIONE"]


GAP_HEADING = (
    "Il rischio di sanzioni legali o amministrative va ridotto al minimo.\n"
    "\n"
    "RESPONSABILITÀ DI OSSERVAZIONE E ATTUAZIONE\n"
    "L'osservanza e l'attuazione delle policy sono responsabilità di:\n"
    "tutto il personale che collabora con l'azienda.\n"
)


def test_a_heading_the_segmenter_dropped_still_titles_the_span_below():
    """The block carries a real heading; only the spans are missing, not the text."""
    spans = _spans_at(
        [
            "Il rischio di sanzioni legali o amministrative va ridotto al minimo.",
            "tutto il personale che collabora con l'azienda.",
        ],
        [["POLICY SICUREZZA DELLE INFORMAZIONI"], ["POLICY SICUREZZA DELLE INFORMAZIONI"]],
        GAP_HEADING,
    )
    cleaned = clean_sections(spans, GAP_HEADING)
    assert cleaned[0]["locator"]["section_path"] == ["POLICY SICUREZZA DELLE INFORMAZIONI"]
    assert cleaned[1]["locator"]["section_path"] == [
        "POLICY SICUREZZA DELLE INFORMAZIONI",
        "RESPONSABILITÀ DI OSSERVAZIONE E ATTUAZIONE",
    ]


def test_a_table_label_in_a_gap_is_not_a_section():
    """Title case and no sentence under it: rows, not a title."""
    text = (
        "La validità del certificato è soggetta a sorveglianza periodica.\n"
        "\n"
        "Prima Emissione\n"
        "Emissione Corrente\n"
        "Il certificato scade il 27/02/2028.\n"
    )
    spans = _spans_at(
        [
            "La validità del certificato è soggetta a sorveglianza periodica.",
            "Il certificato scade il 27/02/2028.",
        ],
        [["Validità"], ["Validità"]],
        text,
    )
    cleaned = clean_sections(spans, text)
    assert cleaned[1]["locator"]["section_path"] == ["Validità"]
