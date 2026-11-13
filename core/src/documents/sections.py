"""Repair the section paths of a compiled document.

A PDF running header — ``L 119/29``, ``OJ L, 12.7.2024``, ``ELI: …`` — is a
line with no terminal stop and few words, which is exactly what the segmenter
takes for a heading. The heading stack then carries the masthead as the section
of everything below it, so the view prints a page number where the article
should be and the verifier cannot find the subject of the statement.

The segmenter stays frozen: it is parity-tested against the DocBench copy, and
the extraction prompt shows the model those same headings. The prompt and the
reply cache fingerprint are deliberately untouched, so the correction runs on
the way out: after ``compile_document`` has returned, on spans and claims that
no longer feed a model call.
"""

from __future__ import annotations

import re

from compiler.documents.segment import looks_like_heading
from compiler.documents.text import norm

# A page label in its running-header forms: a bare folio ("L 119/29", "12/144"),
# the Official Journal masthead, the ELI pointer printed in every footer, and the
# date line a standards publisher prints on every page ("February 26, 2024").
# The date must be the whole element: "AI RMF 1.0 (January 2023)" is a heading
# that happens to carry a date, and a masthead is a date and nothing else.
MONTHS = r"January|February|March|April|May|June|July|August|September|October|November|December"
PAGE_LABEL = re.compile(
    r"^(?:[A-Z]{1,3}\s+)?\d+/\d+$"
    r"|^OJ\s+L,\s*\d+\.\d+\.\d{4}$"
    r"|^ELI:\s*https?://\S+$"
    rf"|^(?:(?i:{MONTHS})\s+\d{{1,2}},\s*\d{{4}}|\d{{1,2}}\s+(?i:{MONTHS})\s+\d{{4}})$"
)

MAX_PATH = 3

# Where a heading printed in the middle of a span is, and what it sits on: the
# offset it starts at, the heading, and the path it belongs to. The base travels
# with the heading because two headings of one document are siblings, not parent
# and child, and a claim below the second one must get the same path the span
# below it gets.
Breaks = dict[tuple[str, str], list[tuple[int, str, list[str]]]]
# A line short enough that it is a page marker rather than a heading. Length is
# the only safe signal: "Security of processing" is a real module heading that a
# standard-contractual-clauses annex restates on four pages, and repetition
# alone cannot tell it from a masthead.
MAX_MARKER = 12

# The table of contents is not a section: it is the page that announces the
# sections. A path element naming it is a heading the stack never popped, so the
# article below it arrives as "Indice > Articolo 1". The contents page is also
# where a claim under "Indice" alone would end up, and no document states a rule
# on its own table of contents.
TOC_MARKERS = frozenset(
    {"indice", "sommario", "contenuti", "contenuto", "contents", "table of contents", "index"}
)

# A heading at the end of a page is folded into the paragraph that starts the
# next one: the extractor prints "RIESAME" as the last line before the break and
# the segmenter joins it to the sentence below, so the path never carries it.
# The marker is still in the text — an all-caps line printed on its own — and it
# is read again here, on the way out. The guards keep a heading from being
# mistaken for an identifier ("EA 33 (NACE 62)"), a legal name ("NETCARING
# S.R.L.") or a running header ("INFORMAZIONI"), which are lines of the same
# shape. What counts as a heading is the segmenter's own definition, imported
# rather than restated: a candidate that ``looks_like_heading`` rejects is not a
# heading here either, however many capitals it prints.
SENTENCE_START = re.compile(r"^[A-ZÀ-ÖØ-Þ][a-zà-öø-ÿ]")

# Position is the second signal, for the headers that are too long to be caught
# by length: "N° QMS18180211 - 33.0017" sits in the header slot of every page of
# a corporate PDF. A line is furniture when it occupies the first lines of a
# page (or the last ones) on at least four fifths of the pages. The share, not
# the repetition, is what keeps a real module heading: a heading restated on
# four pages of a long annex is a small fraction of the document, while a
# running header is on nearly every page. Three pages is the floor, because on a
# two-page document any repeated line is 100% of the pages and nothing can be
# told apart.
HEADER_LINES = 4
FOOTER_LINES = 12
FURNITURE_SHARE = 0.8
FURNITURE_MIN_PAGES = 3


def _is_masthead(line: str) -> bool:
    """True when a line has one of the shapes a running header takes."""
    return bool(PAGE_LABEL.match(line)) or "official journal" in line.lower()


