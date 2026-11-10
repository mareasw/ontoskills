# Segmentation and extraction — how other projects solve cell association, and what it would cost us

Scope: a zero-cost survey, written after §10.7(e)(ii) rejected the key/value
fix. Public sources only, read by hand; no package installed, no model called, no
document fetched from a paid service. Every number below is either quoted from a
public source or measured today on the two probe PDFs already on disk. Nothing
here changes a threshold, a gate, an artifact or the verdict of the last run.

Date: 2026-11-10. Sources: poppler `pdftotext` 24.02.0 man page and local
experiments; `pdfminer.six`, `pdfplumber`, `camelot`, `Docling`, `Marker`,
`MinerU`, `GROBID`, `table-transformer` repository licences read from upstream;
Docling model catalogue and `docling.rs` `MODELS_NOTICE.md`; Adhikari & Agarwal,
*Comparative Study of PDF Parsing Tools Across Diverse Document Categories*,
arXiv:2410.09871v2; W3C Web Annotation Data Model (selectors and state).

## 1. What the measurement actually says

The last run failed on two named claims. Neither is an extraction defect, and
this is the fact that should drive the decision:

| Defect (from `gold/audit.probe.kv.md`) | Class | Owner | Would an extractor swap fix it? |
|---|---|---|---|
| `D5-0002` — exporter legal name and address never claimed | **model skip**: `S0007`/`S0008` exist, are in the first chunk, and contain the text; none of the 411 raw claims quote `Full legal name`, `Beacon House` or `BS8` | extractor coverage | no |
| `D5-0003` — primary place of legal claims lost | **instrument disagreement**: the census rule (§10.4) is evidence = quote **and** locator; the verifier re-evidences a definition whose label is outside the quote, so the row is audited away | verifier | no |
| 27 spans / 49 claims carry `["Laws", "15.2.1.5 contact point for more information; and"]` | heading rule: a numbered clause fragment becomes a section title | segmenter (text) | no — it survives `pdftotext -layout` |
| `S0008` opens with a stale `Full legal name:` prefix from the Importer's empty cell | empty-cell carry-over | segmenter (text) | no |
| D6 table as content | default reading order is already correct here (item, description, instruction, authority arrive in stream order; all 14 `DAA-GRS…` strings intact) | — | `-layout` destroys it (§4) |

Span coverage of the measured artifact, computed today from
`probe.kv.compiled.verified.jsonl` by char-range overlap: **D5 228/325 spans
referenced (70.2%)**, **D6 31/35 (88.6%)**. Most unreferenced spans are page
footers (`VERSION A1.0…`), section headings and list continuations, which is
correct. The one unreferenced span whose absence costs a gold claim is the
exporter cell — which is why `D5-0002` belongs to the extractor, not to the
segmenter.

So: the segmenter defect that remains is real but textual (headings, empty
cells). The extractor defect is a *skip*, not a misread. Only the third failure
mode — cell association across columns and vertical stacks — is an extraction
problem, and the last run does not show it as the bottleneck.

## 2. What the field offers

Text-extraction comparison (arXiv:2410.09871, 10 tools, 6 categories, DocLayNet):
"PyMuPDF and pypdfium generally outperformed others, but all parsers struggled
with Scientific and Patent documents"; for table detection "TATR excelled in the
Financial, Patent, Law & Regulations, and Scientific categories", Camelot best on
tenders, PyMuPDF best on manuals. The paper's conclusion is to pick a parser per
document *category* — which, for this project, is precisely the per-document
patch we have forbidden ourselves. The only generalisable form of that advice is
to pick **per region**, not per document.

| Tool | What it gives | Licence | Weight |
|---|---|---|---|
| `pdftotext -tsv` / `-bbox-layout` | word boxes, line/block boxes, page geometry | poppler, GPL-2 or GPL-3, already a runtime dependency (invoked as a process today) | none |
| `pdfminer.six` | line/char boxes + heuristic layout analysis (`LAParams`), AcroForm values | MIT | none |
| `pdfplumber` | chars, rects, lines; table finding on top of pdfminer.six | MIT | none |
| Camelot | ruled/stream table extraction | MIT | none by default (pdfium backend); Ghostscript only for an optional backend |
| Table Transformer (TATR) | table *structure* model (rows/columns/cells) | MIT (repo and weights) | PyTorch + model |
| Docling | layout + reading order + tables, `DoclingDocument` provenance (page, bbox, charspan) | code MIT; layout RT-DETR Apache-2.0; TableFormer CDLA-Permissive-2.0 | ML models, ~GB |
| Marker | PDF → markdown/JSON/HTML | code Apache-2.0; weights **modified AI Pubs OpenRAIL-M**, free only under $5M funding/revenue | ML models |
| MinerU | PDF → markdown/JSON | Apache-2.0 **plus additional terms**: commercial licence above 100M MAU or $20M monthly revenue, attribution when offered as an online service | ML models |
| GROBID | scholarly articles → TEI (header, references) | Apache-2.0 | Java service, CRF/DL models |

