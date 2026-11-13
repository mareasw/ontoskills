"""Deterministic verifier: no model, no network, milliseconds.

This is the product copy of the verifier accepted in ADR 0002 Phase 0
(``benchmark/docbench/verify_deterministic.py``). It answers one question per
claim: *do the claim's own evidence and locators support it?* It is a gate on
the artifact, not a judge of whether the claim is useful.

Six rules, in the order they are applied:

1. **verbatim** — every quote is a substring of the normalised source;
2. **locator** — the locator resolves to a span, the quote is in that span, and
   the declared page is a page the quote occurs on;
3. **section** — the declared section path and the span's own path agree, one
   being a prefix of the other;
4. **numbers** — every number in the statement appears in the evidence or the
   section path;
5. **attestation** — more than one content token in four of the statement is
   not in the evidence or the section path (``weak``);
6. **modality** — a statement that says permission where the evidence says
   obligation, or the reverse, is a *note*, not a verdict. Phase 0 measured it
   as a verdict and it cost 8 false ``weak`` rows while catching none.

The tolerance in rule 5 is measured, not guessed: 25% agreed with the census on
97.7% of the accepted artifact.

One difference from the bench: a locator is resolved by
``(doc_id, char_start, char_end)`` *or* by ``(doc_id, span_id)``, so an artifact
that carries span ids does not need the offsets to survive a re-segmentation.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Iterable

from compiler.documents.text import modal_classes, norm, same_word, statement_tokens, tokens


class SpanIndex:
    """Resolve a claim's evidence to spans by range, by span id, or by text."""

    def __init__(self, spans: Iterable[dict]) -> None:
        self.by_range: dict[tuple, dict] = {}
        self.by_id: dict[tuple, dict] = {}
        self.by_text: dict[tuple, dict] = {}
        self.order: dict[str, list[dict]] = {}
        for span in spans:
            doc = span["doc_id"]
            locator = span.get("locator") or {}
            span_id = span.get("span_id")
            if span_id:
                self.by_id[(doc, span_id)] = span
            if locator.get("char_start") is not None:
                self.by_range[(doc, locator.get("char_start"), locator.get("char_end"))] = span
            self.by_text.setdefault((doc, span.get("paragraph", "")), span)
            self.order.setdefault(doc, []).append(span)
        self.position: dict[tuple, int] = {}
        for doc, doc_spans in self.order.items():
            doc_spans.sort(key=lambda s: (s.get("locator") or {}).get("char_start") or 0)
            for index, span in enumerate(doc_spans):
                self.position[(doc, span["span_id"])] = index

    def resolve(self, claim: dict) -> list[dict]:
        """The spans a claim cites, in citation order, skipping unresolvable ones."""
        out: list[dict] = []
        doc = claim["doc_id"]
        for item in claim.get("evidence") or []:
            locator = item.get("locator") or {}
            span = self.by_range.get((doc, locator.get("char_start"), locator.get("char_end")))
            if span is None and locator.get("span_id"):
                span = self.by_id.get((doc, locator.get("span_id")))
            if span is None:
                span = self.by_text.get((doc, item.get("quote", "")))
            if span is not None and span not in out:
                out.append(span)
        return out

    def __len__(self) -> int:
        return sum(len(items) for items in self.order.values())


NUMBER = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)*(?![\w.])")
PARAPHRASE_TOLERANCE = 0.25

def page_containing(source: str, quote: str, declared: int | None = None) -> int | None:
    """Return the page that carries ``quote``; honour a declared page that does."""
    pages = [i for i, page in enumerate(source.split("\f"), start=1) if quote in norm(page)]
    if not pages:
        return None
    if declared in pages:
        return declared
    return pages[0]


def _prefix_compatible(left: list, right: list) -> bool:
    shared = min(len(left), len(right))
    return shared > 0 and [str(p).strip().lower() for p in left[:shared]] == [
        str(p).strip().lower() for p in right[:shared]
    ]


def evidence_text(claim: dict) -> tuple[str, str]:
    """Return (quotes, section paths) as one normalised string each."""
    quotes: list[str] = []
    paths: list[str] = []
    for item in claim.get("evidence") or []:
        quotes.append(norm(item.get("quote", "")))
        locator = item.get("locator") or {}
        paths.extend(str(part) for part in locator.get("section_path") or [])
    return " ".join(quotes), " ".join(paths)


