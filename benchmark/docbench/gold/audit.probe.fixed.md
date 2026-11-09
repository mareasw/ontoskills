# Evidence-support audit — second-corpus probe, fixed run

Artifact: `benchmark/docbench/gold/probe.fixed.compiled.verified.jsonl` (gitignored).
Produced by: `benchmark/docbench/compile_claims.py --verify` over D5 and D6 with
the record-segmentation fix of `PREFLIGHT.md` §10.7(b), under the §10.7(c)/(d)
scheduling amendments. The unfixed run and its census stay untouched in
`gold/probe.compiled.verified.jsonl` and `gold/audit.probe.md`.
Date: 2026-11-09. Model: `deepseek-v4.1-flash`.

This is the independent census required by §10.4 and promised by §10.7(b)(ii).
It is not the verifier's own audit; that audit reports its own convergence.

The census worksheet (one row per emitted claim, with every quote and page) was
read end to end: **405 rows, no sample**. Verdicts are kept locally in
`gold/probe.fixed.verdicts.jsonl` (gitignored, like `gold/probe.verdicts.jsonl`:
the notes name the source corpus, which is not redistributed in this repo).

## Result in one line

**The probe fails again, on a different row and a different document.** D6 —
the document §10.7(b) was written for — now passes every row: structural 100%,
support 49/51 = **96.1%**, **0** claims asserting facts absent from source,
recall **10/10**. D5 passes support (329/354 = **92.9%**), recall (7/10 =
**70.0%**) and structural validity, but has **8** claims that assert facts the
source does not state; the pre-registered count for that row is zero, so the
probe fails.

All 8 are the same defect, and it is not in the D6 fix: the legal glossary is a
key/value table whose **headword cell wraps onto two lines**, and the segmenter
keeps only the last line as the section heading. The model then defines
`Safeguards`, `Delay`, `Data`, `Clauses`, … — terms the document does not
define — instead of `Appropriate Safeguards`, `Without Undue Delay`,
`Special Category Data`, `Mandatory Clauses`. §10.7(b) does not cover this case
(the glossary has no item numbers), and it was **not** patched after the score
was seen; it is pre-registered as §10.7(e) for a fresh run.

## Pre-registered thresholds (§10.4) — unchanged

| Check | Threshold |
|---|---|
| Structural validity | 100% |
| Evidence support, full census | >= 90% |
| Claims asserting facts absent from source | 0 |
| Gold-set recall proxy | >= 70% |

Per document. A pooled number is reported but does not pass the probe. No
threshold, scale or rule was changed after this run was measured.

## Artifact

| Step | Count |
|---|---:|
| Claims in (raw compile) | 429 (D5 378, D6 51) |
| Spans in (segmentation) | 363 (D5 328, D6 35) |
| Round 1 | 162 failing -> 116 rewritten, 51 re-evidenced, 9 dropped, 5 rejected, 43 still failing |
| Round 2 | 43 failing -> 28 rewritten, 13 re-evidenced, 2 rejected, 19 still failing |
| Near-duplicates merged | 15 |
| Residual `weak` kept | 19 |
| Residual `no` / `fabricated` dropped | 0 |
| Claims out | 405 (D5 354, D6 51) |
| Evidence spans out | 552 |
| `check_claims.py` failures | 0 |

The round counts are the tool's action counts, not disjoint claim buckets: a
re-evidence whose rewrite also changes the statement is counted in both
`rewritten` and `reevidenced`. Round 1 repaired 153 distinct claims.

The verify stage's own audit converged at 386 `ok` (95.3%) / 19 `weak` / 0 `no` /
0 `fabricated`; the census below is independent of it.

## Method — identical to §10.3, with the amendments recorded before the run

1. Span-first segmentation of `pdftotext` default reading order, no `-layout`
   (§10.2), with the §10.7(b) record rule. D5 re-segments byte-identically to the
   unfixed run (§10.7(b)(ii)); D6 moves from 63 to 35 spans and keeps its 14
   record keys.
2. The §9 extraction prompt, schema v2, `deepseek-v4.1-flash`, chunk size 15,
   overlap 2, `min_chars` 60 — unchanged.
3. `verify_claims.py` audit -> repair -> re-audit, unchanged. Scheduling is a
   mixture: the 429-row audit and the first 150 repair rows sequential, the rest
   at `--verify-concurrency 6` (§10.7(c)); eight provider-failed batches were
   split to singles (§10.7(d)).
4. **Every** emitted claim judged against its own quotes on the census scale
   (`ok | weak | no | fabricated`), no sample.
