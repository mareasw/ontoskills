"""Locator validity: the quote must be exactly where the locator says it is.

This is a property test over every compiled claim, not a question set. It asks
three independent questions of each evidence item, in increasing order of how
hard they are to fake:

1. **offset** — `collapse(source)[char_start:char_end]` equals the quote. This
   is the one that must hold for 100% of items; a failure means the compiler
   emitted an offset that does not address the text it cites.
2. **page** — the cited page is the page the offset falls on, computed from the
   form feeds in the raw extraction. A one-page PDF legitimately has no form
   feed, and a docx has none at all, so a document that cannot carry a page
   must not carry one.
3. **section** — the cited `section_path` is the section in force at the cited
   range. A quote that crosses a heading belongs to two sections and has no
   single answer; those are enumerated as `heading_crossing` rather than
   silently accepted or silently failed.

**Coordinate space, stated once.** `char_start`/`char_end` index the
whitespace-collapsed, punctuation-folded text (`documents.text.norm`: curly
quotes and dashes folded to ASCII, every whitespace run to one space, stripped).
They do *not* index `kb/text/*.txt` directly. That is the trap this file exists
to encode, so `collapse` reimplements the transformation independently of
`documents.text.norm` and the tests assert the two agree: a bug inside `norm`
would then show up as a disagreement instead of being invisible to its own
checker.

`span_missing` is a different failure and is reported as such: the cited range
is not any span's range. In both corpora it never happens — every evidence item
is exactly one span — but a checker that assumed it would not notice the day it
stops being true.

    python3 benchmark/retrieval/locator.py --check
    python3 benchmark/retrieval/locator.py --check ../pilot/kb-final5 \\
        examples/demo-corpus/kb --json /tmp/locator.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

# The DocBench folding table, copied from documents.text.norm on purpose. Keep
# the two in step: tests/test_retrieval_locator.py fails if they diverge.
_FOLD = {
    "\u2019": "'",
    "\u2018": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u2013": "-",
    "\u2014": "-",
}


@dataclass(frozen=True)
class Collapsed:
    """The collapsed text and, for each character, its index in the raw text."""

    text: str
    index: tuple[int, ...]

    def raw_offset(self, offset: int) -> int:
        return self.index[offset]

    def page_at(self, offset: int, raw: str) -> int:
        """1-based page the collapsed offset falls on, counted by form feeds."""
        return raw.count("\f", 0, self.raw_offset(offset)) + 1


def collapse(raw: str) -> Collapsed:
    """Fold punctuation and collapse whitespace, keeping a map back to `raw`.

    Equivalent to `re.sub(r"\\s+", " ", folded).strip()`, but each output
    character remembers which raw character it came from, so an offset in the
    collapsed text can be turned back into a page number. 1:1 substitutions do
    not move the map; a whitespace run maps to its first character.
    """
    folded = "".join(_FOLD.get(ch, ch) for ch in raw)
    out: list[str] = []
    index: list[int] = []
    size = len(folded)
    position = 0
    while position < size and folded[position].isspace():
        position += 1
    while position < size:
        if folded[position].isspace():
            end = position
            while end < size and folded[end].isspace():
                end += 1
            if end >= size:
                break
            out.append(" ")
            index.append(position)
            position = end
        else:
            out.append(folded[position])
            index.append(position)
            position += 1
    return Collapsed("".join(out), tuple(index))


@dataclass(frozen=True)
class Locator:
    kind: str = ""
    section_path: tuple[str, ...] = ()
    url: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    page: int | None = None

    @classmethod
    def from_json(cls, raw: dict) -> "Locator":
        return cls(
            kind=str(raw.get("kind") or ""),
            section_path=tuple(str(part) for part in (raw.get("section_path") or ())),
            url=raw.get("url"),
            char_start=raw.get("char_start"),
            char_end=raw.get("char_end"),
            page=raw.get("page"),
        )


@dataclass(frozen=True)
class Span:
    span_id: str
    doc_id: str
    paragraph: str
    locator: Locator


@dataclass(frozen=True)
class Evidence:
    quote: str
    locator: Locator
    role: str = ""


@dataclass(frozen=True)
class Claim:
    claim_id: str
    doc_id: str
    statement: str
    evidence: tuple[Evidence, ...]


@dataclass
class Corpus:
    """One compiled knowledge base: claims, their spans, and the sources."""

    label: str
    root: Path
    claims: tuple[Claim, ...]
    spans: dict[str, tuple[Span, ...]]
    raw: dict[str, str] = field(default_factory=dict)
    _collapsed: dict[str, Collapsed] = field(default_factory=dict, repr=False)

    def collapsed(self, doc_id: str) -> Collapsed:
        if doc_id not in self._collapsed:
            self._collapsed[doc_id] = collapse(self.raw[doc_id])
        return self._collapsed[doc_id]

    @classmethod
    def load(cls, root: Path, label: str | None = None) -> "Corpus":
        root = Path(root)
        claims = []
        with (root / "claims.jsonl").open(encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                claims.append(
                    Claim(
                        claim_id=str(row["claim_id"]),
                        doc_id=str(row["doc_id"]),
                        statement=str(row.get("statement") or ""),
                        evidence=tuple(
                            Evidence(
                                quote=str(item["quote"]),
                                locator=Locator.from_json(item.get("locator") or {}),
                                role=str(item.get("role") or ""),
                            )
                            for item in (row.get("evidence") or ())
                        ),
                    )
                )
        spans: dict[str, list[Span]] = defaultdict(list)
        with (root / "spans.jsonl").open(encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                spans[str(row["doc_id"])].append(
                    Span(
                        span_id=str(row["span_id"]),
                        doc_id=str(row["doc_id"]),
                        paragraph=str(row["paragraph"]),
                        locator=Locator.from_json(row.get("locator") or {}),
                    )
                )
        ordered = {
            doc: tuple(sorted(items, key=lambda s: (s.locator.char_start or 0, s.span_id)))
            for doc, items in spans.items()
        }
        raw = {}
        for doc in ordered:
            path = root / "text" / f"{doc}.txt"
            if not path.exists():
                raise FileNotFoundError(f"{label or root}: no source text for {doc}")
            raw[doc] = path.read_text(encoding="utf-8")
        return cls(label=label or root.name, root=root, claims=tuple(claims), spans=ordered, raw=raw)


# Verdict classes. The first three are the three checks above passing; the rest
# are the defects they can report, ordered from fatal to descriptive.
OK = "ok"
HEADING_CROSSING = "heading_crossing"
SECTION_MISMATCH = "section_mismatch"
PAGE_MISMATCH = "page_mismatch"
PAGE_MISSING = "page_missing"
PAGE_ON_PAGELESS = "page_on_pageless_document"
OFFSET_MISMATCH = "offset_mismatch"
QUOTE_ABSENT = "quote_absent"
SPAN_MISSING = "span_missing"
NO_OFFSETS = "no_offsets"

# Classes that mean the instrument is wrong, not the system under test.
FATAL = frozenset(
    {SECTION_MISMATCH, PAGE_MISMATCH, PAGE_ON_PAGELESS, OFFSET_MISMATCH, QUOTE_ABSENT, SPAN_MISSING, NO_OFFSETS}
)


@dataclass(frozen=True)
class Anomaly:
    claim_id: str
    span_id: str
    doc_id: str
    verdict: str
    detail: str


@dataclass
class Report:
    label: str
    root: Path
    claims: int
    evidence: int
    offset_valid: int = 0
    pages_checked: int = 0
    page_valid: int = 0
    section_valid: int = 0
    heading_crossings: int = 0
    crossing_spans: dict[tuple[str, str], set[tuple[str, ...]]] = field(default_factory=dict)
    classes: Counter = field(default_factory=Counter)
    anomalies: list[Anomaly] = field(default_factory=list)
    per_document: dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))

    @property
    def ok(self) -> bool:
        """The gate: offsets 100%, pages 100% where a page is possible, sections 100%."""
        if self.evidence == 0:
            return False
        if self.offset_valid != self.evidence:
            return False
        if self.pages_checked and self.page_valid != self.pages_checked:
            return False
        if self.section_valid != self.evidence:
            return False
        return not (self.classes.keys() & FATAL)

    def as_json(self) -> dict:
        return {
            "label": self.label,
            "root": str(self.root),
            "claims": self.claims,
            "evidence": self.evidence,
            "offset_validity": self.offset_valid / self.evidence if self.evidence else 0.0,
            "page_validity": self.page_valid / self.pages_checked if self.pages_checked else None,
            "section_validity": self.section_valid / self.evidence if self.evidence else 0.0,
            "heading_crossings": self.heading_crossings,
            "crossing_spans": [
                {
                    "doc_id": doc,
                    "span_id": span,
                    "sections": [list(path) for path in sorted(paths)],
                }
                for (doc, span), paths in sorted(self.crossing_spans.items())
            ],
            "classes": dict(sorted(self.classes.items())),
            "anomalies": [
                {
                    "claim_id": item.claim_id,
                    "span_id": item.span_id,
                    "doc_id": item.doc_id,
                    "verdict": item.verdict,
                    "detail": item.detail,
                }
                for item in self.anomalies
            ],
        }


def _section_timeline(spans: tuple[Span, ...]) -> list[tuple[int, int, tuple[str, ...], tuple[str, ...]]]:
    """Per span: (start, end, path in force, path a heading inside it opens).

    The heading stack persists across spans, so an empty `section_path` inherits
    the previous section — except when the span's own text contains the heading
    that opens the *next* section. That is the case the compiler cannot label
    and the case this checker must not hide.
    """
    timeline: list[tuple[int, int, tuple[str, ...], tuple[str, ...]]] = []
    in_force: tuple[str, ...] = ()
    for position, span in enumerate(spans):
        path = span.locator.section_path
        if path:
            in_force = path
        crossing: tuple[str, ...] = ()
        if not span.locator.section_path:
            for following in spans[position + 1 :]:
                candidate = following.locator.section_path
                if not candidate:
                    continue
                heading = candidate[-1]
                if candidate != in_force and heading and heading in span.paragraph:
                    crossing = candidate
                break
        start = span.locator.char_start or 0
        end = span.locator.char_end or start
        timeline.append((start, end, path or in_force, crossing))
    return timeline


def _title(path: tuple[str, ...]) -> str:
    return " / ".join(path) if path else "(front matter)"


@dataclass(frozen=True)
class Verdict:
    """One evidence item, judged. Three independent booleans, one label."""

    label: str
    detail: str
    offset_ok: bool
    page_ok: bool
    section_ok: bool
    span_id: str = ""
    paths: tuple[tuple[str, ...], ...] = ()


def _evaluate_evidence(
    corpus: Corpus, claim: Claim, item: Evidence, timeline, span_ranges: dict[tuple[str, int, int], str]
) -> Verdict:
    """Judge one evidence item against the source, in the order a reader would.

    All three checks are computed before the label is chosen, so a page defect
    cannot mask a section defect: the report keeps three independent fractions.
    The label is the first failure in priority order — offset, span, page,
    section — because that is also the order of how much of the citation can
    still be trusted.
    """
    locator = item.locator
    if locator.char_start is None or locator.char_end is None:
        return Verdict(NO_OFFSETS, "the locator has no character range", False, False, False)

    raw = corpus.raw[claim.doc_id]
    flat = corpus.collapsed(claim.doc_id)
    start, end = locator.char_start, locator.char_end
    expected = collapse(item.quote).text
    if start < 0 or end > len(flat.text) or start >= end:
        return Verdict(
            OFFSET_MISMATCH,
            f"range {start}:{end} is outside the text (length {len(flat.text)})",
            False,
            False,
            False,
        )

    # 1. Offset: the quote is exactly where the locator says it is.
    if flat.text[start:end] != expected:
        if expected and expected in flat.text:
            where = flat.text.find(expected)
            return Verdict(
                OFFSET_MISMATCH,
                f"the quote is at {where}:{where + len(expected)}, cited as {start}:{end}",
                False,
                False,
                False,
            )
        return Verdict(QUOTE_ABSENT, f"the quote is not in the source ({expected[:60]!r})", False, False, False)

    # 2. The range must be a span, not merely somewhere in the text.
    span_id = span_ranges.get((claim.doc_id, start, end), "")
    if not span_id:
        return Verdict(SPAN_MISSING, f"range {start}:{end} is not a span", True, False, False)

    # 3. Page, which only a document with form feeds can legitimately carry.
    pageable = "\f" in raw
    page_ok = True
    page_label = ""
    page_detail = ""
    if locator.page is not None and not pageable:
        page_ok, page_label = False, PAGE_ON_PAGELESS
        page_detail = f"cites page {locator.page}, the document has no pages"
    elif locator.page is None and pageable:
        page_ok, page_label = False, PAGE_MISSING
        page_detail = "a pageable document, but the evidence cites no page"
    elif locator.page is not None:
        actual = flat.page_at(start, raw)
        if actual != locator.page:
            page_ok, page_label = False, PAGE_MISMATCH
            page_detail = f"cites page {locator.page}, the offset falls on {actual}"

    # 4. Section: every section the range touches, plus any heading inside it.
    touched = [entry for entry in timeline if entry[0] < end and entry[1] > start]
    paths = {entry[2] for entry in touched}
    paths.update(entry[3] for entry in touched if entry[3])
    declared = locator.section_path
    section_ok = declared in paths
    crossing = section_ok and (len(paths) > 1 or any(entry[3] for entry in touched))
    ordered = tuple(sorted(paths))

    if not page_ok:
        return Verdict(page_label, page_detail, True, False, section_ok, span_id, ordered)
    if not section_ok:
        titles = ", ".join(_title(path) for path in ordered)
        return Verdict(
            SECTION_MISMATCH,
            f"cites {_title(declared)}, the range is in {titles}",
            True,
            True,
            False,
            span_id,
            ordered,
        )
    if crossing:
        titles = " -> ".join(_title(path) for path in ordered)
        return Verdict(HEADING_CROSSING, f"the quote spans a heading: {titles}", True, True, True, span_id, ordered)
    return Verdict(OK, "", True, True, True, span_id, ordered)


def check_corpus(corpus: Corpus) -> Report:
    report = Report(label=corpus.label, root=corpus.root, claims=len(corpus.claims), evidence=0)
    timelines = {doc: _section_timeline(spans) for doc, spans in corpus.spans.items()}
    span_ranges = {
        (doc, span.locator.char_start or 0, span.locator.char_end or 0): span.span_id
        for doc, spans in corpus.spans.items()
        for span in spans
    }
    for claim in corpus.claims:
        for item in claim.evidence:
            report.evidence += 1
            try:
                verdict = _evaluate_evidence(
                    corpus, claim, item, timelines.get(claim.doc_id, []), span_ranges
                )
            except (KeyError, IndexError) as error:  # a locator that addresses nothing
                verdict = Verdict(SPAN_MISSING, f"{type(error).__name__}: {error}", False, False, False)
            report.offset_valid += verdict.offset_ok
            report.section_valid += verdict.section_ok
            if item.locator.page is not None or "\f" in corpus.raw.get(claim.doc_id, ""):
                report.pages_checked += 1
                report.page_valid += verdict.page_ok
            if verdict.label == HEADING_CROSSING:
                report.heading_crossings += 1
                report.crossing_spans.setdefault((claim.doc_id, verdict.span_id), set()).update(verdict.paths)
            report.classes[verdict.label] += 1
            report.per_document[claim.doc_id][verdict.label] += 1
            if verdict.label not in (OK, HEADING_CROSSING):
                report.anomalies.append(
                    Anomaly(
                        claim_id=claim.claim_id,
                        span_id=verdict.span_id,
                        doc_id=claim.doc_id,
                        verdict=verdict.label,
                        detail=verdict.detail,
                    )
                )
    return report


def format_report(report: Report) -> str:
    lines = [
        f"{report.label}: {report.claims} claims, {report.evidence} evidence items",
        f"  offset validity : {report.offset_valid}/{report.evidence}",
        "  page validity   : "
        + (f"{report.page_valid}/{report.pages_checked}" if report.pages_checked else "n/a (no pageable text)"),
        f"  section validity: {report.section_valid}/{report.evidence}"
        f"  ({report.heading_crossings} quotes in {len(report.crossing_spans)} spans cross a heading)",
        "  classes         : " + ", ".join(f"{name} {count}" for name, count in sorted(report.classes.items())),
    ]
    for (doc, span), paths in sorted(report.crossing_spans.items()):
        sections = " -> ".join(_title(path) for path in sorted(paths))
        lines.append(f"  crossing        : {doc} {span} ({sections})")
    for doc, counts in sorted(report.per_document.items()):
        flagged = {name: count for name, count in counts.items() if name not in (OK, HEADING_CROSSING)}
        if flagged:
            lines.append(f"  {doc}: " + ", ".join(f"{name} {count}" for name, count in sorted(flagged.items())))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "corpora",
        nargs="*",
        type=Path,
        default=[Path("../pilot/kb-final5"), Path("examples/demo-corpus/kb")],
        help="knowledge-base directories holding claims/spans/text",
    )
    parser.add_argument("--check", action="store_true", help="run the property test (the default)")
    parser.add_argument("--json", type=Path, help="write the full audit, anomalies included")
    args = parser.parse_args(argv)

    reports = []
    failures = 0
    for path in args.corpora:
        if not path.exists():
            parser.error(f"no such corpus: {path}")
        corpus = Corpus.load(path)
        report = check_corpus(corpus)
        reports.append(report)
        print(format_report(report))
        for anomaly in report.anomalies[:20]:
            print(f"    {anomaly.verdict:24s} {anomaly.claim_id} [{anomaly.span_id}] {anomaly.detail}")
        if len(report.anomalies) > 20:
            print(f"    ... {len(report.anomalies) - 20} more")
        if not report.ok:
            failures += 1
            print("  FAIL: a locator does not address the source it cites")
        print()

    if args.json:
        args.json.write_text(
            json.dumps([report.as_json() for report in reports], indent=1, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {args.json}")
    return failures


if __name__ == "__main__":
    sys.exit(main())
