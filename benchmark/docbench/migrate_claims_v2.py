#!/usr/bin/env python3
"""Migrate a DocBench claim file from the v1 shape to the v2 shape.

v1: one ``quote`` + one ``locator`` at the top level.
v2: ``evidence``: a non-empty list of ``{quote, locator, role}``.

The migration is lossless and mechanical: every v1 claim becomes a v2 claim with
exactly one evidence span whose ``role`` is ``supports``. Claims already in v2
pass through unchanged. Nothing is invented, re-quoted or re-ordered.

Usage:
    python benchmark/docbench/migrate_claims_v2.py gold/claims.jsonl -o gold/claims.v2.jsonl
    python benchmark/docbench/migrate_claims_v2.py gold/claims.example.jsonl --in-place
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from claims_model import load_claims, shape, to_v2  # noqa: E402


def ordered(claim: dict) -> dict:
    """Keep a stable, readable field order in the output file."""
    head = ("claim_id", "doc_id", "schema_version", "statement")
    middle = ("subject", "predicate", "object", "polarity", "modality", "actor", "deadline", "conditions")
    tail = ("evidence", "conflicts_with", "context", "confidence", "notes")
    out = {key: claim[key] for key in head if key in claim}
    out.update({key: claim[key] for key in middle if key in claim})
    out.update({key: claim[key] for key in tail if key in claim})
    leftover = {k: v for k, v in claim.items() if k not in out}
    out.update(leftover)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="v1 or v2 claim file (JSONL)")
    ap.add_argument("-o", "--output", help="output path (default: <input>.v2.jsonl)")
    ap.add_argument("--in-place", action="store_true", help="rewrite the input file")
    args = ap.parse_args()

    source = Path(args.input)
    claims = load_claims(source)
    converted = [ordered(to_v2(claim)) for claim in claims]

    before = {shape(claim) for claim in claims}
    target = source if args.in_place else Path(args.output or source.with_suffix(".v2.jsonl"))
    target.write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in converted), encoding="utf-8")

    spans = sum(len(c["evidence"]) for c in converted)
    print(f"{len(claims)} claims ({'+'.join(f'v{v}' for v in sorted(before))}) -> {target}")
    print(f"{spans} evidence span(s); schema_version=2")
    if args.in_place:
        print("note: the input file was rewritten in place")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
