"""Give a span back to the sentence the segmenter dropped.

The segmenter emits a span per block and leaves out the lines it reads as page
furniture. A heading printed at the top of a page travels with the running
header, and the sentence printed under the heading travels with it: the spans
below still carry the heading (``sections`` hands it down), but the sentence
itself is in no span, so no claim can quote it and the knowledge base is silent
about a rule the page states.

The sentence lost this way is a lead-in — "L'osservanza e l'attuazione delle
policy sono responsabilità di:" — and the list it introduces is in the KB
without it. The repair therefore runs *before* the model call, on the span list:
the heading and its lead-in become one span, in document order, and the prompt
shows it. It is the one repair that has to change the span set, and it changes
the reply cache with it; everything else in the pipeline is untouched.

Nothing is invented. The span is the heading ``sections`` already reads from the
gap plus the sentence printed under it, both verbatim, and it is added only when
that sentence can be found at the offsets the pipeline records.
"""

from __future__ import annotations

from compiler.documents.sections import furniture, gap_heading, starts_sentence
from compiler.documents.text import norm

# A lead-in closes with the colon that announces the list. A whole sentence
# closes with a stop; anything else is a fragment of a wrapped paragraph, which
# belongs to the span above and is not a statement of its own.
TERMINAL = (".", ":", "?", "!")
# Four words is where a sentence stops being a label ("Prima Emissione", "Ed. 01
# Rev. 00") and starts saying something. The ceiling is generous: a lead-in is
# one sentence, and a block longer than this is a paragraph the segmenter would
# not have dropped whole.
MIN_LEAD_IN_WORDS = 4
MAX_LEAD_IN = 400
# The bullet the extractor prints at the start of the list item, and the form
# feed it prints at a page break. Both sit on the line the sentence is read from.
LIST_MARK = "\x0c•·\u2022\u2023\u25cf\u25aa"


def raw_offsets(text: str) -> list[int]:
    """The raw offset of every character of ``norm(text)``.

    ``char_start`` and ``char_end`` are offsets into the whitespace-collapsed
    text, while the shape a heading has — a line of its own — only exists in the
    raw one. This map is what lets a gap found at the pipeline's offsets be read
    as the lines the page prints. It has one entry per character of ``norm(text)``:
    the first character of a whitespace run stands for the run, and leading and
    trailing runs collapse away as they do under ``norm``.
    """
    out: list[int] = []
    in_space = False
    for index, char in enumerate(text):
        if char.isspace():
            if not in_space and out:
                out.append(index)
            in_space = True
            continue
        out.append(index)
        in_space = False
    while out and text[out[-1]].isspace():
        out.pop()
    return out


def recover_lead_ins(spans: list[dict], text: str, meta: dict) -> list[dict]:
    """Return ``spans`` with one span added for each dropped heading and lead-in.

    The block is inserted where it is printed, so the spans below keep their
    order and the heading they already carry. It declares no section path: it
    opens with the heading it is printed under, and ``sections`` reads that
    heading back from the paragraph. Span ids are renumbered in document order,
    because the pipeline and the prompt read them as positions.
    """
    if len(spans) < 2:
        return spans
    ordered = sorted(
        spans, key=lambda span: (span.get("locator") or {}).get("char_start") or 0
    )
    bad = furniture(text)
    bad_norm = {norm(line) for line in bad if len(norm(line)) >= 2}
    flat = norm(text)
    raw = raw_offsets(text)
    out: list[dict] = []
    previous: dict | None = None
    cursor: int | None = None
    for span in ordered:
        locator = span.get("locator") or {}
        start = locator.get("char_start")
        if previous is not None and cursor is not None and start is not None and int(start) > cursor:
            recovered = _dropped_lead_in(text, raw, flat, cursor, int(start), bad, bad_norm)
            if recovered is not None:
                out.append(_recovered_span(recovered, span, meta, text))
        out.append(span)
        end = locator.get("char_end")
        if end is not None:
            cursor = int(end) if cursor is None else max(cursor, int(end))
        previous = span
    if len(out) == len(ordered):
        return spans
    return [
        {**span, "span_id": f"S{index:04d}"} for index, span in enumerate(out, start=1)
    ]


def _dropped_lead_in(
    text: str,
    raw: list[int],
    flat: str,
    cursor: int,
    start: int,
    bad: set[str],
    bad_norm: set[str],
) -> tuple[str, str, int, int] | None:
    """The heading in a gap and the sentence under it, or ``None``.

    Returns the heading, the sentence, the offset of the sentence in ``flat``,
    and the raw offset of the heading. The heading is the one ``sections``
    already reads from a gap; what is added here is the line beneath it, and
    only when that line is a sentence of the document.
    """
    if cursor >= len(raw) or start >= len(raw) or raw[start] <= raw[cursor]:
        return None
    gap = text[raw[cursor]: raw[start]]
    heading = gap_heading(gap, bad, bad_norm)
    if not heading:
        return None
    after = gap.split(heading, 1)[1]
    for line in after.split("\n"):
        sentence = line.strip().strip(LIST_MARK).strip()
        if not _is_lead_in(sentence, bad_norm):
            continue
        paragraph = norm(f"{heading} {sentence}")
        at = flat.find(paragraph, cursor)
        if at < 0:
            # The pipeline's offsets and the raw text disagree by more than the
            # collapsed whitespace: the sentence is not where it says it is, so
            # it is left to the span it already belongs to.
            return None
        return heading, sentence, at, text.find(heading, raw[cursor])
    return None


def _is_lead_in(sentence: str, bad_norm: set[str]) -> bool:
    """True when the line is a sentence, and not a header that looks like one."""
    words = sentence.split()
    if len(words) < MIN_LEAD_IN_WORDS or len(sentence) > MAX_LEAD_IN:
        return False
    if not sentence.endswith(TERMINAL):
        return False
    if not starts_sentence(words[0]):
        return False
    return norm(sentence) not in bad_norm


def _recovered_span(
    recovered: tuple[str, str, int, int],
    following: dict,
    meta: dict,
    text: str,
) -> dict:
    """The span for the recovered block, with the locator of the page it is on."""
    heading, sentence, at, heading_at = recovered
    paragraph = norm(f"{heading} {sentence}")
    # The block declares no path: it opens with the heading it is printed under,
    # and ``sections`` reads that heading back from the paragraph, keeping the
    # band the spans above carry. Declaring a path here would take the band from
    # a running-header fragment the segmenter happened to record.
    path: list[str] = []
    locator = {
        "kind": (following.get("locator") or {}).get("kind") or meta.get("kind"),
        "page": text.count("\f", 0, heading_at) + 1,
        "section_path": path,
        "url": (following.get("locator") or {}).get("url") or meta.get("url"),
        "char_start": at,
        "char_end": at + len(paragraph),
    }
    return {
        "span_id": "",  # renumbered in document order by the caller
        "doc_id": meta["doc_id"],
        "paragraph": paragraph,
        "locator": locator,
    }
