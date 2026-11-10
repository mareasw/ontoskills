# Evidence-support audit — key/value row claims and the repair section guard

Artifact: `benchmark/docbench/gold/probe.rows.compiled.verified.jsonl` (gitignored).
Produced by: `benchmark/docbench/compile_claims.py --verify` over D5 and D6 on
2026-11-10, with the row-claim rule and the repair section guard of `PREFLIGHT.md`
§10.7(f), including the gap fix of §10.7(f)(i). The earlier runs and their
censuses stay untouched in `gold/probe.compiled.verified.jsonl` /
`gold/audit.probe.md`, `gold/probe.fixed.compiled.verified.jsonl` /
`gold/audit.probe.fixed.md` and `gold/probe.kv.compiled.verified.jsonl` /
`gold/audit.probe.kv.md`.
Date: 2026-11-10. Model: `deepseek-v4.1-flash`.

This is the independent census required by §10.4 and promised by §10.7(f). It is
not the verifier's own audit; that audit reports its own convergence. The
worksheet (one row per emitted claim, with every quote, page and section path)
was read end to end: **389 rows, no sample**. Verdicts are kept locally in
`gold/probe.rows.verdicts.jsonl` (gitignored, like the earlier verdict files:
the notes name the source corpus, which is not redistributed in this repo).

The first billable attempt at this pipeline was stopped before any score
existed — one quote was not verbatim, because dropping an empty cell left a gap
that the short-cell buffer joined across (§10.7(f)(i)). Its files are preserved
as `gold/probe.rows.attempt1.*` and are not a measurement.

## Result in one line

**The fix is rejected by its own pre-registered criteria.** It repairs the two
things §10.7(f) was opened for — `D5-0002` is now recalled by the two exporter
row claims, and the bogus `15.2.1.5` section path is gone — and it lifts D5
support to 98.5% with 0 facts absent and 9/10 recall. But `D5-0003` is still not
recalled: the primary-place claim **is emitted** (`D5-0007` in the compile) and
then **dropped by the verifier** at round 2, and the section guard of §10.7(f)
covers `reevidence` only, not `drop`. A named claim absent rejects the fix.

| Document | Structural | Support (census) | Facts absent from source | Recall | Verdict |
|---|---|---|---|---|---|
| D5 — contract | pass | 333/338 = **98.5%** | **0** | 9/10 = **90.0%** | **fail** (named claim `D5-0003` missed) |
| D6 — table-as-content | pass | 51/51 = **100%** | 0 | 10/10 = 100% | **pass** |

Support split as §10.7(f) requires — model claims and rule claims separately,
plus the pooled figure the gate uses:

| | Claims | `ok` | Support |
|---|---:|---:|---:|
| D5, model | 337 | 332 | 98.5% |
| D5, rule | 1 | 1 | 100% |
| D6, model | 51 | 51 | 100% |
| D6, rule | 0 | — | — |
| **Pooled** | **389** | **384** | **98.7%** |

Pooled: 384/389 = 98.7%, 0 `no`, 0 `fabricated`. The rule contributed exactly one
claim (`D5-0367`, the `Relevant Data Subjects` row the model skipped); the other
six row cells were extracted by the model itself, which is the outcome
§10.7(f) wanted and is why the split is reported rather than folded in.

## Artifact and pipeline

| Stage | Result |
|---|---|
| Spans | 359 (D5 324, D6 35); 28 extraction chunks, 15 spans each, overlap 2 |
| Raw compile | 394 claims (D5 343, D6 51); 25 near-duplicates merged, 13 rejected, 8 truncated retries, 6 conflict pairs confirmed |
| Rule claims | 1 (`D5-0367`) — the model cited the other six row spans, so the rule had nothing to add |
| Verify | 394 rows: 284 `ok` / 110 `weak` / 0 `no` / 0 `fabricated` initially; two repair rounds; 1 dropped, 4 near-duplicates merged, 3 `reevidence` rejected by the section guard |
| Final | **389 claims** (D5 338, D6 51), **516 evidence spans**, schema v2, `check_claims.py` **0 failures** |
| Verify residual | 380 `ok` / 9 `weak` / 0 `no` / 0 `fabricated` (97.69% pooled) |

Segmentation checks that precede the model, from the dry run and re-confirmed
on this artifact: D1-D4 are byte-identical to the committed baseline
(154/50/115/101 spans), D6 is byte-identical to the fixed run (35 spans), and
D5 segments to 324 spans. Every span of all six documents is verbatim in the
whitespace-normalised source (checked on both sides of the model call).

## The five `weak` rows

They are kept and listed, not hidden. All five are model claims; the one rule
claim is `ok` by construction (its statement is the cell, verbatim).

