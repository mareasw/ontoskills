# Evidence-support audit — key/value table fix, second-corpus probe

Artifact: `benchmark/docbench/gold/probe.kv.compiled.verified.jsonl` (gitignored).
Produced by: `benchmark/docbench/compile_claims.py --verify` over D5 and D6 on
2026-11-10, with the region-scoped key/value segmentation of `PREFLIGHT.md`
§10.7(e)(i). The earlier runs and their censuses stay untouched in
`gold/probe.compiled.verified.jsonl` / `gold/audit.probe.md` and
`gold/probe.fixed.compiled.verified.jsonl` / `gold/audit.probe.fixed.md`.
Date: 2026-11-10. Model: `deepseek-v4.1-flash`.

This is the independent census required by §10.4 and promised by
§10.7(e)(i). It is not the verifier's own audit; that audit reports its own
convergence. The worksheet (one row per emitted claim, with every quote and
page) was read end to end: **397 rows, no sample**. Verdicts are kept locally in
`gold/probe.kv.verdicts.jsonl` (gitignored, like `gold/probe.verdicts.jsonl` and
`gold/probe.fixed.verdicts.jsonl`: the notes name the source corpus, which is
not redistributed in this repo).

## Result in one line

**The fix is rejected by its own pre-registered criteria.** It repairs the
defect it was written for — the eight glossary definitions of terms the
document does not define go to zero, D5 "facts absent from source" goes 8 -> 0,
D5 support rises 92.9% -> 98.2% — but D5 does not recall `D5-0002` or
`D5-0003`, two of the three Table 1/Table 2 claims the acceptance names, and an
overall 8/10 does not substitute for a named requirement.

| Document | Structural | Support (census) | Facts absent from source | Recall | Verdict |
|---|---|---|---|---|---|
| D5 — contract | pass | 329/335 = **98.2%** | **0** | 8/10 = **80.0%** | **fail** (named claims missed) |
| D6 — table-as-content | pass | 61/62 = **98.4%** | 0 | 10/10 = 100% | **pass** |

Pooled support: 390/397 = 98.2%, 0 `no`, 0 `fabricated`.

## Artifact and pipeline

| Stage | Result |
|---|---|
| Spans | 360 (D5 325, D6 35); 28 extraction chunks, 15 spans each, overlap 2 |
| Raw compile | 411 claims (D5 348, D6 63); 33 near-duplicates merged, 10 rejected, 12 truncated retries |
| Verify | 411 rows: 301 `ok` / 107 `weak` / 2 `no` / 1 `fabricated` initially; two repair rounds; 7 dropped, 7 near-duplicates merged |
| Final | **397 claims** (D5 335, D6 62), **532 evidence spans**, schema v2, `check_claims.py` **0 failures** |
| Verify residual | 385 `ok` / 12 `weak` / 0 `no` / 0 `fabricated` (96.98% pooled) |

Segmentation checks that precede the model, from the dry run and re-confirmed
on this artifact: D1-D4 are byte-identical to the committed baseline (420
spans); D6 is byte-identical to the fixed run (35 spans, sha
`3d2ed8004c39eb0e`). D5 segments to 325 spans (fixed run: 328).

## What the fix repaired — the eight `no` rows are gone

In the fixed run, eight D5 claims defined a term the document does not define,
because a two-line glossary headword kept only its last line as `section_path`:
`Country`, `Safeguards`, `Clauses` (twice), `Data` (narrowed to special category
data), `Controller` (given the *Third Party Controller* definition),
`Protection Laws`, `Delay`. In this artifact **none of them reappears in any
form**:

| Fixed run | Term the source defines | This run |
|---|---|---|
| `D5-0374` "Country" | **Adequate Country** | `D5-0330` names *Adequate Country*; `section_path` `["Adequate Country"]` |
| `D5-0375` "Safeguards" | **Appropriate Safeguards** | `D5-0331` |
| `D5-0385` "Clauses" (Part two) | **Extra Protection Clauses** | `D5-0340` |
| `D5-0410` "Data" | **Special Category Data** | no definition claim emitted (a coverage miss, not an unsupported assertion) |
| `D5-0418` "Controller" | **Controller** = as defined in the UK GDPR | `D5-0334`; *Third Party Controller* is `D5-0372` |
| `D5-0423` "Protection Laws" | **UK Data Protection Laws** | `D5-0376` |
| `D5-0425` "Delay" | **Without Undue Delay** | `D5-0378` |
| `D5-0426` "Clauses" (Part 4) | **Mandatory Clauses** | `D5-0350` |

