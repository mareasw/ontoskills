#!/usr/bin/env python3
"""Deterministic verifier (ADR 0002, Phase 0) — no model, no network.

The LLM audit of ``verify_claims.py`` asks a model whether a claim is supported
by its own evidence. This script answers the same question with rules only, so it
can be replayed over an accepted artifact in milliseconds and compared with the
independent census:

  1. **verbatim** — every quote is a substring of the normalised source (`no`);
  2. **locator** — the locator resolves to a span, the quote is in that span, and
     the declared page is a page the quote occurs on (`no`);
  3. **section** — the declared section path and the span's own path agree, one
     being a prefix of the other (`no`);
  4. **numbers** — every number in the statement appears in the evidence or the
     section path (`no`);
  5. **attestation** — more than one content token in four of the statement is
     not in the evidence or the section path (`weak`). The tolerance is the
     paraphrase allowance: the census treats a restated predicate as supported
     when the substance is carried, and a literal every-token rule marked 85 of
     the census's 389 `ok` rows `weak` (measured on the accepted artifact);
  6. **modality** — a statement that says permission where the evidence says
     obligation (or the reverse) is **reported as a note, not as a verdict**.
     Measured: as a verdict it marked 8 census-`ok` rows `weak` (D6 dispositions
     mix "Destroy…" with "retention is authorized") and caught none of the
     census's 8 `weak` rows, so Phase 0 keeps it as an annotation.

``ok`` / ``weak`` / ``no`` use the census scale. Contradictions are out of scope
for Phase 0: the ADR keeps them as a report until a precedence rule exists.

Usage::

    python benchmark/docbench/verify_deterministic.py \
        --claims gold/probe.rows.g.compiled.verified.jsonl \
        --spans gold/probe.rows.g.compiled.jsonl.spans.jsonl \
        --verdicts gold/probe.rows.g.verdicts.jsonl

The ``--verdicts`` file is the independent census (``claim_id`` + ``verdict``).
With it the script prints the agreement Phase 0 asks for (target: >= 95%).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from check_claims import SOURCES, norm, page_containing  # noqa: E402
from claims_model import evidence_items, load_claims  # noqa: E402
from verify_claims import STOPWORDS, SpanIndex  # noqa: E402

# Modality is compared by class, not by the presence of a word: a schedule writes
# "Destroy when 3 years old" (an imperative) or "longer retention is authorized"
# (a passive permission), and the census counts both as supported. What the
# verifier can see is a *conflict*: the statement says permission where the
# evidence says obligation, or the reverse. Prohibition is tested first because
# "must not" also contains "must".
MODAL_CLASSES = {
    "prohibition": ("must not", "may not", "cannot", "can not", "shall not", "prohibited"),
    "obligation": ("must", "shall", "is required", "are required", "required to"),
    "permission": ("may", "is permitted", "are permitted", "authorized"),
}
NUMBER = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)*(?![\w.])")

# One content token in four may be a paraphrase. Measured, not guessed: on the
# 397-claim accepted artifact a 25% tolerance agrees with the census on 97.7% of
# rows, and the same threshold holds on both halves of D5 (97.7% / 97.1%) and on
# D6 (100%). A literal every-token rule agrees on 78.1% (310/397), because the
# census accepts a restated predicate.
PARAPHRASE_TOLERANCE = 0.25


def tokens(text: str) -> list[str]:
    """Lower-case alphanumeric tokens; one-letter tokens are noise.

    ``Importer's`` tokenises as ``importer`` + ``s`` and ``5.1(b)`` as ``5`` +
    ``1`` + ``b``; neither ``s`` nor ``b`` carries a claim.
    """
    return [t for t in re.findall(r"[a-z0-9]+", str(text or "").lower()) if len(t) > 1]


def same_word(left: str, right: str) -> bool:
    """Share a stem of at least four characters: ``date``/``dated``, ``party``/``parties``.

    Inflection, not paraphrase. A crude stemmer mangled words in both
    directions (``processed`` -> ``proces``), so the comparison is done on the
    two surfaces instead: a shared prefix of four characters or more, allowing
    at most two trailing characters of difference. That maps ``process`` to
    ``processed`` and ``override`` to ``overridden`` (prefix ``overri``) without
    mapping ``claim`` to ``clause``.
    """
    if left == right:
        return True
    shortest = min(len(left), len(right))
    if shortest < 4:
        return False
    prefix = 0
    for a, b in zip(left, right):
        if a != b:
            break
        prefix += 1
    return prefix >= 4 and prefix >= shortest - 2


def attested_by(token: str, pool: list[str]) -> bool:
    return any(same_word(token, candidate) for candidate in pool)


def _prefix_compatible(left: list[str], right: list[str]) -> bool:
    shared = min(len(left), len(right))
    return shared > 0 and [str(p).strip().lower() for p in left[:shared]] == [
        str(p).strip().lower() for p in right[:shared]
    ]


def modal_classes(text: str) -> set[str]:
    """The modality classes the text states, by phrase (prohibition first)."""
    said = " " + " ".join(tokens(text)) + " "
    found: set[str] = set()
    for name, phrases in MODAL_CLASSES.items():
        if any(f" {phrase} " in said for phrase in phrases):
            found.add(name)
    # "must not" is a prohibition, not also an obligation.
    if "prohibition" in found:
        found.discard("obligation")
    return found


def statement_tokens(text: str) -> list[str]:
    """Content tokens of the statement: no grammatical words, no one-letter noise."""
    return [t for t in tokens(text) if t not in STOPWORDS]


def evidence_text(claim: dict) -> tuple[str, str]:
    """Return (quotes, section paths) as one normalised string each."""
    quotes: list[str] = []
    paths: list[str] = []
    for item in evidence_items(claim):
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

    for index, item in enumerate(evidence_items(claim)):
        quote = norm(item.get("quote", ""))
        locator = item.get("locator") or {}
        if not quote:
            hard.append(f"evidence[{index}]: empty quote")
            continue
        if quote not in source:
            hard.append(f"evidence[{index}]: quote not in the source")
            continue
        span = spans.by_range.get(
            (doc, locator.get("char_start"), locator.get("char_end"))
        )
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
    missing = sorted({t for t in content if not attested_by(t, pool)})
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
            name for name in ("prohibition", "obligation", "permission")
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


def agreement(rows: list[dict]) -> dict:
    """Compare deterministic verdicts with the census rows (claim_id-keyed)."""
    same = sum(1 for row in rows if row["verdict"] == row["census"])
    confusion: dict[str, Counter] = {}
    for row in rows:
        confusion.setdefault(row["verdict"], Counter())[row["census"]] += 1
    by_doc: dict[str, dict] = {}
    for row in rows:
        bucket = by_doc.setdefault(row["doc_id"], {"claims": 0, "agree": 0})
        bucket["claims"] += 1
        bucket["agree"] += row["verdict"] == row["census"]
    return {
        "claims": len(rows),
        "agree": same,
        "share": round(same / len(rows), 4) if rows else 0.0,
        "by_verdict": {verdict: dict(c) for verdict, c in confusion.items()},
        "by_doc": by_doc,
        "disagreements": [row for row in rows if row["verdict"] != row["census"]],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--claims", required=True)
    ap.add_argument("--spans", required=True)
    ap.add_argument("--verdicts", help="census JSONL: claim_id, verdict, note")
    ap.add_argument("--out", help="write the full report as JSON")
    args = ap.parse_args(argv)

    claims = load_claims(args.claims)
    spans = SpanIndex(load_claims(args.spans))
    texts = {
        doc: path.read_text(encoding="utf-8", errors="ignore")
        for doc, path in SOURCES.items()
        if path.exists()
    }

    rows: list[dict] = []
    for claim in claims:
        out = verify(claim, spans, texts)
        rows.append({"claim_id": claim["claim_id"], "doc_id": claim["doc_id"], **out})

    report: dict = {
        "claims": len(rows),
        "by_verdict": dict(Counter(row["verdict"] for row in rows)),
    }

    if args.verdicts:
        census = {
            row["claim_id"]: row
            for row in (json.loads(line) for line in Path(args.verdicts).read_text().splitlines() if line.strip())
        }
        unknown = [row["claim_id"] for row in rows if row["claim_id"] not in census]
        if unknown:
            print(f"census has no row for {len(unknown)} claim(s), first: {unknown[:3]}", file=sys.stderr)
        for row in rows:
            row["census"] = census.get(row["claim_id"], {}).get("verdict", "?")
        report["agreement"] = agreement(rows)

    if args.out:
        Path(args.out).write_text(json.dumps({**report, "rows": rows}, indent=1), encoding="utf-8")

    print(json.dumps(report.get("by_verdict"), indent=1))
    if "agreement" in report:
        result = report["agreement"]
        print(f"agreement: {result['agree']}/{result['claims']} = {result['share']:.2%}")
        print("confusion (deterministic -> census):", json.dumps(result["by_verdict"]))
        print("by doc:", json.dumps(result["by_doc"]))
        if result["disagreements"]:
            print(f"\n{len(result['disagreements'])} disagreement(s):")
            for row in result["disagreements"]:
                print(f"  {row['claim_id']} {row['verdict']} vs census {row['census']}: {'; '.join(row['reasons'])[:160]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
