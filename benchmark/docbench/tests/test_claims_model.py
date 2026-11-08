#!/usr/bin/env python3
"""Tests for the dual-shape claim model (v1 quote/locator, v2 evidence list).

Run from the repository root:
    python -m unittest discover -s benchmark/docbench/tests -v
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

DOCBENCH = Path(__file__).resolve().parents[1]
ROOT = DOCBENCH.parents[1]
sys.path.insert(0, str(DOCBENCH))

from claims_model import (  # noqa: E402
    V1,
    V2,
    evidence_items,
    primary_locator,
    primary_quote,
    quotes,
    shape,
    to_v2,
)

V1_CLAIM = {
    "claim_id": "D1-0001",
    "doc_id": "D1",
    "quote": "The addressee shall send those observations within a time limit.",
    "locator": {"kind": "html", "section_path": ["Chapter IV"], "url": "https://example.org/d1"},
    "statement": "The Commission must give the addressee a time limit.",
    "modality": "obligation",
    "conflicts_with": ["D1-0002"],
    "context": {"source": "example", "jurisdiction": "EU"},
    "confidence": 0.9,
}

V2_CLAIM = {
    "claim_id": "D4-0002",
    "doc_id": "D4",
    "schema_version": 2,
    "statement": "Electronic proposers must submit no later than 2 p.m. on January 22, 2026.",
    "modality": "obligation",
    "evidence": [
        {
            "quote": "Proposers must submit one (1) complete copy no later than 2 p.m. on Thursday, January 22, 2026.",
            "locator": {"kind": "pdf", "page": 5, "section_path": ["3.0 Terms", "3.b electronic submissions"]},
            "role": "supports",
        },
        {
            "quote": "Electronic submissions must be received through eVA.",
            "locator": {"kind": "pdf", "page": 5, "section_path": ["3.0 Terms", "3.b electronic submissions"]},
            "role": "qualifies",
        },
    ],
}


class ShapeTest(unittest.TestCase):
    def test_detects_v1(self) -> None:
        self.assertEqual(shape(V1_CLAIM), V1)

    def test_detects_v2(self) -> None:
        self.assertEqual(shape(V2_CLAIM), V2)

    def test_rejects_claim_with_neither(self) -> None:
        with self.assertRaises(ValueError):
            shape({"claim_id": "D1-0001", "doc_id": "D1"})


class EvidenceAccessTest(unittest.TestCase):
    def test_v1_has_one_supporting_span(self) -> None:
        items = evidence_items(V1_CLAIM)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["role"], "supports")
        self.assertEqual(items[0]["quote"], V1_CLAIM["quote"])
        self.assertEqual(items[0]["locator"], V1_CLAIM["locator"])

    def test_v2_preserves_order_and_roles(self) -> None:
        items = evidence_items(V2_CLAIM)
        self.assertEqual([i["role"] for i in items], ["supports", "qualifies"])
        self.assertEqual(quotes(V2_CLAIM), [i["quote"] for i in V2_CLAIM["evidence"]])

    def test_primary_helpers_use_first_span(self) -> None:
        self.assertEqual(primary_quote(V2_CLAIM), V2_CLAIM["evidence"][0]["quote"])
        self.assertEqual(primary_locator(V2_CLAIM)["page"], 5)

    def test_empty_evidence_list_is_an_error(self) -> None:
        with self.assertRaises(ValueError):
            evidence_items({"claim_id": "D1-0001", "doc_id": "D1", "evidence": []})


class MigrationTest(unittest.TestCase):
    def test_v1_to_v2_is_lossless(self) -> None:
        migrated = to_v2(V1_CLAIM)
        self.assertEqual(migrated["schema_version"], 2)
        self.assertNotIn("quote", migrated)
        self.assertNotIn("locator", migrated)
        self.assertEqual(migrated["evidence"][0]["quote"], V1_CLAIM["quote"])
        self.assertEqual(migrated["evidence"][0]["locator"], V1_CLAIM["locator"])
        self.assertEqual(migrated["evidence"][0]["role"], "supports")
        for key in ("claim_id", "doc_id", "statement", "modality", "context", "confidence", "conflicts_with"):
            self.assertEqual(migrated[key], V1_CLAIM[key])

    def test_migration_is_idempotent(self) -> None:
        once = to_v2(V1_CLAIM)
        twice = to_v2(once)
        self.assertEqual(once, twice)

    def test_no_field_is_dropped(self) -> None:
        migrated = to_v2(V1_CLAIM)
        expected = (set(V1_CLAIM) - {"quote", "locator"}) | {"schema_version", "evidence"}
        self.assertEqual(set(migrated), expected)


class SchemaTest(unittest.TestCase):
    def test_example_file_validates_against_v2(self) -> None:
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema not installed")

        schema = json.loads((ROOT / "schemas" / "claim.v2.schema.json").read_text(encoding="utf-8"))
        example = DOCBENCH / "gold" / "claims.example.jsonl"
        claims = [json.loads(line) for line in example.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertGreater(len(claims), 0)
        for claim in claims:
            jsonschema.validate(claim, schema)

    def test_v1_claim_does_not_validate_against_v2(self) -> None:
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema not installed")

        schema = json.loads((ROOT / "schemas" / "claim.v2.schema.json").read_text(encoding="utf-8"))
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(V1_CLAIM, schema)

    def test_evidence_role_is_constrained(self) -> None:
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema not installed")

        schema = json.loads((ROOT / "schemas" / "claim.v2.schema.json").read_text(encoding="utf-8"))
        broken = json.loads(json.dumps(V2_CLAIM))
        broken["evidence"][0]["role"] = "citation"
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(broken, schema)


if __name__ == "__main__":
    unittest.main()
