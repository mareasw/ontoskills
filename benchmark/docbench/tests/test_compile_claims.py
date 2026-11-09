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


class HeadingTest(unittest.TestCase):
    def test_all_caps_label_with_qualifier_is_a_table_label(self) -> None:
        for label in ("HIGH (Orange)", "CRITICAL (Red)", "LOW (Blue)", "MEDIUM (Yellow)"):
            self.assertTrue(cc.is_table_label(label), label)
            self.assertTrue(cc.looks_like_heading(label), label)

    def test_plain_all_caps_heading_is_not_a_table_label(self) -> None:
        # D4 is full of these; treating them as labels swallowed whole sections.
        for line in ("PURPOSE", "CRITERIA", "EXHIBIT A", "TABLE OF CONTENTS"):
            self.assertFalse(cc.is_table_label(line), line)
            self.assertTrue(cc.looks_like_heading(line), line)

    def test_sentence_ending_in_a_parenthetical_is_body(self) -> None:
        line = "Notify regulators within required timeframe (typically 72 hours)"
        self.assertFalse(cc.is_table_label(line))
        self.assertFalse(cc.looks_like_heading(line))

    def test_address_fragment_is_body(self) -> None:
        self.assertFalse(cc.looks_like_heading("P.O. Box 1998"))


TABLE_DOC = """\
Incident Playbook

Severity Classification

CRITICAL (Red)

System compromise in progress

Response time : 1 hour

HIGH (Orange)

Active campaign detected

Response time : 4 hours

Incident Response Workflow

Detect the incident and classify its severity before anything else happens.
"""


class SeverityTableTest(unittest.TestCase):
    def setUp(self) -> None:
        self.spans = cc.segment(TABLE_DOC, "D3", min_chars=60)

    def test_band_and_its_response_time_share_one_span(self) -> None:
        hour = [s for s in self.spans if "Response time : 1 hour" in s["paragraph"]]
        self.assertEqual(len(hour), 1)
        # The band must be in the same span, or the value inherits its
        # neighbour's severity label.
        self.assertTrue(hour[0]["paragraph"].startswith("CRITICAL (Red)"))
        self.assertNotIn("HIGH", hour[0]["paragraph"])

    def test_each_band_keeps_its_own_rows(self) -> None:
        four = [s for s in self.spans if "Response time : 4 hours" in s["paragraph"]]
        self.assertEqual(len(four), 1)
        self.assertTrue(four[0]["paragraph"].startswith("HIGH (Orange)"))
        self.assertIn("Active campaign detected", four[0]["paragraph"])

    def test_a_real_heading_closes_the_block(self) -> None:
        # The heading itself is section metadata, not span text: the body that
        # follows it must be clean of table rows.
        body = [s for s in self.spans if s["paragraph"].startswith("Detect the incident")]
        self.assertEqual(len(body), 1)
        self.assertNotIn("Response time", body[0]["paragraph"])
        self.assertEqual(body[0]["locator"]["section_path"], ["Incident Response Workflow"])

    def test_table_text_is_still_verbatim(self) -> None:
        flat = cc.norm(TABLE_DOC)
        for span in self.spans:
            self.assertIn(cc.norm(span["paragraph"]), flat)


GLOSSARY_DOC = """\
Table 1: Definitions

Adequate
Country

A third country, or a territory, which the Secretary of State has specified by regulations.

Special Category
Data

Data described in the UK GDPR, together with criminal conviction or criminal offence data.
"""

KEY_VALUE_DOC = """\
Table 2: Transfer Details

UK country's law that governs the IDTA:

England and Wales

The status of the Exporter

In relation to the Processing of the Transferred Data:
Exporter is a Controller
"""

STATUS_DOC = """\
Table 4: Status

Status

Controller

The Importer may process the data only as instructed by the Exporter and must keep a written record of every transfer it makes.
"""


class KeyValueTableTest(unittest.TestCase):
    """The key/value table branch (PREFLIGHT.md §10.7(e)(i)).

    Three properties, each stated on synthetic text so no document's
    vocabulary is encoded: a label that wraps is one label, a label and its
    value are one quotable row, and a value never heads unrelated text.
    """

    def test_wrapped_label_becomes_one_section(self) -> None:
        spans = cc.segment(GLOSSARY_DOC, "D4", min_chars=60)
        paths = [s["locator"]["section_path"] for s in spans]
        self.assertIn(["Adequate Country"], paths)
        self.assertIn(["Special Category Data"], paths)
        # The value is still its own span, so it stays quotable.
        values = [s for s in spans if s["paragraph"].startswith("A third country")]
        self.assertEqual(len(values), 1)
        self.assertEqual(values[0]["locator"]["section_path"], ["Adequate Country"])

    def test_key_and_value_are_quotable_together(self) -> None:
        spans = cc.segment(KEY_VALUE_DOC, "D4", min_chars=60)
        rows = [
            s
            for s in spans
            if "UK country's law that governs the IDTA: England and Wales"
            in s["paragraph"]
        ]
        self.assertEqual(len(rows), 1)

    def test_assertion_is_a_value_not_a_section(self) -> None:
        spans = cc.segment(KEY_VALUE_DOC, "D4", min_chars=60)
        rows = [s for s in spans if "Exporter is a Controller" in s["paragraph"]]
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0]["locator"]["section_path"], ["The status of the Exporter"]
        )

    def test_a_value_does_not_head_the_next_block(self) -> None:
        spans = cc.segment(STATUS_DOC, "D4", min_chars=60)
        body = [s for s in spans if s["paragraph"].startswith("The Importer may process")]
        self.assertEqual(len(body), 1)
        self.assertEqual(body[0]["locator"]["section_path"], ["Status"])

    def test_table_text_is_still_verbatim(self) -> None:
        for doc in (GLOSSARY_DOC, KEY_VALUE_DOC, STATUS_DOC):
            flat = cc.norm(doc)
            for span in cc.segment(doc, "D4", min_chars=60):
                self.assertIn(cc.norm(span["paragraph"]), flat)


