# Evidence-support audit — second-corpus probe (D5 contract, D6 table)

Artifact: `benchmark/docbench/gold/probe.compiled.verified.jsonl` (gitignored).
Produced by: `benchmark/docbench/compile_claims.py --verify` from D5 and D6,
with the protocol fixed in `PREFLIGHT.md` §10 before any model call.
Date: 2026-11-09. Model: `deepseek-v4.1-flash`.

This is the independent census of the emitted artifact required by §10.4. It is
not the verifier's own audit; that audit reports its own convergence and is
worthless as a measure.

The census worksheet (one row per emitted claim, with every quote and page) was
read end to end: 376 rows. The verdicts are kept locally in
`gold/probe.verdicts.jsonl` (gitignored: the notes name the source corpus,
which is not redistributed in this repo).

## Result in one line

**D5 passes every row: 323/325 claims supported (99.4%), 0 fabrications, recall
7/10 (70.0%, exactly on the bar). D6 passes structural validity and evidence
support (47/51 = 92.2%) but fails recall (2/10 = 20.0%). The gate is per
document, so the probe fails.** Under the gate's literal "facts absent from
source" row, D6 also has four claims that assert an association the source does
not state (one row's disposition authority attached to another row's records);
those four are counted below as `no`, and the row is reported as failed either
way.

## Pre-registered thresholds (§10.4)

| Check | Threshold |
|---|---|
| Structural validity | 100% |
| Evidence support, full census | >= 90% |
| Claims asserting facts absent from source | 0 |
| Gold-set recall proxy | >= 70% |

Per document. A pooled number is reported but does not pass the probe.

## Artifact

| Step | Count |
|---|---:|
| Claims in (raw compile) | 401 |
| Round 1 | 139 failing -> 80 rewritten, 58 re-evidenced, 12 dropped, 28 still failing |
| Round 2 | 38 failing -> 22 rewritten, 8 re-evidenced, 4 dropped, 6 still failing |
| Near-duplicates merged | 9 |
| Residual `weak` kept | 6 |
| Residual `no` / `fabricated` dropped | 0 |
| Claims out | 376 (D5 325, D6 51) |
| Evidence spans out | 512 |
| `check_claims.py` failures | 0 (see the page-check note below) |

The verify stage's own audit converged at 370 `ok` / 6 `weak`; the census below
is independent of it. The six rows it kept are `D5-0008`, `D5-0010`,
`D5-0111`, `D6-0039`, `D6-0045`, `D6-0052`.

## Method

1. Span-first segmentation of `pdftotext` default reading order, no `-layout`
   (§10.2). D5: 328 spans. D6: 63 spans.
2. The §9 extraction prompt, schema v2, `deepseek-v4.1-flash`, chunk size 15,
   overlap 2, `min_chars` 60 — unchanged.
3. `verify_claims.py` audit -> repair -> re-audit, unchanged.
4. **Every** emitted claim judged against its own quotes on the census scale
   (`ok | weak | no | fabricated`), no sample.
5. All 376 rows are fresh: the §9.1 join rule cannot apply, because no row in
   this artifact is byte-identical to a D1-D4 row.

Verdict scale: `ok` — every material element is in the quote; `weak` — the
statement is true but a material element (actor, qualifier, exception, number)
is outside its own quote; `no` — the quote does not state the claim or the
modality is strengthened; `fabricated` — the statement asserts a specific fact
with no basis at all.

## Structural validity — and a page-check amendment

