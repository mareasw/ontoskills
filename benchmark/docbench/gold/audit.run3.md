# Evidence-support audit — machine-compiled claims (run 3)

Artifact: `benchmark/docbench/gold/claims.compiled.jsonl`
Compiled: 2026-11-08, `deepseek-v4.1-flash`, one pass, no prompt tuning against
the gold set.
Manifest: 420 spans, 33 chunks, 517 claims, 15 rejected, 24 near-duplicates
merged, 11 truncation retries, 5 conflict pairs, 1 conflict batch failure,
105,095 input / 209,723 output tokens.

This is step 3 of Gate 2 in `PREFLIGHT.md` §9 — the part structural validation
cannot guarantee.

## Result in one line

**459 of 517 claims (88.8%) are fully supported by their own evidence; 55 are
weak, 3 are wrong, 0 are fabricated. The gate asks for >= 90%, so evidence
support does not pass.**

The pre-registered sample of 60 had given 95.0%. The full census, run after the
sample, is the number that counts: the sample under-drew the largest defect
class.

## Method

1. **Pre-registered sample** (the method fixed in `PREFLIGHT.md` §9): 15 claims
   per document, taken every `floor(n/15)`-th claim. 60 claims. The reviewer
   saw `(statement, evidence quotes, section_path)` and no source text.
2. **Census**: all 517 claims, same verdict scale, one reviewer per document,
   again with only `(statement, quotes)`.