Note on licences, because the survey changed two beliefs: MinerU is no longer
AGPL-3.0 (its `LICENSE.md` is Apache-2.0 plus the terms above), and TATR — the
model the only comparative study found best on Law & Regulations — is MIT.

## 3. The constraint that decides between them

The kernel copies the `quote` from the span, so the quote is verbatim **with
respect to the text the segmenter read**. Any change of the text source changes
every measured artifact, and any reflow (markdown, normalised whitespace,
reordered cells) makes the quote no longer a contiguous passage of the document.

That is not an argument against converters per se — Docling keeps `page_no`,
`bbox` and `charspan` provenance, so it *could* be used with verbatim quotes. It
is an argument against using their reflowed text as the text source. A converter
is safe in exactly one role: producing a **structure map** (which region is a
table, which cells form a row) while the text still comes from the existing
extraction. In that role it is an expensive version of option A below.

## 4. `-layout` is a falsification, not a candidate

The cheapest "fix" — switch to `pdftotext -layout` — was tried today on both
probe PDFs before writing this memo. It is a regression, and recording it here
stops it from being proposed again:

| Test | Default order (in use) | `-layout` |
|---|---|---|
| D5 spans | 325 | **440** |
| D6 spans | 35 | **45** |
| D6 `DAA-GRS…` strings intact | **14/14** | **0/14** (each splits `DAA-GRS-` / `2016-0013-` / `0001`) |
| D6 spans that are contiguous prose of the document | — | 12/45 = 26.7% (73.3% fuse two columns) |
| D5 two-column Table 1 | exporter and importer cells separated | columns fused: `Exporter (who sends the Importer (who receives The Parties Restricted Transfer) the Restricted Transfer)` |
| D5 page 16 heading bug | 27 spans / 49 claims | **still present** (`["The Importer", "15.2.1.5 contact point for more information; and"]`) |

Two conclusions. Physical order is not reading order: it fixes one multi-column
page and breaks a table that default order already got right. And the heading
bug is a rule bug in `_segment_blocks`, not a reading-order bug — no extractor
change touches it.

## 5. Options

**A. Geometry-scoped cell reconstruction from poppler `-tsv` / `-bbox-layout`.**
Keep today's default-order text for body blocks; add per-word boxes; inside a
detected table region, group words into column x-bands and row y-bands, emit one
span per cell, and join vertically stacked fragments *inside* a cell.

*Measured today, zero cost:* a ~20-line prototype reconstructs **14/14** D6 DAA
strings exactly (`DAA-GRS-` + `2016-0013-` + `0001` are three lines at the same
x, in the last column), and reconstructs D5 Table 1 into an exporter cell that
reads `Full legal name: University of Bristol (through the Avon Longitudinal
Study of Parents and Children (ALSPAC)) … University of Bristol, Beacon House,
Queens Road, Bristol, BS8 1QU, UK.` and an importer cell that stays empty — which
also removes the stale `Full legal name:` prefix on `S0008` by construction.

Fixes: cell association, colonless labels, vertical stacks, empty cells.
Breaks: every PDF span id and text changes (D2, D4, D5, D6) → all prior numbers
become a different pipeline and must be re-baselined; the region detector can
false-positive on prose. HTML documents (D1, D3) untouched.
Dependencies: none new — poppler is already required. GPL-2/GPL-3 binary called
as a process, no linking, same status as today.
Pre-registration: **yes**, with property-based acceptance (every table row
quotable; all authority strings intact; D1-D4 byte-identical; no cell span
spanning two rows), not document-specific assertions.

