#!/usr/bin/env python3
"""Compile a source document into claims with evidence (v0, span-first).

The pipeline is the one in ``docs/adr/0001-document-first-kernel.md``:

    source -> segmenter -> extractor -> validator -> emitter

What makes this version falsifiable rather than hopeful:

* **Span-first.** The segmenter assigns every span an id and a locator *before*
  the model runs. The extractor may only reference existing span ids; it never
  writes the quote. The emitted quote is copied from the segmenter, so it is
  verbatim by construction, and the locator (page, section path, char offsets,
  url) comes from the span, not from the model.
* **Schema-constrained.** The model answers with a JSON array of
  ``{span_ids, statement, modality, ...}``; anything else is rejected.
* **Deduplicated.** Consecutive chunks of a long document overlap, so the same
  claim can be extracted twice. Statements are normalised and deduplicated.

Usage:
    # 1. See what would be sent, and the token estimate (no API calls)
    python benchmark/docbench/compile_claims.py --dry-run

    # 2. Compile (this costs API calls; see --estimate first)
    python benchmark/docbench/compile_claims.py --out gold/claims.compiled.jsonl

    # 3. Validate the result against the sources
    python benchmark/docbench/check_claims.py gold/claims.compiled.jsonl

    # 4. Use it as the B2 context
    python benchmark/docbench/run_baselines.py --conditions B2 --claims gold/claims.compiled.jsonl

The extractor only sees a span list, so the cost is bounded by the source size
once, not once per question.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from claims_model import to_v2  # noqa: E402
from env import load_dotenv  # noqa: E402

PRIVATE = ROOT / "private"
GOLD = ROOT / "gold"

# Document metadata. This is context about the document, not a claim about it:
# it comes from the source page itself and is already recorded in sources.md.
DOCS = {
    "D1": {
        "file": "D1.txt",
        "kind": "html",
        "url": "https://artificialintelligenceact.eu/implementing-regulation-evaluations/",
        "context": {
            "source": "Commission Implementing Regulation (EU) 2026/1755",
            "version": "2026-07-20",
            "jurisdiction": "EU",
            "doc_type": "regulation",
            "valid_from": "2026-08-10",
        },
    },
    "D2": {
        "file": "D2.txt",
        "kind": "pdf",
        "url": "https://www.luc.edu/media/lucedu/ai/pdfs/AI-Policy-Guidance.pdf",
        "context": {
            "source": "Loyola University Chicago AI Policy & Guidance",
            "version": "2025",
            "jurisdiction": "US-IL",
            "doc_type": "policy",
        },
    },
    "D3": {
        "file": "D3.txt",
        "kind": "html",
        "url": "https://owasp.org/www-project-ai-security-and-privacy-guide/",
        "context": {
            "source": "OWASP AI Security and Privacy Guide — Incident Response Playbook",
            "version": "2025",
            "jurisdiction": "global",
            "doc_type": "playbook",
        },
    },
    "D4": {
        "file": "D4.txt",
        "kind": "pdf",
        "url": "https://greenecountyva.gov/DocumentCenter/View/1577",
        "context": {
            "source": "Greene County RFP 2026-001",
            "version": "2026-01",
            "jurisdiction": "US-VA-Greene",
            "doc_type": "rfp",
            "valid_from": "2026-01-01",
        },
    },
    # Generalisation probe (PREFLIGHT.md §10): a contract and a table-as-content
    # schedule. Same schema, same prompt, no per-document handling.
    "D5": {
        "file": "D5.txt",
        "kind": "pdf",
        "url": "https://www.bristol.ac.uk/media-library/sites/alspac/documents/researchers/data-access/ALSPAC_IDTA_template_SAMPLE.pdf",
        "context": {
            "source": "ALSPAC International Data Transfer Agreement (ICO IDTA A1.0)",
            "version": "v1, 24 March 2024",
            "jurisdiction": "UK",
            "doc_type": "contract",
        },
    },
    "D6": {
        "file": "D6.txt",
        "kind": "pdf",
        "url": "https://www.archives.gov/files/records-mgmt/grs/grs01-1.pdf",
        "context": {
            "source": "NARA General Records Schedule 1.1 — Financial Management and Reporting Records",
            "version": "Transmittal 31, April 2020",
            "jurisdiction": "US-federal",
            "doc_type": "records_schedule",
        },
    },
}

# HTML extractions keep the site chrome: cookies, JavaScript notices, navigation
# and print artefacts. They are not part of the document, and a span made of
# them can only produce a junk claim. This is a conservative blocklist of
# boilerplate phrases, not a topic filter.
BOILERPLATE = re.compile(
    r"enable javascript|cookies? to analyze|uses cookies|privacy policy|terms of (use|service)"
    r"|all rights reserved|skip to (main )?content|sign in|log in|subscribe to|newsletter"
    r"|share this|follow us|©|\bcopyright\b|download (the )?(pdf|app)|back to top",
    re.IGNORECASE,
)

MODALITIES = (
    "obligation",
    "permission",
    "prohibition",
    "recommendation",
    "definition",
    "procedure_step",
    "condition",
)

SYSTEM = f"""\
You are a claim extractor for a document compiler. You never write prose.