3. The census was added because an automated lexical screen (share of the
   statement's 4+ character words present in its own quotes) flagged 52 claims
   below 60% coverage — too many to dismiss as noise. It was run independently
   of the sample and both results are reported.

Verdict scale:

- **ok** — every material element of the statement (actor, action, object,
  number/deadline, condition, modality strength) is in the quote.
- **weak** — the statement is true, but a material element is not in the quote
  and comes from a heading, a section title or the adjacent line. Not false,
  not fully supported.
- **no** — the quote does not state the claim, the modality is strengthened
  (`may` -> `must`), or the claim contradicts the quote.
- **fabricated** — the statement asserts a specific fact for which the quote
  gives no basis at all.

## Results

### By verdict

| Verdict | Census (517) | Share | Sample (60) | Share |
|---|---:|---:|---:|---:|
| ok | 459 | 88.8% | 57 | 95.0% |
| weak | 55 | 10.6% | 3 | 5.0% |
| no | 3 | 0.6% | 0 | 0.0% |
| fabricated | 0 | 0.0% | 0 | 0.0% |

| Document | Claims | ok | weak | no |
|---|---:|---:|---:|---:|
| D1 — Commission implementing regulation | 148 | 144 | 3 | 1 |
| D2 — University AI policy | 95 | 79 | 16 | 0 |
| D3 — Incident response playbook | 83 | 59 | 22 | 2 |
| D4 — County RFP | 191 | 177 | 14 | 0 |

Gate threshold: evidence support >= 90%, zero fabricated claims.
**Fabrications: pass (0). Evidence support: fail (88.8% < 90%).**

### Why the sample said 95% and the census says 88.8%

The 60-claim sample drew only 3 of the 24 D3 defects: D3 is the document where
the same fault repeats 14 times (every timed step has the actor implied), and a
one-in-five stride through 83 claims can miss a run of consecutive defects.
Sampling by stride is not sampling by defect cluster. The gate's method is
therefore sound as a *tripwire* but weak as a *measure* on repetitive documents.

## The weakness is systematic, not random

The 58 non-ok claims fall into six mechanisms:

| Mechanism | Count | Example |
|---|---:|---|
| Actor/subject supplied from outside the quote (heading, list lead-in, implied playbook narrator) | 28 | `D3-0061` "responders stop the data flow" — quote: "Immediate (15 min): Stop data flow, notify affected users" |
| Qualifier or set membership supplied from a heading or the adjacent line | 21 | `D2-0067` adds "for research and publication support"; `D1-0110` adds "limitation period for the enforcement of penalties" |
| Exception present in the source but omitted from the statement (statement broader than source) | 4 | `D2-0053` drops "unless explicitly approved"; `D2-0075`, `D2-0080`, `D2-0082` |
| Specific action or number added and absent from the quote | 2 | `D4-0072` "15 points" for familiarity; `D3-0014` "notify platform operators" |
| Quote unrelated to the statement | 2 | `D3-0045`, `D3-0076` |
| Modality strengthened (`may`/`should` -> `must`) | 1 | `D1-0157` quote says "should always obtain", statement says "must" |

Only the last three rows are semantic errors about the source. The first two are
a *packaging* defect: the sentence is true in the document, but the evidence
does not carry the whole sentence. That is fixable structurally, and it is the
single highest-value fix in the compiler.

### The structural cause: evidence is a whole span, not a supporting passage

The span-first design makes verbatim evidence structural — the quote is copied
from the span, so it cannot be invented. The cost is that the quote is the
*whole span*, and spans are large:

| Quote length (chars) | Value |
|---|---:|
| median | 432 |
| p90 | 681 |
| p99 | 700 |
| max | 742 |
| quotes > 400 chars | 301 / 554 (54.3%) |
| distinct quotes | 263 |
| quotes reused by more than one claim | 140 |

Because the subject of a claim often lives in the heading of the block, and the
heading is stored in `section_path` rather than in the span text, the extractor
writes a complete sentence whose subject is not inside its quote. The same
mechanism lets one 210-character quote serve 10 different claims.

The consequence for measurement is uncomfortable: `check_claims.py` can be 100%
green while a tenth of the claims are not fully supported, because "the quote
exists verbatim in the source" and "the quote states the claim" are different
properties, and only the second one matters to a reader.

## Verdict on Gate 2 evidence support

**Fail**, as measured on the full set. The gate's response is fixed in advance
by the stop rule: do not tune the prompt against the gold set; change the
pipeline and re-run from a clean compile.

## The 58 non-ok claims

| Claim | Verdict | Reason |
|---|---|---|
| `D1-0026` | **weak** | three termination grounds (a)-(c) not in quoted intro line |
| `D1-0058` | **weak** | "points (a) to (e)" supplied by following list, not quote |
| `D1-0110` | **weak** | "limitation period for the enforcement of penalties" comes from article heading |
| `D1-0157` | **no** | quote says "should always obtain"; statement asserts "must" |
| `D2-0024` | **weak** | subject 'guidance for faculty section' from heading; quote says 'This section' |
| `D2-0028` | **weak** | 'disclosure of AI use' antecedent not in quote ('Such disclosure') |
| `D2-0035` | **weak** | actor 'faculty and staff' not in quote |
| `D2-0044` | **weak** | quote 'we will not use'; recast as student prohibition |
| `D2-0045` | **weak** | quote 'would be considered'; actor not in quote |
| `D2-0047` | **weak** | staff lead-in only in line above; quote is bare list |
| `D2-0053` | **weak** | omits 'unless explicitly approved' exception |
| `D2-0063` | **weak** | adds 'used to train AI models' qualifier not in quote |
| `D2-0066` | **weak** | actor 'Units' not in quote |
| `D2-0067` | **weak** | adds 'for research and publication support' qualifier |
| `D2-0075` | **weak** | omits educational-experience exception |
| `D2-0080` | **weak** | omits educational-experience exception |
| `D2-0082` | **weak** | omits 'unless vetted/approved' exception |
| `D2-0084` | **weak** | 'This includes' subject resolved to restricted data; not in quote |
| `D2-0087` | **weak** | 'is prohibited' from section heading; quote is bare list item |
| `D2-0095` | **weak** | action 'finalized the draft' from line above |
| `D3-0007` | **weak** | step number and 'confirm detection' come from heading; quote is code only |
| `D3-0008` | **weak** | Communications Officer absent from both quotes |
| `D3-0014` | **weak** | quote only lists platforms; notifying platform operators is absent |
| `D3-0028` | **weak** | actor and 'for affected users' not in quote |
| `D3-0029` | **weak** | actor 'incident response team' not in quote |
| `D3-0030` | **weak** | actor 'incident response team' not in quote |
| `D3-0031` | **weak** | actor and 'to affected users' not in quote |
| `D3-0032` | **weak** | actor and 'after a security incident' not in quote |
| `D3-0045` | **no** | quote is unrelated template fragment; no basis for software updates |
| `D3-0061` | **weak** | actor 'responders' absent; timing and action match |
| `D3-0062` | **weak** | actor 'responders' absent; timing and action match |
| `D3-0063` | **weak** | actor 'responders' absent; timing and action match |
| `D3-0064` | **weak** | actor 'responders' absent; timing and action match |
| `D3-0065` | **weak** | actor 'responders' absent; timing and action match |
| `D3-0066` | **weak** | actor 'responders' absent; timing and action match |
| `D3-0067` | **weak** | actor 'responders' absent; timing and action match |
| `D3-0068` | **weak** | actor 'responders' absent; timing and action match |
| `D3-0069` | **weak** | actor 'responders' absent; timing and content match |
| `D3-0070` | **weak** | actor 'Responders' absent; command content matches |
| `D3-0071` | **weak** | actor 'Responders' absent; command content matches |
| `D3-0072` | **weak** | actor 'Responders' absent; command content matches |
| `D3-0073` | **weak** | actor 'Responders' absent; command content matches |
| `D3-0074` | **weak** | actor 'Responders' absent; command content matches |
| `D3-0076` | **no** | quote is a different playbook heading; no documentation rule |
| `D4-0003` | **weak** | recipient 'designated contact' not in quote (address block follows) |
| `D4-0012` | **weak** | actor Greene County supplied by context; quote passive |
| `D4-0029` | **weak** | 'Greene County Business License' named only in preceding item c |
| `D4-0042` | **weak** | 'Firm shall maintain' from earlier list header, not in quote |
| `D4-0043` | **weak** | 'Firm shall maintain' from earlier list header, not in quote |
| `D4-0044` | **weak** | 'Firm shall maintain' from earlier list header, not in quote |
| `D4-0072` | **weak** | 15 points for familiarity criterion absent from all quotes |
| `D4-0150` | **weak** | coverage name Employer's Liability from preceding item b |
| `D4-0151` | **weak** | coverage name Employer's Liability from preceding item b |
| `D4-0152` | **weak** | coverage name Employer's Liability from preceding item b |
| `D4-0193` | **weak** | form title from heading, not in quote |
| `D4-0194` | **weak** | 'Exhibit C' and Offeror/Bidder from heading, not in quote |
| `D4-0195` | **weak** | 'Exhibit C' form name from heading, not in quote |
| `D4-0199` | **weak** | actor Offeror/Bidder from form heading, not in quote |

## Fix implied by this audit

Ranked by claims repaired per unit of change:

1. **Carry the heading into the evidence.** Either include the governing heading
   in the span text, or emit `context: {section_path, preceding_line}` as a
   first-class field so the subject is machine-checkable instead of hidden in
   the sentence. Repairs the 28 actor claims and most of the 21 qualifier ones.
   The second option is better: quotes stay clean and the enrichment becomes
   explicit.
2. **Quote a passage, not a span.** Have the extractor return character offsets
   into the span (the span id is already assigned) and validate that the quoted
   passage contains the statement's subject. Repairs the long-quote problem that
   makes 54% of quotes over 400 characters and lets one quote serve 10 claims.
3. **Reject statements broader than their evidence.** A cheap check: if the
   statement contains an exception-bearing cue ("unless", "except") that the
   quote lacks, flag it. Catches the 4 omitted-exception claims, which are the
   most dangerous class because the statement overstates the rule.
4. **Enforce modality.** The compiler already assigns a modality; compare it
   with the quote's modal verb. Catches `D1-0157`.
5. **Reject a quote that shares no content words with its statement.** Catches
   `D3-0045` and `D3-0076` at compile time instead of audit time.

## What this audit does not cover

- Completeness: claims the document states and the compiler never emitted. That
  is the separate recall proxy (40/41 = 97.6%), not this audit.
- The three `no` verdicts were judged from the quote alone; the quote for
  `D3-0045` and `D3-0076` may be a segmentation artefact rather than an
  extraction error. Either way the claim is unsupported as emitted.
- One reviewer per document, all reading the same mechanical rubric. No human
  second pass; no inter-rater agreement figure.