class KeyValueRegionTest(unittest.TestCase):
    """The region detector uses text properties, never a document's words."""

    def test_caption_opens_a_region(self) -> None:
        flags = cc.kv_region_lines(
            ["Table 1: Definitions", "", "Alpha", "", "One thing.", ""]
        )
        self.assertTrue(flags[0])
        self.assertTrue(flags[2])
        self.assertTrue(flags[4])

    def test_caption_region_stops_at_a_part_heading(self) -> None:
        lines = [
            "Table 3: Data",
            "",
            "Alpha",
            "",
            "One thing.",
            "",
            "Part 2: Other Rules",
            "",
            "This part contains general obligations for every party.",
        ]
        flags = cc.kv_region_lines(lines)
        self.assertTrue(flags[0])
        self.assertFalse(any(flags[6:]))

    def test_dense_colon_cells_open_a_region(self) -> None:
        lines = [
            "Alpha:",
            "",
            "One.",
            "",
            "Beta:",
            "",
            "Two.",
            "",
            "Gamma:",
            "",
            "Three.",
            "",
            "Delta:",
            "",
            "Four.",
        ]
        flags = cc.kv_region_lines(lines)
        self.assertTrue(flags[0])
        self.assertTrue(flags[8])
        self.assertTrue(flags[12])

    def test_repeated_header_pair_opens_a_region(self) -> None:
        lines = []
        for term in ("Alpha", "Beta", "Gamma"):
            lines += ["Word or Phrase", "", "Legal definition", "", term, "", "Value.", ""]
        flags = cc.kv_region_lines(lines)
        self.assertTrue(flags[0])  # the repeated header itself
        self.assertTrue(flags[4])  # Alpha
        self.assertTrue(flags[12])  # Beta
        self.assertTrue(flags[20])  # Gamma

    def test_plain_prose_has_no_region(self) -> None:
        self.assertFalse(any(cc.kv_region_lines(DOC.split("\n"))))
        self.assertFalse(any(cc.kv_region_lines(TABLE_DOC.split("\n"))))


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


class DedupeTest(unittest.TestCase):
    def _claim(self, cid: str, doc: str, statement: str, quote: str = "q") -> dict:
        return {
            "claim_id": cid,
            "doc_id": doc,
            "statement": statement,
            "modality": "obligation",
            "evidence": [{"quote": quote, "locator": {"page": 1}, "role": "supports"}],
        }

    def test_paraphrase_of_the_same_rule_is_merged(self) -> None:
        claims = [
            self._claim("D4-0001", "D4", "The Firm shall maintain automobile liability of no less than $1,000,000.", "a"),
            self._claim("D4-0002", "D4", "The Firm must maintain automobile liability of no less than $1,000,000.", "b"),
        ]
        kept, merged = cc.dedupe_claims(claims)
        self.assertEqual(merged, 1)
        self.assertEqual(len(kept), 1)
        # A merge must not delete evidence: both quotes are still there.
        self.assertEqual({e["quote"] for e in kept[0]["evidence"]}, {"a", "b"})
        self.assertEqual(kept[0]["claim_id"], "D4-0001")

    def test_different_rules_are_kept(self) -> None:
        claims = [
            self._claim("D4-0001", "D4", "Proposals are due on February 12, 2026 at 2 p.m."),
            self._claim("D4-0002", "D4", "The County shall publish the notice on its website."),
        ]
        kept, merged = cc.dedupe_claims(claims)
        self.assertEqual(merged, 0)
        self.assertEqual(len(kept), 2)

    def test_the_same_rule_in_two_documents_is_not_merged(self) -> None:
        claims = [
            self._claim("D4-0001", "D4", "The Firm shall maintain automobile liability of no less than $1,000,000."),
            self._claim("D2-0001", "D2", "The Firm shall maintain automobile liability of no less than $1,000,000."),
        ]
        kept, merged = cc.dedupe_claims(claims)
        self.assertEqual(merged, 0)
        self.assertEqual(len(kept), 2)

    def test_missing_fields_are_filled_from_the_absorbed_claim(self) -> None:
        first = self._claim("D4-0001", "D4", "The Firm shall maintain automobile liability of no less than $1,000,000.")
        second = self._claim("D4-0002", "D4", "The Firm must maintain automobile liability of no less than $1,000,000.")
        second["deadline"] = "during the term of the contract"
        kept, _ = cc.dedupe_claims([first, second])
        self.assertEqual(kept[0]["deadline"], "during the term of the contract")

    def test_output_is_sorted_and_stable(self) -> None:
        claims = [
            self._claim("D2-0002", "D2", "A rule about something entirely different here."),
            self._claim("D1-0003", "D1", "Another rule about something else entirely."),
        ]
        kept, _ = cc.dedupe_claims(claims)
        self.assertEqual([c["claim_id"] for c in kept], ["D1-0003", "D2-0002"])


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
