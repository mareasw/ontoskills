#!/usr/bin/env python3
"""Tests for the span-first claim compiler.

The compiler's guarantee is structural: the model may only reference span ids,
so the emitted quote is always the segmenter's text. These tests pin the parts
that make that true, without calling a model.

Run from the repository root:
    python -m unittest discover -s benchmark/docbench/tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

DOCBENCH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DOCBENCH))

import compile_claims as cc  # noqa: E402

DOC = """\
REGULATION ON THINGS

The addressee shall send written observations within a time limit set by the Commission that shall be no less than 21 days.

Response time : 1 hour
Response time : 4 hours
Level 1 - Critical

Access to the file shall not be granted before the notification of the preliminary findings.
\f
The Commission may adopt a decision within five years from the day on which the conduct was carried out, including for continuing or repeated conduct.
"""


class SegmentTest(unittest.TestCase):
    def setUp(self) -> None:
        self.spans = cc.segment(DOC, "D4", min_chars=60)

    def test_pages_are_counted(self) -> None:
        self.assertEqual({s["locator"]["page"] for s in self.spans}, {1, 2})

    def test_heading_becomes_section_path(self) -> None:
        first = self.spans[0]
        self.assertEqual(first["locator"]["section_path"], ["REGULATION ON THINGS"])

    def test_short_tabular_lines_are_merged_not_dropped(self) -> None:
        joined = " ".join(s["paragraph"] for s in self.spans)
        self.assertIn("Response time : 1 hour", joined)
        self.assertIn("Response time : 4 hours", joined)

    def test_symbols_only_lines_are_not_spans(self) -> None:
        for span in self.spans:
            self.assertRegex(span["paragraph"], r"[A-Za-z]{3,}")

    def test_every_span_has_a_locator(self) -> None:
        for span in self.spans:
            locator = span["locator"]
            self.assertIn("kind", locator)
            self.assertEqual(locator["url"], cc.DOCS["D4"]["url"])
            self.assertGreaterEqual(locator["page"], 1)

    def test_span_ids_are_unique_and_ordered(self) -> None:
        ids = [s["span_id"] for s in self.spans]
        self.assertEqual(ids, sorted(ids))
        self.assertEqual(len(ids), len(set(ids)))

    def test_quotes_are_verbatim_after_whitespace_normalisation(self) -> None:
        source = cc.norm(DOC)
        for span in self.spans:
            self.assertIn(cc.norm(span["paragraph"]), source)


class ParseTest(unittest.TestCase):
    def test_plain_array(self) -> None:
        self.assertEqual(cc.parse_claims('[{"statement": "x"}]'), [{"statement": "x"}])

    def test_fenced_array(self) -> None:
        reply = '```json\n[{"statement": "x"}]\n```'
        self.assertEqual(cc.parse_claims(reply), [{"statement": "x"}])

    def test_array_inside_prose(self) -> None:
        reply = 'Here you go:\n[{"statement": "x"}]\nHope that helps.'
        self.assertEqual(cc.parse_claims(reply), [{"statement": "x"}])

    def test_single_object(self) -> None:
        self.assertEqual(cc.parse_claims('{"statement": "x"}'), [{"statement": "x"}])

    def test_garbage_is_empty_not_an_exception(self) -> None:
        self.assertEqual(cc.parse_claims("I cannot help with that."), [])
        self.assertEqual(cc.parse_claims("[not json"), [])

    def test_missing_comma_between_objects_is_repaired(self) -> None:
        reply = '[{"statement": "a"}\n{"statement": "b"}]'
        self.assertEqual([c["statement"] for c in cc.parse_claims(reply)], ["a", "b"])

    def test_trailing_comma_is_repaired(self) -> None:
        self.assertEqual([c["statement"] for c in cc.parse_claims('[{"statement": "a"},]')], ["a"])

    def test_truncated_reply_keeps_complete_objects(self) -> None:
        # The gateway sometimes returns finish=stop with the content cut in the
        # middle of the last object. The complete ones are still usable.
        reply = '[{"span_ids": ["S0001"], "statement": "a"}, {"span_ids": ["S0002"], "stat'
        self.assertEqual([c["statement"] for c in cc.parse_claims(reply)], ["a"])

    def test_truncated_without_any_complete_object_is_empty(self) -> None:
        self.assertEqual(cc.parse_claims('[{"span_ids": ["S00'), [])

    def test_repair_does_not_invent_objects(self) -> None:
        # Nothing complete, nothing returned: salvage must not guess.
        self.assertEqual(cc.repair_json_array("no array here"), [])


class BuildClaimTest(unittest.TestCase):
    def setUp(self) -> None:
        self.spans = cc.segment(DOC, "D4", min_chars=60)
        self.by_id = {s["span_id"]: s for s in self.spans}
        self.first_id = self.spans[0]["span_id"]

    def test_quote_is_copied_from_the_span(self) -> None:
        claim = cc.build_claim(
            {"span_ids": [self.first_id], "statement": "The Commission must give at least 21 days.", "modality": "obligation"},
            self.by_id,
            "D4",
            1,
        )
        self.assertIsNotNone(claim)
        self.assertEqual(claim["evidence"][0]["quote"], self.by_id[self.first_id]["paragraph"])
        self.assertEqual(claim["evidence"][0]["role"], "supports")
        self.assertEqual(claim["claim_id"], "D4-0001")

    def test_unknown_span_id_is_rejected(self) -> None:
        claim = cc.build_claim(
            {"span_ids": ["S9999"], "statement": "The Commission must give at least 21 days.", "modality": "obligation"},
            self.by_id,
            "D4",
            1,
        )
        self.assertIsNone(claim)

    def test_short_statement_is_rejected(self) -> None:
        claim = cc.build_claim(
            {"span_ids": [self.first_id], "statement": "21 days", "modality": "obligation"},
            self.by_id,
            "D4",
            1,
        )
        self.assertIsNone(claim)

    def test_unknown_modality_falls_back_to_a_valid_one(self) -> None:
        claim = cc.build_claim(
            {"span_ids": [self.first_id], "statement": "The Commission must give at least 21 days.", "modality": "rule"},
            self.by_id,
            "D4",
            1,
        )
        self.assertIn(claim["modality"], cc.MODALITIES)

    def test_string_span_id_and_conditions_are_normalised(self) -> None:
        claim = cc.build_claim(
            {
                "span_ids": self.first_id,
                "statement": "The Commission must give at least 21 days to submit observations.",
                "modality": "obligation",
                "conditions": ["  the addressee  has received the findings ", ""],
            },
            self.by_id,
            "D4",
            1,
        )
        self.assertEqual(len(claim["evidence"]), 1)
        self.assertEqual(claim["conditions"], ["the addressee has received the findings"])

    def test_two_spans_are_kept_in_order_and_deduplicated(self) -> None:
        second = self.spans[1]["span_id"]
        claim = cc.build_claim(
            {
                "span_ids": [self.first_id, second, self.first_id],
                "statement": "A rule with an exception that scopes it.",
                "modality": "obligation",
            },
            self.by_id,
            "D4",
            1,
        )
        self.assertEqual([e["quote"] for e in claim["evidence"]],
                         [self.by_id[self.first_id]["paragraph"], self.by_id[second]["paragraph"]])

    def test_output_is_v2(self) -> None:
        claim = cc.build_claim(
            {"span_ids": [self.first_id], "statement": "The Commission must give at least 21 days.", "modality": "obligation"},
            self.by_id,
            "D4",
            1,
        )
        self.assertEqual(claim["schema_version"], 2)
        self.assertNotIn("quote", claim)
        self.assertIn("context", claim)


class ConflictTest(unittest.TestCase):
    def _claims(self) -> list[dict]:
        return [
            {"claim_id": "D4-0001", "statement": "Sealed proposals are due 12 February 2026."},
            {"claim_id": "D4-0002", "statement": "Electronic proposals are due 22 January 2026."},
            {"claim_id": "D4-0003", "statement": "Proposers must submit four copies."},
        ]

    def test_pairs_are_linked_in_both_directions(self) -> None:
        claims = self._claims()
        linked = cc.link_conflicts(claims, '[["D4-0001","D4-0002"]]')
        self.assertEqual(linked, 1)
        self.assertEqual(claims[0]["conflicts_with"], ["D4-0002"])
        self.assertEqual(claims[1]["conflicts_with"], ["D4-0001"])

    def test_unknown_and_self_pairs_are_dropped(self) -> None:
        self.assertEqual(cc.parse_conflicts('[["D4-0001","D4-9999"],["D4-0001","D4-0001"]]',
                                            {"D4-0001", "D4-0002"}), [])

    def test_duplicate_pairs_are_collapsed_and_symmetry_enforced(self) -> None:
        pairs = cc.parse_conflicts('[["D4-0002","D4-0001"],["D4-0001","D4-0002"]]',
                                   {"D4-0001", "D4-0002"})
        self.assertEqual(pairs, [("D4-0001", "D4-0002")])

    def test_empty_reply_is_no_conflicts(self) -> None:
        self.assertEqual(cc.parse_conflicts("[]", {"D4-0001"}), [])
        self.assertEqual(cc.parse_conflicts("no conflicts", {"D4-0001"}), [])

    def test_candidates_prefer_claims_about_the_same_thing(self) -> None:
        claims = self._claims() + [
            {"claim_id": "D4-0004", "statement": "The county shall publish the notice on its website."},
            {"claim_id": "D4-0005", "statement": "The county shall advertise the notice in a newspaper."},
        ]
        pairs = cc.conflict_candidates(claims)
        # The two deadline claims overlap the most, so they must be offered.
        self.assertIn(("D4-0001", "D4-0002"), pairs)
        # A claim about something unrelated must not be paired with everything.
        self.assertLessEqual(len(pairs), 5)

    def test_candidates_respect_k_and_floor(self) -> None:
        claims = self._claims()
        self.assertEqual(cc.conflict_candidates(claims, k=1), [("D4-0001", "D4-0002")])
        # A floor above every score yields no pairs at all.
        self.assertEqual(cc.conflict_candidates(claims, floor=0.99), [])

    def test_pairs_prompt_is_numbered_from_one(self) -> None:
        claims = self._claims()
        pairs = [("D4-0001", "D4-0002"), ("D4-0002", "D4-0003")]
        prompt = cc.pairs_prompt(claims, pairs)
        self.assertIn("1. [D4-0001]", prompt)
        self.assertIn("2. [D4-0002]", prompt)
        self.assertIn("pair numbers", prompt)

    def test_pair_indices_are_validated(self) -> None:
        self.assertEqual(cc.parse_pair_indices("[2,1]", 3), [2, 1])
        # Out of range, non-numeric and duplicate entries are dropped.
        self.assertEqual(cc.parse_pair_indices("[0,4,2,2,\"x\"]", 3), [2])
        self.assertEqual(cc.parse_pair_indices("none", 3), [])
        self.assertEqual(cc.parse_pair_indices("```json\n[1]\n```", 3), [1])


class EstimateTest(unittest.TestCase):
    def test_estimate_counts_calls_and_tokens(self) -> None:
        spans = cc.segment(DOC, "D4", min_chars=60)
        chunks = cc.chunk(spans, size=2, overlap=0)
        est = cc.estimate(spans, chunks, None)
        self.assertEqual(est["extraction_calls"], len(chunks))
        self.assertEqual(est["calls"], est["extraction_calls"] + est["conflict_calls"])
        self.assertGreater(est["conflict_calls"], 0)
        self.assertGreater(est["input_tokens_est"], 0)
        self.assertGreater(est["output_tokens_est"], 0)

    def test_chunking_covers_every_span(self) -> None:
        spans = cc.segment(DOC, "D4", min_chars=60)
        chunks = cc.chunk(spans, size=2, overlap=1)
        covered = {s["span_id"] for block in chunks for s in block}
        self.assertEqual(covered, {s["span_id"] for s in spans})


if __name__ == "__main__":
    unittest.main()
