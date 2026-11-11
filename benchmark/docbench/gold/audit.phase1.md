# Phase 1 census — evidence-first prompt (2026-11-11)

The artifact is `gold/probe.phase1.compiled.jsonl` (364 claims, 463 evidence
spans, D5 315 / D6 49). It is a **first pass**: compile only, `--verify` off, no
repair round, no drop. The run used the prompt pre-registered in
`PREFLIGHT.md` §10.8, verbatim.

Method: every emitted claim was read against its own evidence, as in every
previous census. `ok` means the quotes contain the substance of the statement;
the statement may take its subject from the locator when the evidence is a table
row or a glossary row. `weak` means a material element — actor, object, modality
or operative predicate — is only outside the quotes. The deterministic verifier
was run first and its number is reported below, but it selected nothing: the
verdict is this census, as §10.8 requires.

## Result

| Document | Claims | `ok` | `weak` | Support |
|---|---:|---:|---:|---:|
| D5 (IDTA) | 315 | 296 | 19 | **93.97%** |
| D6 (NARA GRS 1.1) | 49 | 48 | 1 | **97.96%** |
| **Pooled** | **364** | **344** | **20** | **94.51%** |

## Pre-registered criteria (§10.8)

| Criterion | Threshold | Measured | Result |
|---|---|---|---|
| D5 first-pass support | ≥ 90% | 93.97% | **pass** |
| D6 first-pass support | ≥ 90% | 97.96% | **pass** |
| Facts absent from the source | 0 | 0 | **pass** |
| `no` / `fabricated` | 0 | 0 | **pass** |
| Recall | ≥ 70%, with `D5-0002`, `D5-0003`, `D5-0004` | 10/10 D5, 10/10 D6, all three named | **pass** |
| Cost | ≤ $0.30 | $0.145 | **pass** |

**Verdict: accepted.** Both documents clear their own 90% bar; no document
carries the other.

## Run shape and cost

| Item | Value |
|---|---|
| Claims | 364 (D5 315, D6 49) |
| Evidence spans | 463 |
| Rejected by the schema check | 41 |
| Near-duplicates merged | 15 |
| Truncated retries | 9 |
| Conflict batches failed | 3 (gateway 503s; no claim lost) |
| Input tokens | 96,164 |
| Output tokens | 217,937 |
| Cost at $0.15/M in, $0.60/M out | **$0.145** |
| `check_claims.py` | 0 failures |

The same corpus under §10.7(g) produced 402 claims and cost $0.37 with two
repair rounds. The first pass here is smaller and cheaper by construction: no
repair, no second model call per claim.

## The twenty `weak` rows

They are kept and listed, not hidden.

| Claim | Where the statement goes beyond its quotes |
|---|---|
| `D5-0030` | Object of "provide" ("Information Security policies (or equivalent) confirming this") is in the column header, not in the cited quotes; the quotes stop at "provide institutional". |
| `D5-0060` | The permission ("may be changed") is the unquoted list lead-in; the quote starts at "so the IDTA operates as a multi-party agreement". |
| `D5-0062` | The permission ("may be changed") is the unquoted list lead-in; the quote is the purpose clause alone. |
| `D5-0066` | Subject invented: the quote's subject is "a revised Approved IDTA", not "Changing this IDTA". |
| `D5-0067` | Subject invented: the quote is the limb "reflects changes to UK Data Protection Laws"; the subject is the revised Approved IDTA. |
| `D5-0082` | Subject ("References to") is in the unquoted lead-in; the quote starts at "singular or plural words or people". |
| `D5-0130` | Actor and modal ("the Importer must") are the 12.1 lead-in, a different span; the quote is 12.1.5 alone. |
| `D5-0131` | Actor and modal ("the Importer must") are the 12.1 lead-in, a different span; the quote is 12.1.6 alone. |
| `D5-0143` | Subject and modal ("the Importer must provide ... information about the Importer Personal Data Breach") are the 15.3 lead-in; the quote starts at 15.3.2. |
| `D5-0163` | Condition ("If a Party receives a request ... for a copy of this IDTA") and actor are the 18.1 lead-in; the quote starts at 18.1.2. |
| `D5-0164` | Condition and actor are the 18.1 lead-in; the quote starts at 18.1.2. |
| `D5-0165` | Condition and actor are the 18.1 lead-in; the quote starts at 18.1.3. |
| `D5-0178` | Actor and modal ("the Importer must provide") are the 20.4 lead-in; the quote starts at 20.4.5. |
| `D5-0179` | Actor and modal ("the Importer must provide") are the 20.4 lead-in; the quote starts at 20.4.5. |
| `D5-0183` | Actor, modal and condition ("If a Relevant Data Subject requests, the Importer must") are the 20.5 lead-in; the quote is 20.5.4 alone. |
| `D5-0200` | Actor, modal and qualifier ("In so far as Local Laws allow, the Importer must") are the 23.4 lead-in; the quote is 23.4.2 alone. |
| `D5-0219` | Actor and modal ("Each Party must") are the 26.1 lead-in, a different span; the quote starts at 26.1.2. |
| `D5-0244` | Actor and modal ("the Importer must") are the 31.1 lead-in, a different span; the quote is 31.1.2 alone. |
| `D5-0246` | Actor and modal ("the Importer must") are the 31.1 lead-in, a different span; the quote is 31.1.3 alone. |
| `D6-0047` | The retention clause ("longer retention is authorized if required for business use") is in a later span; the cited quotes stop at "Destroy when 3 years old, but" and at "Includes:". |