5. **Carry-forward (§9.1).** A claim byte-identical to a D5/D6 claim already
   judged in the §9.1 census inherits that verdict. 64 rows qualify (63 D5,
   `D6-0008`), all `ok`. One of them, `D5-0392`, is re-judged below: its text is
   the glossary scaffolding `(this is how this word or phrase must be
   interpreted in the IDTA)`, byte-identical to `D5-0421`, which this census
   finds `weak`. Keeping one `ok` and one `weak` for the same text would be
   incoherent, so both are `weak`; the re-judgement is disclosed, and it lowers
   the score, which is the direction that cannot be gaming.

Verdict scale (unchanged from `gold/audit.probe.md`): `ok` — every material
element is in the evidence (quote **and** locator, as schema v2 defines the
pair); `weak` — the statement is true but a material element is outside its own
evidence; `no` — the evidence does not state the claim, or the claim attaches
an element (a definition, an authority, a number) to the wrong subject;
`fabricated` — a specific fact with no basis at all.

## Structural validity

`check_claims.py gold/probe.fixed.compiled.verified.jsonl`:
**405 claims, 552 evidence spans, 0 failures**, all schema v2, by shape
`{'v2': 405}`, by document `{'D5': 354, 'D6': 51}`. The §10.7(a) page checker is
in force; no page failure occurs in this artifact. Structural validity: **pass**.

## Evidence support by document

| Document | Claims | ok | weak | no | fabricated | Support | Threshold |
|---|---:|---:|---:|---:|---:|---:|---|
| D5 — ALSPAC IDTA (contract) | 354 | 329 | 17 | 8 | 0 | **92.9%** | pass |
| D6 — NARA GRS 1.1 (table) | 51 | 49 | 2 | 0 | 0 | **96.1%** | pass |
| **Total** | **405** | **378** | **19** | **8** | **0** | **93.3%** | |

The pooled 93.3% is reported for completeness only.

## The 8 `no` rows — one defect, measured at the span

Every one of them is a glossary entry whose headword is printed on **two lines**
("Adequate / Country", "Appropriate / Safeguards", "Special Category / Data",
"Without Undue / Delay", …). `looks_like_heading` accepts each line separately,
and because both lines sit at the same depth the stack keeps only the **last**
one. The model is given `section_path: ["Delay"]` and writes a definition of
`Delay`, which is not a term in the document.

| Claim | Statement defines | Headword in the source | Page | Span | `section_path` |
|---|---|---|---|---|---|
| `D5-0374` | `Country` | **Adequate Country** | 31 | `S0279` | `["Country"]` |
| `D5-0375` | `Safeguards` | **Appropriate Safeguards** | 31 | `S0280` | `["Safeguards"]` |
| `D5-0385` | `Clauses` (Part two) | **Extra Protection Clauses** | 32 | `S0290` | `["Clauses"]` |
| `D5-0410` | `Data` | **Special Category Data** | 34 | `S0313` | `["Data"]` |
| `D5-0418` | `Controller` | **Third Party Controller** | 34 | `S0318` | `["Controller"]` |
| `D5-0423` | `Protection Laws` | **UK Data Protection Laws** | 35 | `S0323` | `["Protection Laws"]` |
| `D5-0425` | `Delay` | **Without Undue Delay** | 35 | `S0325` | `["Delay"]` |
| `D5-0426` | `Clauses` (Part 4) | **Mandatory Clauses** | 35 | `S0327` | `["Clauses"]` |

Two of them are worse than a missing label:

- `D5-0410` says **`Data`** means "as described in the UK GDPR, together with
  criminal conviction or criminal offence data" — i.e. it narrows *all* data to
  special category data.
- `D5-0418` defines **`Controller`**, which the glossary defines as "As defined
  in the UK GDPR", with the *Third Party Controller* definition. It contradicts
  the entry it looks like.
- `D5-0385` and `D5-0426` both define `Clauses`, with two different definitions
  (Part two vs Part 4). The document defines neither; it defines **Extra
  Protection Clauses** and **Mandatory Clauses**.

This is not a new criterion applied after the fact. The **unfixed** run already
contained one instance of exactly this defect and the §9.1 census already
counted it `no`: `D5-0348` defined "Harmful Impact", a truncated form of
"Significant Harmful Impact" (`gold/audit.probe.md`, row table). The fixed run's
D5 output is richer (378 claims vs 325) and now contains eight.

## The 17 `weak` rows

13 of the 17 are the same key/value defect in a milder form: the statement is
the definition **body** with no headword, or a bare fragment, so the claim is
supported but cannot be resolved on its own.

