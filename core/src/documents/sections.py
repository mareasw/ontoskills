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

# A page label in its running-header forms: a bare folio ("L 119/29", "12/144"),
# the Official Journal masthead, and the ELI pointer printed in every footer.
PAGE_LABEL = re.compile(
    r"^(?:[A-Z]{1,3}\s+)?\d+/\d+$|^OJ\s+L,\s*\d+\.\d+\.\d{4}$|^ELI:\s*https?://\S+$"
)

MAX_PATH = 3
# A line short enough that it is a page marker rather than a heading. Length is
# the only safe signal: "Security of processing" is a real module heading that a
# standard-contractual-clauses annex restates on four pages, and repetition
# alone cannot tell it from a masthead.
MAX_MARKER = 12


def _is_masthead(line: str) -> bool:
    """True when a line has one of the shapes a running header takes."""
    return bool(PAGE_LABEL.match(line)) or "official journal" in line.lower()


def furniture(text: str) -> set[str]:
    """Lines that are page furniture rather than document text.

    Furniture is recognised by form, not by frequency: a folio or Official
    Journal line, or a page marker short enough that it cannot be a heading and
    that repeats across pages. A repeated phrase is only evidence of furniture
    in that third case, because documents are allowed to restate a real heading
    on every page of a module.
    """
    seen: dict[str, set[int]] = {}
    marks: set[str] = set()
    for number, page in enumerate(text.split("\f")):
        for raw in page.split("\n"):
            line = raw.strip()
            if not line:
                continue
            if _is_masthead(line):
                marks.add(line)
            if len(line) <= MAX_MARKER:
                seen.setdefault(line, set()).add(number)
    repeated = {line for line, pages in seen.items() if len(pages) >= 2}
    return marks | repeated


def clean_sections(spans: list[dict], text: str) -> list[dict]:
    """Return the spans with their section paths stripped of page furniture.

    A dropped element is not replaced by a guess: the span inherits the last
    real path seen above it in the same document, because a page break does not
    start a new article. A span that has nothing to inherit keeps an empty path
    rather than borrowing a heading the document never set.
    """
    bad = furniture(text)
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
                if not _is_masthead(str(part).strip()) and str(part).strip() not in bad
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
