"""Span-first document segmenter.

Adapted from the validated DocBench segmenter (``benchmark/docbench/compile_claims.py``,
ADR 0002 Phase 1). The benchmark keeps its own frozen copy so the accepted
artifacts remain reproducible; this module is the product implementation and is
parity-tested against the benchmark on the same text.

Unlike the benchmark, the document metadata (kind, url, context) is passed in
explicitly, so the segmenter has no per-document table of its own.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from compiler.documents.text import norm

# HTML extractions keep site chrome: cookies, JavaScript notices, navigation and
# print artefacts. They are not part of the document, and a span made of them can
# only produce a junk claim. This is a conservative blocklist of boilerplate
# phrases, not a topic filter.
BOILERPLATE = re.compile(
    r"enable javascript|cookies? to analyze|uses cookies|privacy policy|terms of (use|service)"
    r"|all rights reserved|skip to (main )?content|sign in|log in|subscribe to|newsletter"
    r"|share this|follow us|©|\bcopyright\b|download (the )?(pdf|app)|back to top",
    re.IGNORECASE,
)

HEADING_NUMBERED = re.compile(
    r"^\s*(?:ARTICLE\s+|Article\s+)?(?:\d+(?:\.\d+)*\.?|[IVXLC]+\.|[A-Z]\.)\s+\S"
)
HEADING_SHORT = re.compile(r"^[A-Z][A-Za-z0-9 ,'&()\-/]{2,70}$")
# A numbered line that ends in a conjunction is the tail of a clause, not a
# heading: the sentence continues in the next numbered item (PREFLIGHT §10.7(f)).
CLAUSE_FRAGMENT_END = re.compile(r"\b(?:and|or|but|nor)\s*$", re.IGNORECASE)
# A table block opened by an ALL-CAPS label is closed and reopened past this
# length, so one label can never swallow a whole document.
TABLE_BLOCK_CHARS = 700

# An item-numbered table gives each row a short flat key ("001", "010", "012").
RECORD_KEY_MAX = 8
RECORD_KEY_CHARS = re.compile(r"^[A-Za-z0-9][A-Za-z0-9/\-]*$")
# Record spans stay within one page and one record, and below this length so a
# single record cannot fill a prompt chunk.
RECORD_SPAN_CHARS = 900


# An ALL-CAPS label with a trailing qualifier, e.g. "CRITICAL (Red)". This is
# the shape a flattened HTML table gives to a column/band header, and it is
# what distinguishes it from an ordinary section title such as "PURPOSE".
TABLE_LABEL = re.compile(r"^[A-Z][A-Z0-9 &/\-.,']{1,40}\s*\([^)]{1,40}\)$")


def is_table_label(line: str) -> bool:
    """True for an ALL-CAPS label with a qualifier that heads a table block.

    Severity bands arrive from HTML as ``CRITICAL (Red)`` followed by their
    rows. The label is the only thing that says what the rows mean, so it has
    to travel with them instead of becoming a heading that the next row
    immediately replaces.
    """
    return bool(TABLE_LABEL.match(line.strip()))


def is_clause_fragment(line: str) -> bool:
    """True when a numbered heading-shaped line is the tail of a clause.

    ``15.2.1.5 contact point for more information; and`` is a list item whose
    sentence continues in the next numbered item. It looks exactly like the
    numbered title ``15.2.1 Importer obligations``: a number, then lower-case
    words, no terminal stop. The conjunction at the end is what separates them,
    and it is a property of the line, not of any document's vocabulary
    (PREFLIGHT.md §10.7(f)).
    """
    stripped = line.strip()
    return bool(CLAUSE_FRAGMENT_END.search(stripped)) and bool(
        HEADING_NUMBERED.match(stripped)
    )


def looks_like_heading(line: str) -> bool:
    stripped = line.strip()
    if not stripped or len(stripped) > 90:
        return False
    if stripped.endswith((".", ";", ":", ",")):
        return False
    if is_clause_fragment(stripped):
        return False
    words = stripped.split()
    if len(words) > 7:
        return False
    if is_table_label(stripped):
        return True
    # A parenthetical line is usually a table row ("... (typically 72 hours)"),
    # not a title; keep it in the body so it can carry a claim.
    if stripped.endswith(")") and not HEADING_NUMBERED.match(stripped):
        return False
    if HEADING_NUMBERED.match(stripped):
        return True
    # ALL CAPS or Title Case with no terminal punctuation and few words.
    letters = [c for c in stripped if c.isalpha()]
    if letters and sum(1 for c in letters if c.isupper()) / len(letters) > 0.6:
        return True
    return bool(HEADING_SHORT.match(stripped)) and len(words) <= 8


# A heading is a noun phrase, not a clause: "Exporter is a Controller" is a
# table's value cell. Treating it as a heading hides the value from every span
# and hands it to the next block as a section name. Question headings ("What
# happens if there is ...") are real headings and stay.
ASSERTION_LINE = re.compile(
    r"^[A-Z][A-Za-z0-9 ,'&()\-/]{0,70}\s(?:is|are|was|were)\s+"
    r"(?:a|an|the|not|no|bound|subject)\b"
)
INTERROGATIVE_HEADING = re.compile(
    r"^(?:What|Whether|How|When|Where|Which|Who|Why|Can|Could|Is|Are|Does|Do|Will|Would|Should|May|Must)\b"
)
# A heading that breaks after one of these words is continued by the next line
# ("Exporter (who sends the" / "Restricted Transfer)"), not ended by it.
HEADING_CONTINUATION_WORDS = frozenset(
    "a an and any as at by for from if in into of on or over the to under with".split()
)


def is_clause_heading(line: str) -> bool:
    """True when a heading-shaped line is actually a full assertion."""
    stripped = line.strip()
    if INTERROGATIVE_HEADING.match(stripped):
        return False
    return bool(ASSERTION_LINE.match(stripped))


def continues_heading(line: str, previous: str) -> bool:
    """True when ``line`` is the wrapped remainder of the heading ``previous``."""
    stripped = line.strip()
    if not stripped:
        return False
    if stripped[0].islower() or stripped[0] in ")]}":
        return True
    if previous.strip().count("(") > previous.strip().count(")"):
        return True
    words = previous.strip().split()
    return bool(words) and words[-1].lower().strip(".,;:") in HEADING_CONTINUATION_WORDS


def starts_a_value(previous: str, line: str) -> bool:
    """True when ``line`` opens a table value, not a heading (PREFLIGHT §10.7(e)(i)).

    Two text properties decide it. A key that ends with ``:`` owns the next
    line, and a clause is not a heading. Both are properties of the line pair,
    not of any document's vocabulary. A numbered heading and a band label are
    headings even when the line above ends with a colon.
    """
    if HEADING_NUMBERED.match(line.strip()) or is_table_label(line):
        return False
    if previous.rstrip().endswith(":"):
        return True
    return is_clause_heading(line)


def is_pending_key(block: str) -> bool:
    """True when a short block is a table key that owns the next block.

    A key is a label, not content: "UK country's law that governs the IDTA:" and
    "Full legal name:" name the cell that follows. Keeping the key for the next
    block lets label and value be quoted together, which is the evidence a
    key/value row needs (PREFLIGHT.md §10.7(e)(i)). Long paragraphs and
    sentence-shaped blocks are never keys.
    """
    stripped = block.strip()
    if not stripped.endswith(":") or len(stripped) > 120:
        return False
    return "." not in stripped and ";" not in stripped


# A label colon is followed by its value: a colon inside a time ("10:00") or a
# ratio is not a cell boundary (PREFLIGHT.md §10.7(f)).
ROW_COLON = re.compile(r":(?=\s|$)")
# A value that is only a section number points at another clause; it states
# nothing a row claim can assert.
BARE_SECTION_NUMBER = re.compile(r"^\d+(?:\.\d+)*\.?$")


def split_key_value(block: str) -> tuple[str, str, int] | None:
    """Split a block at its last label colon: ``(label, value, offset)``.

    ``offset`` is where the label starts, which is how a caller tells a cell
    that opens with its own label (offset 0) from one whose label is glued to
    the text before it. A label is a capitalised noun phrase without a sentence
    stop; a value is whatever follows the colon (PREFLIGHT.md §10.7(f)).
    """
    best: tuple[str, str, int] | None = None
    for match in ROW_COLON.finditer(block):
        end = match.start()
        start = 0
        for marker in (". ", "; ", "! ", "? "):
            found = block.rfind(marker, 0, end)
            if found != -1:
                start = max(start, found + 2)
        previous = block.rfind(": ", 0, end)
        if previous != -1:
            start = max(start, previous + 2)
        label = block[start:end].strip()
        if not label or len(label) > 120:
            continue
        if not label[0].isupper() and not label[0].isdigit():
            continue
        if "." in label or ";" in label:
            continue
        best = (label, block[end + 1 :].strip(), start)
    return best


def clean_row(block: str) -> tuple[str, str] | None:
    """The ``(label, value)`` of a cell that is one label and one value.

    A block with two labels is a chain of cells the extractor fused — an empty
    cell followed by a filled one, or several cells of a row. Its label is
    ambiguous, and guessing one is how a claim ends up asserting the wrong
    thing, so only a clean single cell is promoted (PREFLIGHT.md §10.7(f)).

    The remaining guards are properties of the text, not of a document: a label
    that ends on a conjunction is the tail of a clause, a label that names a
    table is a caption reference, and a value that is only a section number
    points at another clause instead of stating anything.
    """
    if block.count(":") != 1:
        return None
    split = split_key_value(block)
    if split is None or split[2] != 0:
        return None
    label, value, _ = split
    if not value:
        return None
    if CLAUSE_FRAGMENT_END.search(label):
        return None
    if re.search(r"\bTable\s+\d+", label):
        return None
    if INTERROGATIVE_HEADING.match(value):
        # A question after a label is the next row's label, not this row's
        # value ("In relation to ...: Whether UK GDPR applies to the Importer").
        return None
    if BARE_SECTION_NUMBER.match(value):
        return None
    return label, value


def split_sentences(text: str, limit: int = 700) -> list[str]:
    """Split a block into sentence windows of at most roughly ``limit`` chars."""
    parts = re.split(r"(?<=[.;:])\s+", text)
    out: list[str] = []
    current = ""
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if current and len(current) + 1 + len(part) > limit:
            out.append(current)
            current = part
        else:
            current = f"{current} {part}".strip()
    if current:
        out.append(current)
    return out


def _key_like_line(line: str) -> bool:
    """True for a line that can be a table key: a heading or a "Label:" cell."""
    stripped = line.strip()
    if not stripped:
        return False
    if looks_like_heading(stripped):
        return True
    return is_pending_key(stripped)


def _continues_line(line: str, previous: str) -> bool:
    """True when a line is the wrapped remainder of the line above it."""
    stripped = line.strip()
    if not stripped:
        return False
    if stripped[0].islower() or stripped[0] in ")]}(":
        return True
    if previous.count("(") > previous.count(")"):
        return True
    words = previous.split()
    return bool(words) and words[-1].lower().strip(".,;:") in HEADING_CONTINUATION_WORDS


def _wrapped_label(lines: list[str]) -> bool:
    """True for a multi-line cell that is one label: "Adequate" / "Country"."""
    if len(lines) < 2 or not _key_like_line(lines[0]):
        return False
    for previous, line in zip(lines, lines[1:]):
        if _key_like_line(line) or _continues_line(line, previous):
            continue
        return False
    return True


def _line_units(lines: list[str]) -> list[list[tuple[int, str]]]:
    """Group raw lines into units separated by blank lines or page breaks."""
    units: list[list[tuple[int, str]]] = []
    current: list[tuple[int, str]] = []
    for index, raw in enumerate(lines):
        if "\f" in raw or not raw.strip():
            if current:
                units.append(current)
                current = []
            continue
        current.append((index, raw.strip()))
    if current:
        units.append(current)
    return units


def kv_region_lines(lines: list[str]) -> list[bool]:
    """Mark raw lines that belong to a key/value table (PREFLIGHT §10.7(e)(i)).

    Three text properties open a region, and none of them names a document or a
    term:

    * a "Table N:" caption — an explicit table marker;
    * a dense run of "Label:" cells — the shape of a key/value table;
    * a header pair repeated on several pages — the shape of a long table.

    Inside the region the segmenter keeps a label and its value together and
    never promotes a value to a section. Outside it, segmentation is unchanged.
    """
    units = _line_units(lines)
    if not units:
        return [False] * len(lines)
    texts = [norm(" ".join(text for _, text in unit)) for unit in units]
    marked = [False] * len(units)

    # 1. A captioned table runs to the next caption, a new Part/Section, or a
    # real prose paragraph.
    captions = [
        index
        for index, text in enumerate(texts)
        if re.search(r"\bTable\s+\d+[A-Za-z]?\s*[:.]", text)
    ]
    for position, start in enumerate(captions):
        stop = (
            captions[position + 1] - 1
            if position + 1 < len(captions)
            else len(units) - 1
        )
        for index in range(start + 1, stop + 1):
            text = texts[index]
            if re.match(r"^(?:Part\s+\d+|Section\s+\d+)\b", text):
                stop = index - 1
                break
            if len(text) > 400 and not text.endswith(":"):
                stop = index - 1
                break
        for index in range(start, stop + 1):
            marked[index] = True

    # 2. A dense run of "Label:" cells.
    colon = [is_pending_key(text) for text in texts]
    window, need = 12, 3
    for start in range(len(units)):
        if sum(colon[start : start + window]) >= need:
            for index in range(start, min(start + window, len(units))):
                marked[index] = True

    # 3. A header pair that repeats like a table header does on every page.
    pairs = Counter(
        (texts[index], texts[index + 1]) for index in range(len(texts) - 1)
    )
    repeated = [
        index
        for index in range(len(texts) - 1)
        if pairs[(texts[index], texts[index + 1])] >= 3
    ]
    if repeated:
        start = repeated[0]
        stop = len(units) - 1
        for index in range(repeated[-1] + 2, len(units)):
            text = texts[index]
            if re.match(r"^(?:Part\s+\d+|Section\s+\d+)\b", text):
                stop = index - 1
                break
            if len(text) > 400 and not text.endswith(":"):
                stop = index - 1
                break
        for index in range(start, stop + 1):
            marked[index] = True

    flags = [False] * len(lines)
    start_unit: int | None = None
    for index in range(len(units) + 1):
        here = index < len(units) and marked[index]
        if here and start_unit is None:
            start_unit = index
        elif not here and start_unit is not None:
            first_line = units[start_unit][0][0]
            last_line = units[index - 1][-1][0]
            for line_index in range(first_line, last_line + 1):
                flags[line_index] = True
            start_unit = None
    return flags


def _segment_blocks(
    text: str, doc: dict[str, Any], min_chars: int = 60, locate: bool = True
) -> list[dict]:
    """Segment prose documents by block and heading (the original path).

    Short blocks are merged with their neighbours instead of dropped: tabular
    runbooks state their rules in lines like "Response time: 1 hour", and
    discarding those would remove the very content the benchmark is about.

    A key/value table takes a separate branch (PREFLIGHT.md §10.7(e)(i)). Inside
    one, a label that wraps over two lines is a single heading, a label and the
    value cell that follows it are one row, and a cell value never becomes the
    section of unrelated text. Outside one the original rules run unchanged, so
    documents without such a region are segmented exactly as before.
    """
    raw_lines = text.split("\n")
    doc_id = doc["doc_id"]
    in_kv = kv_region_lines(raw_lines)
    spans: list[dict] = []
    page = 1
    section_stack: list[tuple[int, str]] = []
    pending: list[str] = []
    short_buffer: list[str] = []
    # Lines of the table block opened by an ALL-CAPS label, or None.
    table_block: list[str] | None = None
    # Heading group for the key/value branch: a label may wrap over two lines
    # ("Adequate" / "Country"), and that is one section label.
    heading_group: list[str] = []
    block_mode = ""  # "" at a block start, then "heading" or "body"
    previous_line = ""
    # A short key block that owns the next block ("Full legal name:"), kept so
    # label and value are one span (PREFLIGHT.md §10.7(e)(i)).
    pending_key = ""
    kv_active = False

    def emit(piece: str, row: tuple[str, str] | None = None) -> None:
        # A span must carry words: table rules, arrows and page numbers are not
        # claims, and a span with no letters only wastes prompt space.
        if not re.search(r"[A-Za-z]{3,}", piece):
            return
        if BOILERPLATE.search(piece):
            return
        span = {
            "span_id": f"S{len(spans) + 1:04d}",
            "doc_id": doc_id,
            "paragraph": piece,
            "locator": {
                "kind": doc["kind"],
                "page": page,
                "section_path": [title for _, title in section_stack][-3:],
                "url": doc["url"],
            },
        }
        if row is not None:
            # The cell's label and value travel with the span: the evidence of a
            # table row is label + value, and the emitter must not have to parse
            # it back out of the text (PREFLIGHT.md §10.7(f)).
            span["row"] = {"label": row[0], "value": row[1]}
        spans.append(span)

    def flush_short() -> None:
        nonlocal short_buffer
        if short_buffer:
            merged = norm(" ".join(short_buffer))
            short_buffer = []
            if kv_active:
                # A table cell is a value even when it is short: "England and
                # Wales" must survive, a printed page number must not.
                if re.search(r"[A-Za-z]{3,}", merged):
                    emit(merged)
            elif len(merged) >= 20:
                emit(merged)

    def flush() -> None:
        nonlocal pending, short_buffer, pending_key
        if not pending:
            return
        block = norm(" ".join(pending))
        pending = []
        row: tuple[str, str] | None = None
        if kv_active and is_pending_key(block):
            # A label that is followed by another label owns an empty cell: the
            # first label is dropped, never glued to the second (PREFLIGHT
            # §10.7(f)). "Full legal name:" with no value is a fact about the
            # form, not the start of the next row. Dropping it opens a gap in
            # the source, so text buffered before it is closed here: a span may
            # never elide a dropped label or the quote stops being verbatim.
            if pending_key:
                flush_short()
            pending_key = block
            return
        if kv_active:
            split = split_key_value(block)
            if (
                split is not None
                and not split[1]
                and block.count(":") >= 2
                and "." not in block
                and ";" not in block
            ):
                # A run of labels with no value at all is an empty cell: it
                # asserts nothing, so it is not a span (PREFLIGHT §10.7(f)).
                # Two or more label colons is what makes it a chain; a sentence
                # that merely ends with a colon keeps its text. The dropped
                # block is a gap, so the buffer before it is closed first.
                flush_short()
                pending_key = ""
                return
        if kv_active and pending_key:
            split = split_key_value(block)
            if split is None or split[2] != 0:
                # A key and its value are one row: quote the pair, not the value
                # alone, so the span says what the value is evidence for. Key
                # and value are adjacent in the source, so the join is verbatim.
                block = norm(f"{pending_key} {block}")
                row = clean_row(block)
            else:
                # The block opens with its own label, so the pending key owned
                # an empty cell: it is dropped, and the gap it leaves closes the
                # buffer above it.
                flush_short()
            pending_key = ""
        if kv_active and row is None:
            row = clean_row(block)
        if len(block) < min_chars:
            short_buffer.append(block)
            if len(" ".join(short_buffer)) >= min_chars:
                flush_short()
            return
        flush_short()
        pieces = split_sentences(block)
        for piece in pieces:
            if len(piece) >= min_chars:
                emit(piece, row if len(pieces) == 1 else None)

    def push_heading_group() -> None:
        """Close a key/value heading group: it is one section label."""
        nonlocal heading_group, pending_key
        if not heading_group:
            return
        # Short content buffered above belongs to the previous section.
        flush_short()
        joined = norm(" ".join(heading_group))[:90]
        first = heading_group[0].strip()
        # Keep a shallow stack: a numbered heading pops to its own depth.
        match = re.match(
            r"^\s*(?:ARTICLE\s+|Article\s+)?((?:\d+|[IVXLC]+|[A-Z]))(?:\.\d+)*\.?\s",
            first,
        )
        depth = 1
        if match:
            raw = first.split()[0].rstrip(".")
            depth = raw.count(".") + 1
        while section_stack and section_stack[-1][0] >= depth:
            section_stack.pop()
        section_stack.append((depth, joined))
        heading_group = []
        pending_key = ""

    def flush_table(reopen: bool = False) -> None:
        """Emit the open table block: the label plus the rows it governs.

        The rows of a flattened HTML table are meaningless on their own —
        "Response time : 1 hour" says nothing about which band it belongs to.
        The label is the row's meaning, so it stays in the same span.
        """
        nonlocal table_block
        if not table_block:
            table_block = None
            return
        block = norm(" ".join(table_block))
        label = table_block[0]
        table_block = [label] if reopen else None
        emit(block)

    # splitlines() also splits on form feed, which is how pages are encoded
    # here, so split on newlines only and handle \f explicitly.
    for line_index, raw_line in enumerate(raw_lines):
        entering = in_kv[line_index] and not kv_active
        leaving = kv_active and not in_kv[line_index]
        if entering:
            # Close the prose block before switching rules.
            flush()
            flush_short()
            flush_table()
            heading_group = []
            block_mode = ""
            previous_line = ""
            pending_key = ""
            kv_active = True
        elif leaving:
            if heading_group:
                push_heading_group()
            flush()
            flush_short()
            flush_table()
            heading_group = []
            block_mode = ""
            previous_line = ""
            pending_key = ""
            kv_active = False

        if "\f" in raw_line:
            flush()
            flush_short()
            if kv_active:
                push_heading_group()
            flush_table()
            page += raw_line.count("\f")
            block_mode = ""
            previous_line = ""
            # A key owns a value on its own page: the span's declared page has
            # to contain the whole quote, so never merge across a page break.
            if kv_active:
                pending_key = ""
            continue
        stripped = raw_line.strip()
        if not stripped:
            # A blank line separates rows in flattened HTML, not blocks: do not
            # close the table here.
            flush()
            block_mode = ""
            continue
        # Inside an open table block every short line is a row — including the
        # ones that look like headings, because a flattened HTML table ships its
        # cells as separate <div>s. The block is closed by its next label or by
        # a "key : value" terminator row, never by the shape of a cell.
        in_block = table_block is not None and not is_table_label(stripped)
        if in_block:
            table_block.append(stripped)
            if re.search(r"\s:\s", stripped):
                flush_table()
            elif len(norm(" ".join(table_block))) > TABLE_BLOCK_CHARS:
                # Never let a label swallow a whole document: close the block
                # and reopen it with the label repeated.
                flush_table(reopen=True)
            previous_line = stripped
            continue

        if not kv_active:
            # Original block path, unchanged outside key/value regions.
            if looks_like_heading(stripped):
                flush()
                flush_short()
                flush_table()
                # Keep a shallow stack: a numbered heading pops to its own depth.
                match = re.match(
                    r"^\s*(?:ARTICLE\s+|Article\s+)?((?:\d+|[IVXLC]+|[A-Z]))(?:\.\d+)*\.?\s",
                    stripped,
                )
                depth = 1
                if match:
                    raw = stripped.split()[0].rstrip(".")
                    depth = raw.count(".") + 1
                while section_stack and section_stack[-1][0] >= depth:
                    section_stack.pop()
                section_stack.append((depth, stripped[:90]))
                if is_table_label(stripped):
                    table_block = [stripped]
                continue
            pending.append(stripped)
            continue

        # Key/value table region.
        if is_table_label(stripped):
            # An ALL-CAPS band header still owns its rows.
            flush()
            flush_short()
            push_heading_group()
            flush_table()
            heading_group.append(stripped)
            push_heading_group()
            table_block = [stripped]
            block_mode = ""
            previous_line = stripped
            continue
        heading_like = looks_like_heading(stripped) and not starts_a_value(
            previous_line, stripped
        )
        if block_mode == "":
            if heading_like:
                if heading_group:
                    # A second heading block before any body: it is a value or
                    # the next column of the label above, not a replacement.
                    push_heading_group()
                    block_mode = "body"
                    pending.append(stripped)
                else:
                    heading_group.append(stripped)
                    block_mode = "heading"
            else:
                push_heading_group()
                block_mode = "body"
                pending.append(stripped)
        elif block_mode == "heading":
            if heading_like or continues_heading(stripped, heading_group[-1]):
                heading_group.append(stripped)
            else:
                push_heading_group()
                block_mode = "body"
                pending.append(stripped)
        else:
            pending.append(stripped)
        previous_line = stripped
    if kv_active and heading_group:
        push_heading_group()
    flush()
    flush_short()
    flush_table()

    # Char offsets index the whitespace-normalised source (the same string the
    # verbatim check uses). They are a convenience, not the identity of a span;
    # page + section path + url are the stable part.
    if locate:
        _locate(spans, text)
    return spans


def _locate(spans: list[dict], text: str) -> None:
    flat = norm(text)
    cursor = 0
    for span in spans:
        found = flat.find(span["paragraph"], cursor)
        if found == -1:
            found = flat.find(span["paragraph"])
        if found != -1:
            span["locator"]["char_start"] = found
            span["locator"]["char_end"] = found + len(span["paragraph"])
            cursor = found + len(span["paragraph"])


def _line_pages(raw: list[str]) -> list[int]:
    """Page number (1-based) at the start of each raw line."""
    pages: list[int] = []
    page = 1
    for line in raw:
        pages.append(page)
        if "\f" in line:
            page += line.count("\f")
    return pages


def _next_text_index(raw: list[str], start: int) -> int | None:
    for j in range(start + 1, len(raw)):
        if "\f" in raw[j]:
            continue
        if raw[j].strip():
            return j
    return None


def record_key_lines(text: str) -> list[int]:
    """Raw-line indices that look like the item keys of an item-numbered table.

    A table of records (a records schedule, a catalogue, a runbook) gives each
    row a short flat key — ``001``, ``010``, ``012`` — on its own line. Section
    numbering looks identical but is a hierarchy (``1``, ``1.1``, ``1.2.1``),
    and printed page numbers are standalone numbers too. The rules that tell
    them apart are in PREFLIGHT.md §10.7(b)(i); all are properties of the text,
    not of any score.
    """
    raw = text.split("\n")
    pages = _line_pages(raw)
    candidates: list[tuple[int, str]] = []
    for i, line in enumerate(raw):
        stripped = line.strip()
        if not stripped or "\f" in line:
            continue
        if len(stripped) > RECORD_KEY_MAX or not re.search(r"\d", stripped):
            continue
        if not RECORD_KEY_CHARS.match(stripped):
            continue
        after = _next_text_index(raw, i)
        if after is None:
            continue
        # A printed page number is the last text on its page.
        if pages[after] > pages[i]:
            continue
        candidates.append((i, stripped))
    # A token repeated in the document is page furniture, not a key.
    counts: dict[str, int] = {}
    for _, key in candidates:
        counts[key] = counts.get(key, 0) + 1
    candidates = [(i, key) for i, key in candidates if counts[key] == 1]
    keys = [key.rstrip(".") for _, key in candidates]
    if len(keys) < 3:
        return []
    # An item column has one fixed width and is zero-padded ("001", "010").
    # A numbered list is all one-digit ("1", "2", …), and a consecutive run of
    # integers is list numbering however wide it is; neither is a record table.
    if not all(key.isdigit() for key in keys):
        return []
    widths = {len(key) for key in keys}
    if len(widths) != 1 or next(iter(widths)) < 2:
        return []
    values = sorted(int(key) for key in keys)
    if values == list(range(values[0], values[0] + len(values))):
        return []
    # Reject a dotted hierarchy: "1" is a component-prefix of "1.1".
    components = [tuple(key.split(".")) for key in keys]
    for a in components:
        for b in components:
            if a != b and len(a) < len(b) and b[: len(a)] == a:
                return []
    return [i for i, _ in candidates]


def _section_path(text: str, furniture: set[str]) -> list[str]:
    """The heading stack at the end of ``text``, minus repeated page furniture."""
    stack: list[tuple[int, str]] = []
    for line in text.split("\n"):
        if "\f" in line:
            continue
        stripped = line.strip()
        if not stripped or not looks_like_heading(stripped):
            continue
        match = re.match(
            r"^\s*(?:ARTICLE\s+|Article\s+)?((?:\d+|[IVXLC]+|[A-Z]))(?:\.\d+)*\.?\s",
            stripped,
        )
        depth = 1
        if match:
            raw_token = stripped.split()[0].rstrip(".")
            depth = raw_token.count(".") + 1
        while stack and stack[-1][0] >= depth:
            stack.pop()
        stack.append((depth, stripped[:90]))
    return [title for _, title in stack if title not in furniture][-3:]


def _record_spans(text: str, doc: dict[str, Any], key_lines: list[int]) -> list[dict]:
    """Segment an item-numbered table by record, not by line shape.

    The PDF reads column-major, so a row arrives as the item key, then its
    description, then the disposition cell, then the authority. Treating the
    first line of the disposition cell ("Destroy 2 years") as a heading drops
    the operative instruction from every span, and leaving the authority line on
    the heading stack attaches row N's authority to row N+1's records. A record
    runs from its key to the line before the next key; no line inside it is a
    heading, and no span crosses a record boundary.
    """
    raw = text.split("\n")
    pages = _line_pages(raw)
    first = key_lines[0]
    key_set = set(key_lines)

    seen: dict[str, set[int]] = {}
    for i, line in enumerate(raw):
        stripped = line.strip()
        if not stripped or "\f" in line:
            continue
        seen.setdefault(stripped, set()).add(pages[i])
    furniture = {s for s, ps in seen.items() if len(ps) >= 2 and len(s) <= 80}

    preamble = "\n".join(raw[:first])
    base = _section_path(preamble, furniture)
    spans = _segment_blocks(preamble, doc, locate=False)

    records: list[dict] = []
    current: dict | None = None
    for i in range(first, len(raw)):
        if i in key_set:
            if current is not None:
                records.append(current)
            current = {"key": raw[i].strip(), "parts": []}
            continue
        if current is None:
            continue
        for offset, chunk in enumerate(raw[i].split("\f")):
            stripped = chunk.strip()
            if stripped:
                current["parts"].append((pages[i] + offset, stripped))
    if current is not None:
        records.append(current)

    for record in records:
        groups: list[list] = []
        for page, line in record["parts"]:
            if not groups or groups[-1][0] != page:
                groups.append([page, []])
            groups[-1][1].append(line)
        first_span = True
        for page, lines in groups:
            body = norm(" ".join(lines))
            piece = norm(f"{record['key']} {body}") if first_span else body
            first_span = False
            # Windows stay inside one page, so a span's declared page always
            # contains its text. A span never crosses a record boundary.
            for window in split_sentences(piece, limit=RECORD_SPAN_CHARS):
                _append_span(
                    spans, doc, window, page, base + [record["key"]]
                )

    _locate(spans, text)
    return spans


def _append_span(
    spans: list[dict], doc: dict[str, Any], piece: str, page: int, section_path: list[str]
) -> None:
    if not re.search(r"[A-Za-z]{3,}", piece):
        return
    if BOILERPLATE.search(piece):
        return
    spans.append(
        {
            "span_id": f"S{len(spans) + 1:04d}",
            "doc_id": doc["doc_id"],
            "paragraph": piece,
            "locator": {
                "kind": doc["kind"],
                "page": page,
                "section_path": section_path[-3:],
                "url": doc["url"],
            },
        }
    )


def segment(text: str, doc: dict[str, Any], min_chars: int = 60) -> list[dict]:
    """Turn a document into spans with ids and locators. No model involved.

    Documents whose operative content is an item-numbered table take the
    record-scoped path; everything else keeps the block/heading path unchanged.
    """
    key_lines = record_key_lines(text)
    if key_lines:
        return _record_spans(text, doc, key_lines)
    return _segment_blocks(text, doc, min_chars)


def chunk(spans: list[dict], size: int, overlap: int = 1) -> list[list[dict]]:
    if size <= 0:
        return [spans]
    out = []
    step = max(1, size - overlap)
    for start in range(0, len(spans), step):
        block = spans[start : start + size]
        if block:
            out.append(block)
        if start + size >= len(spans):
            break
    return out


# A span that opens with a list marker — "(k) the mechanisms …", "iv. the
# authority" — is an item of an enumeration whose lead-in lives above it.
LIST_MARKER = re.compile(r"^[\(\[]?(?:[A-Za-z]|[ivxlcIVXLC]{1,5}|\d{1,3})[\)\].]\s+")
# A demonstrative opener points back at what the previous span said, so the
# sentence has no subject of its own ("Such measures may include …").
ANAPHORA = re.compile(r"^(?:Such|This|These|Those|That|It|They|Its|Their)\b")

# A numbered paragraph is prose that happens to open with a number: "1. Any
# distributor …", "(164) The AI Office …". An enumeration item is marked with a
# letter or a roman numeral in these documents; a number is a clause or recital
# number. When a document does number its items, the terminal colon says a list
# follows, and a full-length sentence says a paragraph does.
NUMBERED_PARAGRAPH = re.compile(r"^(?:\(\d{1,3}\)|\d{1,3}[.)])\s+")
PARAGRAPH_CHARS = 100


def _opens_a_paragraph(text: str) -> bool:
    """True when a numeric marker introduces prose, not an item of an enumeration."""
    return bool(NUMBERED_PARAGRAPH.match(text)) and (
        text.rstrip().endswith(":") or len(text) > PARAGRAPH_CHARS
    )


def _same_section(left: dict, right: dict) -> bool:
    """True when both locators carry the same section path."""
    here = (left.get("locator") or {}).get("section_path") or []
    there = (right.get("locator") or {}).get("section_path") or []
    return here == there


def _page_furniture(order: list[dict]) -> set[str]:
    """Text repeated across pages: a running header or footer, not the document.

    A PDF breaks a sentence and even a list at the page edge, so its furniture
    lands between two spans of the same enumeration. The walk must pass over it,
    otherwise a list item borrows the journal's masthead as its subject.
    """
    pages: dict[str, set] = {}
    for span in order:
        text = span.get("paragraph") or ""
        if len(text) > 80:
            continue
        page = (span.get("locator") or {}).get("page")
        pages.setdefault(text, set()).add(page)
    return {text for text, seen in pages.items() if len(seen) >= 2}


def _opener(order: list[dict], index: int, furniture: set[str]) -> dict | None:
    """The span that opens the list this one belongs to, if any.

    Walking back matters: the span before "(k)" is usually "(j)", so taking the
    immediate predecessor attaches a sibling item as context and the subject the
    statement names stays unattested. The opener is the first span before the
    run that is neither a list item nor page furniture. The walk is capped so a
    malformed enumeration cannot attach a heading from pages above as the
    subject.
    """
    span = order[index]
    text = (span.get("paragraph") or "").lstrip()
    previous = order[index - 1]
    previous_text = (previous.get("paragraph") or "").lstrip()
    current_is_item = bool(LIST_MARKER.match(text)) and not _opens_a_paragraph(text)
    needs = bool(text[:1].islower() or ANAPHORA.match(text) or current_is_item)
    if not needs and not LIST_MARKER.match(previous_text):
        return None
    seen_item = False
    for cursor in range(index - 1, max(-1, index - 21), -1):
        candidate = order[cursor]
        candidate_text = (candidate.get("paragraph") or "").lstrip()
        if candidate_text in furniture:
            continue
        if LIST_MARKER.match(candidate_text) and not _opens_a_paragraph(candidate_text):
            seen_item = True
            continue
        if candidate_text[:1].islower():
            # A lowercase span is the tail of the sentence or of the item above
            # it. It is the antecedent of a continuation, but never the opener
            # of a list: past the first item, a lowercase span is a sibling's
            # tail, which says nothing about the current item's subject. The
            # exception is the line that ends in a colon: whatever its first
            # character, it is the lead-in that introduces the enumeration.
            if candidate_text.rstrip().endswith(":"):
                return candidate
            if not current_is_item and not seen_item:
                return candidate
            continue
        # The first span outside the run: a prose sentence, or the line that
        # ends in the colon introducing the list.
        return candidate
    return None


def lead_ins(spans: list[dict]) -> dict[str, dict]:
    """Map a span id to the span that carries its subject, when it needs one.

    Deliberately narrow: only a list item, a lowercase continuation or a
    demonstrative opener, and only a span in the same section. A list item takes
    the opener of its list, not the sibling item printed before it: "(j)" shares
    the enumeration with "(k)" but not its subject, so quoting it answers
    nothing. A wrong context quote is worse than a missing one, because the
    verifier trusts every evidence quote it is given.

    The context is always exactly one span: that is the whole guarantee. No
    length cap applies, because the segmenter already caps a span at what a
    sentence can be, and a cap here only rejected real openers.
    """
    grouped: dict[str, list[dict]] = {}
    for span in spans:
        grouped.setdefault(span["doc_id"], []).append(span)
    out: dict[str, dict] = {}
    for doc_spans in grouped.values():
        doc_spans.sort(key=lambda s: (s.get("locator") or {}).get("char_start") or 0)
        furniture = _page_furniture(doc_spans)
        for index in range(1, len(doc_spans)):
            span = doc_spans[index]
            candidate = _opener(doc_spans, index, furniture)
            if candidate is not None and _same_section(span, candidate):
                out[span["span_id"]] = candidate
    return out

