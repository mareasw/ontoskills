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
# A line short enough that it is a page marker rather than a heading. Length is
# the only safe signal: "Security of processing" is a real module heading that a
# standard-contractual-clauses annex restates on four pages, and repetition
# alone cannot tell it from a masthead.
MAX_MARKER = 12

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


def clean_sections(spans: list[dict], text: str) -> list[dict]:
    """Return the spans with their section paths stripped of page furniture.

    A dropped element is not replaced by a guess: the span inherits the last
    real path seen above it in the same document, because a page break does not
    start a new article. A span that has nothing to inherit keeps an empty path
    rather than borrowing a heading the document never set.
    """
    bad = furniture(text)
    bad_norm = {norm(line) for line in bad if len(norm(line)) >= 2}
    grouped: dict[str, list[dict]] = {}
    for span in spans:
        grouped.setdefault(span["doc_id"], []).append(span)
    out: list[dict] = []
    for doc_spans in grouped.values():
        doc_spans.sort(key=lambda s: (s.get("locator") or {}).get("char_start") or 0)
        last: list[str] = []
        for span in doc_spans:
            locator = dict(span.get("locator") or {})
            path = [
                part
                for part in locator.get("section_path") or []
                if not _is_page_furniture(str(part).strip(), bad, bad_norm)
            ]
            if path:
                path = _collapse(path)[-MAX_PATH:]
                last = path
            else:
                path = list(last)
            locator["section_path"] = path
            cleaned = dict(span)
            cleaned["locator"] = locator
            out.append(cleaned)
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


def apply_sections(claims: list[dict], cleaned_spans: list[dict]) -> list[dict]:
    """Copy the cleaned path into the claims, which carry a locator of their own.

    A claim's evidence locator is a copy taken at build time, and a claim whose
    declared section disagrees with the span it resolves to fails verification,
    so the copy has to follow. Schema v2 locators carry a span id only when the
    producer put one there; the (char_start, char_end) range resolves the rest,
    which is the same order the verifier uses.
    """
    by_id = {(span["doc_id"], span["span_id"]): span for span in cleaned_spans}
    by_range = {
        (span["doc_id"], (span.get("locator") or {}).get("char_start"),
         (span.get("locator") or {}).get("char_end")): span
        for span in cleaned_spans
    }
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
            locator["section_path"] = list(
                (span.get("locator") or {}).get("section_path") or []
            )
    return claims