`check_claims.py` initially reported **7 page failures out of 512 evidence
spans**. All seven are short quotes that occur on several pages: the glossary
scaffolding `(this is how this word or phrase must be interpreted in the IDTA)`,
`As defined in the UK GDPR.`, `As set out in Table 2: Transfer Details.`,
`Section 1 (This IDTA and Linked Agreements); •`, and a repeated disposition
clause. The checker resolved the quote to its **first** occurrence and
contradicted its own stated contract ("the declared page must match the page
where the quote occurs"): in every one of the seven, the declared page does
contain the quote, and it is the span's actual page.

This is an instrument defect, not an artifact defect. It is fixed as
`PREFLIGHT.md` §10.7(a): `page_containing()` now keeps the declared page when
the quote occurs there, and falls back to the first occurrence only when it does
not. The fix is general (it applies to every PDF document, D1-D6), it changes
neither a threshold nor the artifact, and it is covered by
`benchmark/docbench/tests/test_check_claims.py`. Re-measured on the same
artifact with no model call: **376/376 claims, 512/512 spans, 0 failures**. The
D1-D4 artifact also stays at 0 failures.

| Claim | Declared page | Pages containing the quote |
|---|---:|---|
| `D5-0289` | 28 | 27, 28 |
| `D5-0320` | 32 | 31, 32, 33 |
| `D5-0342` | 33 | 31, 32, 33 |
| `D5-0345` | 34 | 31-35 |
| `D5-0354` | 34 | 33, 34 |
| `D5-0358` | 35 | 31-35 |
| `D6-0053` | 9 | 2, 5, 6, 7, 8, 9 |

Structural validity: **pass**, 0 failures after §10.7(a).

## Evidence support by document

| Document | Claims | ok | weak | no | fabricated | Support | Threshold |
|---|---:|---:|---:|---:|---:|---:|---|
| D5 — ALSPAC IDTA (contract) | 325 | 323 | 1 | 1 | 0 | **99.4%** | pass |
| D6 — NARA GRS 1.1 (table) | 51 | 47 | 0 | 4 | 0 | **92.2%** | pass |
| **Total** | **376** | **370** | **1** | **5** | **0** | **98.4%** | |

The pooled 98.4% is reported for completeness only. D6's 92.2% is above the bar
but coarse: one claim moves it by 1.96 pp.

### The six non-ok rows

They are kept and listed, not hidden.

| Claim | Verdict | What is outside the quote |
|---|---|---|
| `D5-0010` | weak | Table 2 defines a **place** — "Primary place for legal claims to be made by the Parties". The claim turns the field label into a rule ("legal claims are to be made by the Parties") and gives the table's law field without its value. The first half is supported; the second is a misreading of a table cell. |
| `D5-0348` | no | The glossary defines **Significant Harmful Impact** (p. 34). The claim defines "Harmful Impact", a term that does not exist in the document. The quote is the definition of a different term. |
| `D6-0027` | no | `DAA-GRS2016-00010001` is item **012**'s disposition authority (bids and proposals), not item **020**'s (financial-statement compilation records). The quote is item 020's description and contains no identifier. |
| `D6-0029` | no | The longer-retention sentence is item **020**'s disposition; its authority is `DAA-GRS2013-00030011`, not `DAA-GRS2016-00010001` (item 012). |
| `D6-0030` | no | The PP&E description is item **030**; its authority is `DAA-GRS2013-00030004`, not `DAA-GRS2013-00030011` (item 020). |
| `D6-0032` | no | The longer-retention sentence is item **030**'s disposition; its authority is `DAA-GRS2013-00030004`, not `DAA-GRS2013-00030011` (item 020). |

The DAA pairings were verified against the official NARA PDF
(`https://www.archives.gov/files/records-mgmt/grs/grs01-1.pdf`) extracted with
`pdftotext -layout`, so the check does not depend on the default-order text the
compiler consumed: item 012 -> `DAA-GRS2016-00010001`, item 020 ->
`DAA-GRS2013-00030011`, item 030 -> `DAA-GRS2013-00030004`.

**Fabrication row.** On the census scale, `fabricated` means "a specific fact
with no basis at all", and the number is 0: every DAA string exists in the
document. Read literally, though, the gate row says "claims asserting facts
absent from source", and the four D6 associations are absent from (and
contradicted by) the source. The honest report is therefore **4**, not 0, and
the row fails. The distinction is recorded rather than hidden; it does not
change the verdict, which already fails on D6 recall.

## Gold-set recall

Definition (§9): for each gold claim, is a compiled claim — or a set of compiled
claims taken together — present that states the same rule? The gold set is 10
claims per document, written from the source before the compile and not
adjusted afterwards.

### D5 — 7/10 = 70.0% (exactly on the bar)