| Claim | Why `weak` |
|---|---|
| `D5-0378`, `D5-0380` | definition body only ("The term is as defined in the UK GDPR" / "As defined in the UK GDPR"); the term `Data Subject` is in the locator, not the statement |
| `D5-0379` | bare fragment ("All material and non-material loss and damage"); the term `Damage` is absent |
| `D5-0381` | definition body of `Decision-Making`, term not named |
| `D5-0390` | definition body of `Importer Information`, term not named |
| `D5-0391` | body of `Importer Personal Data Breach`; the statement names the inner term `personal data breach` |
| `D5-0392`, `D5-0421` | glossary scaffolding, no term and no proposition |
| `D5-0405` | bare fragment; the term `Relevant Data Subject` is absent |
| `D5-0407` | "The defined entry reads …"; the term `Restricted Transfer` is absent |
| `D5-0411` | bare fragment ("As set out in Table 1"); the term `Start Date` is absent |
| `D5-0415` | "This includes …" with no antecedent |
| `D5-0420` | the span is cut mid-sentence ("…the IDTA provides the"); the object (the **Appropriate Safeguards**) is in the next span, and the statement substitutes "what the IDTA provides" |
| `D5-0033` | the span stops at "are able to provide institutional"; "information … upon request" is in the next span (carried from §9.1 pattern; judged fresh) |
| `D5-0100` | "including any Security + Safeguards: Requirements and Extra Protection Clauses" is not in the evidence |
| `D5-0194` | obligation frame ("at the Start Date and during the Term") is in another span; the quote carries the bare fragment |
| `D5-0272` | the quote stops at 20.6.1; the other routes out of the prohibition (20.6.2, 20.6.3) are outside, so the statement reads as if consent were the only exception |

`D6-0017` and `D6-0018` are the only D6 `weak` rows: the record type
("procurement and payment records") is in a different span from the quote, so
the referent of "All other copies" is not inside the evidence.

## D6 — the fix is confirmed on the document it was written for

### Recall 10/10

The eight gold claims the unfixed run missed are all present, and each carries
the **disposition instruction inside its own quote**:

| Gold | Rule | Now recalled by | Operative text in the quote |
|---|---|---|---|
| `D6-0002` | Administrative records: destroy when 3 years old | `D6-0010` | "Destroy when 3 years old" |
| `D6-0003` | Financial transactions: destroy 6 years after final payment | `D6-0013` | "Destroy 6 years after final payment or cancellation" |
| `D6-0004` | Unsolicited bids: destroy when no longer required | `D6-0032` | "Destroy when no longer required for business use" |
| `D6-0005` | Financial-statement records: destroy 2 years after audit/closure | `D6-0033` | "Destroy 2 years after completion of audit or closure" |
| `D6-0006` | PP&E records: destroy 2 years after disposal | `D6-0034` | "Destroy 2 years after asset is disposed of" |
| `D6-0008` | Drug-Free Workplace suspensions: destroy 5 years after removal | `D6-0040` | "Destroy 5 years after removal from approved status" |
| `D6-0009` | Stores/inventory cost accounting: destroy when 3 years old | `D6-0037` | "Destroy when 3 years old" |
| `D6-0010` | Purchase-card files: destroy at separation or card return | `D6-0048` | "destroyed upon card holder separation or when card is returned" |
| `D6-0001` | Offer pre-1921 records to NARA | `D6-0008` | carried from §9.1 |
| `D6-0007` | Contract-appeal files: destroy 1 year after final resolution | `D6-0039` | "Destroy 1 year after…" |

### 0 misattributed disposition authorities

The unfixed run's four `no` rows attached one item's DAA to another item's
records. In this artifact **no claim quotes a DAA that belongs to a different
item**: every claim that names an item number was compared against the source's
item → DAA map (read off `private/D6.txt`, full strings with the year, because
items 010 and 090 share the eight digits `00030001`), and there are **0
mismatches**. The contradictory rows `D6-0027`/`0029`/`0030`/`0032` of the
unfixed run do not reappear in any form.

### The two `weak` rows

`D6-0017` and `D6-0018` state a disposition for "procurement and payment
records" (item 011) but the record type is in the neighbouring span, so the
subject is outside the quote. Support stays at 49/51 = 96.1%.

## Gold-set recall

Definition (§9): for each gold claim, is a compiled claim — or a set of compiled
claims taken together — present that states the same rule? 10 gold claims per
document, written before the compile.

### D5 — 7/10 = 70.0% (unchanged, exactly on the bar)

| Gold | Rule | Recalled | Where / why not |
|---|---|---|---|
| `D5-0001` | the IDTA has four parts | yes | `D5-0046` |
| `D5-0002` | Exporter is the University of Bristol, through ALSPAC, at Beacon House | **no** | no claim states the legal name or the address; `D5-0008` gives only the two party names |
| `D5-0003` | governing law is England and Wales, and England and Wales is the primary place for claims | **no** | `D5-0092` states the *default* rule and the Table 2 reference, not the selected value |
| `D5-0004` | both Parties are Controllers | **no** | `D5-0002`/`0003`/`0007` were produced and dropped as `weak`/`fabricated` — "Controller" is the checkbox cell, outside the span (see below) |
| `D5-0005` | UK GDPR does not apply to the Importer's processing | yes | `D5-0004` |
| `D5-0006` | cannot end before the Term except breach or written agreement | yes | `D5-0009` (+ `D5-0010`) |
| `D5-0007` | onward transfer only to named co-applicants with a DAA | yes | `D5-0011` + `D5-0013` |
| `D5-0008` | no change to the Mandatory Clauses except as expressly permitted | yes | `D5-0172` |
| `D5-0009` | Importer remains fully liable after sub-contracting | yes | `D5-0243` |
| `D5-0010` | the IDTA ends at the end of the Term, a notice period, by agreement, or under s.29.2 | yes | `D5-0319`/`0320`/`0321` |