def _edge_lines(pages: list[str]) -> dict[str, int]:
    """How many pages each line occupies in a header or footer slot."""
    counts: dict[str, int] = {}
    for page in pages:
        lines = [line.strip() for line in page.split("\n") if line.strip()]
        if not lines:
            continue
        for line in set(lines[:HEADER_LINES]) | set(lines[-FOOTER_LINES:]):
            counts[line] = counts.get(line, 0) + 1
    return counts


def furniture(text: str) -> set[str]:
    """Lines that are page furniture rather than document text.

    Furniture is recognised by form, by position and by share of the pages, not
    by bare frequency: a folio or Official Journal line, a page marker short
    enough that it cannot be a heading and that repeats across pages, or a line
    that sits in the header/footer slot of at least four fifths of the pages. A
    phrase merely repeated a few times is not evidence of furniture, because
    documents are allowed to restate a real heading on every page of a module.
    """
    pages = text.split("\f")
    seen: dict[str, set[int]] = {}
    marks: set[str] = set()
    for number, page in enumerate(pages):
        for raw in page.split("\n"):
            line = raw.strip()
            if not line:
                continue
            if _is_masthead(line):
                marks.add(line)
            if len(line) <= MAX_MARKER:
                seen.setdefault(line, set()).add(number)
    repeated = {line for line, where in seen.items() if len(where) >= 2}
    marks |= repeated
    if len(pages) >= FURNITURE_MIN_PAGES:
        needed = FURNITURE_SHARE * len(pages)
        marks |= {
            line for line, count in _edge_lines(pages).items() if count >= needed
        }
    return marks


def _is_joined_furniture(text: str, pieces: set[str]) -> bool:
    """True when an element is two or more furniture lines joined as a heading.

    The segmenter joins consecutive heading-like lines into one heading group,
    ``norm(" ".join(group))[:90]``, so a footer printed over three lines arrives
    as one element. Consuming the element from furniture lines is the only way to
    see that none of its words came from the body of the document.
    """
    remaining = text
    consumed = 0
    # Short pieces are left out on purpose: "EN" or a folio can occur inside a
    # real heading, and a match on one of them would drop the heading.
    ordered = sorted((piece for piece in pieces if len(piece) >= 4), key=len, reverse=True)
    while remaining:
        for piece in ordered:
            if remaining.startswith(piece):
                remaining = remaining[len(piece):].lstrip()
                consumed += 1
                break
        else:
            return False
    return consumed >= 1


def _is_page_furniture(part: str, bad: set[str], bad_norm: set[str]) -> bool:
    """True when a path element is a running header, alone or joined."""
    if _is_masthead(part) or part in bad:
        return True
    return _is_joined_furniture(norm(part), bad_norm)


def _caps_word(word: str) -> bool:
    """A word that can be part of an all-caps heading.

    Capitals alone are not enough: an identifier ("EA 33 (NACE 62)"), a legal
    name ("NETCARING S.R.L.") and a folio print the same shape, and each carries
    a digit, a dot or a bracket that a heading does not.
    """
    return word.isupper() and not any(char in word for char in ".0123456789()")


def _folded_heading(
    paragraph: str, lines: set[str], bad: set[str], bad_norm: set[str]
) -> str:
    """The all-caps heading a paragraph starts with, or ``""``.

    ``paragraph`` is a span: ``RIESAME La Direzione verificherà …``. The heading
    is real when it is a whole line of the source, in capitals, a heading by the
    segmenter's own definition, followed by a sentence, and not furniture or an
    identifier.
    """
    words = paragraph.split()
    if len(words) < 2:
        return ""
    taken: list[str] = []
    for word in words:
        if not _caps_word(word):
            break
        taken.append(word)
    # A span that is nothing but capitals has no sentence under the heading, so
    # there is nothing that says the capitals are a heading rather than a title
    # and the paragraph is somewhere else.
    if not taken or len(taken) == len(words):
        return ""
    following = words[len(taken)]
    if not SENTENCE_START.match(following):
        return ""
    candidate = " ".join(taken).strip()
    if len(candidate) < 3 or norm(candidate) not in lines:
        return ""
    if not looks_like_heading(candidate) or _is_page_furniture(candidate, bad, bad_norm):
        return ""
    return candidate


