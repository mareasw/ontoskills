#!/usr/bin/env python3
"""Tests for table-record segmentation (PREFLIGHT.md §10.7(b)).

D6's operative content is an item-numbered table. The block segmenter treated
the first line of a disposition cell ("Destroy 2 years") as a heading, so the
instruction never entered a span, and the previous row's authority stayed on the
heading stack. These tests pin the record path without calling a model.

Run from the repository root:
    python -m unittest discover -s benchmark/docbench/tests -v
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

DOCBENCH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DOCBENCH))

import compile_claims as cc  # noqa: E402


def norm(text: str) -> str:
    text = text.replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')
    return re.sub(r"\s+", " ", text).strip()


# A three-record item table in the shape D6 arrives in: column-major cells, the
# disposition prefix on its own line, the authority before the next key.
TABLE_DOC = """\
General Records Schedule 1.1

Item

Records Description

Disposition
Instruction

001

First record description.
Temporary.
Destroy when 3
years old.

DAA-GRS2016-00010001

010

Second record description.
Temporary.
Destroy 6 years
after final payment.

DAA-GRS2013-00030001
\f
Item

Records Description

Disposition
Instruction

011

Third record description.
Destroy when no
longer required.

DAA-GRS2013-00030002
"""

# A numbered contract: identical line shape to an item table, but the keys are
# a dotted hierarchy. It must keep the block path.
CLAUSE_DOC = """\
AGREEMENT

1.
Preamble that is long enough to be a real block of text in this document.

1.1
First clause text that is long enough to be a real block here.

1.2
Second clause text that is long enough to be a real block here.

2.
Third clause text that is long enough to be a real block here.

2.1
Fourth clause text that is long enough to be a real block here.
"""


class RecordDetectionTest(unittest.TestCase):
    def test_flat_item_keys_are_detected(self) -> None:
        keys = cc.record_key_lines(TABLE_DOC)
        self.assertEqual([TABLE_DOC.split("\n")[i].strip() for i in keys],
                         ["001", "010", "011"])

    def test_dotted_hierarchy_is_not_a_record_table(self) -> None:
        self.assertEqual(cc.record_key_lines(CLAUSE_DOC), [])

    def test_printed_page_number_is_not_a_key(self) -> None:
        doc = "Body one.\n1\n\fBody two.\n2\n\fBody three.\n3\n"
        self.assertEqual(cc.record_key_lines(doc), [])

    def test_repeated_token_is_not_a_key(self) -> None:
        doc = (
            "Intro.\n41T\nbody\n010\nfirst record\n41T\nbody\n"
            "020\nsecond record\n030\nthird record\n"
        )
        keys = [doc.split("\n")[i].strip() for i in cc.record_key_lines(doc)]
        self.assertNotIn("41T", keys)
        self.assertIn("030", keys)

    def test_numbered_bibliography_is_not_a_record_table(self) -> None:
        doc = (
            "References\n1\nAuthor A (2026). First paper.\n2\n"
            "Author B (2026). Second paper.\n3\nAuthor C (2026). Third paper.\n"
        )
        self.assertEqual(cc.record_key_lines(doc), [])

    def test_consecutive_padded_keys_are_still_a_list(self) -> None:
        doc = "001\nfirst\n002\nsecond\n003\nthird\n"
        self.assertEqual(cc.record_key_lines(doc), [])

    def test_fewer_than_three_keys_is_not_a_table(self) -> None:
        doc = "001\nfirst record\n010\nsecond record\n"
        self.assertEqual(cc.record_key_lines(doc), [])


class RecordSpanTest(unittest.TestCase):
    def setUp(self) -> None:
        self.spans = cc.segment(TABLE_DOC, "D6", min_chars=60)

    def _for(self, key: str) -> list[dict]:
        return [s for s in self.spans if s["locator"]["section_path"] == [key]]

    def test_disposition_prefix_is_in_a_span_not_a_heading(self) -> None:
        text = " ".join(s["paragraph"] for s in self._for("001"))
        self.assertIn("Temporary. Destroy when 3 years old", text)

    def test_key_travels_with_the_record(self) -> None:
        self.assertTrue(self._for("001")[0]["paragraph"].startswith("001 "))

    def test_section_path_is_the_record_key_not_an_authority(self) -> None:
        for key in ("001", "010", "011"):
            paths = {tuple(s["locator"]["section_path"]) for s in self._for(key)}
            self.assertEqual(paths, {(key,)})
        self.assertEqual(self._for("001")[0]["locator"]["section_path"], ["001"])

    def test_authority_does_not_leak_into_the_next_record(self) -> None:
        first = " ".join(s["paragraph"] for s in self._for("001"))
        second = " ".join(s["paragraph"] for s in self._for("010"))
        self.assertIn("DAA-GRS2016-00010001", first)
        self.assertNotIn("DAA-GRS2016-00010001", second)
        self.assertIn("DAA-GRS2013-00030001", second)

    def test_no_span_crosses_a_record_boundary(self) -> None:
        for key in ("001", "010", "011"):
            text = " ".join(s["paragraph"] for s in self._for(key))
            other = [k for k in ("001", "010", "011") if k != key]
            for k in other:
                self.assertNotIn(f" {k} ", text)

    def test_every_span_is_contained_in_its_declared_page(self) -> None:
        pages = [norm(page) for page in TABLE_DOC.split("\f")]
        for span in self.spans:
            self.assertIn(
                span["paragraph"],
                pages[span["locator"]["page"] - 1],
                span["span_id"],
            )

    def test_char_offsets_index_the_normalised_source(self) -> None:
        flat = norm(TABLE_DOC)
        for span in self.spans:
            start = span["locator"]["char_start"]
            end = span["locator"]["char_end"]
            self.assertEqual(flat[start:end], span["paragraph"], span["span_id"])


if __name__ == "__main__":
    unittest.main()
