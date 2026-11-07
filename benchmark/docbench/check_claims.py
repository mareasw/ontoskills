#!/usr/bin/env python3
"""Check DocBench claims against their source documents.

Rules enforced:
  * the quote must exist verbatim in the source text (whitespace-normalised);
  * for PDF sources, the declared page must match the page where the quote occurs;
  * the claim must validate against gold/schema.json when jsonschema is installed.

Usage:
    python benchmark/docbench/check_claims.py [--fix-pages] [gold/claims.jsonl]

Exit code 0 when every claim passes, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PRIVATE = ROOT / "private"

SOURCES = {
    "D1": PRIVATE / "D1.txt",
    "D2": PRIVATE / "D2.txt",
    "D3": PRIVATE / "D3.txt",
    "D4": PRIVATE / "D4.txt",
}


def norm(text: str) -> str:
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def page_containing(source: str, quote: str) -> int | None:
    for i, page in enumerate(source.split("\f"), start=1):
        if quote in norm(page):
            return i
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("claims", nargs="?", default=str(ROOT / "gold" / "claims.jsonl"))
    ap.add_argument("--fix-pages", action="store_true", help="Rewrite PDF page numbers in place")
    args = ap.parse_args()

    claims_path = Path(args.claims)
    claims = [json.loads(line) for line in claims_path.read_text(encoding="utf-8").splitlines() if line.strip()]

    texts = {}
    for doc, path in SOURCES.items():
        if not path.exists():
            print(f"MISSING source text: {path}", file=sys.stderr)
            return 2
        texts[doc] = path.read_text(encoding="utf-8", errors="ignore")

    jsonschema = None
    schema = None
    try:
        import jsonschema as _jsonschema

        jsonschema = _jsonschema
        schema = json.loads((ROOT / "gold" / "schema.json").read_text(encoding="utf-8"))
    except ImportError:
        pass

    failures = 0
    fixed = 0
    by_doc: dict[str, int] = {}
    by_modality: dict[str, int] = {}

    for claim in claims:
        cid = claim["claim_id"]
        doc = claim["doc_id"]
        by_doc[doc] = by_doc.get(doc, 0) + 1
        by_modality[claim["modality"]] = by_modality.get(claim["modality"], 0) + 1

        if jsonschema is not None and schema is not None:
            try:
                jsonschema.validate(claim, schema)
            except Exception as exc:  # noqa: BLE001 - report and continue
                print(f"SCHEMA  {cid}: {getattr(exc, 'message', exc)}")
                failures += 1

        source = texts[doc]
        quote = norm(claim["quote"])
        if quote not in norm(source):
            print(f"QUOTE   {cid}: not found in {doc}")
            print(f"        {claim['quote'][:120]}")
            failures += 1
            continue

        locator = claim.get("locator", {})
        if locator.get("kind") == "pdf":
            computed = page_containing(source, quote)
            declared = locator.get("page")
            if computed is not None and declared != computed:
                print(f"PAGE    {cid}: declared {declared}, computed {computed}")
                if args.fix_pages:
                    locator["page"] = computed
                    fixed += 1
                else:
                    failures += 1

    if args.fix_pages and fixed:
        claims_path.write_text(
            "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in claims),
            encoding="utf-8",
        )
        print(f"fixed {fixed} page number(s)")

    print(f"\n{len(claims)} claims; {failures} failure(s)")
    print("by doc:", dict(sorted(by_doc.items())))
    print("by modality:", dict(sorted(by_modality.items())))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