| Claim | What is outside the quote |
|---|---|
| `D5-0037` | The claim says the recipient institution can provide "institutional confirmation"; the quotes stop at "provide institutional" and resume at "this", and the object — "Information Security policies (or equivalent)" — exists only in the schedule heading. |
| `D5-0067` | The permission ("the IDTA may be changed so it operates as a multi-party agreement") is not in the quote: the quote starts at "so the IDTA operates as a multi-party agreement". The permission comes from the list lead-in "except only:", a neighbouring line. |
| `D5-0068` | Actor not named: the quote says "This may include nominating a lead Party", never that the Parties nominate. The actor comes from the surrounding clause. |
| `D5-0069` | Same shape as `D5-0067`: the permission to update the IDTA comes from the "except only:" lead-in, not from the quote, which starts at "to update the IDTA to set out in writing". |
| `D5-0106` | Qualifier dropped: the source limits the Local Laws to those "which may prevent or limit the Importer complying with its obligations"; the statement generalises to "any Local Laws". |

## Named claims of §10.7(f)

| Named claim | Recalled by | Result |
|---|---|---|
| `D5-0002` — exporter name **and** Beacon House address | `D5-0004` (full legal name row) + `D5-0005` (main address row) | **pass**, by the mechanism the pre-registration named |
| `D5-0003` — governing law **and** primary place for legal claims | `D5-0006` only (governing law) | **fail** |
| `D5-0004` — both Exporter and Importer are Controllers | `D5-0008` + `D5-0011` | **pass** |

**Why `D5-0003` fails, and it is not the same failure as last time.** In this
artifact the primary-place claim is not a census disagreement and not a missing
segmentation: the raw compile **did** emit it —

> `D5-0007` (compile): *The primary place for legal claims to be made by the
> Parties is England and Wales.*

— and the verify stage removed it. The recorded actions:

| Round | Action | Reason recorded by the verifier |
|---|---|---|
| 1 | `rewrite` | "Span is only the value; no broader wording claimed." |
| 2 | `drop` | "Spans name England and Wales but never state it is the primary place for legal claims." |

The section guard of §10.7(f) rejects a `reevidence` that abandons its own
section; it does not touch `rewrite` or `drop`, which is what the pre-registration
says ("Rewrites and drops are untouched"). The guard therefore did not fire on
the one claim it was written to protect, because the claim was not re-evidenced:
it was rewritten and then dropped. The governing-law half (`D5-0006`) survives
and is supported, so the loss is exactly the primary-place rule.

The bug is the drop policy, not the row rule: the row is still a four-line
colonless label whose value cell is `England and Wales`, and a policy that
requires the label inside the quote will always drop it. §10.7(f) named this
claim as a requirement on the assumption the guard would keep it; the guard
addresses the wrong action for this failure mode.

## D5 recall — 9/10 = 90.0%

| Gold claim | Recalled by | Note |
|---|---|---|
| `D5-0001` | `D5-0043` | four parts of the IDTA |
| `D5-0002` | `D5-0004` + `D5-0005` | name and address, as the pre-registration allows |
| `D5-0003` | `D5-0006` **(half)** | governing law only; primary place dropped in verify |
| `D5-0004` | `D5-0008` + `D5-0011` | Exporter and Importer status |
| `D5-0005` | `D5-0009` | UK GDPR does not apply |
| `D5-0006` | `D5-0016` | cannot end before the Term |
| `D5-0007` | `D5-0021` (with `D5-0019`) | forward only to co-applicants with a DAA |
| `D5-0008` | `D5-0063` | prohibition recalled; the exception is narrowed to Section 5.1.1 (source: 5.1.1-5.1.3) — recorded as a defect, not counted as a miss |
| `D5-0009` | `D5-0179` | Importer remains fully liable |
| `D5-0010` | `D5-0263` + `D5-0264` + `D5-0265` + `D5-0266` | four ways the IDTA ends |

## D6 — 10/10, 100% support, 0 misattributed authorities

| Gold claim | Recalled by |
|---|---|
| `D6-0001` | `D6-0008` |
| `D6-0002` | `D6-0010` |
| `D6-0003` | `D6-0014` |
| `D6-0004` | `D6-0032` |
| `D6-0005` | `D6-0033` |
| `D6-0006` | `D6-0034` |
| `D6-0007` | `D6-0039` |
| `D6-0008` | `D6-0040` |
| `D6-0009` | `D6-0037` |
| `D6-0010` | `D6-0047` |

Every DAA string quoted by a D6 claim was checked against the item that owns it
in the source (14 items, `d6.map.json`): **24 attributions, 24 correct, 0
misattributed**. The `D6-0008` / `D6-0031` pair is a real difference in the
source (schedule-wide 1921 note, item 011 note 1933), not an extraction error.

D6's pass is again not evidence for the fix: its 35 spans are byte-identical to
the fixed run, so its input did not change. The 51 claims (vs 62 in the kv run)
are model nondeterminism on the same spans.

## Verifier audit vs independent census

| | `ok` | `weak` | `no` | `fabricated` |
|---|---:|---:|---:|---:|
| Verifier (final) | 380 | 9 | 0 | 0 |
| Census | 384 | 5 | 0 | 0 |

