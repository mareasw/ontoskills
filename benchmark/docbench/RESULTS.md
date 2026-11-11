# DocBench results

**Dates:** 2026-11-07 (hand-built claims) · 2026-11-08 (machine-compiled claims) ·
2026-11-09 (second-corpus probe, failed run and fixed run).
**Status:** both technical gates pass — the representation (2026-11-07) and
machine extraction (Gate 2, 2026-11-08). The second-corpus probe (2026-11-09)
**fails, twice**. The first run fails on D6 recall: the table document recalls
2/10 gold obligations because disposition cells are segmented as headings. The
fixed run repairs that (D6 recall 10/10, support 96.1%) and **fails again on
D5**, which now has 8 claims asserting a definition for a term the document does
not define, because glossary headwords wrap onto two lines and only the last
line survives as the section heading. The **market gate is still open**: no
interviews, no design partner, no public-evidence memo yet.

The file is chronological: the 2026-11-07 run, then Gate 2 — first attempt
(kept as the measured failure the amendments answer), then **Gate 2 — final**,
then the **second-corpus probe** (failed run), then the **fixed run** it
pre-registered, still failing on a different document and a different row.

## First run (2026-11-07): hand-built claims

## Setup

| Item | Value |
|---|---|
| Model | `deepseek-v4.1-flash` |
| Endpoint | OpenAI-compatible gateway (`/v1/chat/completions`) |
| Temperature | 0 |
| System prompt | identical in all three conditions |
| Output contract | JSON: `answer`, `citation`, `claim_ids` |
| Questions | 40 (32 answerable, 8 unanswerable) |
| Documents | 4 (EU AI Act guidelines, Loyola AI policy, OWASP IR playbook, Greene County RFP) |
| Calls | 120 sequential, no truncation, no retry that changed the answer |

Only the context changes between conditions:

- **B0** — the full document text.
- **B1** — the top 5 paragraphs retrieved with BM25.
- **B2** — the compiled claims for the document: statement, modality, actor,
  deadline, conditions, verbatim quote and locator.

## Automatic triage

| Condition | answer recall | citation present | citation supported | citation matches gold | abstention correct | input tok (total) | output tok | reasoning tok | avg latency |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| B0 | 85.5% | 87.5% | 82.5% | 80.0% | 95.0% | 281,246 | 8,796 | 6,068 | 5.8 s |
| B1 | 57.3% | 60.0% | 60.0% | 55.0% | 75.0% | 49,532 | 6,593 | 4,427 | 4.2 s |
| B2 | 90.1% | 80.0% | 80.0% | 80.0% | 100.0% | 42,696 | 6,257 | 3,910 | 4.7 s |

These heuristics only triage. `citation present` is lower for B2 by
construction: an unanswered question correctly returns an empty citation.

## Manual review

Every one of the 120 answers was read against the gold answer and the source
text. One question (`D4-Q10`) is excluded because the gold label is wrong: the
RFP says *"The County may issue multiple awards"*, so an answer that says "not
specified, possibly multiple" is supported by the document and should not be
counted as a failure. 39 questions remain.

| Condition | Answer correct | Answerable (32) | Unanswerable (7) | Verbatim, on-point citation | Partial citation | Unsupported claims |
|---|---:|---:|---:|---:|---:|---:|
| B0 | 38/39 — 97.4% | 32/32 | 6/7 | 30/32 — 93.8% | 2 | 0 |
| B1 | 28/39 — 71.8% | 22/32 | 6/7 | 22/32 — 68.8% | 1 | 0 |
| B2 | **39/39 — 100%** | 32/32 | **7/7** | **31/32 — 96.9%** | 1 | **0** |

### What failed

**B1 (BM25 top-5)** — 10 answerable questions wrong:

- The 8 OWASP response-time and escalation questions all came back `UNKNOWN`.
  The playbook is a table-heavy document; five fixed-size paragraphs did not
  contain the rows that answer them.
- `D4-Q02` (contract term): `UNKNOWN` — the sentence was not retrieved.
- `D4-Q06` (deadline): answered "February 12, no inconsistency" — the January 22
  clause was in a different paragraph and never retrieved. A retrieval baseline
  cannot report a conflict it did not retrieve.

**B0 (full document)** — one wrong answer:

- `D3-Q09` ("how many users were affected?"): answered *"Approximately 12,400
  users"*. That number is the download count of a **fictional example incident**
  inside the template playbook (`suspicious-skill-123`), not a real figure. The
  full document invites this error; a context without the example does not.
- Two citations were not verbatim (`D3-Q03`, `D4-Q06` used `...`), and `D3-Q10`
  cited the placeholder `[Number]`.

**B2 (compiled claims)** — no answer errors. One partial citation:

- `D4-Q06`: the answer states both deadlines and the conflict, and the claim ids
  include all four conflicting claims, but the single `citation` field quotes
  only the January 22 sentence. The evidence is complete in the claim set, not
  in the one quote. This is a schema-level point: a single citation field cannot
  represent a two-sided conflict.

## What the numbers say

1. **B2 matches B0 on answerable questions (32/32) at 15% of the input tokens**
   (42,696 vs 281,246). The saving is structural, not a prompt trick.
2. **B2 beats B1 by +28 points on answer accuracy and +28 points on citation
   accuracy.** On this corpus, paragraph RAG fails where structure carries the
   answer (tables, cross-references, conflicting deadlines).
3. **The only question where B2 beats B0 is the abstention trap** (`D3-Q09`).
   That is the claim-layer thesis in one row: a claim carries its own evidence,
   so an example inside a template does not silently become a fact.
4. **Zero unsupported claims in all three conditions**, but B0 reaches that only
   with a quote-following prompt; B2 gets it from the context itself.

## Independent re-score (2026-11-08)

The manual pass above was made by the same agent that built the harness, which
is a conflict of interest. The 120 answers were therefore re-scored by an
independent reviewer with the condition label and the claim ids stripped
(`build_blind_sheet.py`, `key.json` withheld), then unblinded and compared
(`compare_blind.py`, `blind_metrics.py`).

Because a reviewer can tell an abstention from a wrong answer, the citation
metric is reported on **answerable questions only** (32 per condition); an empty
citation on a correct abstention is not a failure.