You are given numbered spans of one document. Each span is one or more
sentences, taken verbatim from the source. Your job is to select the spans that
state a normative or factual rule, and to state that rule as one atomic claim.

Return ONLY a JSON array. Every element is an object with exactly these keys:

  span_ids   array of span ids (strings) that together support the claim
  statement  one sentence, third person, no hedging, no citation markers
  modality   one of: {", ".join(MODALITIES)}
  actor      the party the rule binds or benefits (string, may be "")
  deadline   a date or duration if the source states one (string, may be "")
  conditions array of conditions/exceptions that scope the claim (may be [])

Keep the JSON compact: one object per line, no extra keys, no explanation.

Rules, in order of importance:

1. NEVER write text that is not in a span. If a rule needs two separate spans
   (the rule, and the exception that scopes it), list both span ids in the same
   claim and use role-free supporting evidence.
2. One claim per atomic assertion. "A must do X and must also do Y" is two
   claims sharing the same span. An exception is its own claim with
   modality "condition", and its statement names what it scopes.
3. A definition is a claim (modality "definition"). A numbered step is a claim
   (modality "procedure_step"). An example inside a template or a fictional
   illustration is NOT a claim: skip it.
4. Do not merge spans that state contradictory things. Emit them as separate
   claims; the compiler links conflicts afterwards.
5. Do not infer, summarise across sections, or add world knowledge. If the
   document does not say it, it is not a claim.
6. Skip navigation, headers, footers, tables of contents, cookie notices and
   anything that is not a rule or a substantive fact.
7. Prefer fewer, better claims. An empty array is a valid answer for a span
   group that contains no rule.
"""


CONFLICT_SYSTEM = """\
You are given the claims compiled from ONE document, with their ids. Some pairs
of claims contradict each other: two different deadlines for the same
obligation, two different actors, a rule and an exception that cannot both hold.

Return ONLY a JSON array of pairs, e.g. [["D4-0001","D4-0002"]]. Each pair must
be two ids from the list, and the contradiction must be readable from the two
statements alone. Do not report pairs that merely talk about the same subject,
and do not report a rule together with a condition that scopes it: that is not
a conflict. If there are no conflicts, return [].
"""


def norm(text: str) -> str:
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    # Collapse *all* whitespace, newlines included: that is the same
    # convention check_claims.py verifies, so "verbatim" means one thing.
    text = re.sub(r"\s+", " ", text)
    return text.strip()


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
    text: str, doc_id: str, min_chars: int = 60, locate: bool = True
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
                "kind": DOCS[doc_id]["kind"],
                "page": page,
                "section_path": [title for _, title in section_stack][-3:],
                "url": DOCS[doc_id]["url"],
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


def _record_spans(text: str, doc_id: str, key_lines: list[int]) -> list[dict]:
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
    spans = _segment_blocks(preamble, doc_id, locate=False)

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
                    spans, doc_id, window, page, base + [record["key"]]
                )

    _locate(spans, text)
    return spans


def _append_span(
    spans: list[dict], doc_id: str, piece: str, page: int, section_path: list[str]
) -> None:
    if not re.search(r"[A-Za-z]{3,}", piece):
        return
    if BOILERPLATE.search(piece):
        return
    spans.append(
        {
            "span_id": f"S{len(spans) + 1:04d}",
            "doc_id": doc_id,
            "paragraph": piece,
            "locator": {
                "kind": DOCS[doc_id]["kind"],
                "page": page,
                "section_path": section_path[-3:],
                "url": DOCS[doc_id]["url"],
            },
        }
    )


def segment(text: str, doc_id: str, min_chars: int = 60) -> list[dict]:
    """Turn a document into spans with ids and locators. No model involved.

    Documents whose operative content is an item-numbered table take the
    record-scoped path; everything else keeps the block/heading path unchanged.
    """
    key_lines = record_key_lines(text)
    if key_lines:
        return _record_spans(text, doc_id, key_lines)
    return _segment_blocks(text, doc_id, min_chars)


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


def make_prompt(spans: list[dict], doc_id: str) -> str:
    lines = [f"DOCUMENT: {DOCS[doc_id]['context']['source']} ({doc_id})", ""]
    for span in spans:
        path = " > ".join(span["locator"].get("section_path") or [])
        header = f"[{span['span_id']}]" + (f" {path}" if path else "")
        lines.append(header)
        lines.append(span["paragraph"])
        lines.append("")
    lines.append("Return the JSON array of claims now. JSON only, no prose.")
    return "\n".join(lines)


def repair_json_array(text: str) -> list[dict]:
    """Recover the JSON objects from a malformed or truncated reply.

    Two failure modes are common with reasoning models behind a gateway:

    * the separating comma between two objects is dropped (``}{``);
    * the reply is cut in the middle of an object, while the objects before
      it are complete.

    Both are recoverable without inventing anything: the objects that survive
    are still model output, and every one of them is validated afterwards
    against real span ids.
    """
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    start = text.find("[")
    if start == -1:
        return []
    body = text[start:]
    end = body.rfind("]")
    if end != -1:
        body = body[: end + 1]

    def close_objects(piece: str) -> str:
        return re.sub(r"\}\s*(?=\{)", "},", piece)

    for candidate in (body, close_objects(body), re.sub(r",\s*\]", "]", close_objects(body))):
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]

    # Salvage: keep the complete top-level objects of a truncated reply.
    depth = 0
    last_complete = -1
    in_string = False
    escaped = False
    for index, char in enumerate(body):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "[{":
            depth += 1
        elif char in "]}":
            depth -= 1
            if char == "}" and depth == 1:
                last_complete = index
    if last_complete > 0:
        try:
            data = json.loads(close_objects(body[: last_complete + 1]) + "]")
        except json.JSONDecodeError:
            return []
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
    return []


def parse_claims(text: str) -> list[dict]:
    """Extract the JSON array from a model reply, tolerating fences and damage."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("["), text.rfind("]")
        if start == -1 or end == -1:
            return repair_json_array(text)
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return repair_json_array(text)
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def parse_pair_indices(reply: str, count: int) -> list[int]:
    """Parse a JSON array of pair numbers (1-based), validated against count."""
    text = reply.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("["), text.rfind("]")
        if start == -1 or end == -1:
            return []
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return []
    if not isinstance(data, list):
        return []
    out: list[int] = []
    for item in data:
        try:
            index = int(item)
        except (TypeError, ValueError):
            continue
        if 1 <= index <= count and index not in out:
            out.append(index)
    return out