The two audits agree on **379/389 rows = 97.4%**; ten rows disagree, all in the
two directions the calibration documents:

| | Count | Rows |
|---|---:|---|
| Both `weak` | 2 | `D5-0037`, `D5-0068` |
| Verifier only | 7 | `D5-0340`, `D5-0343`, `D5-0347`, `D5-0348`, `D5-0349`, `D5-0350`, `D5-0351` |
| Census only | 3 | `D5-0067`, `D5-0069`, `D5-0106` |

- **Verifier `weak` -> census `ok` (7).** Their only complaint is that the
  glossary term appears in the section path and not in the quote. The census has
  always read a glossary headword in `section_path` as the term of the row (the
  kv census called `D5-0334` *Controller is as defined in the UK GDPR* `ok`
  on exactly this shape), and §10.4 defines evidence as the quote **and** the
  locator. This is a verifier false positive, not an artifact defect, and it is
  recorded rather than fixed: changing the rubric for this run would be moving
  the goalposts.
- **Census `weak` -> verifier `ok` (3).** `D5-0067`, `D5-0069`, `D5-0106`: a
  permission supplied by a list lead-in and a dropped qualifier. The verifier
  accepted them; the census does not.

## Residual defects the fix does not repair

1. **`D5-0003` is dropped by the verify policy** (above). This is the failure.
2. **`D5-0063` narrows the exception**: it says "except only as set out in
   Section 5.1.1", while the source lists 5.1.1, 5.1.2 and 5.1.3. Supported by
   its own quote (the span ends inside 5.1.1), misleading on the document.
3. **One wrong locator**: `D5-0366` (*Mandatory Clauses*) carries the section
   path `Without Undue Delay`, the previous glossary headword. Quote and page are
   right; the path is not. This is the glossary-headword class of §10.7(e)(i)
   again, in one row, and no census verdict moves.
4. **Near-duplicates that survived dedupe**: `D5-0137`/`D5-0144`,
   `D5-0174`/`D5-0177`, `D5-0338`/`D5-0341`, `D5-0357`/`D5-0359` (same fact, two
   claims). No support effect; it inflates the claim count by four.
5. **Bare definition fragments as statements**: `D5-0336`, `D5-0345`,
   `D5-0355`, `D5-0363` are emitted as "As defined in the UK GDPR." / "As set
   out in Table 2: Transfer Details." — a fragment whose subject exists only in
   the section path. Counted `ok` under the locator rule, but not a standalone
   sentence.
6. **Modality labels are not audited by this scale**: `D5-0065` is a prohibition
   labelled `permission`. The statement is supported; the label is wrong.

## Verdict

**Rejected by §10.7(f).** D5: structural pass, support 98.5% pass, facts absent 0
pass, recall 90.0% pass — and `D5-0003` not recalled, which the acceptance names
as a hard requirement. Overall recall does not substitute for a named claim, and
a pass here would require re-defining the gate after seeing the number. D6
passes on all four criteria plus 0 misattributed authorities.

What the pipeline did deliver is measurable and should not be lost in the
verdict: the exporter name and address are extracted by the model
(`D5-0004`, `D5-0005`), support rises to the best D5 figure this corpus has
produced (98.5%, 0 `no`, 0 `fabricated`, 5 `weak`), the bogus `15.2.1.5` path is
gone, and the only rule claim is one row the model skipped. What it did not
deliver is the other half of `D5-0003`, and the cause is now precise: the verify
drop stage, which the section guard does not cover.

## Cost

| Stage | Cost |
|---|---:|
| Compile (394 claims, 359 spans, 28 chunks, 6 conflict pairs) | $0.1843 |
| Verify (132 calls, 295,779 in / 518,306 out) | $0.3554 |
| Census (no model call) | $0.00 |
| **This run** | **$0.5397** |
| Aborted attempt (§10.7(f)(i), no score) | ≈ $0.1764 |
| **Total for §10.7(f)** | **≈ $0.72** |

The verify came in at $0.3554 against the ~$0.28 quoted: two repair rounds with
11 token-limit splits and 4 `503` splits cost more than the estimate. That is
recorded rather than absorbed silently.

## Limits

- **One run, one model, two documents.** The verdict is about this pipeline on
  D5 and D6, not about D1-D4, and not about answer quality (§10.4 keeps B1/B2
  outside this gate).
- **The census was done by the agent that built the pipeline**, not blind. The
  verdicts and their notes are in the gitignored `gold/probe.rows.verdicts.jsonl`
  so a reader can disagree row by row.
- **The recall reading of a set of claims as one rule** is the gate's own
  convention (§10.7(f), and §10.7(e) before it); it is applied identically to
  D5 and D6.
- **D6 is a control, not a replication**: its spans are unchanged since the
  fixed run, so its pass says nothing about the row rule.