| | B0 | B1 | B2 |
|---|---:|---:|---:|
| Answer correct (39) | 38/39 — 97.4% | 28/39 — 71.8% | **39/39 — 100%** |
| Citation verbatim and on point (32 answerable) | 26/32 — 81.2% | 21/32 — 65.6% | **30/32 — 93.8%** |
| Citation partial | 6 | 2 | 2 |
| Unsupported claims | 0 | **1** | 0 |
| Correct abstention (7 unanswerable) | 6/7 | 6/7 | **7/7** |

**Agreement with the original pass:** 117/117 answers, zero flips. The answer
scores are not an artefact of who did the scoring. Of the 24 citation
disagreements, 18 are the convention above (an empty citation on a correct
abstention) and 6 are real — every one of them a two-part answer supported by a
quote that covers only one part (four in B0, one in B1, one in B2).

**Deltas under the clean convention:** B2 − B1 = **+28.1 pp** on citation
quality, identical to the original number; B2 − B0 = **+12.5 pp**. The decision
rule (+15 pp vs B1) survives an independent, stricter reviewer.

**Two things the re-score changed:**

1. **B1 makes an unsupported claim, and it is the worst kind.** On `D4-Q06`
   (conflicting deadlines) it answers *"The provided context does not show an
   inconsistency."* That is a negative about the whole document asserted from
   five retrieved paragraphs. Paragraph RAG does not merely miss a conflict; it
   certifies its absence. The original pass scored it as 0 unsupported claims.
2. **B0's citation gap is larger than reported** (81.2%, not 93.8%): six of its
   answers are multi-part, and one quote cannot cover them. B2's answers are
   more atomic, so a single quote usually does. This is a real, structural
   advantage of compiling claims, not a scoring artefact — but it is
   smaller than the original pass implied, and it is the honest number to quote.

**Still not blind in the strict sense.** The reviewer was an LLM agent with no
access to the labels, but B2 answers are visibly shorter and more atomic, which
can hint at the condition. A human reviewer remains the only fully blind option.

### Decision rule from `PREFLIGHT.md`

| Criterion | Threshold | Measured | Verdict |
|---|---|---|---|
| Citation accuracy vs B1 | ≥ +15 pp | +28.1 pp | pass |
| Answer accuracy vs B1 | ≥ −5 pp | +28.2 pp | pass |
| Unsupported claims | 0 | 0 | pass |
| Tokens per correct answer | ≤ +20% vs B1 | 1,095 vs 1,769 (−38%) | pass |

Technical gate: **pass on this run**.

## Gate 2 — machine extraction, first attempt (2026-11-08) — superseded

> **Superseded by "Gate 2 — final" below.** This section is the *raw compile*
> measured against the gate, before the repair stage existed. It is kept
> unchanged because it is the honest failure the amendments were written
> against: evidence support at 88.8% is what triggered `PREFLIGHT.md` §9.1–§9.4.
> Do not cite its verdict as the current one.

The 2026-11-07 run used hand-built claims: it validated the representation, not
the compiler. Gate 2 was fixed in `PREFLIGHT.md` §9 before the run and is
scored here.

**Artifact.** `gold/claims.compiled.jsonl`, `deepseek-v4.1-flash`, one pass, no
tuning against the gold set: 420 spans, 33 chunks, 517 claims, 15 rejected,
24 near-duplicates merged, 11 truncation retries, 5 conflict pairs, 1 conflict
batch failure, 105,095 input / 209,723 output tokens.

### What the compiler got right

- **Structural validity: 517/517 claims, 554/554 evidence spans, 0 failures.**
  Every quote is verbatim in the source, every PDF page recomputed, every claim
  valid against `schemas/claim.v2.schema.json` (all v2).
- **Fabrications: 0.** No claim asserts a fact absent from its source.
- **Recall proxy: 40/41 = 97.6%** (D1 10/10, D2 10/10, D3 9/10, D4 11/11). The
  single miss is `Step 3: Notification & Escalation (30 minutes)`: the span
  exists and was sent to the model, no claim came back. Extraction variance, not
  segmentation.
- **Conflicts: 5 pairs, all real.** `D4-0048` (22 Jan 2026) vs `D4-0077`
  (12 Feb 2026) is the substantive contradiction; `D4-0010`/`D4-0014` vs
  `D4-0050` is the `#20246-001` / `#2026-001` typo; `D1-0057` vs `D1-0073` is
  access vs redaction; `D2-0089` vs `D2-0090` is the reporting path.
- **A segmentation defect was found and fixed before this run.** The first clean
  compile produced `D3-0002 = "1 hour, classified HIGH (Orange)"`: a flattened
  HTML table ships every cell as a block, so all rows were headings and the band
  label was popped before the row that used it. The segmenter now keeps a band
  label with its rows (commit `06ba3b1`). Blast radius measured before the paid
  run: 4 lines change class, 0 headings lost, 420 spans before and after, 41/41
  gold quotes still covered. The result reads CRITICAL 1 hour, HIGH 4 hours,
  MEDIUM 1 business day, LOW 1 week.

### What it got wrong: evidence support does not pass

| Verdict | Census (517) | Sample (60) |
|---|---:|---:|
| ok — quote states the claim | 459 (88.8%) | 57 (95.0%) |
| weak — true, but a material element is outside the quote | 55 (10.6%) | 3 (5.0%) |
| no — quote does not state it, or modality changed | 3 (0.6%) | 0 |
| fabricated | 0 | 0 |

The pre-registered sample passes the 90% bar; the full census (run afterwards,
because a lexical screen flagged too many claims) does not. Sampling by stride
under-drew the largest defect cluster: D3 repeats the same fault 14 times, so a
one-in-five stride can miss a run of consecutive cases.

The defects are systematic: 28 claims carry an actor or subject supplied from a
heading or a list lead-in, 21 carry a qualifier from a heading or the adjacent
line, 4 drop an exception present in the source (the statement is broader than
the rule), 2 add a specific number or action, 2 cite an unrelated quote, 1
strengthens `should` to `must`. Full table: `gold/audit.run3.md`.

Root cause is structural, not stochastic: the quote is the whole *span*, and
spans are large (median 432 characters, 54% over 400, one quote shared by 10
claims). When the subject lives in the heading, the extractor writes a complete
sentence and cites a span that does not contain the subject. `check_claims.py`
stays green because "verbatim in the source" and "states this claim" are
different properties.

### Gate 2 criteria

