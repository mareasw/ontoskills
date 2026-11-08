#!/usr/bin/env python3
"""Tests for the baseline runner's prompt and citation plumbing.

No model runs here: these pin the parts that decide what the model is asked and
how its answer is checked, so a change to either cannot silently move a score.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

DOCBENCH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DOCBENCH))

import run_baselines as rb  # noqa: E402


CLAIM = {
    "claim_id": "D1-0001",
    "doc_id": "D1",
    "statement": "The Commission may terminate the appointment.",
    "modality": "permission",
    "actor": "Commission",
    "evidence": [
        {
            "quote": "The Commission may terminate the appointment of the expert when:",
            "locator": {"section_path": ["Chapter II"]},
            "role": "supports",
        }
    ],
}

DOCUMENT = "Article 4\nThe Commission may terminate the appointment of the expert when:\nMore text."


class CitationCheckTest(unittest.TestCase):
    def test_exact_quote_is_verbatim(self) -> None:
        self.assertTrue(rb.citation_is_verbatim("The Commission may terminate", DOCUMENT))

    def test_whitespace_and_typography_are_normalised(self) -> None:
        document = "Please submit  the proposal\u2019s cover page today."
        self.assertTrue(rb.citation_is_verbatim("Please submit the proposal's cover page", document))

    def test_paraphrase_is_not_verbatim(self) -> None:
        self.assertFalse(rb.citation_is_verbatim("The Commission can end the appointment", DOCUMENT))

    def test_empty_citation_is_never_verbatim(self) -> None:
        self.assertFalse(rb.citation_is_verbatim("", DOCUMENT))
        self.assertFalse(rb.citation_is_verbatim("   ", DOCUMENT))

    def test_retry_prompt_quotes_the_rejected_text(self) -> None:
        prompt = rb.citation_retry_prompt("CONTEXT:\nx\n\nQUESTION: y", "a paraphrase")
        self.assertIn("a paraphrase", prompt)
        self.assertIn("keeping the answer unchanged", prompt)
        self.assertIn("never copy the claim statement", prompt)


class ContextTest(unittest.TestCase):
    def test_claims_context_carries_statement_and_quote(self) -> None:
        context, meta = rb.build_context("B2", "D1", "terminate?", [CLAIM], DOCUMENT)
        self.assertEqual(meta["mode"], "all_claims")
        self.assertIn("[D1-0001] The Commission may terminate the appointment.", context)
        self.assertIn("QUOTE: The Commission may terminate the appointment of the expert when:", context)

    def test_paragraph_context_has_no_claims(self) -> None:
        context, meta = rb.build_context("B1", "D1", "terminate?", [CLAIM], DOCUMENT)
        self.assertEqual(meta["kind"], "bm25_paragraphs")
        self.assertNotIn("QUOTE:", context)


class ParseAnswerTest(unittest.TestCase):
    def test_json_object(self) -> None:
        answer, citation, ids = rb.parse_answer(
            json.dumps({"answer": "Yes", "citation": "q", "claim_ids": ["D1-0001"]})
        )
        self.assertEqual((answer, citation, ids), ("Yes", "q", ["D1-0001"]))

    def test_fenced_json(self) -> None:
        answer, _, _ = rb.parse_answer('```json\n{"answer": "No", "citation": ""}\n```')
        self.assertEqual(answer, "No")

    def test_unparseable_text_is_the_answer(self) -> None:
        answer, citation, ids = rb.parse_answer("just prose")
        self.assertEqual((answer, citation, ids), ("just prose", "", []))


if __name__ == "__main__":
    unittest.main()