def parse_conflicts(reply: str, valid_ids: set[str]) -> list[tuple[str, str]]:
    """Parse and validate conflict pairs. Symmetry is enforced by the caller."""
    text = reply.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("["), text.rfind("]")
        if start == -1 or end == -1:
            return []
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return []
    if not isinstance(data, list):
        return []
    pairs: list[tuple[str, str]] = []
    for item in data:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            continue
        left, right = str(item[0]).strip(), str(item[1]).strip()
        if left == right or left not in valid_ids or right not in valid_ids:
            continue
        pair = tuple(sorted((left, right)))
        if pair not in pairs:
            pairs.append(pair)
    return pairs


def link_conflicts(claims: list[dict], reply: str) -> int:
    """Set conflicts_with in both directions. Returns the number of pairs linked."""
    by_id = {c["claim_id"]: c for c in claims}
    pairs = parse_conflicts(reply, set(by_id))
    for left, right in pairs:
        for a, b in ((left, right), (right, left)):
            existing = by_id[a].setdefault("conflicts_with", [])
            if b not in existing:
                existing.append(b)
    return len(pairs)


STOP = set(
    "the a an and or of to in on for by with from as at is are was were be been being that this these those "
    "it its their his her shall must may can will would should not no any all such other which who whom whose".split()
)


def tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOP and len(t) > 2}


def conflict_candidates(claims: list[dict], k: int = 3, floor: float = 0.12) -> list[tuple[str, str]]:
    """Cheap local candidate generation: a contradiction is usually between two
    claims that talk about the same thing. The model then only confirms or
    rejects a numbered pair list, instead of comparing every claim to every
    other one (which made it exhaust its reasoning budget and return nothing).
    """
    sets = {c["claim_id"]: tokens(c["statement"] + " " + str(c.get("deadline") or "")) for c in claims}
    scored: dict[tuple[str, str], float] = {}
    ids = list(sets)
    for i, left in enumerate(ids):
        for right in ids[i + 1 :]:
            a, b = sets[left], sets[right]
            if not a or not b:
                continue
            score = len(a & b) / len(a | b)
            if score >= floor:
                scored[(left, right)] = score
    per_claim: dict[str, int] = {}
    picked: list[tuple[str, str, float]] = []
    for (left, right), score in sorted(scored.items(), key=lambda kv: -kv[1]):
        if per_claim.get(left, 0) >= k or per_claim.get(right, 0) >= k:
            continue
        per_claim[left] = per_claim.get(left, 0) + 1
        per_claim[right] = per_claim.get(right, 0) + 1
        picked.append((left, right, score))
    return [(left, right) for left, right, _ in picked]


def pairs_prompt(claims: list[dict], pairs: list[tuple[str, str]]) -> str:
    by_id = {c["claim_id"]: c for c in claims}
    lines = ["PAIRS:"]
    for index, (left, right) in enumerate(pairs, start=1):
        lines.append(f"{index}. [{left}] {by_id[left]['statement']}")
        lines.append(f"   [{right}] {by_id[right]['statement']}")
    lines.append("")
    lines.append("Return the JSON array of pair numbers that contradict each other, e.g. [3,7]. JSON only.")
    return "\n".join(lines)


