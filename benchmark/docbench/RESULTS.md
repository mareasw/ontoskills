# DocBench results — first full run

**Date:** 2026-11-07
**Run:** `runs/baselines/20261107T140843Z` (local, gitignored)
**Status:** technical gate passed on one model and one run; market gate still open.

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

## Gate 2 — machine extraction (2026-11-08)

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
  invoices or internal wikis without a second corpus.
- **The claim layer is machine-compiled as of 2026-11-08, and it does not yet
  pass its own support bar.** B2's context now comes from
  `gold/claims.compiled.jsonl` (517 claims). Structural validity, recall and
  fabrication are clean, but the full evidence-support census is 88.8%, below
  the 90% gate. See the Gate 2 section above.
- **A single `citation` field cannot express a multi-claim answer**
  (`D3-Q06`). The compiler emits v2 evidence lists, but the B2 prompt still
  asks for one citation string, so a correct two-part answer looks unsupported.
  `schemas/claim.v2.schema.json` models the evidence; the answer-side
  `{answer, claim_ids}` contract in `docs/adr/0001-document-first-kernel.md` is
  designed but not shipped, because it has not been measured against this
  baseline.
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
