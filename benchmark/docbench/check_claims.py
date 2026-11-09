#!/usr/bin/env python3
"""Check DocBench claims against their source documents.

Accepts both claim shapes (see docs/adr/0001-document-first-kernel.md):

  v1  one ``quote`` + one ``locator`` at the top level
  v2  ``evidence``: a non-empty list of ``{quote, locator, role}``

Rules enforced for every evidence span:
  * the quote must exist verbatim in the source text (whitespace-normalised);
  * for PDF sources, the declared page must match the page where the quote occurs;
  * the claim must validate against the schema for its shape when jsonschema is
    installed (v1: gold/schema.json, v2: schemas/claim.v2.schema.json).

Usage:
    python benchmark/docbench/check_claims.py [--fix-pages] [--schema-only] [claims.jsonl]

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
REPO = ROOT.parent.parent

SCHEMAS = {
    1: ROOT / "gold" / "schema.json",
    2: REPO / "schemas" / "claim.v2.schema.json",
}

SOURCES = {
    "D1": PRIVATE / "D1.txt",
    "D2": PRIVATE / "D2.txt",
    "D3": PRIVATE / "D3.txt",
    "D4": PRIVATE / "D4.txt",
    "D5": PRIVATE / "D5.txt",
    "D6": PRIVATE / "D6.txt",
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
    ap.add_argument(
        "--schema-only",
        action="store_true",
        help="Validate JSON schema only; do not require the source texts",
    )
    args = ap.parse_args()

    sys.path.insert(0, str(ROOT))
    from claims_model import evidence_items, load_claims, shape  # local module

    claims_path = Path(args.claims)
    claims = load_claims(claims_path)

    texts = {}
    if not args.schema_only:
        for doc, path in SOURCES.items():
            if not path.exists():
                print(f"MISSING source text: {path}", file=sys.stderr)
                return 2
            texts[doc] = path.read_text(encoding="utf-8", errors="ignore")

    jsonschema = None
    schemas: dict[int, dict] = {}
    try:
        import jsonschema as _jsonschema

        jsonschema = _jsonschema
        for version, path in SCHEMAS.items():
            if path.exists():
                schemas[version] = json.loads(path.read_text(encoding="utf-8"))
    except ImportError:
        pass

    failures = 0
    fixed = 0
    spans = 0
    by_doc: dict[str, int] = {}
    by_modality: dict[str, int] = {}
    by_shape: dict[int, int] = {}

    for claim in claims:
        cid = claim["claim_id"]
        doc = claim["doc_id"]
        version = shape(claim)
        by_shape[version] = by_shape.get(version, 0) + 1
        by_doc[doc] = by_doc.get(doc, 0) + 1
        by_modality[claim["modality"]] = by_modality.get(claim["modality"], 0) + 1

        schema = schemas.get(version)
        if jsonschema is not None and schema is not None:
            try:
                jsonschema.validate(claim, schema)
            except Exception as exc:  # noqa: BLE001 - report and continue
                print(f"SCHEMA  {cid}: {getattr(exc, 'message', exc)}")
                failures += 1

        items = evidence_items(claim)
        spans += len(items)
        if args.schema_only:
            continue

        source = texts[doc]
        for index, item in enumerate(items):
            quote = norm(item["quote"])
            if not quote:
                print(f"EMPTY   {cid}[{index}]: empty quote")
                failures += 1
                continue
            if quote not in norm(source):
                print(f"QUOTE   {cid}[{index}]: not found in {doc}")
                print(f"        {item['quote'][:120]}")
                failures += 1
                continue

            locator = item.get("locator") or {}
            if locator.get("kind") == "pdf":
                computed = page_containing(source, quote)
                declared = locator.get("page")
                if computed is not None and declared != computed:
                    print(f"PAGE    {cid}[{index}]: declared {declared}, computed {computed}")
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

    print(f"\n{len(claims)} claims, {spans} evidence span(s); {failures} failure(s)")
    print("by shape:", {f"v{k}": v for k, v in sorted(by_shape.items())})
    print("by doc:", dict(sorted(by_doc.items())))
    print("by modality:", dict(sorted(by_modality.items())))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
