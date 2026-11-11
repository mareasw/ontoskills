#!/usr/bin/env python3
"""Tests for the deterministic verifier (ADR 0002, Phase 0).

No model and no corpus: every test pins one rule of the six on a tiny synthetic
source. The agreement number itself is measured on the accepted artifact with
``--verdicts``; it is not a unit test, because it depends on the private corpus.

Run from the repository root:
    python -m unittest discover -s benchmark/docbench/tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

DOCBENCH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DOCBENCH))

import verify_deterministic as vd  # noqa: E402
from verify_claims import SpanIndex  # noqa: E402

PAGE = "The Importer must destroy the records when 3 years old.\fSecond page text."


def span(start: int, text: str, section=None, doc: str = "D1") -> dict:
    return {
        "span_id": f"S{start:04d}",
        "doc_id": doc,
        "paragraph": text,
        "locator": {
            "kind": "pdf",
            "page": 1,
            "section_path": section or ["Retention"],
            "char_start": start,
            "char_end": start + len(text),
        },
    }


def claim(statement: str, spans: list[dict], page: int = 1, section=None) -> dict:
    item = {
        "quote": spans[0]["paragraph"],
        "locator": dict(spans[0]["locator"]),
        "role": "supports",
    }
    item["locator"]["page"] = page
    if section is not None:
        item["locator"]["section_path"] = section
    return {
        "claim_id": "D1-0001",
        "doc_id": "D1",
        "statement": statement,
        "modality": "obligation",
        "evidence": [item],
    }


class WordMatchingTest(unittest.TestCase):
    def test_inflections_match(self):
        for left, right in [
            ("date", "dated"),
            ("party", "parties"),
            ("process", "processed"),
            ("override", "overridden"),
            ("require", "required"),
        ]:
            self.assertTrue(vd.same_word(left, right), f"{left} ~ {right}")

    def test_different_words_do_not_match(self):
        for left, right in [("claim", "clause"), ("importer", "exporter"), ("must", "may")]:
            self.assertFalse(vd.same_word(left, right), f"{left} !~ {right}")

    def test_one_letter_tokens_are_noise(self):
        self.assertEqual(vd.tokens("Importer's 5.1(b)"), ["importer"])


class ModalityTest(unittest.TestCase):
    def test_prohibition_wins_over_obligation(self):
        self.assertEqual(vd.modal_classes("the Importer must not disclose"), {"prohibition"})

    def test_permission_and_obligation_are_distinct(self):
        self.assertEqual(vd.modal_classes("may disclose"), {"permission"})
        self.assertEqual(vd.modal_classes("must disclose"), {"obligation"})

    def test_imperative_has_no_class(self):
        self.assertEqual(vd.modal_classes("Destroy when 3 years old"), set())


class VerifyTest(unittest.TestCase):
    def setUp(self):
        self.sources = [span(0, "The Importer must destroy the records when 3 years old.")]
        self.spans = SpanIndex(self.sources)
        self.texts = {"D1": PAGE}

    def test_supported_claim_is_ok(self):
        out = vd.verify(claim("The Importer must destroy the records.", self.sources), self.spans, self.texts)
        self.assertEqual(out["verdict"], "ok", out)

    def test_quote_absent_from_source_is_no(self):
        bad = span(0, "This sentence is not in the source.")
        out = vd.verify(claim("This sentence is not in the source.", [bad]), SpanIndex([bad]), self.texts)
        self.assertEqual(out["verdict"], "no")
        self.assertIn("not in the source", " ".join(out["reasons"]))

    def test_wrong_page_is_no(self):
        out = vd.verify(claim("The Importer must destroy the records.", self.sources, page=2), self.spans, self.texts)
        self.assertEqual(out["verdict"], "no")
        self.assertIn("page", " ".join(out["reasons"]))

    def test_section_mismatch_is_no(self):
        out = vd.verify(
            claim("The Importer must destroy the records.", self.sources, section=["Something else"]),
            self.spans,
            self.texts,
        )
        self.assertEqual(out["verdict"], "no")
        self.assertIn("section", " ".join(out["reasons"]))

    def test_paraphrase_inside_tolerance_is_ok(self):
        # 1 of 6 content tokens unattested = 17%, under the 25% allowance.
        out = vd.verify(
            claim("The Importer must destroy the records promptly.", self.sources), self.spans, self.texts
        )
        self.assertEqual(out["verdict"], "ok", out)

    def test_paraphrase_beyond_tolerance_is_weak(self):
        out = vd.verify(
            claim("The Importer must destroy the files immediately without delay.", self.sources),
            self.spans,
            self.texts,
        )
        self.assertEqual(out["verdict"], "weak", out)
        self.assertIn("unattested", " ".join(out["reasons"]))

    def test_missing_number_is_no(self):
        out = vd.verify(claim("The Importer must destroy the records when 7 years old.", self.sources), self.spans, self.texts)
        self.assertEqual(out["verdict"], "no")
        self.assertIn("numbers", " ".join(out["reasons"]))

    def test_modality_conflict_is_a_note_not_a_verdict(self):
        # Evidence says "must"; a statement claiming permission is annotated but
        # kept `ok`: measured on the accepted artifact, a modality verdict cost
        # 8 false `weak` and caught no census `weak`.
        out = vd.verify(claim("The Importer may destroy the records.", self.sources), self.spans, self.texts)
        self.assertEqual(out["verdict"], "ok", out)
        self.assertTrue(out["notes"])


class AgreementTest(unittest.TestCase):
    def test_agreement_counts_and_confusion(self):
        rows = [
            {"claim_id": "a", "doc_id": "D1", "verdict": "ok", "census": "ok"},
            {"claim_id": "b", "doc_id": "D1", "verdict": "weak", "census": "ok"},
            {"claim_id": "c", "doc_id": "D2", "verdict": "ok", "census": "weak"},
        ]
        out = vd.agreement(rows)
        self.assertEqual(out["claims"], 3)
        self.assertEqual(out["agree"], 1)
        self.assertEqual(out["by_verdict"]["weak"], {"ok": 1})
        self.assertEqual(out["by_doc"]["D1"], {"claims": 2, "agree": 1})
        self.assertEqual([row["claim_id"] for row in out["disagreements"]], ["b", "c"])


if __name__ == "__main__":
    unittest.main()