def _with_heading(path: list[str], heading: str) -> list[str]:
    """Append the heading unless it is already the last element of the path."""
    if path and norm(path[-1]) == norm(heading):
        return path
    return [*path, heading][-MAX_PATH:]


def _inline_headings(
    paragraph: str, lines: set[str], bad: set[str], bad_norm: set[str]
) -> list[str]:
    """The all-caps headings printed *inside* a paragraph, in order.

    The extractor joins the lines of a page into one block, so a heading that is
    not the first line of a span — "… Stakeholder coinvolti. SCOPO E OBIETTIVI
    La Direzione …" — never reaches the heading stack, and every claim below it
    inherits the band above. The heading is still a whole line of the source,
    printed after the end of a sentence and followed by the sentence it titles,
    which is the same evidence ``_folded_heading`` asks for at the start of a
    span. They are read separately because they are two positions, not two
    rules.
    """
    out: list[str] = []
    words = list(re.finditer(r"\S+", paragraph))
    index = 0
    while index < len(words):
        if not _caps_word(words[index].group()):
            index += 1
            continue
        end = index
        while end < len(words) and _caps_word(words[end].group()):
            end += 1
        # A run that reaches the end of the paragraph has no sentence under it,
        # so nothing says it titles what comes next.
        if end < len(words):
            candidate = " ".join(word.group() for word in words[index:end])
            before = paragraph[: words[index].start()].rstrip()
            if (
                before.endswith((".", "!", "?"))
                and SENTENCE_START.match(words[end].group())
                and len(candidate) >= 3
                and norm(candidate) in lines
                and looks_like_heading(candidate)
                and not _is_page_furniture(candidate, bad, bad_norm)
            ):
                out.append(candidate)
        index = end
    return out


# The segmenter accepts a heading only if it has seven words or fewer. Italian
# article titles are descriptive and often longer — "Articolo 5 - Divieto di
# detenzione di materiale pornografico" is nine words — so the line stays in the
# body and every claim under it inherits the band above. The marker is what makes
# the line a heading, whatever its length, so the article headings the segmenter
# skipped are read again here, on the way out.
ARTICLE_HEADING = re.compile(r"^(?:Articolo|Article|Art\.)\s+\d+(?:\.\d+)*\b")
# An index line is the same heading followed by a page number: "Articolo 4 -
# Gestione del personale.....................16". It is not a section, it is a
# table of contents entry.
TOC_ENTRY = re.compile(r"\.{3,}\s*\d*\s*$")
MAX_HEADING = 90
# A long title wraps, and the extractor prints the wrap on its own line:
# "Articolo 30 - Entrata in vigore, coordinamento, efficacia, aggiornamento e"
# followed by "modifiche". Ending a title on a conjunction is the signature of
# the wrap, and a one- or two-word lower-case line below it is the rest of it.
WRAPPING_WORDS = frozenset(
    """
    e ed o od di del della delle dello degli dei per in con a al alla ai agli
    da dal dalla dalle dai su sul sulla tra fra il la lo le gli i
    """.split()
)
# The ceiling exists to tell a heading from a paragraph, and a paragraph is one
# line. A joined title is two lines of the same title, one of them already
# checked for shape, so it may run longer than a single line is allowed to
# ("Articolo 8 - … beni o utilità di" / "provenienza illecita" is 99 characters,
# and it is the whole title).
MAX_JOINED_HEADING = 120


def _join_wrapped(line: str, following: list[str]) -> str:
    """Complete a title whose last word wrapped onto the next line."""
    last = line.split()[-1].strip(",;:").lower() if line.split() else ""
    if last not in WRAPPING_WORDS:
        return line
    for raw in following:
        rest = raw.strip()
        if not rest:
            continue
        # A page break, a body line or a table-of-contents entry is not the tail
        # of the title: the wrap is one or two lower-case words and nothing else.
        if "\f" in rest or len(rest) > 25 or len(rest.split()) > 2:
            return line
        if not rest[0].islower() or rest.endswith((".", ";", ":", ",")):
            return line
        joined = f"{line} {rest}"
        return joined if len(joined) <= MAX_JOINED_HEADING else line
    return line