| Check | Threshold | Measured | Verdict |
|---|---|---|---|
| Structural validity | 100% | 517/517, 0 failures | pass |
| Evidence support, pre-registered sample | ≥ 90% | 57/60 = 95.0% | pass |
| Evidence support, full census | ≥ 90% | 459/517 = **88.8%** | **fail** |
| Claims asserting facts absent from source | 0 | 0 | pass |
| Gold-set recall proxy | ≥ 70% | 40/41 = 97.6% | pass |
| B2 − B1 citation, compiled claims | ≥ +15 pp | 75.0 − 60.0 = **+15.0 pp** | pass (exactly) |
| B2 answer vs hand-built B2 (100%) | within 5 pp | blind **97.4% (−2.6 pp)**; automatic 83.9% (−6.2 pp) | pass on blind, fail on the automatic proxy |

**Gate 2 does not pass.** Five of the seven rows pass outright; the sixth passes
exactly at its threshold; evidence support fails on the full set. Per the stop
rule, the response is a pipeline change, not prompt tuning — the ranked fixes
are in `gold/audit.run3.md`.

### B2 with compiled claims — read the retrieval switch separately

`PREFLIGHT.md` §9 requires reporting the retrieval change separately from
extraction quality. With 517 claims, **every document exceeds the 12-claim
context cap (D1 148, D2 95, D3 83, D4 191), so all 40 questions ran in
`bm25_claims` mode**. The hand-built set had ≤ 12 claims per document and ran in
`all_claims` mode. The B2 number below therefore measures *retrieval +
extraction*, not extraction alone.

| Run | Answer recall (auto) | Citation supported (auto) |
|---|---:|---:|
| Hand-built B2 (`20261107T140843Z`) | 90.1% | 80.0% |
| Compiled B2 (`20261108T141134Z`) | 83.9% | 75.0% |
| B1, fresh, same day (`20261108T141837Z`) | 57.0% | 60.0% |

- **B2 − B1 citation = +15.0 pp**, exactly at the threshold. The fresh B1
  reproduces the 2026-11-07 B1 to the decimal (60.0%), which is expected: B1
  never reads the claim file, so a claims change cannot move it.
- **B2 answer: −6.2 pp against the hand-built B2 on the automatic metric**
  (83.9 vs 90.1), which misses the 5 pp window by 1.2 pp. The automatic
  `answer_recall` is word overlap and penalises longer correct answers
  (`D1-Q03` goes 1.0 → 0.4 while the answer gets more complete). The blind
  re-score is the fair measure: **38/39 = 97.4%**, i.e. −2.6 pp, inside the
  window. Both are reported; the gate text calls the automatic metric triage.

### The two unsupported answers are not fabrications

- `D3-Q06` — the answer needs two claims (CRITICAL = 1 hour, and the 15-minute
  step). Its `claim_ids` are correct and complete (`D3-0002`, `D3-0006`,
  `D3-0061`, `D3-0062`), but the single `citation` field carries only
  `Response time : 1 hour`. The answer is supported; the field cannot express
  it. This is measured evidence for the `{answer, claim_ids}` contract that
  `docs/adr/0001-document-first-kernel.md` left unshipped.
- `D4-Q06` — the question asks for the deadline and any inconsistency. The
  retrieved context holds `D4-0010`/`D4-0014` with `CONFLICTS WITH: D4-0050`,
  but not `D4-0050` itself, and not `D4-0048`/`D4-0077` (the 22 Jan / 12 Feb
  pair). The model answered the deadline and explicitly said the conflict's
  substance was not in the context. That is a retrieval defect with honest
  behaviour, not an invented answer. Fix: expand retrieved claims with their
  `conflicts_with` closure.

### Cost

| Item | Input | Output | Cost |
|---|---:|---:|---:|
| Compile, 3 attempts (2 aborted/resumed + final) | 268,791 | 523,723 | $0.355 |
| B2 with compiled claims, 40 answers | ~76,900 | ~9,440 | $0.017 |
| B1 fresh, 40 answers | 49,532 | 6,971 | $0.012 |

About **$0.38** for the whole gate, against the ~$0.02 estimated in
`PREFLIGHT.md` §9. The estimate was wrong by an order of magnitude: output
tokens dominate because reasoning tokens are generated on every call
(209,723 output for 105,095 input on the final compile), and the prefix needed
three attempts. The per-run cost is still small, but the estimate in the
preflight was not honest and is corrected here.

## Gate 2 — final (2026-11-08)

Gate 2 is fixed in `PREFLIGHT.md` §9. The first attempt failed on evidence
support (88.8%); the amendments in §9.1–§9.4 were written against that measured
failure, one at a time, and each one's effect was measured before the next was
written. **Only this section's numbers count as the verdict**; everything above
marked superseded is history.

**Artifact.** `gold/claims.verified.jsonl`: 504 claims, 586 evidence spans, all
schema v2, `check_claims.py` failures 0. It is the run-3 compile (517 claims)
passed through `verify_claims.py`: round 1 repaired 139 failing claims (95
rewritten, 47 re-evidenced, 2 dropped), round 2 repaired 19 (8, 10, 1), 10
near-duplicates merged, 11 residual `weak` kept and listed, 0 residual
`no`/`fabricated` dropped.

### Gate 2 criteria — final

| Check | Threshold | Measured | Verdict |
|---|---|---|---|
| Structural validity | 100% | 504/504 claims, 586/586 spans, 0 failures | pass |
| Evidence support, full census | ≥ 90% | 499/504 = **99.0%** | **pass** |
| Claims asserting facts absent from source | 0 | 0 | pass |
| Gold-set recall proxy | ≥ 70% | 40/41 = 97.6% | pass |
| B2 − B1 citation, compiled claims (automatic) | ≥ +15 pp | 80.0 − 60.0 = **+20.0 pp** | pass |
| B2 − B1 citation, blind (n = 32 answerable) | ≥ +15 pp | 84.4 − 62.5 = **+21.9 pp** | pass |
| B2 answer vs hand-built B2 (100%) | within 5 pp | blind **97.4% (−2.6 pp)** | pass |

The census is the independent one in `gold/audit.run4.md`: every row of the
emitted artifact judged fresh or carried over by the join rule pre-registered in
`PREFLIGHT.md` §9.1. By document: D1 142/144, D2 90/92, D3 79/79, D4 188/189.
The 5 misses are `weak`, not wrong — each statement is true, with one material
element outside its own quote — and each is listed in that report. There are 0
`no` and 0 `fabricated` claims.

### How each amendment was paid for