| Gold | Rule | Recalled | Where |
|---|---|---|---|
| `D5-0001` | The IDTA has four parts | yes | `D5-0051` |
| `D5-0002` | Exporter is the University of Bristol, through ALSPAC, at Beacon House | **no** | no claim states the Exporter's legal name or address; `D5-0016` is the *ALSPAC DAA's* parties, a different instrument |
| `D5-0003` | Governing law is England and Wales, and England and Wales is the primary place for claims | **no** | `D5-0099` states the *default* when no selection is made; `D5-0010` names Table 2 but gives no value. The selected value is absent. |
| `D5-0004` | Both Exporter and Importer are Controllers | **no** | no emitted claim states either party's Table 2 status |
| `D5-0005` | UK GDPR does not apply to the Importer's processing | yes | `D5-0012` |
| `D5-0006` | The Parties cannot end the IDTA before the Term except for breach or written agreement | yes | `D5-0017` |
| `D5-0007` | Onward transfer only to named co-applicants with a DAA (and IDTA) | yes | `D5-0023` |
| `D5-0008` | No change to the Mandatory Clauses except as expressly permitted | yes | `D5-0067` |
| `D5-0009` | Importer remains fully liable after sub-contracting | yes | `D5-0181` |
| `D5-0010` | The IDTA ends at the end of the Term, a notice period, by agreement, or under s.29.2 | yes | decomposed across `D5-0263`, `D5-0264`, `D5-0265`, `D5-0266` |

D5 passes at exactly 70.0%; the three misses are all Part 1 table facts (the
Exporter row, the governing-law row, the controller-status row).

### D6 — 2/10 = 20.0% (fails)

| Gold | Rule | Recalled | Where |
|---|---|---|---|
| `D6-0001` | Offer pre-1921 records to NARA before applying disposition | yes | `D6-0008` |
| `D6-0002` | Financial-management administrative records: temporary, destroy when 3 years old | **no** | `D6-0011` states only the longer-retention permission |
| `D6-0003` | Financial-transaction records: destroy 6 years after final payment | **no** | `D6-0013` states only the permission |
| `D6-0004` | Unsolicited/unaccepted bids: destroy when no longer required | **no** | no emitted claim mentions the item |
| `D6-0005` | Financial-statement records: destroy 2 years after audit/closure | **no** | `D6-0028` has the trigger and the permission; the destruction rule is not in the artifact |
| `D6-0006` | PP&E records: destroy 2 years after disposal | **no** | `D6-0031`, same shape |
| `D6-0007` | Contract-appeal files: destroy 1 year after final resolution | yes | `D6-0042` ("destroyed after final resolution"; `deadline` = 1 year after) |
| `D6-0008` | Drug-Free Workplace suspensions: destroy 5 years after removal | **no** | the item is absent; `D6-0046` is item 071 ("all other suspensions"), a different row |
| `D6-0009` | Stores/inventory cost accounting: destroy when 3 years old | **no** | `D6-0037` states only the permission |
| `D6-0010` | Purchase-card files: destroy at separation or card return | **no** | `D6-0052` states only the permission |

D6 fails the recall row with 2/10. Even counting every partial row generously
(the permission rows that carry the trigger in `deadline`), the ceiling is 6/10
= 60%, still below 70%.

## Why D6 lost recall — stage attribution

The failure is in **segmentation**, not extraction, not the prompt, not the
repair stage. The spans show it directly.

A D6 record is a four-cell table row: item number, description, disposition
instruction, disposition authority. The PDF text is column-major, so each cell
arrives as its own line block. The segmenter's rule for "a short, Title-Case
line with no terminal punctuation" (`looks_like_heading`) classifies the first
line of the disposition cell as a **section heading**:

| Span | Text the model received | `section_path` |
|---|---|---|
| `S0029` | `longer required for business use.` | `["Destroy when no"]` |
| `S0031` | `after completion of audit or closure of financial statement /accounting treatment/issue, but longer retention is authorized if required for business use.` | `["Destroy 2 years"]` |
| `S0034` | `after asset is disposed of and/or removed from agency's financial statement, but longer retention is authorized if required for business use.` | `["Destroy 2 years"]` |
| `S0039` | `years old, but longer retention is authorized if required for business use.` | `["Destroy when 3"]` |

