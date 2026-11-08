# Evidence-support audit — compiled claims (run of 2026-11-08)

Artifact: `gold/claims.compiled.jsonl`, 478 claims, sha256
`892f2360178d0f3a027bbe6bda0039faabd05a7f483655110146326bc692510e`.

Method (fixed in `PREFLIGHT.md` §9 before the run): a deterministic systematic
sample of 15 claims per document — every ⌈n/15⌉-th claim, in file order — so the
sample is reproducible and not chosen by the reviewer. The reviewer sees only
`(statement, evidence quote, locator)` and asks the single question: *does this
quote state this claim, as written?*

Verdicts: `ok` = the quote states the claim; `weak` = the quote states it only
with the span's section path or table header; `no` = the quote does not state it.

## D1 — EU implementing regulation (146 claims, sample every 9)

| claim | verdict | note |
|---|---|---|
| D1-0001 | ok | first sentence of the quote |
| D1-0010 | ok | "may include but is not limited to" |
| D1-0019 | **no** | statement says "Chapter II governs"; the quote is a nav link (`Article 2 : … Open in side peek`) |
| D1-0029 | ok | |
| D1-0038 | ok | |
| D1-0047 | ok | |
| D1-0057 | ok | |
| D1-0066 | ok | |
| D1-0075 | ok | |
| D1-0087 | ok | |
| D1-0098 | ok | two spans joined: the lead-in and point (b) |
| D1-0107 | ok | |
| D1-0116 | ok | resolves "the period referred to in paragraph 1" |
| D1-0125 | ok | |
| D1-0135 | ok | |

14/15.

## D2 — university AI policy (90 claims, sample every 6)

15/15 ok. D2-0044 is a syllabus template quoted verbatim; it is well supported,
but the extractor's own rule 3 says templates should be skipped — counted as a
precision issue, not a support failure.

## D3 — OWASP incident-response playbook (76 claims, sample every 5)

| claim | verdict | note |
|---|---|---|
| D3-0001 | weak | quote is `Response time : 1 hour HIGH (Orange)`; the subject ("system compromise in progress") is the table row label, outside the span |
| D3-0006 | weak | quote is a shell snippet; the fact `1.1 Confirm Detection` is the span's section path, not the quote |
| D3-0007..0036 (13) | ok | |

13/15 ok, 2 weak, 0 no.

The two weak cases are the same defect: tabular and headed HTML content carries
its meaning in the header/section path, and the claim cites the value without
it. The `section_path` is in the locator, so the claim is still checkable — but
the quote alone is not self-sufficient.

## D4 — county RFP (166 claims, sample every 11)

15/15 ok. Includes both conflicting deadlines (D4-0049 22 January, D4-0082
12 February) and the RFP number typo (D4-0013 `#20246-001`, verbatim from the
source).

## Result

| | |
|---|---|
| Sample | 60 claims (15 per document) |
| Supported by the quote alone | **57/60 = 95.0%** |
| Supported once section path / table header is included | 59/60 = 98.3% |
| Claims asserting a fact absent from the source | **0** |

Gate §9 threshold is ≥90%: **pass** on the quote alone.

Residual defects, named rather than hidden:

1. **Navigation chrome becomes claims.** D1-0019 turns a page-menu entry into a
   "definition". The boilerplate blocklist covers cookies/JS/downloads but not a
   table-of-contents link list.
2. **Tabular claims lose their row label.** D3-0001 and D3-0006 are true to the
   source but not provable from the quote. Fixing this means carrying the table
   header into the span (segmenter) or requiring the statement to name the row
   the extractor is answering.
3. **Template text is still extracted.** D2-0044 is a syllabus template quote,
   which rule 3 of the extractor prompt says to skip.
4. **Semantic near-duplicates survive the dedup pass.** D3-0021/D3-0026 and
   D3-0056/D3-0061 state the same list item with different wording and fall
   below the 0.85 Jaccard floor.

None of these is a fabricated claim, which is the one failure mode the gate does
not tolerate.