Sixteen of the twenty are one mechanism: the model splits a clause into atomic
sub-items and quotes the sub-item, while the parent lead-in that supplies the
actor, the modal or the condition is a different span. Rule 2 of the prompt
asked for exactly this to be avoided; it was not. Two more are a wrong subject
(`D5-0066`, `D5-0067`), one is an object taken from a table column
(`D5-0030`), and one is a retention phrase left in a later span
(`D6-0047`).

This is the honest reading of the prompt change: it fixed the named failures
(paraphrase drift, narrowed exception ranges, bare definition fragments), but
atomic splitting increased the number of sub-item claims exposed to an unquoted
lead-in. §10.7(g) had 8 weak in 397 (2.0%); this run has 20 in 364 (5.5%), and
the lead-in class is 16 of them (4.4% of claims) against 6 of 397 (1.5%). The
support bar is met, so the phase passes, but rule 2 as prompt text did not
close the class.

## Defects recorded but not counted as `weak`

| Claim | Defect |
|---|---|
| `D5-0003` | Locator section path points at the Importer signature row; the quote is the Table 2 governing-law row. Page and quote are right. |
| `D5-0007` | Locator section path is "Linked Agreement"; the quote is the Importer status row. |
| `D5-0137` | The source prints two Section 15 entries; the duplicate is faithful to the document. |
| `D5-0138` | Extra evidence: 19.1 and 20.1 are quoted alongside 14.1; the statement uses only 14.1. |
| `D5-0157` | A heading restated as a claim; every content word is the heading's, "applies" is the compiler's copula. |
| `D5-0293`, `D5-0294` | Duplicate glossary rows: ICO and Importer are each emitted twice. |
| `D5-0327` | Locator section path is "Without Undue Delay"; the quote is the "Alternative Part 4 Mandatory Clauses" row. |

One class is not claim-specific: 17 evidence rows of `D5-0177`–`D5-0190` carry
the section path `Laws > 20.4.4 in an easily accessible form`, a segmenter
artefact from a list item read as a heading. The page and the quote are right;
the section path is not. It is a segmenter defect, not a support failure, and it
is the reason the locator cannot yet be used as a citation string without a
check.

## Recall — 10/10 D5 and 10/10 D6