| Amendment | Defect measured | What changed | Effect |
|---|---|---|---|
| A1 (`§9.1`) | support 88.8% < 90% | audit → repair → re-audit stage, drop every residual | support 99.4%, but recall 39/41 and B2 citation only +10 pp |
| A2 (`§9.2`) | A1 dropped 6 census-`ok` claims; `D1-Q08` lost | keep residual `weak`, drop only `no`/`fabricated` | 504 claims, support 99.0%, recall 40/41, `D1-Q08` answered again |
| A3 (`§9.3`) | 4/5 unsupported B2 citations were claim *statements*, which the prompt allowed and the metric rejects | one explicit citation contract in the shared prompt; re-run B1 and B2 | B2 citation 67.5%, B1 unchanged |
| A4 (`§9.4`) | the other defect: `QUOTE` lines that concatenate several spans are not contiguous document text | one mechanical retry, checked against the source, identical for B1/B2 | fired 5/40 B2, 0/40 B1; B2 citation 80.0% |

Each of these was added *after* seeing the number it fixes, which is exactly
what a stop rule is for; none changed a threshold, the census method, or the
gate's definition. The final support number is not the verifier's own audit: a
stage that repairs and re-judges would report ~100% by construction. It is a
fresh census of the emitted text.

### B2 with compiled claims (automatic metrics)

With 504 claims every document still exceeds the 12-claim context cap, so all 40
questions run in `bm25_claims` mode. B2 therefore measures *retrieval +
extraction*, and it is compared against a B1 run made in the same session.

| Run | Artifact | Answer recall | Citation supported | Citation matches gold |
|---|---|---:|---:|---:|
| `20261107T140843Z` | hand-built, `all_claims` | 90.1% | 80.0% | — |
| `20261108T141134Z` | 517 raw compile | 83.9% | 75.0% | 72.5% |
| `20261108T194632Z` | 493, A1 drop-all | 81.5% | 70.0% | 65.0% |
| `20261108T195811Z` | 504, old prompt | 83.2% | 70.0% | 62.5% |
| `20261108T200226Z` | 504, A3 prompt | 82.2% | 67.5% | 77.5% |
| **`20261108T201155Z`** | **504, A3 + A4 retry** | **79.6%** | **80.0%** | **77.5%** |
| `20261108T201155Z` | **B1, same run** | **57.0%** | **60.0%** | **55.0%** |

The final run's B2 citation is 80.0% — equal to the hand-built set's 80.0% — and
20.0 pp above B1. The automatic answer recall falls from 83.2% to 79.6% across
the A3/A4 change; the blind re-score below shows that this is the metric, not the
answers: `answer_recall` is word overlap and penalises longer, more complete
answers.

### Blind re-score of the final run

| | B1 | B2 | Delta |
|---|---:|---:|---:|
| Answer correct (n = 39, `D4-Q10` excluded) | 28/39 = 71.8% | **38/39 = 97.4%** | +25.6 pp |
| Citation whole (of 32 answerable) | 20/32 = 62.5% | **27/32 = 84.4%** | **+21.9 pp** |
| Heavily partial | 3/32 | 5/32 | |
| Unsupported citation | 1 | 1 | |
| Correct abstention (of 7 unanswerable) | 6/7 | 7/7 | |

B2 at 38/39 is −2.6 pp against the hand-built B2's 100%, inside the 5 pp window.
The single B2 miss is `D4-Q06`, where the retrieved context did not include the
conflicting claim — a retrieval defect, still open, and the reason the next
change is `conflicts_with` closure in retrieval rather than more extraction.

### Cost

| Item | Calls | Cost |
|---|---:|---:|
| Compile (3 attempts, 2 resumed) | 18+ | ~$0.36 |
| Verify stage, 517 claims, two rounds | 204 | ~$0.15 |
| Emit the A2 artifact (`--resume` on the per-claim cache) | 0 | $0.00 |
| B1 + B2, 80 answers, final run | 85 | ~$0.04 |
| All baseline runs in this section | ~480 | ~$0.22 |

About **$0.73** for the whole gate against the ~$0.02 preflight estimate. The
error is output tokens at reasoning price, not input; the preflight estimate is
corrected in the superseded section above and in `gold/audit.run4.md`.

## Second corpus probe (2026-11-09) — contract + table

The probe is fixed in `PREFLIGHT.md` §10, before any model call on D5/D6. It
asks one narrow question: does the compiler that reached 99.0% support on
D1-D4 still produce supported, non-fabricated claims when the document type
changes? The gate is **per document**: structural 100%, support >= 90%,
fabrications 0, gold recall >= 70%, for each document. A pooled number cannot
pass a failing document.

**Artifact.** `gold/probe.compiled.verified.jsonl`: 376 claims (D5 325,
D6 51), 512 evidence spans, `check_claims.py` 0 failures, 9 near-duplicates
merged, 6 residual `weak` kept, 0 residual `no`/`fabricated` dropped. The full
census is
`gold/audit.probe.md`; every row was judged, not sampled.

| Document | Type | Structural | Support (census) | Fabrications | Recall | Verdict |
|---|---|---|---|---:|---:|---|
| **D5** | contract (ALSPAC IDTA v1) | 100% | 323/325 = **99.4%** | 0 | 7/10 = **70.0%** | **pass** |
| **D6** | table-as-content (NARA GRS 1.1) | 100% | 47/51 = **92.2%** | 0 (4 literal) | 2/10 = **20.0%** | **fail** |
| Pooled | | 100% | 370/376 = **98.4%** | 0 | — | reported only |

**Verdict: the probe fails.** D6 misses the recall bar by 50 pp. D5 passes at
exactly 70.0%, so the contract result is not used to average D6 away. There are
0 `fabricated` claims on the census scale; under the gate's literal "facts
absent from source" row D6 has four, because it attaches a row's disposition
authority to the neighbouring row's records. Both readings are reported; the
verdict does not depend on which is used.

**Erratum (2026-11-09).** An earlier version of this section said D5 "passes
every row". That is wrong under the gate's literal wording: `D5-0348` is `no` in
the census, so D5 has **1** claim asserting a fact absent from source, not 0,
and the "facts absent from source = 0" row fails for D5 as well as D6. The
probe verdict is unchanged (it already failed on D6 recall) and no measured
number changes; the same erratum is appended to `gold/audit.probe.md`.

