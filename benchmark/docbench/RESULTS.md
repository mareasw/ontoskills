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
- **The claim layer was hand-built.** B2's context came from `gold/claims.jsonl`,
  annotated by hand, not produced by a compiler. The benchmark validates the
  *representation* (claim + evidence + locator), not the extraction. Machine
  extraction is the next gate and has not been measured.
- **A single `citation` field cannot express conflicting evidence** (`D4-Q06`).
  The 2026-11-07 run used the old contract. `schemas/claim.v2.schema.json` now
  models evidence as a list with roles, but no run has measured it yet.
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