The glossary also resolves the definition-body-only `weak` rows of the fixed
run: `Importer Information` (`D5-0346`), `Relevant Data Subject`, `Significant
Harmful Impact` (`D5-0262`), `Restricted Transfer`, `Transfer Risk Assessment`,
`Importer Data Subject Contact` (`D5-0344`) are named in their statements. D5
support moves 329/354 = 92.9% -> 329/335 = **98.2%**, and the class of
"definition of a term the document does not define" is empty.

Table 1/2 rows are also better:

- `S0007` `Full legal name: University of Bristol (through the Avon Longitudinal
  Study of Parents and Children (ALSPAC))` — the exporter name in one span.
- `S0017` `... Table 2: Transfer Details UK country's law that governs the IDTA:
  England and Wales` — the governing-law cell with its label.
- `S0018` carries `section_path ["Primary place for legal claims to be made by
  the Parties"]` with the value `England and Wales` as its text.

Two rows are still wrong, and both matter below: `S0008` carries a stale
`Full legal name:` prefix, and `S0024` (`Importer is a Controller`) carries
`section_path ["Linked Agreement"]`.

## D5 recall — 8/10 = 80.0%

| Gold | Rule | Recalled | Where / why not |
|---|---|---|---|
| `D5-0001` | the IDTA has four parts | yes | `D5-0042` |
| `D5-0002` | Exporter is the University of Bristol, through ALSPAC, at Beacon House | **no** | the row is segmented (`S0007`, `S0008`) but no claim is emitted from either span; see below |
| `D5-0003` | governing law is England and Wales, and England and Wales is the primary place for claims | **no** | the governing-law half is `D5-0005`/`D5-0006`; the primary-place half existed in the raw compile (`D5-0006`) and the verify stage replaced it with the governing-law claim |
| `D5-0004` | both Parties are Controllers | yes | `D5-0007` (*Exporter*) + `D5-0009` (*Importer*) |
| `D5-0005` | UK GDPR does not apply to the Importer's processing | yes | `D5-0008` |
| `D5-0006` | cannot end before the Term except breach or written agreement | yes | `D5-0012` |
| `D5-0007` | onward transfer only to named co-applicants with a DAA | yes | `D5-0018` |
| `D5-0008` | no change to the Mandatory Clauses except as expressly permitted | yes | `D5-0057` |
| `D5-0009` | Importer remains fully liable after sub-contracting | yes | `D5-0193` |
| `D5-0010` | the IDTA ends at the end of the Term, a notice period, by agreement, or under s.29.2 | yes | `D5-0276` + `D5-0277` + `D5-0278` + `D5-0279` |

Recall is measured under the §9 proxy: a gold claim counts if a compiled claim,
or a set of compiled claims taken together, states the same rule. `D5-0004` and
`D5-0010` are the "set" cases; both are complete without any claim outside the
set.

### `D5-0002` — the row is segmented, the extractor does not use it

The segmenter does produce the exporter's details on page 1:

| Span | `section_path` | Text |
|---|---|---|
| `S0007` | `["Exporter (who sends the Restricted Transfer)"]` | `Full legal name: University of Bristol (through the Avon Longitudinal Study of Parents and Children (ALSPAC))` |
| `S0008` | `["Exporter (who sends the Restricted Transfer)"]` | `Full legal name: Main address (if a company registered address): University of Bristol, Beacon House, Queens Road, Bristol, BS8 1QU, UK.` |

`S0007` is exactly the row the gold claim asks for. Two defects follow from it:

1. **Extraction miss.** Both spans sit in the first chunk (`S0001`-`S0015`),
   together with the Table 1 rows the model did extract (governing law,
   primary place, controller status). Scan of all 411 raw claims: **zero**
   quotes contain `Full legal name`, `Beacon House` or `BS8`. The model read the
   table and skipped the party's identity.
2. **Stale label prefix.** `S0008` opens with `Full legal name:`, an empty
   label that belongs to the Importer column (`private/D5.txt` line 33), before
   the `Main address` label and the address value. `pending_key` accumulates a
   label with the next label instead of being closed when the value is empty,
   so the address row is quotable but mislabelled. This is a residual defect of
   the new branch, not a fixed-run regression (the fixed run split the same row
   over `S0006`-`S0008`).

The miss is therefore **not** a segmentation miss of the kind §10.7(e)(i)
targets: the text needed to recall `D5-0002` is in one span. It is an
extraction miss, with a segmentation defect that plausibly contributed.

### `D5-0003` — the primary-place row is quoted, then audited away

