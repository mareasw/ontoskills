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
  The verdicts and the excluded question are in `runs/.../scores.csv`; an
  independent reviewer should re-score before this number is quoted publicly.
- **The corpus is public and small.** The result says "claims help on
  structure-heavy normative documents"; it does not generalise to contracts,
  invoices or internal wikis without a second corpus.
- **A single `citation` field cannot express conflicting evidence** (`D4-Q06`).
  The schema needs `evidence: [...]` or the answer must cite claim ids instead
  of one quote.
- **Market gate is untouched.** No interviews and no design partner: willingness
  to pay is still unproven, and these numbers do not prove it.

## Reproduce

```bash
python benchmark/docbench/run_baselines.py \
  --backend http --model deepseek-v4.1-flash
python benchmark/docbench/score.py
```

The corpus and the full gold set are gitignored; see `README.md` and
`sources.md` to rebuild them.