| Gold claim | Recalled by | Note |
|---|---|---|
| `D5-0001` | `D5-0036` | four parts of the IDTA |
| `D5-0002` | `D5-0328` + `D5-0329` | exporter name and Beacon House address |
| `D5-0003` | `D5-0003` + `D5-0004` | governing law and primary place, both at first pass |
| `D5-0004` | `D5-0005` + `D5-0007` | Exporter and Importer status |
| `D5-0005` | `D5-0006` | UK GDPR does not apply to the Importer |
| `D5-0006` | `D5-0013` + `D5-0014` | cannot end before the Term, with the exception |
| `D5-0007` | `D5-0016` + `D5-0018` | forward only to co-applicants with a DAA |
| `D5-0008` | `D5-0053` + `D5-0054` | Mandatory Clauses, exception **5.1.1 to 5.1.3** kept whole |
| `D5-0009` | `D5-0160` | Importer remains fully liable |
| `D5-0010` | `D5-0233`–`D5-0236` | four ways the IDTA ends |

| Gold claim | Recalled by |
|---|---|
| `D6-0001` | `D6-0009` |
| `D6-0002` | `D6-0010` + `D6-0011` |
| `D6-0003` | `D6-0012` |
| `D6-0004` | `D6-0027` |
| `D6-0005` | `D6-0028` |
| `D6-0006` | `D6-0029` |
| `D6-0007` | `D6-0034` |
| `D6-0008` | `D6-0037` + `D6-0038` |
| `D6-0009` | `D6-0032` |
| `D6-0010` | `D6-0044` + `D6-0045` |

The three named claims of §10.8 are recalled by the first pass: exporter name
and address (`D5-0328`, `D5-0329`), governing law and primary place
(`D5-0003`, `D5-0004`), both parties Controllers (`D5-0005`, `D5-0007`). The
primary-place half of `D5-0003` — the fact the §10.7(g) guard existed for —
survives with the correct section path.

`D5-0008` is worth one line: §10.7(g)'s claim narrowed the exception to
"5.1.1". This run keeps "5.1.1 to 5.1.3", which is what rule 3 asked for and
what the source prints.

## Facts absent from the source

Every content token of every statement was checked against the full document
vocabulary, not just the cited quotes. Nine tokens are not found verbatim and
all nine are inflections or framing, not facts:

| Claim | Token | In the source as |
|---|---|---|
| `D5-0030` | policies | "Information Security policies" (table header row) |
| `D5-0057`, `D5-0185` | permission, prohibition | the compiler's modality label in the statement |
| `D5-0064`, `D5-0065` | published | "may publish a revised Approved IDTA" |
| `D5-0098` | notified | "inform the Exporter" |
| `D5-0111` | retains | "The Importer may retain a copy" |
| `D5-0213` | delaying, enforcement | "delays enforcing" |
| `D5-0219` | anticipated | "should reasonably anticipate" |

**0 facts absent.** No claim states a date, number, party or rule the document
does not contain. No claim was rated `no` or `fabricated`: every statement has a
verbatim anchor in its own quotes.

## Deterministic verifier vs this census

| | Count |
|---|---:|
| Both `weak` | 3 (`D5-0163`, `D5-0164`, `D6-0047`) |
| Verifier `ok`, census `weak` | 17 |
| Verifier `weak`, census `ok` | 0 |
| Verifier support | 361/364 = 99.18% |
| Census support | 344/364 = 94.51% |

The verifier's bias is exactly the one Phase 0 measured, and it is now worse in
relative terms because the weak class grew: 17 of the 20 census `weak` rows are
`ok` to it, all of them the unquoted lead-in. It caught the three rows whose
missing element is a content word (the condition in `18.1`, the retention
clause in `D6-0047`) and missed every row whose missing element is the actor or
the modal. Phase 0's conclusion stands: the verifier is the hard gate
(verbatim, page, schema), not the judge of support. The 10% LLM QA stays.

## What Phase 1 settles

1. The prompt change is worth keeping: first-pass support is 93.97% / 97.96%,
   the two named fact families survive, the exception range is no longer
   narrowed, and the cost falls from $0.37 to $0.145 with no repair loop.
2. It does not make the pipeline automatic: 20 claims in 364 still need a human
   or LLM pass to be cited honestly, and 16 of them are a structural problem —
   the parent span of a split sub-item. The fix is structural (attach the parent
   span at split time), not another paragraph of prompt.
3. Phase 2 can start. The claim graph, the CLI and the web view operate on the
   `ok` rows and on the hard gate; the `weak` class is a known, measured,
   bounded debt, not a surprise.