The three misses are the same three as the unfixed run, and all three are
**Table 1/Table 2 key/value rows**. The controller-status row is the clearest:
the model produced `D5-0002`/`0003`/`0007` ("the Exporter/Importer is a
Controller"), the audit correctly judged them `weak` — "Controller appears only
in the section heading, not in the quoted text" — and they were dropped. The
label span is `S0022` (`section_path: ["The status of"]`, text "the Exporter In
relation to the Processing of the Transferred Data:"), and the value cell
`Exporter is a Controller` becomes the `section_path` of the **next** span
(`S0023`, which is the page footer). The value is in the artifact — as a
heading — and not in any quote. **This is the same root cause as the 8 `no`
rows**: table cells read column-major, and the label/value split is not
rejoined.

No prompt, schema or threshold was changed to chase these three; §10.7(e)
pre-registers the fix and requires a fresh run.

### D6 — 10/10 = 100% (was 2/10)

D5 and D6 recall are reported per document; both clear 70%.

## Verifier audit vs independent census

Both report 19 `weak`; only 9 of the rows are the same.

| | Count | Rows |
|---|---:|---|
| Both | 9 | `D5-0033`, `D5-0374`, `D5-0375`, `D5-0378`, `D5-0385`, `D5-0410`, `D5-0420`, `D6-0017`, `D6-0018` |
| Verifier only | 10 | `D5-0016`, `D5-0039`, `D5-0069`, `D5-0172`, `D5-0176`, `D5-0386`, `D5-0387`, `D5-0397`, `D5-0401`, `D6-0022` |
| Census only | 18 | `D5-0100`, `D5-0194`, `D5-0272`, `D5-0379`, `D5-0380`, `D5-0381`, `D5-0390`, `D5-0391`, `D5-0392`, `D5-0405`, `D5-0407`, `D5-0411`, `D5-0415`, `D5-0418`, `D5-0423`, `D5-0425`, `D5-0426`, `D5-0421` |

The verifier-only rows are cases where it reads the quote alone: `D5-0386`
("ICO means the Information Commissioner") is `weak` for the verifier because
the quote is only the body, but the locator's `section_path` is `["ICO"]`, which
names the term correctly, and the schema's evidence pair is quote **and**
locator. The census-only rows are the headword mismatches the verifier cannot
see: the quote is right, the locator is wrong. That is the same lesson as Gate 2
and as the DAA rows — the stage's own audit is not the measure.

## What this run does and does not show

**Does.** (1) §10.7(b) fixes the item-numbered table: D6 recall 2/10 -> 10/10,
0 misattributed authorities, support 92.2% -> 96.1%, structural 100%. (2) The
fix is not D5-specific and does not touch D5: D5 spans are byte-identical and
D5 recall is unchanged at 7/10. (3) The probe still fails, now on D5's
"facts absent from source" row, because the key/value tables of the same
document (Tables 1-4 and the Legal Glossary) have the same class of defect that
§10.7(b) does not cover.

**Does not.** It does not show that the key/value fix works; that fix is not
written. It does not re-open the failed run: `gold/probe.*` and
`gold/audit.probe.md` remain the measurement of the unfixed pipeline. It does
not test B1/B2 answer quality on D5/D6 (§10.4: outside this gate).

## Cost

| Item | Calls | Cost |
|---|---:|---:|
| Compile (29 extraction chunks, resumed) | 29 | ~$0.0180 (est.) |
| Verify (audit + 2 repair rounds, resumed) | 14 on the last resume | $0.0333 (19,917 in / 50,512 out) |
| Census | 0 | $0.00 |

Earlier verify resumes are not aggregated by the manifest (counters reset per
resume), so no total is claimed.

## Limits

- One model, two documents, one domain shift. The census is manual and the
  reviewer is the agent that built the pipeline; the claim-level verdicts and
  the span evidence are what a second reviewer can check.
- D6 is 51 claims: one row is worth 1.96 pp of support.
- D5's recall sits exactly on the bar: one claim would move it below.
- The 8 `no` rows are instrument-caused and mechanically repairable, but they
  are still claims the artifact asserts and the source does not. They are
  counted, not excused.
- The conflicts pass remains partial for this run; conflict links are outside
  the §10 gate.
