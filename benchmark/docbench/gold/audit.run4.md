# Evidence-support audit — repaired claims (run 4, final)

Artifact: `benchmark/docbench/gold/claims.verified.jsonl`
Produced by: `benchmark/docbench/verify_claims.py` (audit → repair → re-audit)
from `gold/claims.compiled.jsonl` (run 3, 517 claims).
Date: 2026-11-08. Model: `deepseek-v4.1-flash`.

This is the independent census of the final artifact required by Gate 2
(`PREFLIGHT.md` §9). It is not the verifier's own audit: that audit reports its
own convergence and is worthless as a measure.

## Result in one line

**499 of 504 claims (99.0%) are fully supported by their own evidence; 5 are
weak, 0 are wrong, 0 are fabricated. The gate asks for >= 90%, so evidence
support passes.**

The artifact also keeps the recall the first repair attempt had lost: the gold
recall proxy is **40/41 = 97.6%** (D1 10/10, D2 10/10, D3 9/10, D4 11/11).

## Trajectory

| Artifact | Rule | Claims | ok | weak | no | fabricated | ok share |
|---|---|---:|---:|---:|---:|---:|---:|
| run 3 — raw compile | none | 517 | 459 | 55 | 3 | 0 | 88.8% |
| A1 — drop every residual | repair, drop all non-ok | 493 | 490 | 3 | 0 | 0 | 99.4% |
| **A2 — keep `weak`, drop hard failures** | **repair, drop `no`/`fabricated`** | **504** | **499** | **5** | **0** | **0** | **99.0%** |

A1 passed the support bar but cost more than it bought: 6 of its 11 residual
drops were census-`ok`, the recall proxy fell to 39/41, and B2 lost the
interim-measures answer (`D1-Q08`). A2 is the rule that ships.

## Method

1. **Audit.** The verifier shows a model `(statement, quotes, section path)` —
   never the rest of the document — and records `ok | weak | no | fabricated` on
   the census scale.
2. **Repair.** One further call per failing claim sees the claim, its own spans
   and the spans within ±3 positions, and may `rewrite`, `reevidence` or `drop`;
   it cannot invent a span or a sentence.
3. **Re-audit and emit.** Two rounds. A residual `weak` claim is kept and listed;
   a residual `no`/`fabricated` claim is dropped (`PREFLIGHT.md` §9.2).
4. **Census of the emitted artifact.** The join rule was fixed in
   `PREFLIGHT.md` §9.1 before these numbers existed: a row whose statement and
   evidence quotes are byte-identical to an already-censused row keeps that
   verdict; every changed or new row is judged fresh. Of the 504 final rows,
   **381** are byte-identical to a run-3 row and keep its verdict, **114** are
   identical to a row that the 493-claim A1 census judged fresh and keep that
   verdict, and the remaining **9** are new text and were judged fresh. All 11
   rows that A2 re-added over the drop-all artifact were judged individually:
   9 above, plus `D1-0037` and `D2-0028`, which are byte-identical to run-3
   rows — they were re-judged anyway, and the fresh verdicts (`ok`, `weak`)
   agree with the run-3 ones, so the rule is not load-bearing on the number.
   The raw verdicts are kept locally in
   `gold/audit.run4.verdicts.jsonl` (gitignored: the notes quote the source
   corpus, which is not public in this repo).

Verdict scale: `ok` — every material element is in the quote; `weak` — the
statement is true but a material element (actor, qualifier, exception, number)
is outside its own quote; `no` — the quote does not state the claim or the
modality is strengthened; `fabricated` — the statement asserts a specific fact
with no basis at all.

## Results

### Stage output

| Step | Count |
|---|---:|
| Claims in | 517 |
| Round 1 | 139 failing → 95 rewritten, 47 re-evidenced, 2 dropped, 19 still failing |
| Round 2 | 19 failing → 8 rewritten, 10 re-evidenced, 1 dropped, 11 still failing |
| Near-duplicates merged | 10 |
| Residual `weak` kept | 11 |
| Residual `no` / `fabricated` dropped | 0 |
| Claims out | 504 |
| Evidence spans out | 586 |
| `check_claims.py` failures | 0 |

Structural validity: **504/504 claims and 586/586 spans valid**, all schema v2,
every quote verbatim in its source, every PDF page recomputed. Fabrications: 0.

### By document

| Document | Claims | ok | weak | ok share |
|---|---:|---:|---:|---:|
| D1 — Commission implementing regulation | 144 | 142 | 2 | 98.6% |
| D2 — University AI policy | 92 | 90 | 2 | 97.8% |
| D3 — OWASP incident-response playbook | 79 | 79 | 0 | 100.0% |
| D4 — Greene County RFP | 189 | 188 | 1 | 99.5% |
| **Total** | **504** | **499** | **5** | **99.0%** |

### The five weak rows

They are kept, not hidden. Each is true; in each, one material element is
outside the claim's own quote.

| Claim | What is outside the quote |
|---|---|
| `D1-0058` | The statement puts the disclosure terms "in the Commission decision"; the quote says they are determined "in accordance with the following:", i.e. by the list that follows, not by the decision. |
| `D1-0110` | "limitation period for the enforcement of penalties": the word *penalties* comes from the article heading. The quotes support the five-year period and its start. |
| `D2-0028` | "Disclosure of AI use": the quote begins "Such disclosure", and the antecedent is in the previous span. |
| `D2-0035` | Actor "faculty and staff" comes from the section heading; the quote states the duty without naming the actor. |
| `D4-0072` | The weighted criteria omit 5.2 *Familiarity with the County* (15 points): the quotes cover 5.1, 5.3, 5.4 and 5.5, i.e. 85 of 100 points. |

### What the repair fixed

The run-3 defect classes were systematic, not stochastic: an actor or subject
from a heading (28 claims), a qualifier from an adjacent line (21), an omitted
exception (4), numbers added, unrelated quotes, a strengthened modality. The
repair addresses them with the same two levers for every document — re-evidence
from the neighbourhood, or restate within the current evidence — and the stage
declines the repair when neither is honest (`0 rejected` is a property of the
prompt, not of a lenient validator: a rewrite under the extractor's 15-character
floor is refused, and a re-evidence needs a span inside the neighbourhood).

### Instrument calibration

Recorded in `gold/audit.calibration.md`, frozen before the stage was applied to
the artifact: against the census it catches **62/65** known defects (95.4%) and
flags 6 of 120 known-ok claims, of which **1** survives adjudication as a true
false positive. The instrument errs towards flagging, which is why A2's rule
(keep `weak`) is safe: a flagged-but-true claim is kept, not deleted.

## Cost

| Item | Calls | Cost |
|---|---:|---:|
| Audit + repair + re-audit (two rounds, 517 claims) | 204 | ~$0.15 |
| Replay for the A2 artifact (`--resume`, per-claim cache) | 0 | $0.00 |
| A fresh full run of the same stage, for comparison | 204 | ~$0.15 |

The stage is deterministic given its cache, and `--resume` makes a policy change
free to measure: the A2 artifact was produced with zero new model calls.

## Limits

- One model, four documents, one domain. A second, structure-heavy corpus
  (contracts, tabular runbooks) is the next test.
- The census is manual, one reviewer per document, and the reviewer is the agent
  that built the verifier. The calibration run is what makes it an instrument;
  it is still not a second human.
- `weak` is a citation-quality defect, not a truth defect. The gate's 90% bar
  treats it as a miss, and the report keeps every one of them visible.