The line `Destroy 2 years` never enters a span; it becomes the section path.
The remaining `Temporary.` is a block under `min_chars` and is merged into
`short_buffer`, where `flush_short()` drops anything under 20 characters.
Measured on the span file: `Destroy 2 years`, `Destroy 6 years`,
`Destroy when 3` and `Destroy when no` occur in **no span at all**, and the only
span containing `Temporary` is `S0058`, an unrelated page-footer block.

The model can only quote what it is given. It therefore emits the continuation
("…longer retention is authorized") and the trigger, and never the operative
"Temporary. Destroy X after Y". The repair stage cannot recover it either: it
may only re-evidence from existing spans, and the missing sentence has no span.

The same mechanism produces the four DAA misattributions. The authority line is
also a short line, so it becomes a section heading and stays on the stack while
the **next** item's description arrives; the item number between them (`020`)
is a short block that `flush_short()` drops. The result is visible in the span
metadata: `S0030` (item 020's description) carries
`section_path: ["DAA-GRS2016-00010001"]`, item 012's authority; `S0032` (item
030's description) carries item 020's authority. The model read the section
path and wrote the association.

That is one root cause with two symptoms: **table-cell lines are treated as
document headings, and short fragments that carry the row identity are
discarded**. It is a segmentation defect that is general to item-numbered PDF
tables, not a D5/D6 quirk.

## Verifier audit vs independent census

Both report 370 `ok` out of 376 — a coincidence of the total, not of the rows.

| | Non-ok rows |
|---|---|
| Verifier (stage audit, kept `weak`) | `D5-0008`, `D5-0010`, `D5-0111`, `D6-0039`, `D6-0045`, `D6-0052` |
| Independent census | `D5-0010`, `D5-0348`, `D6-0027`, `D6-0029`, `D6-0030`, `D6-0032` |

Only `D5-0010` is in both. The verifier flags citation quality inside D5's
prose; the census catches the D6 identifier misattribution the verifier cannot
see, because each DAA string does appear in a span — only not in the span that
states the record. This is the same lesson as Gate 2: the stage's own audit is
not the measure.

## Cost

| Item | Calls | Cost |
|---|---:|---:|
| Compile (31 chunks, resumed) | 31 | not instrumented (counters reset per resume) |
| Verify (audit + repair + re-audit, resumed) | 5 recorded | $0.0101 (11,968 in / 13,855 out) |
| Census | 0 | $0.00 |

The verify figure is what the manifest records after the resumed rounds; the
compile and the earlier verify attempts are not aggregated by the manifest, so
no total is claimed.

## Limits

- One model, two documents, one domain shift (contract; table-as-content).
- The census is manual and the reviewer is the agent that built the verifier.
  Unlike Gate 2 there is no calibration set for D5/D6; the claim-level verdicts
  and the span evidence are what a second reviewer can check.
- D6 is 51 claims: its percentages are coarse by construction.
- The recall proxy is 10 gold claims per document. D5's 70.0% sits exactly on
  the bar; one claim would move it below.
- §10.7(a) changes the page checker after the failure was measured. It is an
  instrument fix, it is recorded here with the before/after numbers, and it
  changes no statement, quote or threshold.
- The conflicts pass is partial: 3 `conflicts_with` links were removed by the
  verify stage, and no new conflict pass was completed for the probe because
  the gateway returned HTTP 503 on the large prompts. Conflicts are outside the
  §10 gate; the limitation is that the probe artifact's conflict links are not
  a complete audit of D5/D6.
- No B1/B2 answer run was made on D5/D6. §10.4 says those rows are not part of
  this gate; none is reported.

## Erratum (2026-11-09, added with the fixed-run census)

The summary and the table above label D5 **pass** on every row. That is wrong
under the gate's literal wording: `D5-0348` is counted `no` in this very report
(it defines "Harmful Impact", a truncated form of "Significant Harmful Impact"),
so D5 has **1** claim asserting a fact absent from source, not 0, and the
"claims asserting facts absent from source = 0" row fails for D5 as well as for
D6. The probe's verdict is unchanged — it already failed on D6 recall — and no
measured number in this report changes. The correction matters because the same
defect, on the same document, is the reason the fixed run fails
(`gold/audit.probe.fixed.md`).