**The support misses are kept visible.** `D5-0010` (`weak`) turns Table 2's
"primary place for legal claims" field into a rule; `D5-0348` (`no`) defines
"Harmful Impact", a truncated form of "Significant Harmful Impact"; `D6-0027`,
`D6-0029`, `D6-0030`, `D6-0032` (`no`) each cite the disposition authority of
the neighbouring item. The DAA pairings were checked against the official NARA
PDF, not against the text the compiler consumed.

### Why D6 failed — segmentation, not extraction or repair

A D6 row has four cells: item number, description, disposition instruction,
disposition authority. Default-order `pdftotext` delivers each cell as its own
line block. The segmenter's "short Title-Case line is a heading" rule consumes
`Destroy 2 years`, `Destroy when 3`, `Destroy 6 years` and `Destroy when no` as
`section_path`, so those lines never enter a span; the residual `Temporary.` is
under `min_chars` and is dropped by `flush_short()` (`< 20` characters). The
span file confirms it: none of the four disposition prefixes, and none of the
item keys (`012`, `020`, …), occurs in any span. The model therefore emits the
continuation ("…longer retention is authorized") and the trigger, never
"Temporary. Destroy X after Y". Repair cannot re-evidence a sentence that has no
span. The same mechanism puts row N's authority line on the heading stack while
row N+1's description arrives, which is exactly the four `D6-0027/29/30/32`
misattributions.

This is a real generalisation finding: the compiler is span-first and honest,
but its segmenter has no notion of a table record. A fix is pre-registered as
`PREFLIGHT.md` §10.7(b) and will be measured on a fresh compile of both D5 and
D6; the failed run stays as the measurement of the unfixed pipeline.

### Instrument amendment (§10.7(a))

`check_claims.py` first reported 7 page failures on 512 spans. All seven are
quotes that recur on several pages (glossary scaffolding, a repeated disposition
clause) and the declared page does contain the quote; the checker's
first-occurrence rule contradicted its own contract. The checker now keeps the
declared page when the quote occurs there, with a test. Re-measured on the same
artifact, no model call: **0 failures**. No statement, quote, threshold or
artifact changed; D1-D4 remain at 0 failures.

### What the probe did not test

No B1/B2 answer run was made on D5/D6, so no answer or citation row is reported:
§10.4 fixes that as outside this gate, and 16 questions cannot support the 15 pp
delta used in Gate 2.

## Second corpus probe, fixed run (2026-11-09) — D6 fixed, D5 fails

The failed run above stands as the measurement of the unfixed pipeline. A second
run applied the record-segmentation rule pre-registered as `PREFLIGHT.md`
§10.7(b) and was measured under the same §10 gate, thresholds and census scale.
The two scheduling amendments made while resuming (concurrency, split-on-failure,
§10.7(c)/(d)) change throughput and retry only, not the prompt or the claim.

**Artifact.** `gold/probe.fixed.compiled.verified.jsonl`: 429 claims compiled
(D5 378, D6 51), 405 after verify (D5 354, D6 51), 552 evidence spans,
`check_claims.py` 0 failures, 15 near-duplicates merged, 19 residual `weak`
kept, 0 residual `no`/`fabricated` dropped. The full census is
`gold/audit.probe.fixed.md`; 405 rows were judged, no sample.

| Document | Type | Structural | Support (census) | Facts absent | Recall | Verdict |
|---|---|---|---:|---:|---:|---|
| **D5** | contract (ALSPAC IDTA v1) | 100% | 329/354 = **92.9%** | **8** | 7/10 = **70.0%** | **fail** |
| **D6** | table-as-content (NARA GRS 1.1) | 100% | 49/51 = **96.1%** | 0 | 10/10 = **100%** | **pass** |
| Pooled | | 100% | 378/405 = **93.3%** | 8 | — | reported only |

**Verdict: the probe fails again.** D6 is fixed on every row, including the one
it failed before: recall 2/10 -> 10/10, every disposition instruction inside its
own quote, and **0** misattributed disposition authorities against the source's
full item -> DAA map (year included, because items 010 and 090 share the same
eight digits). Support 92.2% -> 96.1%; the two remaining `weak` rows lose the
record type, not the disposition.