def call_model(prompt: str, args, system: str = SYSTEM) -> tuple[str, dict, str]:
    from llm import chat

    return chat(
        args.base_url or os.environ.get("OPENAI_BASE_URL", ""),
        os.environ.get("OPENAI_API_KEY", ""),
        args.model,
        [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        args.max_tokens,
    )


def statement_key(statement: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", statement.lower()).strip()


def dedupe_claims(claims: list[dict], threshold: float = 0.85) -> tuple[list[dict], int]:
    """Merge claims that state the same rule twice.

    Consecutive chunks overlap by two spans, so the same rule is often
    extracted twice and paraphrased slightly ("must"/"shall"). Exact
    statement matching does not catch that, and a duplicated rule crowds a
    retrieval budget that should cover different rules.

    Only near-identical statements inside one document are merged, and the
    survivor keeps the union of the evidence: a merge never deletes support.
    """
    by_doc: dict[str, list[dict]] = {}
    for claim in claims:
        by_doc.setdefault(claim["doc_id"], []).append(claim)

    kept: list[dict] = []
    merged_count = 0
    for doc_claims in by_doc.values():
        token_sets = [tokens(c["statement"]) for c in doc_claims]
        absorbed: set[int] = set()
        for i, claim in enumerate(doc_claims):
            if i in absorbed:
                continue
            for j in range(i + 1, len(doc_claims)):
                if j in absorbed:
                    continue
                left, right = token_sets[i], token_sets[j]
                if not left or not right:
                    continue
                if len(left & right) / len(left | right) < threshold:
                    continue
                other = doc_claims[j]
                quotes = {e["quote"] for e in claim.get("evidence", [])}
                for evidence in other.get("evidence", []):
                    if evidence["quote"] not in quotes:
                        claim.setdefault("evidence", []).append(evidence)
                        quotes.add(evidence["quote"])
                for field in ("actor", "deadline", "subject", "predicate", "object"):
                    if not claim.get(field) and other.get(field):
                        claim[field] = other[field]
                conditions = claim.setdefault("conditions", [])
                for condition in other.get("conditions", []) or []:
                    if condition not in conditions:
                        conditions.append(condition)
                if not conditions:
                    claim.pop("conditions", None)
                conflicts = claim.setdefault("conflicts_with", [])
                for conflict in other.get("conflicts_with", []) or []:
                    if conflict not in conflicts:
                        conflicts.append(conflict)
                if not conflicts:
                    claim.pop("conflicts_with", None)
                absorbed.add(j)
                merged_count += 1
        kept.extend(c for index, c in enumerate(doc_claims) if index not in absorbed)
    kept.sort(key=lambda c: (c["doc_id"], int(c["claim_id"].split("-")[-1])))
    return kept, merged_count


def build_claim(raw: dict, span_by_id: dict[str, dict], doc_id: str, number: int) -> dict | None:
    ids = raw.get("span_ids") or raw.get("spans") or []
    if isinstance(ids, str):
        ids = [ids]
    ids = [str(i).strip().strip("[]") for i in ids]
    spans = [span_by_id[i] for i in ids if i in span_by_id]
    if not spans:
        return None
    statement = norm(str(raw.get("statement", "")))
    if len(statement) < 15:
        return None
    modality = str(raw.get("modality", "")).strip().lower()
    if modality not in MODALITIES:
        modality = "definition" if modality in {"fact", "rule", "statement"} else "obligation"
    evidence = []
    seen: set[str] = set()
    for span in spans:
        if span["paragraph"] in seen:
            continue
        seen.add(span["paragraph"])
        evidence.append({"quote": span["paragraph"], "locator": dict(span["locator"]), "role": "supports"})
    if not evidence:
        return None
    claim = {
        "claim_id": f"{doc_id}-{number:04d}",
        "doc_id": doc_id,
        "statement": statement,
        "modality": modality,
    }
    for field in ("actor", "deadline", "subject", "predicate", "object"):
        value = raw.get(field)
        if isinstance(value, str) and value.strip():
            claim[field] = norm(value)
    conditions = raw.get("conditions")
    if isinstance(conditions, list):
        cleaned = [norm(str(c)) for c in conditions if str(c).strip()]
        if cleaned:
            claim["conditions"] = cleaned
    claim["evidence"] = evidence
    claim["context"] = dict(DOCS[doc_id]["context"])
    return to_v2(claim)


def row_claims(spans: list[dict]) -> list[dict]:
    """One deterministic claim per key/value row span (PREFLIGHT §10.7(f)).

    The statement is the cell itself: the printed label and the printed value,
    with nothing paraphrased. A row that the model skipped therefore still
    reaches the artifact, and a row the model did extract is left alone (the
    caller drops rows its claims already cite).
    """
    out: list[dict] = []
    for span in spans:
        row = span.get("row")
        if not row:
            continue
        label = norm(str(row.get("label", "")))
        value = norm(str(row.get("value", "")))
        if not label or not value:
            continue
        statement = f"{label}: {value}"
        if not statement.endswith((".", ";", "?", "!")):
            statement += "."
        out.append({"span": span, "statement": norm(statement)})
    return out


def build_row_claim(record: dict, number: int) -> dict:
    """Turn a rule-emitted row into a claim in the artifact's own shape."""
    span = record["span"]
    doc_id = span["doc_id"]
    claim = {
        "claim_id": f"{doc_id}-{number:04d}",
        "doc_id": doc_id,
        "statement": record["statement"],
        "modality": "definition",
        "evidence": [
            {"quote": span["paragraph"], "locator": dict(span["locator"]), "role": "supports"}
        ],
        "context": dict(DOCS[doc_id]["context"]),
    }
    return to_v2(claim)


def estimate(spans: list[dict], chunks: list[list[dict]], args, conflicts: bool = True) -> dict:
    prompt_chars = sum(len(make_prompt(c, c[0]["doc_id"])) for c in chunks if c)
    # ~3.6 chars/token for English, plus the system prompt on every call.
    input_tokens = int(prompt_chars / 3.6 + 900 * len(chunks))
    output_tokens = int(len(spans) * 45)
    calls = len(chunks)

    # The conflict pass is one small call per document: claim id + statement,
    # and a short array of pairs.
    conflict_calls = 0
    if conflicts:
        docs = {c[0]["doc_id"] for c in chunks if c}
        claims_est = max(1, len(spans) // 3)
        conflict_calls = len(docs)
        calls += conflict_calls
        input_tokens += claims_est * 25 + 700 * len(docs)
        output_tokens += 40 * len(docs)

    return {
        "calls": calls,
        "extraction_calls": len(chunks),
        "conflict_calls": conflict_calls,
        "prompt_chars": prompt_chars,
        "input_tokens_est": input_tokens,
        "output_tokens_est": output_tokens,
    }


def main() -> int:
    load_dotenv()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--docs", default="D1,D2,D3,D4")
    ap.add_argument("--out", default=str(GOLD / "claims.compiled.jsonl"))
    ap.add_argument("--spans-out", default="", help="Write the span list here (default: <out>.spans.jsonl)")
    ap.add_argument("--backend", choices=["http", "dry-run"], default="http")
    ap.add_argument("--model", default=os.environ.get("DOCBENCH_MODEL") or os.environ.get("OPENAI_MODEL", ""))
    ap.add_argument("--base-url", default=os.environ.get("OPENAI_BASE_URL", ""))
    ap.add_argument("--chunk-size", type=int, default=15, help="Spans per request")
    ap.add_argument("--overlap", type=int, default=2, help="Spans repeated between requests")
    ap.add_argument("--min-chars", type=int, default=60)
    ap.add_argument("--max-tokens", type=int, default=10000)
    ap.add_argument("--resume", action="store_true",
                    help="Continue a previous run, skipping completed chunks")
    ap.add_argument("--retry-failed", action="store_true",
                    help="With --resume: redo the chunks touched by recorded failures")
    ap.add_argument("--conflicts", dest="conflicts", action="store_true", default=True,
                    help="Second pass that links contradicting claims (default: on)")
    ap.add_argument("--no-conflicts", dest="conflicts", action="store_false")
    ap.add_argument("--pair-batch", type=int, default=20, help="Candidate pairs per conflict request")
    ap.add_argument("--verify", action="store_true",
                    help="After compiling, audit every claim against its own evidence, repair "
                         "what fails, and drop what cannot be repaired (see verify_claims.py)")
    ap.add_argument("--verify-rounds", type=int, default=2)
    ap.add_argument("--verify-audit-batch", type=int, default=10)
    ap.add_argument("--verify-repair-batch", type=int, default=6)
    ap.add_argument("--verify-concurrency", type=int, default=1,
                    help="independent verify batches in flight (throughput only; prompts unchanged)")
    ap.add_argument("--dry-run", action="store_true", help="Segment and estimate only")
    ap.add_argument("--estimate", action="store_true", help="Estimate tokens and stop (implies --dry-run)")
    ap.add_argument("--rule-report", action="store_true",
                    help="Print every claim the key/value row rule would emit, then stop")
    ap.add_argument("--no-rules", action="store_true",
                    help="Do not emit the deterministic key/value row claims")
    args = ap.parse_args()

    if args.rule_report:
        args.dry_run = True
    if args.estimate:
        args.dry_run = True
    if not args.model and not args.dry_run:
        raise SystemExit("no model: pass --model or set OPENAI_MODEL")

    doc_ids = [d.strip() for d in args.docs.split(",") if d.strip()]
    all_spans: list[dict] = []
    per_doc_spans: dict[str, list[dict]] = {}
    for doc_id in doc_ids:
        path = PRIVATE / DOCS[doc_id]["file"]
        if not path.exists():
            raise SystemExit(f"missing source: {path}")
        spans = segment(path.read_text(encoding="utf-8", errors="ignore"), doc_id, args.min_chars)
        per_doc_spans[doc_id] = spans
        all_spans.extend(spans)
        print(f"{doc_id}: {len(spans)} spans, {sum(len(s['paragraph']) for s in spans)} chars")

    chunks: list[list[dict]] = []
    for doc_id in doc_ids:
        chunks.extend(chunk(per_doc_spans[doc_id], args.chunk_size, args.overlap))

    est = estimate(all_spans, chunks, args, conflicts=args.conflicts)
    print(
        f"\ncalls: {est['calls']} ({est['extraction_calls']} extraction"
        f" + {est['conflict_calls']} conflicts)  "
        f"input tokens (est): {est['input_tokens_est']:,}  "
        f"output tokens (est): {est['output_tokens_est']:,}"
    )
    usd_in = est["input_tokens_est"] / 1_000_000 * 0.15
    usd_out = est["output_tokens_est"] / 1_000_000 * 0.60
    print(f"cost at $0.15/M in, $0.60/M out: ${usd_in + usd_out:.4f}")

    spans_out = Path(args.spans_out) if args.spans_out else Path(str(args.out) + ".spans.jsonl")
    spans_out.parent.mkdir(parents=True, exist_ok=True)
    spans_out.write_text(
        "".join(json.dumps(s, ensure_ascii=False) + "\n" for s in all_spans), encoding="utf-8"
    )
    print(f"wrote spans: {spans_out}")

    if args.dry_run:
        if args.rule_report:
            total = 0
            for doc_id in doc_ids:
                records = row_claims(per_doc_spans[doc_id])
                total += len(records)
                print(f"\n--- {doc_id}: {len(records)} rule claim(s) from key/value rows ---")
                for record in records:
                    span = record["span"]
                    print(
                        f"{span['span_id']} p{span['locator'].get('page')} "
                        f"{span['locator'].get('section_path')}"
                    )
                    print(f"    {record['statement']}")
            print(f"\n{total} rule claim(s) over {len(doc_ids)} document(s)")
            return 0
        if chunks:
            print(f"\n--- first prompt (chunk 1/{len(chunks)}) ---\n")
            print(make_prompt(chunks[0], chunks[0][0]["doc_id"])[:2500])
        return 0

    # Span ids are per document, so the lookup is per document.
    per_doc_by_id = {
        doc_id: {s["span_id"]: s for s in spans} for doc_id, spans in per_doc_spans.items()
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    state_path = Path(str(out) + ".state.json")
    failures_path = Path(str(out) + ".failures.jsonl")

    claims: list[dict] = []
    counters: dict[str, int] = {}
    done_chunks: dict[str, int] = {}
    if args.resume and out.exists() and state_path.exists():
        claims = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines() if line.strip()]
        for claim in claims:
            doc = claim["doc_id"]
            counters[doc] = max(counters.get(doc, 0), int(claim["claim_id"].split("-")[-1]))
        done_chunks = json.loads(state_path.read_text(encoding="utf-8")).get("done", {})
        print(f"resuming: {len(claims)} claims, {len(done_chunks)} chunk(s) already done")
        # Keep the accounting honest across invocations: tokens already spent
        # belong in the manifest of the finished artifact.
        prior_manifest = Path(str(out) + ".manifest.json")
        if prior_manifest.exists():
            prior = json.loads(prior_manifest.read_text(encoding="utf-8"))
            prior_totals = {
                "input_tokens": prior.get("input_tokens", 0),
                "output_tokens": prior.get("output_tokens", 0),
            }
            prior_rejected = prior.get("rejected", 0)
            prior_counts = {
                "truncated_retries": prior.get("truncated_retries", 0),
                "duplicates_merged": prior.get("duplicates_merged", 0),
                "conflict_pairs": prior.get("conflict_pairs", 0),
                "conflict_batch_failures": prior.get("conflict_batch_failures", 0),
            }
        else:
            prior_totals = {"input_tokens": 0, "output_tokens": 0}
            prior_rejected = 0
            prior_counts = {}
    else:
        counters = {}
        prior_totals = {"input_tokens": 0, "output_tokens": 0}
        prior_rejected = 0
        prior_counts = {}

    seen_statements: set[str] = {statement_key(c["statement"]) for c in claims}
    totals = dict(prior_totals)
    rejected = prior_rejected
    # These describe the whole artifact, not one invocation, so a resumed run
    # adds to what the previous invocation already recorded.
    truncated = prior_counts.get("truncated_retries", 0)
    duplicates_merged = prior_counts.get("duplicates_merged", 0)
    if not (args.resume and done_chunks):
        failures_path.write_text("", encoding="utf-8")

    if args.retry_failed and failures_path.exists():
        failed_spans: set[str] = set()
        for line in failures_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                failed_spans.update(json.loads(line).get("span_ids") or [])
        reset = 0
        for block in chunks:
            key = f"{block[0]['doc_id']}:{block[0]['span_id']}-{block[-1]['span_id']}"
            if key in done_chunks and any(span["span_id"] in failed_spans for span in block):
                del done_chunks[key]
                reset += 1
        print(f"retry: {reset} chunk(s) reset, touching {len(failed_spans)} recorded span(s)")

    def save() -> None:
        out.write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in claims), encoding="utf-8")
        state_path.write_text(json.dumps({"done": done_chunks}, indent=1), encoding="utf-8")

    def record_failure(doc_id: str, block: list[dict], reply: str, reason: str) -> None:
        with failures_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "doc_id": doc_id,
                "span_ids": [s["span_id"] for s in block],
                "reason": reason,
                "reply": reply[:4000],
            }, ensure_ascii=False) + "\n")

    def absorb_objects(doc_id: str, parsed: list[dict]) -> int:
        """Turn parsed reply objects into claims. Returns how many were kept."""
        nonlocal rejected
        kept = 0
        for raw in parsed:
            counters[doc_id] = counters.get(doc_id, 0) + 1
            claim = build_claim(raw, per_doc_by_id[doc_id], doc_id, counters[doc_id])
            if claim is None:
                counters[doc_id] -= 1
                rejected += 1
                continue
            key = statement_key(claim["statement"])
            if key in seen_statements:
                counters[doc_id] -= 1
                rejected += 1
                continue
            seen_statements.add(key)
            claims.append(claim)
            kept += 1
        return kept

    def absorb(doc_id: str, block: list[dict]) -> tuple[int, int]:
        """Extract from one block, salvaging what is complete and retrying the rest."""
        nonlocal truncated
        prompt = make_prompt(block, doc_id)
        reply, usage, finish = call_model(prompt, args)
        totals["input_tokens"] += usage["input_tokens"]
        totals["output_tokens"] += usage["output_tokens"]

        cut_off = finish == "length" or (bool(reply.strip()) and not reply.strip().endswith("]"))
        parsed = parse_claims(reply)
        kept = absorb_objects(doc_id, parsed)
        if not parsed and reply.strip() not in ("[]", ""):
            record_failure(doc_id, block, reply, "unparseable")

        # A reply cut in the middle is not "this block has no rules". Keep the
        # objects that arrived complete, and ask again only for the spans they
        # do not cover.
        if cut_off:
            truncated += 1
            record_failure(doc_id, block, reply, f"truncated (finish={finish or 'unknown'})")
            covered = {
                str(span_id).strip().strip("[]")
                for raw in parsed
                for span_id in (raw.get("span_ids") or raw.get("spans") or [])
            }
            remaining = [span for span in block if span["span_id"] not in covered]
            if remaining and len(block) > 1:
                middle = len(remaining) // 2
                first, _ = absorb(doc_id, remaining[:middle])
                second, _ = absorb(doc_id, remaining[middle:])
                return kept + first + second, len(parsed)
        return kept, len(parsed)

    for index, block in enumerate(chunks, start=1):
        doc_id = block[0]["doc_id"]
        chunk_key = f"{doc_id}:{block[0]['span_id']}-{block[-1]['span_id']}"
        if chunk_key in done_chunks:
            continue
        before = (totals["input_tokens"], totals["output_tokens"])
        kept, parsed = absorb(doc_id, block)
        done_chunks[chunk_key] = kept
        save()
        print(
            f"[{index}/{len(chunks)}] {doc_id} spans={len(block)} parsed={parsed} "
            f"kept={kept} tokens={totals['input_tokens'] - before[0]}+"
            f"{totals['output_tokens'] - before[1]}"
        )

    # Deterministic row claims: the evidence of a table row is label + value, so
    # a row the model did not use is emitted from the span itself, before dedupe
    # and the conflict pass see the claim list (PREFLIGHT.md §10.7(f)).
    rule_added = 0
    if not args.no_rules:
        covered: set[tuple] = set()
        for claim in claims:
            for item in claim.get("evidence") or []:
                locator = item.get("locator") or {}
                start, end = locator.get("char_start"), locator.get("char_end")
                if start is not None and end is not None:
                    covered.add((claim["doc_id"], start, end))
        for doc_id in doc_ids:
            for record in row_claims(per_doc_spans[doc_id]):
                locator = record["span"]["locator"]
                key = (doc_id, locator.get("char_start"), locator.get("char_end"))
                if key in covered:
                    continue
                counters[doc_id] = counters.get(doc_id, 0) + 1
                claim = build_row_claim(record, counters[doc_id])
                signature = statement_key(claim["statement"])
                if signature in seen_statements:
                    counters[doc_id] -= 1
                    continue
                seen_statements.add(signature)
                claims.append(claim)
                covered.add(key)
                rule_added += 1
        if rule_added:
            print(f"rows: {rule_added} deterministic claim(s) from key/value rows")

    claims, newly_merged = dedupe_claims(claims)
    duplicates_merged += newly_merged
    if newly_merged:
        seen_statements = {statement_key(c["statement"]) for c in claims}
        print(f"dedupe: merged {newly_merged} near-duplicate claim(s) -> {len(claims)} claims")
    save()

    conflict_pairs = prior_counts.get("conflict_pairs", 0)
    conflict_failures = prior_counts.get("conflict_batch_failures", 0)
    if args.conflicts:
        by_doc_claims: dict[str, list[dict]] = {}
        for claim in claims:
            by_doc_claims.setdefault(claim["doc_id"], []).append(claim)
        for doc_id in doc_ids:
            doc_claims = by_doc_claims.get(doc_id, [])
            if len(doc_claims) < 2:
                continue
            pairs = conflict_candidates(doc_claims)
            linked = 0
            failed = 0
            for start in range(0, len(pairs), args.pair_batch):
                batch = pairs[start : start + args.pair_batch]
                try:
                    reply, usage, finish = call_model(pairs_prompt(doc_claims, batch), args, CONFLICT_SYSTEM)
                except SystemExit as exc:
                    # The gateway drops long runs with 503s. Losing one batch of
                    # 20 candidate pairs must not lose the other 100 claims.
                    failed += 1
                    record_failure(doc_id, [], str(exc), "conflict batch failed")
                    print(f"  conflicts {doc_id}: batch {start // args.pair_batch + 1} failed ({exc})")
                    continue
                totals["input_tokens"] += usage["input_tokens"]
                totals["output_tokens"] += usage["output_tokens"]
                chosen = parse_pair_indices(reply, len(batch))
                if finish == "length" and not chosen:
                    print(f"  conflicts {doc_id}: batch of {len(batch)} pairs hit the token limit, skipped")
                    continue
                selected = [batch[i - 1] for i in chosen]
                linked += link_conflicts(doc_claims, json.dumps([[a, b] for a, b in selected]))
            conflict_pairs += linked
            conflict_failures += failed
            print(
                f"conflicts {doc_id}: {linked} pair(s) confirmed from {len(pairs)} candidate(s), "
                f"{len(doc_claims)} claims" + (f", {failed} batch(es) failed" if failed else "")
            )

    save()

    verify_summary: dict | None = None
    if args.verify:
        from llm import chat
        from verify_claims import SpanIndex, run_pipeline, write_jsonl

        def verify_call(prompt: str, system: str, max_tokens: int):
            return chat(
                args.base_url or os.environ.get("OPENAI_BASE_URL", ""),
                os.environ.get("OPENAI_API_KEY", ""),
                args.model,
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                max_tokens,
            )

        span_index = SpanIndex(
            [json.loads(line) for line in spans_out.read_text(encoding="utf-8").splitlines() if line.strip()]
        )
        work = Path(str(out) + ".verify")
        verified, verify_report = run_pipeline(
            claims,
            span_index,
            verify_call,
            work=work,
            rounds=args.verify_rounds,
            audit_batch=args.verify_audit_batch,
            repair_batch=args.verify_repair_batch,
            max_tokens=args.max_tokens,
            resume=args.resume,
            concurrency=args.verify_concurrency,
        )
        verified_path = Path(str(out)[: -len(".jsonl")] + ".verified.jsonl") if str(out).endswith(".jsonl") else Path(str(out) + ".verified.jsonl")
        write_jsonl(verified_path, verified)
        (work / "report.json").write_text(json.dumps(verify_report, indent=1), encoding="utf-8")
        print(f"\nverified: {len(verified)} claims -> {verified_path}")
        print(json.dumps(verify_report["final"], indent=1))
        verify_summary = {
            "file": str(verified_path),
            "initial": verify_report["initial"],
            "rounds": verify_report["rounds"],
            "residual_dropped": verify_report["residual_dropped"],
            "kept_weak": verify_report["kept_weak"],
            "kept_weak_ids": verify_report["kept_weak_ids"],
            "merged_duplicates": verify_report["merged_duplicates"],
            "usage": verify_report.get("usage"),
            "cost_usd": verify_report.get("cost_usd"),
            "final": verify_report["final"],
        }

    manifest = {
        "model": args.model,
        "base_url": args.base_url,
        "docs": doc_ids,
        "chunk_size": args.chunk_size,
        "overlap": args.overlap,
        "min_chars": args.min_chars,
        "chunks": len(chunks),
        "spans": len(all_spans),
        "claims": len(claims),
        "rejected": rejected,
        "rule_claims": rule_added,
        "duplicates_merged": duplicates_merged,
        "truncated_retries": truncated,
        "conflict_pairs": conflict_pairs,
        "conflict_batch_failures": conflict_failures,
        "input_tokens": totals["input_tokens"],
        "output_tokens": totals["output_tokens"],
        "spans_sha256": hashlib.sha256(spans_out.read_bytes()).hexdigest(),
        "claims_sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
        "claims_by_doc": {d: sum(1 for c in claims if c["doc_id"] == d) for d in doc_ids},
        "verify": verify_summary,
    }
    Path(str(out) + ".manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"\nwrote {len(claims)} claims -> {out}")
    print(json.dumps(manifest, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