def verify(claim: dict, spans: SpanIndex, texts: dict[str, str]) -> dict:
    """Return ``{"verdict", "reasons", "notes"}`` for one claim, rules only."""
    hard: list[str] = []
    soft: list[str] = []
    notes: list[str] = []
    doc = claim["doc_id"]
    raw = texts.get(doc, "")
    source = norm(raw)

    for index, item in enumerate(claim.get("evidence") or []):
        quote = norm(item.get("quote", ""))
        locator = item.get("locator") or {}
        if not quote:
            hard.append(f"evidence[{index}]: empty quote")
            continue
        if quote not in source:
            hard.append(f"evidence[{index}]: quote not in the source")
            continue
        span = spans.by_range.get((doc, locator.get("char_start"), locator.get("char_end")))
        if span is None and locator.get("span_id"):
            span = spans.by_id.get((doc, locator.get("span_id")))
        if span is None:
            span = spans.by_text.get((doc, quote))
        if span is None:
            hard.append(f"evidence[{index}]: locator does not resolve to a span")
        else:
            span_path = (span.get("locator") or {}).get("section_path") or []
            declared = locator.get("section_path") or []
            if declared and span_path and not _prefix_compatible(declared, span_path):
                hard.append(f"evidence[{index}]: declared section is not the span's")
            if quote not in norm(span.get("paragraph", "")):
                hard.append(f"evidence[{index}]: quote is not in the span it locates")
        page = locator.get("page")
        if locator.get("kind") == "pdf" and page is not None:
            computed = page_containing(raw, quote, page)
            if computed != page:
                hard.append(f"evidence[{index}]: declared page {page} != {computed}")

    quote_text, path_text = evidence_text(claim)
    pool = tokens(quote_text) + tokens(path_text)
    content = statement_tokens(claim.get("statement", ""))
    missing = sorted({t for t in content if not any(same_word(t, c) for c in pool)})
    share = len(missing) / max(1, len(content))
    if share > PARAPHRASE_TOLERANCE:
        soft.append(
            f"{len(missing)}/{len(content)} content tokens unattested "
            f"({share:.0%}): " + ", ".join(missing)
        )

    evidence_classes = modal_classes(" ".join(pool))
    statement_classes = modal_classes(claim.get("statement", ""))
    if evidence_classes:
        conflicting = [
            name
            for name in ("prohibition", "obligation", "permission")
            if name in statement_classes and name not in evidence_classes
        ]
        if conflicting:
            notes.append(
                "modality note: statement is "
                + "/".join(conflicting)
                + ", evidence is "
                + "/".join(sorted(evidence_classes))
            )

    numbers = NUMBER.findall(claim.get("statement", ""))
    missing_numbers = [n for n in numbers if n not in quote_text and n not in path_text]
    if missing_numbers:
        hard.append("numbers not in the evidence: " + ", ".join(missing_numbers))

    if hard:
        return {"verdict": "no", "reasons": hard + soft, "notes": notes}
    if soft:
        return {"verdict": "weak", "reasons": soft, "notes": notes}
    return {"verdict": "ok", "reasons": [], "notes": notes}


def verify_all(claims: list[dict], spans: Iterable[dict], texts: dict[str, str]) -> list[dict]:
    """Verify every claim; returns one row per claim in input order."""
    index = SpanIndex(spans)
    rows: list[dict] = []
    for claim in claims:
        out = verify(claim, index, texts)
        rows.append({"claim_id": claim["claim_id"], "doc_id": claim["doc_id"], **out})
    return rows


def summarise(rows: list[dict]) -> dict:
    """A compact report: verdict counts, per-document split, failures only."""
    by_verdict = Counter(row["verdict"] for row in rows)
    by_doc: dict[str, dict[str, int]] = {}
    for row in rows:
        bucket = by_doc.setdefault(row["doc_id"], {})
        bucket[row["verdict"]] = bucket.get(row["verdict"], 0) + 1
    return {
        "claims": len(rows),
        "by_verdict": dict(by_verdict),
        "by_doc": by_doc,
        "failures": [row for row in rows if row["verdict"] != "ok"],
    }