The row is a colonless four-line label (`private/D5.txt` lines 115-120):

```
Primary place
for legal claims
to be made by
the Parties

England and Wales
```

The label is joined into `section_path` (`["Primary place for legal claims to
be made by the Parties"]`) and the value stays in its own span, `S0018`, whose
text is only `England and Wales`. The raw compile did state the rule:

- `D5-0006` (raw): *"The primary place for legal claims to be made by the
  Parties is England and Wales."*, quote `England and Wales`, locator `S0018`.

The verify stage audited it `weak` — *"Quote is bare 'England and Wales';
legal-claims element only in section heading"* — and repaired it by
re-evidencing the claim on `S0017` (the governing-law cell), which produced
*"The UK country's law that governs the IDTA is England and Wales."* The
primary-place rule then no longer exists in the artifact. The governing-law
half is recalled; the primary-place half is not.

This is the one place where the two layers disagree by construction: the
census scale treats evidence as the schema's pair (quote **and** locator), so a
correct `section_path` plus a correct value quote is support; the verifier's
repair policy reads the quote alone and rewrote the claim. §10.7(e)(i) rule 2
asks for label and value in one span, and for colon-terminated labels it does
that; for this colonless label it joins the label to the locator only.

## D6 — the pass is kept, but it is not evidence for the fix

| Metric | Fixed run | This run |
|---|---|---|
| Structural | 100% | 100% |
| Support (census) | 49/51 = 96.1% | 61/62 = 98.4% |
| Facts absent from source | 0 | 0 |
| Recall | 10/10 | 10/10 |
| Misattributed DAAs | 0 | 0 |

Recall in this artifact: `D6-0001` -> `D6-0015`; `D6-0002` -> `D6-0018`;
`D6-0003` -> `D6-0020` + `D6-0021` + `D6-0022`; `D6-0004` -> `D6-0038`;
`D6-0005` -> `D6-0040`; `D6-0006` -> `D6-0042`; `D6-0007` -> `D6-0047`;
`D6-0008` -> `D6-0053`; `D6-0009` -> `D6-0045`; `D6-0010` -> `D6-0061`. Every
disposition instruction sits inside its own quote.

DAA attribution: every D6 claim that names a record item was checked against the
item -> DAA map read off the source (full strings with the year, because items
010 and 090 share `00030001`). **0 mismatches.** The one apparent mismatch,
`D6-0038` (item 012, `DAA-GRS2016-00010001`), is correct in the artifact; the
checkpoint's map was wrong, not the claim. 29 claims carry both an item number
and a DAA; the other 33 are scope/definition/disposition claims that name no
item, so there is nothing to misattribute.

**The D6 spans are byte-identical to the fixed run.** D6's pass therefore
cannot be attributed to this fix: it keeps the pass because the segmentation it
gets is unchanged. The claim count differs (63 raw here vs 51) and that
difference is model nondeterminism on the same input, which is why support
moves 96.1% -> 98.4% while D6 evidence is the same text.

## The 7 `weak` rows

| Claim | Why `weak` |
|---|---|
| `D5-0070` | statement drops the source condition "by agreeing to the change in writing" and states a broader permission than the IDTA |
| `D5-0186` | turns "one or more of the following apply" (Article 46 routes) into a conjunctive condition; the alternatives are missing |
| `D5-0188` | same defect on the "UK or Adequate Country" alternative |
| `D5-0292` | statement names "the party retaining" the data; the quoted item 31.1.2 does not name the actor (31.1 makes it the Importer) |
| `D5-0294` | statement names "the party" stopping Processing; the quoted item 31.1.3 does not name the actor |
| `D5-0367` | bare fragment ("As set out in Table 1: Parties and signature."); no proposition, and the term `Start Date` is only in the locator. Carried byte-identically from `D5-0411` of the fixed run |
| `D6-0029` | label ("Copies used for administrative or reference purposes") and disposition ("All other copies. Temporary. Destroy when business use ceases.") are adjacent column entries; the attachment is inferred |

All seven are "true but missing an element the evidence also lacks" under the
frozen §10.7(e) scale; none is a fact the source does not contain.

## Verifier audit vs independent census

The verifier kept 12 `weak` rows; the census finds 7. Only 4 are the same row.

| | Count | Rows |
|---|---:|---|
| Both | 4 | `D5-0070`, `D5-0186`, `D5-0188`, `D6-0029` |
| Verifier only | 8 | `D5-0039`, `D5-0068`, `D5-0162`, `D5-0163`, `D5-0346`, `D5-0347`, `D5-0373`, `D5-0377` |
| Census only | 3 | `D5-0292`, `D5-0294`, `D5-0367` |