**B. Replace the base extractor with `pdfminer.six`.**
Fixes: two-column physical order in one pass (`LAParams`, `detect_vertical`);
AcroForm values for fillable templates.
Breaks: the character stream of every PDF changes, so every measured artifact
becomes incomparable; it is still line-level, so D6's DAAs would need the same
column join as A; its layout heuristics can reorder text without saying so.
Dependencies: MIT, one Python package.
Pre-registration: yes — but **A dominates it**: A gets boxes without changing the
text source, and keeps the comparison honest.

**C. Offline document converter as a pre-parser (Docling / Marker / MinerU).**
Fixes: best reading order and table structure (TableFormer / TATR), semantic
roles, provenance with page + bbox.
Breaks: reflowed text (markdown) is not quotable as the document's prose unless
offsets are re-derived; heavy models, per-document nondeterminism, latency;
Marker's weights are OpenRAIL-M with a $5M revenue ceiling, MinerU's licence adds
commercial thresholds and an attribution duty — for a public repository that is a
legal question, not an engineering one.
Pre-registration: yes, and it changes the evidence model (bbox locators), the
largest blast radius of any option here.
Verdict: only if A fails on a broader corpus, and then only as a structure map.

**D. Text-only segmenter repairs.**
Fixes: the heading rule (a numbered clause fragment or list continuation is not a
section title), colonless label/value pairing when both sides are already
adjacent, and the empty-cell carry-over that puts `Full legal name:` on `S0008`.
Breaks: spans shift on D5; no geometry, so a cell boundary is still inferred from
text shape and cannot be demonstrated.
Dependencies: none.
Pre-registration: yes, cheap dry-run checks (D1-D4 byte-identical, D6 identical).

**E. Verify-policy alignment.**
The census (§10.4) already defines evidence as quote **and** locator, and schema
v2 already carries a list of evidence entries with endpoints. The verifier
requires the label inside the single quoted span and, failing that, re-evidences
the claim onto another cell — which is how `D5-0003` was lost after being stated
correctly by the raw compile.
Fix: accept a claim whose evidence carries **two entries**, one quoting the label
and one quoting the value, or (weaker) accept a `section_path` that names the
term when the quote is the definition body. The first keeps a quote for both
sides and is strictly better.
Breaks: nothing in the data; but it changes the instrument that produced every
reported number, so old and new figures are not comparable without re-running.
Dependencies: none, no model change.
Pre-registration: **yes** — it is a gate instrument change, and the whole point of
§10 is that instruments do not move after the score is known.

## 6. Recommendation

Two tracks, both waiting for explicit approval; no billable call has been made.

**Track 1 — cheap, text-only, one pre-registration (D + E, plus a coverage
report).** Fix the heading rule and the empty-cell prefix, align the verifier with
the census definition, and report span coverage as a diagnostic (not a gate).
This is the only combination that addresses both named failures from the last
run, and it needs no new dependency. If it is measured, the acceptance should
name `D5-0002` and `D5-0003` again, unchanged.

**Track 2 — structural, geometry, separate pre-registration (A).** Rebuild only
table regions from word boxes, keep default-order text everywhere else, and
re-baseline all four PDFs. It is the general form of "pick the parser per
category": the choice is made per region from geometry, which is a property of the
document, not a list of document names.

**Do not do B or C now.** B is dominated by A. C trades a licensing question and
a gigabyte of model weights for a structure map that A already produces from data
we have.

## 7. A fourth axis the survey surfaced (not an option, a design question)

`D5-0002` is a model skip on a row that is a definition by construction. A
compiler that knows a span is a key/value row does not need a model to state
`definition`: the statement can be templated from the joined label and the cell
value, deterministically, with the same quote and locator. That would make table
rows reproducible and free, and would shrink what the model is asked to do.

It is not proposed here because it changes what "compiled by a model" means for a
whole class of spans, and it would need its own pre-registration and its own
census rule. It is recorded because it is the cheapest answer to `D5-0002` and it
generalises to every table in the corpus, whereas a prompt tweak does not.

## 8. What this memo does not do

- It does not change §10, §10.4 or §10.7(e), and it does not reopen the rejected
  verdict: `gold/audit.probe.kv.md` and §10.7(e)(ii) stand as measured.
- It does not install, fetch, or run anything billable. The `-layout` and
  `-tsv`/`-bbox-layout` results in §4 and §5 come from `pdftotext` 24.02.0 on the
  two probe PDFs, already present.
- It does not recommend a document-specific path. Every option above is stated as
  a property of text or geometry, so the acceptance can be written for the corpus
  rather than for D5 and D6.