def _missed_headings(text: str) -> list[tuple[int, str]]:
    """Article headings present in the text as ``(offset, line)``, in order.

    The offset is into ``norm(text)``, the same string the span locators count
    characters in, so a heading can be compared with the spans below it.
    """
    flat = norm(text)
    out: list[tuple[int, str]] = []
    cursor = 0
    lines = text.split("\n")
    for position, raw in enumerate(lines):
        line = raw.strip()
        if not line:
            continue
        # Every line has to advance the cursor, not only the headings, or a
        # table-of-contents entry would be found again as the body heading it
        # announces ("Articolo 4 - Gestione del personale……16").
        piece = norm(line)
        at = flat.find(piece, cursor)
        if at < 0:
            continue
        cursor = at + len(piece)
        if not ARTICLE_HEADING.match(line):
            continue
        whole = _join_wrapped(line, lines[position + 1:])
        # The length ceiling rejects a line that is a paragraph; a joined title
        # is two lines and is judged by the shape of its tail, not its length.
        if TOC_ENTRY.search(whole) or (whole == line and len(whole) > MAX_HEADING):
            continue
        line = whole
        if line.endswith((".", ";", ":", ",")):
            continue
        out.append((at, line))
    return out


def _last_seen(flat: str, part: str, before: int) -> int | None:
    """Where the path element last appears above ``before``, if it does."""
    at = flat.rfind(norm(part), 0, before)
    return at if at >= 0 else None


def _add_missed_article(
    path: list[str], start: int, missed: list[tuple[int, str]], flat: str
) -> list[str]:
    """Put the nearest article heading into the path the span sits under.

    Articles are siblings, so an earlier one the segmenter did record is
    replaced, not extended. A heading that comes after the article (a
    subsection) stays, and the article is inserted before it; a heading that
    comes before the article is the band above it and stays first. A heading
    already on the path is never repeated.
    """
    if not missed:
        return path
    nearest = next(((at, line) for at, line in reversed(missed) if at <= start), None)
    if nearest is None:
        return path
    at, line = nearest
    if any(norm(part) == norm(line) for part in path):
        return path
    kept = [
        part
        for part in path
        if not (
            ARTICLE_HEADING.match(part)
            and (seen := _last_seen(flat, part, start)) is not None
            and seen < at
        )
    ]
    below = next(
        (
            index
            for index, part in enumerate(kept)
            if (seen := _last_seen(flat, part, start)) is not None and seen > at
        ),
        None,
    )
    if below is None:
        return [*kept, line][-MAX_PATH:]
    return [*kept[:below], line, *kept[below:]][-MAX_PATH:]


def _starts_sentence(text: str) -> bool:
    """True when a word opens a sentence: a capital, then a lower-case letter.

    The apostrophe of an Italian elision ("L'osservanza") sits between the two,
    so the letter after it is what tells a sentence from a label.
    """
    word = norm(str(text or "")).strip()
    if not word:
        return False
    if SENTENCE_START.match(word):
        return True
    return "'" in word and bool(SENTENCE_START.match(word.replace("'", "")))


def _gap_heading(gap: str, bad: set[str], bad_norm: set[str]) -> str:
    """The heading the segmenter dropped between two spans, or ``""``.

    The extractor leaves a block out of the spans when it reads it as a page
    header, and a real heading printed at the top of a page goes with it. The
    heading is still in the source, and it still titles the text below, so the
    spans that follow are given it. The shape asked for is the one a heading has
    on the page: a line of its own after a blank line, in capitals, with the
    sentence it titles printed under it. Those four facts are what keeps a table
    label ("Prima Emissione"), a fragment of a wrapped title and a masthead out.
    """
    lines = gap.split("\n")
    found = ""
    for index, line in enumerate(lines):
        candidate = line.strip()
        if len(candidate) < 3 or index == 0 or lines[index - 1].strip():
            continue
        if not all(_caps_word(word) for word in candidate.split()):
            continue
        if not looks_like_heading(candidate):
            continue
        if _is_page_furniture(candidate, bad, bad_norm):
            continue
        if norm(candidate).casefold() in TOC_MARKERS:
            continue
        following = next((other.strip() for other in lines[index + 1:] if other.strip()), "")
        if not _starts_sentence(following.split()[0] if following else ""):
            continue
        found = candidate
    return found