D5 fails on the row that is zero by definition: **8 claims assert a definition
for a term the document does not define** — `Safeguards`, `Delay`, `Data`,
`Clauses` (twice), `Country`, `Controller`, `Protection Laws`. All eight are
glossary entries whose headword is printed on two lines ("Appropriate /
Safeguards", "Without Undue / Delay", "Special Category / Data", …); the
segmenter keeps only the last line as `section_path`, so the model is told the
term is `Delay` and defines `Delay`. Two are actively wrong, not just
mislabelled: `Data` is narrowed to special category data and `Controller`
receives the *Third Party Controller* definition while the glossary defines
`Controller` as "As defined in the UK GDPR". The same mechanism explains the
three D5 recall misses: Tables 1-4 are key/value tables, and the
`Exporter is a Controller` value cell becomes the `section_path` of the following
span (`S0022`/`S0023`), so the controller-status claims were dropped as `weak`.

This is not a new criterion applied after the score was seen: the unfixed run
already contained one instance (`D5-0348`, "Harmful Impact") and its census
already counted it `no`. It is the same class of defect as §10.7(b), on a table
without item numbers; the fix is pre-registered as §10.7(e)(i) for a **fresh**
run of both documents, and was not applied to the artifact measured here.

**What the fixed run shows.** (1) The record segmentation works on the document
it was written for, and it does not touch D5 — D5 spans are byte-identical and
D5 recall is unchanged at 7/10. (2) The remaining D5 failure is a pre-existing
key/value-table defect, not a regression. (3) A support number above the bar
(92.9%) coexists with a hard failure on the facts-absent row; the per-document
gate is what catches that, which is why a pooled 93.3% is not used to pass the
probe.

## Second corpus probe, key/value fix (2026-11-10) — rejected by its own criteria

A third run applied the key/value segmentation pre-registered as
`PREFLIGHT.md` §10.7(e)(i), on the same documents, model, prompt, schema and
thresholds. The two earlier runs and their censuses are untouched.

**Artifact.** `gold/probe.kv.compiled.verified.jsonl`: 411 claims compiled
(D5 348, D6 63), **397 after verify** (D5 335, D6 62), 532 evidence spans,
`check_claims.py` 0 failures, 33 near-duplicates merged on compile and 7 on
verify, 12 residual `weak` kept, 0 residual `no`/`fabricated`. The full census is
`gold/audit.probe.kv.md`; 397 rows were judged, no sample.

| Document | Type | Structural | Support (census) | Facts absent | Recall | Verdict |
|---|---|---|---:|---:|---:|---|
| **D5** | contract (ALSPAC IDTA v1) | 100% | 329/335 = **98.2%** | **0** | 8/10 = **80.0%** | **fail** |
| **D6** | table-as-content (NARA GRS 1.1) | 100% | 61/62 = **98.4%** | 0 | 10/10 = **100%** | **pass** |
| Pooled | | 100% | 390/397 = **98.2%** | 0 | — | reported only |

**Verdict: the fix is rejected.** §10.7(e)(i) required D5 to reach 0 facts
absent and to recall `D5-0002`, `D5-0003` and `D5-0004` while keeping recall
>= 70%. Two of the four hold — 0 facts absent and `D5-0004` (recalled by
`D5-0007` *Exporter is a Controller* + `D5-0009` *Importer is a Controller*) —
and recall stays above the bar at 80%. `D5-0002` and `D5-0003` are not recalled,
so the fix fails its own pre-registered condition: overall recall does not
substitute for a named claim.

What it repaired is real. The eight D5 glossary definitions of a term the
document does not define (`Country`, `Safeguards`, `Clauses` twice, `Data`,
`Controller`, `Protection Laws`, `Delay`) do not reappear in any form; the
joined headwords are correct and the definition-body-only `weak` rows of the
fixed run now name their term. D5 "facts absent from source" goes 8 -> **0** and
support 92.9% -> 98.2%. D6 keeps its pass with 0 misattributed DAAs.

The two misses have different causes, and neither is what the region rule
addresses:

- **`D5-0002` is an extraction miss.** The segmenter produces the exporter row
  (`S0007` `Full legal name: University of Bristol (through ALSPAC)`, `S0008` the
  Beacon House address), both in the first chunk with the Table 1 rows the model
  did use; of 411 raw claims, none quotes `Full legal name`, `Beacon House` or
  `BS8`. `S0008` also opens with a stale `Full legal name:` prefix from the
  Importer's empty cell.
- **`D5-0003` is quoted, then audited away.** The primary-place row is a
  colonless four-line label: the label is joined into `section_path`, the value
  `England and Wales` stays in `S0018`. The raw compile did state the rule
  (`D5-0006`); the verify stage judged it `weak` because the label was not in
  the quote, and re-evidencing it on the governing-law cell replaced the
  primary-place rule with the governing-law rule.

D6's pass is not evidence for the fix: its spans are **byte-identical** to the
fixed run (35 spans, same sha), so its input did not change. The support move
96.1% -> 98.4% is model nondeterminism on the same 35 spans (63 raw claims vs
51), not the segmentation.

One residual regression is recorded: the bogus `section_path`
`["Laws", "15.2.1.5 contact point for more information; and"]` attaches to 27
spans / 49 claims here, against 6 spans / 19 claims in the fixed run (pages
16-20). Page and quote are right, no census verdict moves, but a wrong locator
on 49 claims is not a clean fix.

**What this run shows.** (1) The two-line glossary headword defect is fixed at
the root: 8 unsupported definitions -> 0, and D5 support reaches 98.2%, the best
this corpus has produced. (2) Support above the bar still coexists with a hard
failure, twice in a row: the gate that catches it is the per-document named
recall, not the pooled support. (3) The key/value branch is not sufficient on
D5: a correctly segmented row is not a claim (extraction), and a correctly
located value is not accepted by the quote-only repair policy (verify).

**What it does not show.** It does not show that the key/value rule works as a
fix; it shows that it works in part and is not sufficient. It does not re-open
the earlier runs; `gold/probe.*`, `gold/probe.fixed.*` and their censuses remain
the measurement of those pipelines. It does not test B1/B2 answer quality on
D5/D6 (§10.4: outside this gate).

## Second corpus probe, row claims + section guard (2026-11-10) — rejected on `D5-0003`

A fourth run applied the row-claim rule and the repair section guard
pre-registered as `PREFLIGHT.md` §10.7(f), with the gap fix of §10.7(f)(i), on
the same documents, model, prompt, schema and thresholds. The three earlier runs
and their censuses are untouched.

**Artifact.** `gold/probe.rows.compiled.verified.jsonl`: 394 claims compiled
(D5 343, D6 51), **389 after verify** (D5 338, D6 51), 516 evidence spans,
`check_claims.py` 0 failures, 25 near-duplicates merged on compile and 4 on
verify, 9 residual `weak` kept, 0 residual `no`/`fabricated`. The full census is
`gold/audit.probe.rows.md`; 389 rows were judged, no sample.

| Document | Type | Structural | Support (census) | Facts absent | Recall | Verdict |
|---|---|---|---|---:|---:|---|
| **D5** | contract (ALSPAC IDTA v1) | 100% | 333/338 = **98.5%** | **0** | 9/10 = **90.0%** | **fail** |
| **D6** | table-as-content (NARA GRS 1.1) | 100% | 51/51 = **100%** | 0 | 10/10 = **100%** | **pass** |
| Pooled | | 100% | 384/389 = **98.7%** | 0 | — | reported only |

Support split as §10.7(f) requires, model claims and rule claims separately:

| | Claims | `ok` | Support |
|---|---:|---:|---:|
| D5, model | 337 | 332 | 98.5% |
| D5, rule | 1 | 1 | 100% |
| D6, model | 51 | 51 | 100% |
| **Pooled** | **389** | **384** | **98.7%** |

The rule contributed exactly one claim (`D5-0367`, the `Relevant Data Subjects`
row the model skipped); the model extracted the other six row cells itself.

**Verdict: rejected.** §10.7(f) named `D5-0002`, `D5-0003` and `D5-0004` as hard
requirements, with structural 100%, support >= 90%, 0 facts absent and recall
>= 70%. Every numeric threshold passes, and so do `D5-0002` (recalled by the two
exporter row claims, `D5-0004` + `D5-0005`) and `D5-0004` (`D5-0008` +
`D5-0011`). `D5-0003` fails, and one named claim absent rejects the fix:
overall recall does not substitute for it.

What it repaired is real. `D5-0002` is now extracted by the model from the
segmented rows instead of skipped, support reaches 98.5% with 0 `no` and 0
`fabricated`, and the bogus `15.2.1.5 contact point` path of the kv run attaches
to no claim. That is the row rule working as designed.

**Why `D5-0003` fails.** The primary-place half is not a segmentation defect
this time, and not a census disagreement: the compile **did** emit it
(`D5-0007` *The primary place for legal claims to be made by the Parties is
England and Wales*) and the verify stage removed it — `rewrite` in round 1
("Span is only the value"), `drop` in round 2 ("Spans name England and Wales but
never state it is the primary place for legal claims"). The section guard of
§10.7(f) rejects a `reevidence` that abandons its own section; it does not cover
`rewrite` or `drop`, which the pre-registration itself excluded. So the guard
did not fire on the claim it was written to protect, because that claim was not
re-evidenced. The governing-law half (`D5-0006`) survives and is supported.

The drop policy, not the row rule, is the defect: the row is a colonless
four-line label whose value cell is `England and Wales`, and a policy that
requires the label inside the quote will drop it every time.

**Residual defects**, recorded and not repaired in this run: `D5-0063` narrows
the exception to Section 5.1.1 (source: 5.1.1-5.1.3); one wrong `section_path`
on `D5-0366`; four near-duplicate pairs that survived dedupe; four bare
definition fragments whose subject lives only in the section path; one wrong
modality label (`D5-0065`, `permission` on a prohibition). No census verdict
moves.

The verifier audit and the census agree on 379/389 rows = 97.4%. The ten
disagreements are the documented calibration classes: seven glossary-term rows
the verifier called `weak` and the census calls `ok` (the term is in
`section_path`, and §10.4 defines evidence as quote **and** locator), and three
rows the verifier accepted and the census does not.

D6's pass is a control, not evidence for the fix: its 35 spans are byte-identical
to the fixed run, so its input did not change.

**Cost.** Compile $0.1843, verify $0.3554, census $0.00 — **$0.5397** for this
run, plus the aborted first attempt (≈ $0.1764, no score) for **≈ $0.72** spent
on §10.7(f). The verify overran its ~$0.28 quote because two repair rounds split
11 batches on the token limit and 4 on HTTP 503.

**What this run shows.** (1) The row rule works: row cells the model used to skip
are now claims, and support is the best D5 figure this corpus has produced.
(2) A pipeline can pass every numeric threshold and still fail on one named
claim, twice in a row for the same `D5-0003` — the second time through the repair
policy rather than through segmentation. (3) The guard was scoped to the wrong
action: `reevidence` was guarded, `drop` was not, and `drop` is what removed the
claim.

## Zero-cost guard replay (2026-11-11) — no model calls, no new census

`PREFLIGHT.md` §10.7(g) pre-registered a guard on `drop` and `rewrite` and made a
replay of the rejected trace a precondition for the paid run. The replay executes
the pure verify policy against the recorded audit and repair cache, with
`--replay` aborting on any attempted model call. It costs $0 and cannot produce a
new census: the claims come from the same compile.

**Replay 1 (rule 2 as first written): rejected.** `D5-0007` survived its round-2
`drop`, but the rewrite rule rejected 14 rewrites, including `D5-0002` (the
document title abbreviated to "IDTA") and `D5-0004` (a parenthetical column
descriptor dropped while the headword stayed). The trigger — any section-path
n-gram the rewrite loses — cannot tell a lost term from an abbreviation or a
paraphrase. Precondition 2 failed, so no paid run started.

**Replay 2 (rule 2 narrowed to a defined headword, §10.7(g)(ii)): pass.**

| Check | Result |
|---|---|
| `D5-0007` kept | yes, as `weak` |
| changes limited to lost defined headwords | 6 rewrites rejected |
| final set vs the rejected run | 390 vs 389 claims: `D5-0007` added, nothing removed |
| evidence | 0 quotes or locators changed |
| statements | 5 differ, all guard-rejected glossary rows |
| `check_claims.py` | 390 claims, 517 spans, 0 failures |

The six rejections are `D5-0010`, `D5-0336`, `D5-0345`, `D5-0363`, `D5-0310` and
`D5-0312`; four of those fragments were already in the census's residual-defect
list. The guard keeps the row's own term instead of the subjectless fragment.

The audit distribution of replay 2 is 380 `ok`, 10 `weak`, 0 `no`, 0
`fabricated`. That is the verifier's own verdict, **not** a census support
figure; the gate of §10.7(f) is unchanged and will be measured by the paid run,
which has not started.

The replay output is kept beside the measured trace in
`gold/probe.rows.compiled.jsonl.replay-10.7g/` (`report.json`, the 390-claim
artifact and its spans; gitignored like every other measured artifact).

## Second corpus probe, drop/rewrite guard (2026-11-11) — **accepted**

`PREFLIGHT.md` §10.7(g) guarded the two actions that removed `D5-0003` in the
previous run, and §10.7(g)(ii) narrowed the rewrite rule to a defined headword
after the first replay rejected 14 legitimate paraphrases. The paid run was
approved at ≤ $0.55 and cost **$0.37** (compile $0.094, verify $0.2755).

| Document | Type | Structural | Support | Facts absent | Recall | Verdict |
|---|---|---|---:|---:|---:|---|
| D5 — guard run | contract | 100% | 333/341 = **97.7%** | **0** | **10/10** | **pass** |
| D6 — guard run | table-as-content | 100% | 56/56 = 100% | 0 | 10/10 | **pass** |

Pooled census: **389/397 = 98.0%**, 0 `no`, 0 `fabricated`.

**The guard fired on the claim it was written for.** Round 1 audited the
primary-place claim `D5-0006` as `weak` and issued a `drop`; the guard refused
it ("verdict weak, evidence verbatim in its own section"). The claim is in the
final artifact, so `D5-0003` is recalled by `D5-0006` (primary place) and
`D5-0097` (governing law). `D5-0002` is recalled by `D5-0004` (legal name) and
`D5-0362` (address, a deterministic row claim), and `D5-0004` by `D5-0007` and
`D5-0010`. All three named claims pass, and D5 reaches 10/10 recall for the
first time.

| | Claims | `ok` | Support |
|---|---:|---:|---:|
| D5, model | 339 | 331 | 97.6% |
| D5, rule | 2 | 2 | 100% |
| D6, model | 56 | 56 | 100% |
| **Pooled** | **397** | **389** | **98.0%** |

The verifier's own residual is 378 `ok` / 19 `weak` / 0 `no` / 0 `fabricated`
(95.21%); the independent census keeps 8 of those 19 weak and adds six the
verifier passes. The 17 verifier-only weak rows are the known locator class
(glossary headwords and D6 retention clauses whose record type is in the section
path); the six census-only rows are `D5-0072`, `D5-0264`–`D5-0267` and the
reused `D5-0109`, where an operative element comes from a neighbouring unquoted
line. The full census is `gold/audit.probe.rows.g.md`.

Guard activity, recorded in `report.json`: **4 refused drops** (`D5-0006`,
`D5-0039`, `D5-0339`, `D5-0288`) and **5 refused rewrites** (`D5-0009`,
`D5-0343`, `D5-0344`, `D5-0346`, `D5-0347`). One `reevidence` was rejected by
the section guard (`D5-0340`). Final artifact: 397 claims (D5 341, D6 56), 534
evidence spans, `check_claims.py` 0 failures.

**Verdict: accepted by §10.7(g).** The row-claim pipeline is accepted for the
demo. The earlier runs remain the measurements of their own pipelines. The
open technical question is now Phase 0 of ADR 0002 (verifier vs census
agreement), not another bench iteration; the market gate is unaffected.

## Limitations

- **n = 39 scored questions, one run, one model.** No confidence interval is
  reported because 40 questions cannot support one.
- **Manual scoring was done by the agent that built the harness, not blind.**
  The verdicts and the excluded question are in `runs/.../scores.csv`. An
  independent re-score (2026-11-08, above) reproduced every answer verdict and
  the B2 − B1 citation delta; it corrected one unsupported claim in B1 and found
  that the original pass overstated B0's citation accuracy. It was still an LLM
  reviewer, not a human, so treat it as a strong cross-check, not a certified
  score.
- **The corpus is public and small.** The result says "claims help on
  structure-heavy normative documents"; it does not generalise to contracts,
  invoices or internal wikis without a second corpus. The second corpus is still
  two documents (one contract, one records schedule) and one model.
- **The fixed-run census is manual, 405 rows, by the agent that built the
  pipeline.** The claim-level verdicts and the span evidence are the record a
  second reviewer can check; the notes are kept locally because they name the
  source corpus. D6 is 51 claims, so one row is worth 1.96 pp of support.
- **The key/value run is a third manual census, 397 rows, same reviewer.** It
  is the strictest of the three (0 facts absent, 98.2% support) and still fails:
  D5 is 335 claims, one row is worth 0.30 pp, and the failing rows are named
  gold claims, not a support average.
- **D5's recall sits exactly on the bar (7/10)** in the first two runs, and its
  8 `no` rows are instrument-caused and mechanically repairable. They are still
  claims the artifact asserts and the source does not; they are counted, not
  excused. The key/value fix removed them (0 `no`, 0 `fabricated`) but did not
  recover `D5-0002`/`D5-0003`, so the two D5 requirements had to be met
  together and were not.
- **The claim layer passes its own support bar as of 2026-11-08, on this
  corpus.** B2's context comes from `gold/claims.verified.jsonl` (504 claims),
  and the independent census is 99.0%. The 11 rows the repair stage kept as
  `weak` remain visible in `gold/audit.run4.md`, and 5 of them are census misses:
  a true statement whose quote is incomplete is shipped, not hidden.
- **A single `citation` field cannot express a multi-claim answer**
  (`D3-Q06`). The compiler emits v2 evidence lists, but the B2 prompt still
  asks for one citation string, so a correct two-part answer looks unsupported.
  `schemas/claim.v2.schema.json` models the evidence; the answer-side
  `{answer, claim_ids}` contract in `docs/adr/0001-document-first-kernel.md` is
  designed but not shipped, because it has not been measured against this
  baseline. That is the proposed Gate 3.
- **The citation contract is now explicit and mechanically retried once**
  (`PREFLIGHT.md` §9.3–§9.4). Both are measurement fixes applied identically to
  B1 and B2, and the retry count per answer is in the run. A reader who wants the
  raw, un-retried model behaviour should read the first-pass column (67.5%).
- **Market gate is untouched.** No interviews and no design partner: willingness
  to pay is still unproven, and these numbers do not prove it.

## Reproduce

```bash
python benchmark/docbench/run_baselines.py \
  --backend http --model deepseek-v4.1-flash
python benchmark/docbench/score.py
```

The blind re-score:

```bash
RUN=benchmark/docbench/runs/baselines/20261107T140843Z
python benchmark/docbench/build_blind_sheet.py --run "$RUN" \
  --gold benchmark/docbench/gold/questions.jsonl --out "$RUN/blind"
# one independent reviewer per document scores $RUN/blind/cases_D*.jsonl
python benchmark/docbench/compare_blind.py --run "$RUN"
python benchmark/docbench/blind_metrics.py --run "$RUN"
```

The corpus and the full gold set are gitignored; see `README.md` and
`sources.md` to rebuild them. The blind verdict sheets live with the run and are
gitignored with it; `key.json` never leaves that directory.

Gate 2, end to end:

```bash
python benchmark/docbench/compile_claims.py \
  --out benchmark/docbench/gold/claims.compiled.jsonl --model deepseek-v4.1-flash
python benchmark/docbench/check_claims.py \
  benchmark/docbench/gold/claims.compiled.jsonl
python benchmark/docbench/run_baselines.py --backend http \
  --model deepseek-v4.1-flash --conditions B2 \
  --claims benchmark/docbench/gold/claims.compiled.jsonl
python benchmark/docbench/score.py --run "$RUN"
# blind: build_blind_sheet.py, 4 independent reviewers, then
python benchmark/docbench/blind_metrics.py --run "$RUN"
```

The evidence-support audit (sample and full census) is `gold/audit.run3.md`.

The zero-cost guard replay must not touch the measured artifacts, and the replay
writes `report.json`, so it runs on a copy of the cache:

```bash
REPLAY=/tmp/opencode/replay-guard
rm -rf "$REPLAY" && mkdir -p "$REPLAY"
cp benchmark/docbench/gold/probe.rows.compiled.jsonl.verify/*.jsonl "$REPLAY"/
python benchmark/docbench/verify_claims.py \
  --claims benchmark/docbench/gold/probe.rows.compiled.jsonl \
  --spans benchmark/docbench/gold/probe.rows.compiled.jsonl.spans.jsonl \
  --out "$REPLAY/verified.jsonl" --work "$REPLAY" --resume --replay
```

`--replay` aborts on any attempted model call, so the command cannot spend.
