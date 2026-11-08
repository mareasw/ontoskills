#!/usr/bin/env python3
"""Read a claim in either the v1 or the v2 shape.

v1 (2026-11-07 run): a claim has one ``quote`` and one ``locator`` at the top
level. v2 (ADR 0001): a claim has ``evidence``: a non-empty list of
``{quote, locator, role}`` items, so a two-sided conflict or a rule with an
exception can carry every span it needs.

Everything that needs a claim's text goes through :func:`evidence_items`, so the
rest of the benchmark never branches on the shape.
"""

from __future__ import annotations

import json
from pathlib import Path

V1 = 1
V2 = 2

ROLES = ("supports", "qualifies", "contradicts")


def load_claims(path: str | Path) -> list[dict]:
    """Load a JSONL claim file (either shape)."""
    text = Path(path).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def shape(claim: dict) -> int:
    """Return 1 or 2, and fail loudly if the claim is neither."""
    if "evidence" in claim:
        return V2
    if "quote" in claim:
        return V1
    raise ValueError(f"claim {claim.get('claim_id', '?')}: neither 'evidence' nor 'quote' present")


def evidence_items(claim: dict) -> list[dict]:
    """Every evidence span of a claim, always as a list of dicts with role."""
    if shape(claim) == V2:
        items = claim["evidence"]
        if not isinstance(items, list) or not items:
            raise ValueError(f"claim {claim.get('claim_id', '?')}: evidence must be a non-empty list")
        return items
    return [{"quote": claim["quote"], "locator": claim.get("locator", {}), "role": "supports"}]


def quotes(claim: dict) -> list[str]:
    return [item["quote"] for item in evidence_items(claim)]


def primary_quote(claim: dict) -> str:
    return quotes(claim)[0]


def primary_locator(claim: dict) -> dict:
    return evidence_items(claim)[0].get("locator", {}) or {}


def to_v2(claim: dict) -> dict:
    """Return a v2 copy of a claim. Idempotent for claims already in v2."""
    if shape(claim) == V2:
        out = dict(claim)
        out.setdefault("schema_version", 2)
        for item in out["evidence"]:
            item.setdefault("role", "supports")
        return out
    out = {k: v for k, v in claim.items() if k not in {"quote", "locator"}}
    out["schema_version"] = 2
    out["evidence"] = [
        {"quote": claim["quote"], "locator": claim.get("locator", {}), "role": "supports"}
    ]
    return out