def clean_sections(
    spans: list[dict], text: str, breaks: Breaks | None = None
) -> list[dict]:
    """Return the spans with their section paths stripped of page furniture.

    A dropped element is not replaced by a guess: the span inherits the last
    real path seen above it in the same document, because a page break does not
    start a new article. A span that has nothing to inherit keeps an empty path
    rather than borrowing a heading the document never set.

    The same rule applies in the other direction: an article heading the
    segmenter rejected for its word count is added only when it is the heading
    the span actually sits under, and only if it is not already on the path.

    ``breaks``, when given, is filled with the headings printed in the middle of
    a span, the offset where each one starts and the path it belongs to, so a
    claim that quotes the text below one can be given that section even though
    the span above it is not.
    """
    bad = furniture(text)
    bad_norm = {norm(line) for line in bad if len(norm(line)) >= 2}
    flat = norm(text)
    missed = _missed_headings(text)
    lines = {norm(line.strip()) for line in text.splitlines() if line.strip()}
    grouped: dict[str, list[dict]] = {}
    for span in spans:
        grouped.setdefault(span["doc_id"], []).append(span)
    out: list[dict] = []
    for doc_spans in grouped.values():
        doc_spans.sort(key=lambda s: (s.get("locator") or {}).get("char_start") or 0)
        last: list[str] = []
        # Where the previous span ended: the text in between belongs to no span,
        # and a heading printed there still titles what comes below. The text
        # before the first span is the title block, and the document's title is
        # already carried by its metadata, so it is not read as a section.
        cursor = 0
        first = True
        # The folded heading in force, with the path it was folded under. A
        # heading the segmenter did record changes the path, and that ends it.
        promoted: tuple[str, list[str]] | None = None
        for span in doc_spans:
            locator = dict(span.get("locator") or {})
            start = locator.get("char_start")
            raw = [
                str(part).strip()
                for part in locator.get("section_path") or []
                if not _is_page_furniture(str(part).strip(), bad, bad_norm)
                and norm(str(part)).casefold() not in TOC_MARKERS
            ]
            if promoted is not None and raw and raw != promoted[1]:
                promoted = None
            if raw:
                path = _collapse(raw)[-MAX_PATH:]
                last = path
            else:
                path = list(last)
            if start is not None and not first:
                dropped = _gap_heading(text[cursor:int(start)], bad, bad_norm)
                if dropped:
                    # The heading was in the document all along; only the spans
                    # were missing. It titles everything below it, so it is a
                    # sibling of the band above and it starts here.
                    promoted = (dropped, list(path))
                    path = _with_heading(path, dropped)
                    last = path
            paragraph = str(span.get("paragraph") or "")
            heading = _folded_heading(paragraph, lines, bad, bad_norm)
            if heading:
                # A heading is a sibling of the one promoted before it, not its
                # child: two page-end headings are two sections of the document,
                # so the base is the path before the first promotion. Appending
                # would nest "CAMPO DI APPLICAZIONE" under "SCOPO E OBIETTIVI".
                base = promoted[1] if promoted is not None else list(path)
                promoted = (heading, list(base))
                path = _with_heading(base, heading)
                last = path
            elif promoted is not None:
                path = _with_heading(path, promoted[0])
                last = path
            inline = _inline_headings(paragraph, lines, bad, bad_norm)
            if inline:
                base = promoted[1] if promoted is not None else list(path)
                for inline_heading in inline:
                    promoted = (inline_heading, list(base))
                # The span itself keeps the band above: the text before the
                # heading belongs to it. What follows inherits the heading, and
                # a claim that quotes below it gets it in ``apply_sections``.
                last = _with_heading(base, inline[-1])
            if start is not None:
                path = _add_missed_article(path, int(start), missed, flat)
                last = (
                    _add_missed_article(last, int(start), missed, flat) if inline else path
                )
            if inline and path != base and path[: len(base)] == base:
                # The span holds text of two sections that are siblings, and
                # they share only ``base``: its own path has to be that shared
                # path. Declaring the band above would make the claim below the
                # heading point at a span that declares a different section,
                # and the verifier would read a correct claim as a wrong one.
                # The band travels with ``breaks`` instead, so a claim quoting
                # above the heading still gets it.
                if breaks is not None and start is not None:
                    breaks.setdefault((span["doc_id"], span["span_id"]), []).insert(
                        0, (int(start), path[-1], list(base))
                    )
                path = list(base)
            locator["section_path"] = path
            cleaned = dict(span)
            cleaned["locator"] = locator
            out.append(cleaned)
            if breaks is not None and inline:
                at = int(start) if start is not None else 0
                for inline_heading in inline:
                    found = flat.find(norm(inline_heading), at)
                    if found < 0:
                        continue
                    breaks.setdefault((span["doc_id"], span["span_id"]), []).append(
                        (found, inline_heading, list(base))
                    )
                    at = found + len(norm(inline_heading))
            end = locator.get("char_end")
            if end is not None:
                cursor = max(cursor, int(end))
            first = False
    return out


