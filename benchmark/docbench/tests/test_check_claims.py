#!/usr/bin/env python3
"""Tests for the claim checker's page resolution.

A short quote can occur on several pages (glossary scaffolding, a disposition
clause repeated per row). The checker's contract is that the declared page is
a page where the quote occurs, not necessarily its first occurrence.

Run from the repository root:
    python -m unittest discover -s benchmark/docbench/tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

DOCBENCH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DOCBENCH))

import check_claims as check  # noqa: E402

SOURCE = (
    "first page only\n"
    "\f"
    "the clause is repeated\n"
    "\f"
    "second mention: the clause is repeated\n"
)


class PageContainingTest(unittest.TestCase):
    def test_unique_quote_resolves_to_its_page(self) -> None:
        self.assertEqual(check.page_containing(SOURCE, check.norm("first page only")), 1)

    def test_declared_page_is_kept_when_the_quote_repeats(self) -> None:
        quote = check.norm("the clause is repeated")
        self.assertEqual(check.page_containing(SOURCE, quote, 2), 2)
        self.assertEqual(check.page_containing(SOURCE, quote, 3), 3)

    def test_wrong_declared_page_falls_back_to_first_occurrence(self) -> None:
        quote = check.norm("the clause is repeated")
        self.assertEqual(check.page_containing(SOURCE, quote, 9), 2)

    def test_missing_quote_returns_none(self) -> None:
        self.assertIsNone(check.page_containing(SOURCE, check.norm("absent"), 1))


if __name__ == "__main__":
    unittest.main()