The verifier-only rows are quote-only judgements (`D5-0346` "Importer
Information" is `ok` to the census because the quote is the definiens and the
locator names the term). The census-only rows are actor/attachment defects the
verifier's rewrite repaired the wording of but not the evidence for. Same
lesson as Gate 2 and the DAA rows: the stage's own audit is not the measure.

## Residual defects the fix does not repair

These are outside the pre-registered acceptance, and they do not change either
support figure above, but they are part of the measurement:

1. **Stale label prefix on `S0008`** (page 1): the address row opens with the
   Importer's empty `Full legal name:` label. `pending_key` accumulates labels
   instead of closing an empty-valued row.
2. **Displaced controller cell**: `S0024` is the text `Importer is a Controller`
   with `section_path ["Linked Agreement"]`. The claim `D5-0009` is true and
   its quote carries the status, so the census keeps it `ok`, but its locator
   names the wrong Table 2 row — the same column-major displacement §10.7(e)(i)
   was meant to remove, now on one row.
3. **`section_path` regression on pages 16-20**: the bogus path
   `["Laws", "15.2.1.5 contact point for more information; and"]` attaches to
   **27 spans / 49 claims** here, against **6 spans / 19 claims** in the fixed
   run. The seeds are pre-existing (the heading stack never pops the numbered
   list item), but the page-17 region extends their reach to pages 18-20. Page
   remains correct, the quote carries the rule, and no census verdict changes;
   it is still a wrong locator on 49 claims and it grew.

## Verdict

`PREFLIGHT.md` §10.7(e)(i) fixed the acceptance before the run:

> D6 must keep structural 100%, support >= 90%, 0 facts absent, recall 10/10
> and 0 misattributed authorities; D5 must reach 0 facts absent and must recall
> the three Table 1/Table 2 gold claims (`D5-0002`, `D5-0003`, `D5-0004`) while
> keeping recall >= 70%. Failure on either document rejects the fix as a
> regression or as not-a-fix.

Measured:

| Requirement | Result |
|---|---|
| D6 structural 100% | pass |
| D6 support >= 90% | 98.4% — pass |
| D6 0 facts absent | 0 — pass |
| D6 recall 10/10 | 10/10 — pass |
| D6 0 misattributed DAAs | 0 — pass |
| D5 0 facts absent | 0 — pass |
| D5 recall `D5-0002` | **miss** |
| D5 recall `D5-0003` | **miss** |
| D5 recall `D5-0004` | `D5-0007` + `D5-0009` — pass |
| D5 recall >= 70% | 80% — pass |

**The fix is rejected.** It is not carried as a validated fix; the segmentation
code stays on `main` (it was merged before this run, as the pre-registration
required), and this measurement is its record. The rejection is on D5's
named-claim recall, not on the support figures, which are the best this corpus
has produced. The two misses have different causes and neither is repaired by
the region rule as written: one is an extractor miss over a correctly segmented
row, with a stale label prefix on the address row; the other is a colonless
wrapped label whose value the verify stage refuses to accept as evidence for the
rule.

The failed run, the fixed run, their censuses and their verdicts are unchanged
by this document. This artifact and census are the measurement of the key/value
pipeline, not a replacement for them.

## Cost

| Item | Calls | Tokens | Cost at $0.15/M in, $0.60/M out |
|---|---:|---|---:|
| Compile (28 chunks, 12 truncated retries, 9 conflict pairs) | — | 101,078 in / 243,257 out (manifest) | ~$0.1611 |
| Verify (audit + 2 repair rounds) | 102 | 250,147 in / 397,644 out | $0.2761 |
| Census | 0 | — | $0.00 |
| **Total** | | | **~$0.44** |

The compile stage does not record a per-call count in the manifest (the
conflict pass is included in the same totals); the verify stage does.

## Limits

- One model, two documents, one domain shift. The census is manual and the
  reviewer is the agent that built the pipeline; the claim-level verdicts and
  the span evidence are what a second reviewer can check.
- D6 is 62 claims: one row is worth 1.61 pp of support. D5 is 335.
- Recall is the §9 proxy (a claim, or a set of claims, states the rule). It is
  not an entailment test.
- D6's evidence is byte-identical to the fixed run, so its pass says nothing
  about the key/value rule; it only says the rule did not damage D6.
- The three residual defects above are real and counted nowhere in the gate;
  they are disclosed so the next fix is measured against them, not around them.
- The conflicts pass remains partial for this run; conflict links are outside
  the §10 gate.