def _collapse(path: list[str]) -> list[str]:
    """Drop an element that repeats the one before it: ``[a, a, b] -> [a, b]``.

    The heading stack re-pushes a heading it has already recorded when a span
    under it also starts a new section, so a real heading arrives twice. The
    duplication says nothing a reader would want to see.
    """
    out: list[str] = []
    for part in path:
        if not out or part != out[-1]:
            out.append(part)
    return out


def apply_sections(
    claims: list[dict],
    cleaned_spans: list[dict],
    breaks: Breaks | None = None,
    text: str = "",
) -> list[dict]:
    """Copy the cleaned path into the claims, which carry a locator of their own.

    A claim's evidence locator is a copy taken at build time, and a claim whose
    declared section disagrees with the span it resolves to fails verification,
    so the copy has to follow. Schema v2 locators carry a span id only when the
    producer put one there; the (char_start, char_end) range resolves the rest,
    which is the same order the verifier uses.

    A span can hold more than one section, because the extractor joins a page
    into one block and a heading can be printed in the middle of it. The section
    of a claim is the last heading printed above the text it quotes, so the
    quote is located in the document and the headings of the span are applied
    only when they start before it.
    """
    by_id = {(span["doc_id"], span["span_id"]): span for span in cleaned_spans}
    by_range = {
        (span["doc_id"], (span.get("locator") or {}).get("char_start"),
         (span.get("locator") or {}).get("char_end")): span
        for span in cleaned_spans
    }
    flat = norm(text)
    for claim in claims:
        doc_id = claim.get("doc_id")
        for item in claim.get("evidence") or []:
            locator = item.get("locator")
            if not locator:
                continue
            span = None
            if locator.get("span_id"):
                span = by_id.get((doc_id, locator["span_id"]))
            if span is None:
                span = by_range.get(
                    (doc_id, locator.get("char_start"), locator.get("char_end"))
                )
            if span is None:
                continue
            path = list((span.get("locator") or {}).get("section_path") or [])
            cuts = (breaks or {}).get((doc_id, span.get("span_id"))) or []
            if cuts:
                where = _where_quoted(item, claim, flat, locator, cuts)
                for offset, heading, base in cuts:
                    if where is not None and offset <= where:
                        path = _with_heading(base, heading)
            locator["section_path"] = path
    return claims


def _locate(needle: str, flat: str, start: int, limit: int) -> int | None:
    """Where ``needle`` starts inside the block, or ``None`` if it is not there."""
    text = norm(str(needle or ""))
    if not text:
        return None
    found = flat.find(text, start)
    return found if start <= found < limit else None


def _where_quoted(
    item: dict, claim: dict, flat: str, locator: dict, cuts: list[tuple[int, str, list[str]]]
) -> int | None:
    """Where in the block the claim's text starts, if it can be located.

    The locator gives the range of the *block* the claim came from, which is the
    whole page on a PDF: a block that carries a heading in the middle cannot say
    which side of it the claim sits on. The quote is verbatim, so it is tried
    first — but a quote that runs *across* the heading ("… Stakeholder
    coinvolti. SCOPO E OBIETTIVI La Direzione …") is as wide as the block and
    locates nothing. Only then does the statement place the claim: it is the
    model's wording, and it is the text the heading titles. Both are bounded to
    the block, so a phrase printed elsewhere cannot pull a claim out of its span.
    """
    start = int(locator.get("char_start") or 0)
    end = locator.get("char_end")
    limit = int(end) if end is not None else len(flat)
    quote = norm(str(item.get("quote") or ""))
    quoted = _locate(quote, flat, start, limit)
    if quoted is not None:
        stop = quoted + len(quote)
        if not any(quoted <= offset < stop for offset, _, _ in cuts):
            return quoted
    stated = _locate(claim.get("statement"), flat, start, limit)
    if stated is not None:
        return stated
    return quoted if quoted is not None else start
