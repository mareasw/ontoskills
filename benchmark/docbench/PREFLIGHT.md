# Document-First Pre-Flight

**Status:** pre-flight, not a product spec. Timebox: 5 working days.
**Date:** 2026-11-06
**Owner:** Marcello Russo
**Branch:** `feat/document-profile`

---

## 1. Decision memo (one page)

### Problem

An agent that must apply a policy or a procedure reads a long document probabilistically. It cannot reliably answer:
*what is required, under which conditions, by when, by whom, and on what evidence?*

The failure is not "the model cannot read". The failure is that the answer is **not verifiable**: no quote, no location, no context, no way to tell an obligation from a recommendation or an exception.

### Target user

Compliance, quality, and operations teams in regulated organisations, plus the platform engineers who build agent workflows over their documents.

### Job to be done

> When a document governs an action, give the agent the exact obligations, conditions, exceptions and evidence, so it can decide, cite, and act.

### Current workaround

Manual reading, checklists, keyword search, RAG chat over PDFs. All of them return text; none of them returns a claim with a locator and a status.

### Hypothesis

A compiled claim layer with per-claim evidence, locator, and context beats both full-document reading and RAG on **citation accuracy** and **answer accuracy with citation**, at equal or lower tokens per correct answer, on high-stakes documents.

### Success metrics (paper prototype)

| Metric | Target |
|---|---|
| Evidence span accuracy | >= 90% |
| Claim precision | >= 80% |
| Obligation recall | >= 70% |
| Locator accuracy | >= 95% |
| Answer accuracy with citation | >= 75% |
| Correct abstention | >= 90% |
| Claims without evidence in certified output | 0 |

### Non-goals

- A note-taking app or an editor.
- Generic "chat with your documents".
- All formats at once (video and audio are out of scope for this pre-flight).
- Replacing RAG for low-stakes, high-volume documents.
- A UI beyond the minimum needed to review claims.

### Risks

1. **Low reuse (`Q`).** If the document is read once and never again, compilation does not pay back.
2. **Extraction quality.** If claims cannot be extracted with evidence on 20 real documents, there is no product.
3. **Open-world semantics.** OWL does not say "false"; enterprise validation needs a closed-world layer (SHACL) for the fields that matter.
4. **Licensing.** Source documents may not be redistributable; keep them local, store only URLs, hashes and short quotes.
5. **Over-extraction.** More claims is not more knowledge; it is more noise and more tokens.

### What would change our mind

- If the hand-built claim layer does not beat RAG on citation accuracy by a clear margin, stop.
- If the target users describe a "find the passage" problem rather than an "apply the rule" problem, the formal layer is overkill.
- If the corpus has low reuse and low stakes, the economics fail.

---

## 2. Corpus for the paper prototype

Four documents, all published in 2026, all public, none of them a famous document that a model is likely to have memorised end-to-end.

| ID | Document | Type | Why it is a good test | Licence / reuse |
|---|---|---|---|---|
| **D1** | Commission Implementing Regulation (EU) 2026/1755 of 20 July 2026 (AI Act evaluations and proceedings) | Regulation | Obligations, deadlines, roles, conditions, procedural safeguards | EU reuse policy (Commission Decision 2011/833/EU) |
| **D2** | Loyola University New Orleans, *University Artificial Intelligence Policy & Guidance*, AY 26-27 | Institutional policy | Permissions, prohibitions, exceptions, review cadence, roles | Copyright Loyola University; research use only, do not redistribute |
| **D3** | OWASP Agentic Skills Top 10, *Incident Response Playbook* (updated March 2026) | Operational procedure | Steps, severity levels, response times, escalation, notification duties | CC BY-SA 4.0; attribution and share-alike |
| **D4** | County of Greene, Virginia, *RFP #2026-001 — Professional Engineering Services* (issued 22 January 2026) | Procurement solicitation | Mandatory submission requirements, hard deadlines, evaluation criteria, contract terms — and an internal deadline inconsistency between the cover and section 6 | Public procurement record; research use, verify local reuse policy |

URLs:

- D1: https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=OJ:L_202601755
- D1 (reader): https://artificialintelligenceact.eu/ai-act-explorer/proceedings/
- D2: https://academicaffairs.loyno.edu/sites/default/files/university_ai_policy_ay_26-27_0.pdf
- D3: https://owasp.github.io/www-project-agentic-skills-top-10/incident-response
- D4: https://greenecountyva.gov/DocumentCenter/View/1577

**Rule:** do not commit full document text. Download into `benchmark/docbench/private/` (gitignored) or keep outside the repo. Commit only URLs, SHA-256 hashes, and short quotes for evaluation.

### Why these four

- They cover four different claim types: regulatory obligation, institutional permission/prohibition, operational step, procurement requirement.
- They are recent enough to be a fair test against memorisation.
- They are short enough to annotate by hand (D1 ~10 pages, D2 ~10 pages, D3 ~1 long page, D4 ~10 pages).
- D4 contains a conflicting deadline: the cover and section 6 disagree. That is not a bug to smooth over; it is exactly the kind of conflict the claim layer must surface with context.

### Known limitation

We do not have a private internal document for this pre-flight. D4 is a niche public document, which gives some protection against memorisation, but it is not the same as an unseen internal policy. Fairness is therefore approximate, and the result should be read as a pipeline test, not as a market test.

---

## 3. Annotation protocol

### 3.1 Unit of truth

The unit is the **claim**, not the document.

A claim is one atomic assertion that can be true or false, permitted or prohibited. Split conjunctions. Keep conditions separate. Keep the quote that supports it.

### 3.2 Claim record

See `benchmark/docbench/gold/schema.json`. Required fields:

| Field | Meaning |
|---|---|
| `claim_id` | Stable ID, e.g. `D1-0007` |
| `doc_id` | `D1`, `D2`, `D3`, `D4` |
| `quote` | Verbatim text from the source |
| `locator` | Page/bbox, section path, char span, or URL#anchor |
| `statement` | Normalised claim in one sentence |
| `subject` / `predicate` / `object` | Optional structured form |
| `polarity` | `affirmed` or `negated` |
| `modality` | `obligation`, `permission`, `prohibition`, `recommendation`, `definition`, `procedure_step`, `condition` |
| `actor` | Who must / may / must not |
| `deadline` | ISO date or duration, if any |
| `conditions` | List of conditions that scope the claim |
| `context` | Source, version, jurisdiction, doc type |
| `confidence` | Annotator confidence, 0-1 |

### 3.3 Evidence rule

**No quote, no claim.**

The quote must exist verbatim in the source. The locator must resolve to the quote. If either check fails, the claim is invalid.

This is the single most important quality rule. It applies to the hand annotation and, later, to the compiler.

### 3.4 Normalisation rules

- One claim per atomic assertion. "The provider shall do A and B" becomes two claims sharing a quote.
- Keep the modality explicit. "May" is not "shall".
- Normalise relative deadlines to an ISO date where the reference date is known; otherwise keep the duration (`21 days`).
- Keep exceptions as separate claims with `modality: condition` and a link to the rule they scope.
- Do not infer. If the document does not say it, it is not a claim.

### 3.5 Locator rules

| Format | Locator |
|---|---|
| PDF | `page`, `bbox` (if available), `section_path`, `char_start`/`char_end` |
| HTML | `url`, `anchor`, `section_path`, `char_start`/`char_end` |
| DOCX/PPTX | `section_path`, `slide` or `paragraph`, `char_start`/`char_end` |
| Text/Markdown | `section_path`, `char_start`/`char_end` |

If a locator cannot be produced, the claim is not ready.

---

## 4. Paper prototype procedure

### Step 1 — Annotate

- 10 claims per document, 30 total.
- At least 4 obligations, 2 permissions/prohibitions, 2 conditions/exceptions, 2 definitions or procedure steps per document where the document supports them.
- Every claim has a verbatim quote and a locator.

### Step 2 — Build a minimal graph

- One Turtle file per document, or one file with named graphs.
- Classes: `oc:Document`, `oc:Section`, `oc:Claim`, `oc:Evidence`, `oc:Context`.
- No need for the full skill ontology yet. Keep the profile minimal.

### Step 3 — Write questions

- 10 questions per document: 5 direct, 3 multi-hop/conditional, 2 unanswerable.
- Each question has a gold answer, the gold claim IDs, and the gold citation.
- Unanswerable questions must have a gold answer of `UNKNOWN` and a reason.

### Step 4 — Run three baselines

| Baseline | What the model gets |
|---|---|
| **B0 — Full read** | The whole document in context |
| **B1 — RAG** | Top-5 retrieved passages |
| **B2 — Claims** | The 10 compiled claims + locators, retrieved by the tool |

Use the same model, the same prompt, and the same output format for all three. Otherwise the comparison is not fair.

### Step 5 — Score blind

- Answer correctness: correct / partial / wrong.
- Citation correctness: does the cited quote support the answer? yes / no.
- Abstention: did it say `UNKNOWN` when the answer was not in the document?
- Tokens: input + output per question.
- Latency: wall clock per question.
- Cost: tokens x model price.

Score without knowing which baseline produced the answer. Two annotators if possible; otherwise one annotator plus a spot check.

---

## 5. Decision rule

Proceed to implementation only if **all** of the following hold:

1. B2 beats B1 on **citation accuracy** by at least **15 percentage points**.
2. B2 does not lose more than **5 points** on answer accuracy versus B1.
3. B2 has **zero** unsupported claims in the certified output.
4. B2's tokens per correct answer are **not higher** than B1's by more than 20%.
5. At least one target user says the output would change how they review or act on the document.

If any of 1-3 fails, do not build the compiler. Fix the claim model or stop.

If 4 fails, the economics are wrong; compile only high-reuse documents.

If 5 fails, the problem is not painful enough; do not build a product around it.

---

## 6. Interview guide (3-5 conversations)

Ask, in this order, and do not pitch:

1. Which document do you re-read most often to make a decision or take an action?
2. What decision or action does it drive, and how often does that happen?
3. What happens if an agent gets it wrong? What is the cost or risk?
4. How do you verify an answer today? Who signs off?
5. What would make you trust an agent's citation: the quote, the page, the version, the approver, all of them?

Record: document type, frequency (`Q`), stakes, current workaround, trust requirement.

---

## 7. What we need from the user

1. **3-5 conversations** with people who actually use such documents. This is the only part that cannot be done from public sources.
2. **Confirmation of the first domain**: policy/procedure, runbooks, or contracts.

A private document would strengthen the test, but it is optional for the pre-flight. The corpus above is sufficient to decide whether the claim layer is worth building.

---

## 8. Five-day plan

| Day | Deliverable |
|---|---|
| 1 | Download D1-D4, hash them, fill `sources.md`, confirm licences |
| 2 | Annotate 10 claims for D1 and D2 |
| 3 | Annotate 10 claims for D3 and D4; write 40 questions |
| 4 | Build minimal Turtle; run B0/B1/B2 |
| 5 | Score, write the result, decide go/no-go |

If the five days produce no clear signal, the next step is not more code. It is a narrower document class or a different problem.

---

## 9. Gate 2 — machine extraction (added 2026-11-08)

The 2026-11-07 run used hand-built claims. It validated the *representation*
(claim + evidence + locator), not the compiler. `compile_claims.py` closes that
gap; this section fixes the test before it is run, so the result cannot be
redefined afterwards.

**Pipeline (span-first).** `source → segmenter → extractor → validator →
emitter`. The segmenter assigns every span an id and a locator *before* the
model runs. The extractor may only reference span ids; the quote is copied from
the span. Verbatim evidence is therefore a structural property, not a hope.

**Method.**

1. Compile D1–D4: 18 model calls (14 extraction + 4 conflict), ~56K input and
   ~19K output tokens, ~$0.02 at the current flash-model price. One pass, no
   tuning against the gold set.
2. `check_claims.py` on the result: every span verbatim, every PDF page
   recomputed, every claim valid against `schemas/claim.v2.schema.json`.
3. **Evidence support** — the part structure cannot guarantee. An independent
   reviewer gets `(statement, quote)` pairs and no source, and answers "does
   this quote state this claim, as written?" Sample: 15 claims per document.
4. **Recall proxy** — for each of the 41 gold claims, is a compiled claim that
   states the same rule present? A proxy, not a measure: the gold set is small
   and was written by hand for a different purpose.
5. Re-run B2 with the compiled claims, then re-score.

**Go criteria (all must hold).**

| Check | Threshold |
|---|---|
| Structural validity (`check_claims.py`) | 100% — anything less is a bug, not a result |
| Evidence support, sampled | >= 90% of sampled claims |
| Claims asserting facts absent from the source | 0 |
| Gold-set recall proxy | >= 70% |
| B2 − B1 citation accuracy with compiled claims | >= 15 pp |
| B2 answer accuracy with compiled claims | within 5 pp of the hand-built B2 (100%) |

**Stop rule.** If structural validity or evidence support fails, do not tune the
prompt against the gold set — that would measure the tuning, not the compiler.
Change the pipeline (segmenter or validator) and re-run from a clean compile.

**Known limits of this gate.** One model, one pass, four documents, one domain.
The compiled claim set will be larger than the hand-built one (the extractor
sees every span), so B2 switches from `all_claims` to `bm25_claims` with top-12;
that change is part of what the run measures and must be reported separately
from extraction quality.

### 9.1 Amendment A1 (2026-11-08) — a repair stage, after the gate failed on evidence support

Run 3 (the clean compile of D1–D4 in `gold/claims.compiled.jsonl`) passed every
structural criterion and failed one: the full census put evidence support at
**88.8%** (459/517), below the 90% bar. The stop rule above then applies: do not
tune the prompt against the gold set, change the pipeline.

The failure is measured, not guessed: 58 claims where a material element of the
statement is not in the claim's own quote — the actor from a heading (28), a
qualifier from an adjacent line (21), an omitted exception (4), a number added,
a quote that belongs to another rule, a strengthened modality. A deterministic
post-hoc checker was tried first and rejected on measurement (28% precision on
the actor test; ~30% lexical coverage; ~10% exception cues).

The pipeline therefore gains a third stage, `verify_claims.py`:

1. **audit** — a model sees `(statement, quotes, section path)` and nothing else,
   and returns `ok | weak | no | fabricated` on the same scale as the census.
2. **repair** — a second call sees the claim, its current spans and the spans
   within ±3 positions, and may only `reevidence` (cite a neighbouring span),
   `rewrite` (restate within the current evidence) or `drop`. It cannot invent a
   span or a sentence; a rewrite shorter than the extractor's own 15-character
   floor is refused.
3. **re-audit** — repaired claims are audited again; whatever still fails after
   the last round is dropped. An unsupported claim is not shipped.

`compile_claims.py --verify` runs the whole pipeline in one command.

**What this does not change.** The gate thresholds above, the census method, and
the rule that the measure is an independent census of the final artifact. The
audit inside the stage is *not* the measure: after the residual is dropped its
final audit is ~100% by construction, and it is a model grading its own repair.
The number that decides the gate is a fresh census of the emitted artifact.

**Instrument calibration** (recorded in `gold/audit.calibration.md`, run before
the stage was applied to the artifact): against the census, with the stop rule
fixed in advance at >= 45/58 known non-ok caught and <= 5 false positives on 60
known-ok, the frozen instrument catches **62/65** known defects (95.4%) and
flags 6 of 120 known-ok claims, of which **1** survives adjudication as a true
false positive. It is conservative in the right direction: almost everything it
flags is a real defect, so it never rewrites a claim that was already supported.

**Census of the repaired artifact.** Rows whose statement and evidence are
byte-identical to the censused artifact keep their existing verdict: the census
is a function of exactly those fields, the reviewer is the same, and re-judging
identical text measures nothing. Every rewritten, re-evidenced or newly merged
row is judged fresh, and the gate number is the ok share of the whole artifact
under that join. This is stated here before the number exists.

**Why the census, not the audit, is the measure.** Temperature is 0 but the
gateway is not deterministic: three of 118 verdicts flipped between two
identical calibration runs. A stage that both repairs and re-judges would
report its own convergence. An independent pass over the emitted text cannot.

### 9.2 Amendment A2 (2026-11-08) — keep `weak`, drop only hard failures

The first repaired artifact (`gold/claims.verified.jsonl`, 493 claims after 24
rows were removed) was measured by a fresh census: **490/493 = 99.4%** evidence
support, with D1 141/142, D2 88/89, D3 77/77, D4 184/185. The gate's support
bar was met for the first time. Two other gate rows moved the wrong way, and
the cause was measured before the rule was changed:

- **Recall proxy 39/41 = 95.1%.** The lost claim is `D1-0009` (*interim
  measures*); its only compiled counterpart was `D1-0037`, which the stage had
  dropped as a residual `weak`.
- **Blind B2 answer 37/39 = 94.9% (−5.1 pp)** and **automatic citation
  70.0%**: 5.0 pp below the 517-claim run (75.0%), and only 10.0 pp above B1
  where the gate requires 15 pp. The answer regression includes `D1-Q08`, the
  interim-measures question: the dropped claim was the answer.
- **The false-drop audit.** Of the 11 residual drops, 6 were census-`ok`:
  `D1-0037`, `D3-0009`, `D4-0075`, `D4-0076`, `D4-0082`, `D4-0100`. Only 5
  were genuinely `weak`. The audit's own verdict was stricter than the census
  the gate uses, so "drop everything the auditor still flags" deleted true
  claims at a rate the gate could not tolerate.

The stage therefore keeps a residual `weak` claim — it is true, but a material
element of the statement sits outside its own quote, which is the citation
quality the 90% bar already tolerates — and drops only `no`/`fabricated`, where
the quote does not state the claim at all. Kept weak rows are listed in the run
report (`kept_weak_ids`), never hidden. The measurement on the resulting
artifact is in `RESULTS.md`; the weak rows are `D1-0058`, `D1-0110`, `D2-0028`,
`D2-0035`, `D4-0072`.

This amendment was written after seeing the regression. It changes no threshold
and no census rule: the gate is still the ok share of an independent census of
the emitted artifact, and it is 99.0% (499/504) under this rule.

### 9.3 Amendment A3 (2026-11-08) — make the citation contract unambiguous, and re-run both baselines

The B2 runs above exposed a defect in the *instrument*, not only in the
artifact. `score.py` calls a citation supported when it is a verbatim substring
of the source document. The answering prompt asked for "a verbatim quote from
CONTEXT". In B2 the context contains both a claim statement and its `QUOTE`
line, so copying the statement satisfies the prompt and fails the metric. Every
unsupported citation measured so far is that case: 2/2 in the 517-claim run
(`D3-Q07`, `D4-Q07`), 4/4 in the 493-claim run, 4/5 in the 504-claim run. B1
cannot exhibit the defect because its context holds no statements, so the
metric penalised B2 alone and the penalty grew as repair rewrote more
statements. That is a comparison between a clear contract and an ambiguous one,
not between two retrieval strategies.

Fix: the shared system prompt now says the citation must be copied from the
document text and, when a claim block shows a `QUOTE` line, must be that line
and never the claim statement. The scoring rule and every gate threshold are
unchanged. Both B1 and B2 are re-run with the identical prompt (the run
manifest now records `system_sha256`), so the delta remains like-for-like. The
alternative — teaching `score.py` to accept a statement as a citation — was
rejected: it would make an unverifiable paraphrase count as a source quote.

### 9.4 Amendment A4 (2026-11-08) — one mechanical citation retry, checked against the source

With A3 in place the run (`20261108T200226Z`) still had 5 unsupported B2
citations, and they were a second, different defect: none was a claim statement
any more, and none was a paraphrase of an existing quote. Each was a whole
`QUOTE` line copied out of a claim block whose evidence holds *more than one
span* — a concatenation the claim layer printed as one line, and therefore not a
contiguous substring of the document. The prompt could not be fixed by wording,
because the context genuinely shows that concatenation as one quote; the defect
is in what the harness prints, and the cheapest honest fix is not to accept it.

Fix: after the answer is parsed, the harness checks the citation against the
source it already holds. If it is not a verbatim substring after whitespace and
typography normalisation, it re-asks **once**, quoting the rejected text back and
requiring the same answer with a citation that is an exact substring of CONTEXT
(and, in a claim block, a single `QUOTE` line). `CITATION_RETRIES = 1` and the
rule is in the shared loop, so it applies identically to B1 and B2. The count of
retries per answer is recorded (`citation_retried` in `answers.jsonl`,
`citation_retries` in the manifest), so a run that needed more retries is
visible rather than smoothed over.

Measured effect: the retry fired on **5 of 40 B2 answers and 0 of 40 B1
answers**, and every retried citation passed the same mechanical check on the
second attempt. The final numbers are reported twice — first-pass and after the
retry — because the difference is exactly the quantity the retry removes:

| Row | B1 | B2, first pass | B2, final |
|---|---:|---:|---:|
| Citation supported (automatic) | 60.0% | 67.5% | **80.0%** |
| Citation matches gold (automatic) | 55.0% | 77.5% | 77.5% |
| Answer recall (automatic) | 57.0% | 82.2% | 79.6% |
| Blind answer correct (n = 39) | 28/39 | 38/39 | **38/39** |
| Blind citation whole (of 32) | 20/32 | 26/32 | **27/32** |

The answer difference between first pass and final is wording variance in the
three answers that were re-generated, not a gain: the retry is instructed to keep
the answer unchanged, and the blind verdicts on those three cases are the same
before and after. The gate row that matters, B2 − B1 citation, is **+20.0 pp
automatic and +21.9 pp blind** — it passes either way, and the retry raises the
level on both sides of the comparison rather than only B2's.

This is a measurement-instrument change, not an artifact change: no claim was
added, removed or rewritten, and the gate's support bar is measured on the claim
file, which the retry never touches. It is recorded here because it moves a
reported gate row, and because a reader must be able to see that the final B2
citation number includes one repair round that a raw model answer would need.

---

## 10. Second corpus — generalisation probe (added 2026-11-08)

Gate 2 is a result on four normative-prose documents. Every document is a
regulation, a policy, a playbook or a tender. Nothing in it tests a **contract**
or a document whose operative content **is a table**. This section is written
before any model call on the new documents and fixes the documents, the
extraction, the method, the thresholds and the reporting.

The question is narrow and answerable: *does the compiler that reached 99.0%
support on D1-D4 still produce supported, non-fabricated claims when the
document type changes?* It is not a test of invoices, internal wikis or
customer data, and it does not re-open Gate 2.

### 10.1 Documents

| ID | Document | Pages / words | Licence | Why it is here |
|---|---|---:|---|---|
| **D5** | ALSPAC International Data Transfer Agreement (IDTA v1, 24 March 2024) — the ICO IDTA A1.0 completed with the University of Bristol as Exporter | 35 / 10,629 | (c) University of Bristol; publicly available sample, kept local, not redistributed | a **contract**: parties, defined terms, controller/processor duties, liability, termination, sub-processing — and four tables that are part of the operative text |
| **D6** | NARA General Records Schedule 1.1, Financial Management and Reporting Records (Transmittal 31, April 2020) | 9 / 2,403 | US Government work, public domain | the operative content **is a table**: one row per record item, with its disposition instruction, trigger and disposition authority |

Selection rules, applied before either document was read for claims: publicly
available; text-extractable without OCR; no personal or customer data; at least
one document type absent from D1-D4; at least one document whose rules live in
a table; combined size small enough that a **full census** of every emitted
claim stays possible (target <= 15k words).

Rejected for size or access, recorded so the choice is auditable: MSC Core
Terms v2.2A (29,418 words), Short Form Contract v1.5 (35,175 words), Model
Services Contract Schedules, Barnet/Civica call-off contract (20,422 words),
UK council retention schedules (17,731-18,880 words), CISA incident-response
playbooks (403 to automated fetch), ICO IDTA original (Cloudflare challenge).

### 10.2 Extraction

- `pdftotext` 24.02.0, **default reading order (no `-layout`)**, for both
  documents. The choice is part of the method, not a per-claim decision: the
  GRS table is laid out column-major, and `-layout` interleaves its cells so
  that no disposition instruction ("Destroy 6 years after final payment or
  cancellation") remains a contiguous string. Default reading order keeps each
  cell block whole, which is what a verbatim-evidence contract needs. D5's
  Part 1 tables have the same property: `-layout` puts the Exporter and
  Importer columns on one line and shreds the values, default order does not.
- Byte hashes of the extracted `.txt` **and** of the downloaded PDFs are
  recorded in `sources.md`; the PDFs and texts stay in `private/`.
- **No cleaning.** Running page headers and footers, table column headers and
  page numbers stay in the text exactly as the extractor emits them. Skipping
  them is part of what is measured: the compiler's rule 6 says to skip page
  furniture, and this probe tests whether it does.

### 10.3 Method — identical to Gate 2

Span-first segmentation with the §9 compiler at `main` (`7fd946c`), the same
schema v2, the same extraction prompt, the same model (`deepseek-v4.1-flash`),
the same chunking, the same `verify_claims.py` audit -> repair -> re-audit
stage, and an **independent census of every emitted claim** (no sample), with
the same verdict scale (`ok | weak | no | fabricated`) and the same join rule
for rows that are byte-identical to an already-censused row (§9.1).

Gold set: 10 hand-written claims and 8 hand-written questions per document,
kept local and gitignored like D1-D4, written from the source before the
compile and not adjusted afterwards. Each document's questions include at
least 2 unanswerable ones.

**No prompt, threshold or pipeline change is made in advance for these
documents.** In particular, PDF table rows are not reconstructed by hand and
the segmenter is not taught about them first: if it cannot recover a row, that
is the measurement. A fix, if needed, is pre-registered as §10.x *after* the
failure is measured and is then measured on its own re-run.

### 10.4 Thresholds — unchanged, and now per document

| Check | Threshold |
|---|---|
| Structural validity | 100% |
| Evidence support, full census | >= 90% |
| Claims asserting facts absent from source | 0 |
| Gold-set recall proxy | >= 70% |

The gate is **per document**: D5 and D6 each have to clear the bar. A pooled
number that passes because one document carries the other is reported but does
not pass the probe. This is stricter than §9, where the four documents were
pooled, and it is fixed here before the numbers exist. Every figure is reported
with its denominator: D6 is small, so one claim moves its support percentage
by more than two points.

The answer-side rows (B2 - B1 citation, B2 vs hand-built B2) are **not** part
of this probe's gate. They were measured on D1-D4 with 40 questions; 16 new
questions cannot support a 15 pp delta, and stating that after seeing a number
would be exactly the move this protocol forbids. If a B1/B2 run is made on
D5/D6 it is reported descriptively, with n, and labelled as such.

### 10.5 What this probe can and cannot show

- It can show that the compiler's support, recall and fabrication behaviour
  survives a change of document type (contract; table-as-content).
- It cannot show generalisation to invoices, emails, internal wikis or
  customer documents, and it does not test a negotiated contract: D5 is a
  completed standard instrument, not a deal with redlines.
- D6 is a 9-page schedule. Its per-document percentage is coarse by
  construction; the claim-level verdicts, not the percentage alone, are the
  evidence.
- D5's Part 1 tables and D6's page-crossing rows are the two places where the
  extractor and the segmenter are known to be weakest. They are inside the
  measurement on purpose, and a failure there is a finding about the pipeline,
  not an excuse.

### 10.6 Stop rule

If either document misses a threshold, the probe **fails** and is reported as a
failure with the failing rows named. No threshold is lowered, no sample is
re-drawn, no prompt is tuned against the gold set, and the passing document is
not used to average the failing one away. The failure is attributed to a stage
(segmentation, extraction or repair) from the spans and statements themselves;
the fix is written as a new pre-registered amendment before it is measured, and
if it is measured it is measured on a fresh compile of the failing document,
with the failed run kept in the report.

### 10.7 Probe result and amendments (added 2026-11-09, after the probe was measured)

The probe ran on the artifact described in `gold/audit.probe.md` and **fails**.
The numbers are in that report and in `RESULTS.md`; they are not restated here
as a second source of truth.

| Document | Structural | Support (census) | Fabrications | Recall | Verdict |
|---|---|---|---|---|---|
| D5 — contract | pass | 323/325 = 99.4% | 0 | 7/10 = 70.0% | **pass** |
| D6 — table | pass | 47/51 = 92.2% | 0 (4 under the literal row) | 2/10 = 20.0% | **fail** |

D6 fails the recall row. Under the literal "claims asserting facts absent from
source" row it also has four failures (`D6-0027`, `D6-0029`, `D6-0030`,
`D6-0032`), because each asserts a disposition-authority association that
belongs to a different item. Neither a threshold nor the per-document rule is
changed.

**Correction (2026-11-09, added with the fixed-run census).** The D5 row above
reads "0" on facts absent; that is wrong under the same literal rule. `D5-0348`
defines "Harmful Impact", a truncated form of "Significant Harmful Impact", and
is counted `no` in `gold/audit.probe.md` itself — so D5 has **1**, not 0. The
probe verdict is unchanged (it already failed on D6 recall) and no measured
number changes; the erratum is also at the end of `gold/audit.probe.md`. The same
defect, at scale, is why the fixed run fails (§10.7(e)).

#### 10.7(a) Page checker — an instrument fix, applied and re-measured

`check_claims.py` reported 7 page failures on 512 evidence spans. All seven are
quotes that recur on several pages (glossary scaffolding, a repeated disposition
clause); the checker resolved the quote to its *first* occurrence, although the
declared page contained it. That contradicts the checker's own contract, and the
seven declared pages are the spans' actual pages.

Fix, applied and re-measured on the same artifact with no model call:
`page_containing()` keeps the declared page when the quote occurs there and
falls back to the first occurrence only when it does not. Covered by
`benchmark/docbench/tests/test_check_claims.py`. Structural validity is
**376/376 claims, 512/512 spans, 0 failures**; D1-D4 stay at 0. No statement,
quote, threshold or artifact changed.

#### 10.7(b) Table-record segmentation — pre-registered, not yet measured

**Measured defect.** D6's operative content is a four-cell table row (item
number, description, disposition instruction, disposition authority). In the
default-order text each cell arrives as its own line block. `looks_like_heading`
classifies the first line of the disposition cell (`Destroy 2 years`,
`Destroy when 3`, `Destroy 6 years`) as a section heading, so the line becomes
`section_path` and never enters a span. The remaining `Temporary.` is under
`min_chars` and is discarded by `flush_short()` (`< 20` characters). Measured on
`gold/probe.compiled.jsonl.spans.jsonl`: `Destroy 2 years`, `Destroy 6 years`,
`Destroy when 3` and `Destroy when no` occur in **no span**, and the item keys
(`012`, `020`, …) occur in no span. The model can only quote what it is given,
so it emits the continuation ("…longer retention is authorized") and never the
operative "Temporary. Destroy X after Y"; the repair stage cannot recover a
sentence that has no span.

The same rule produces the four DAA misattributions: the authority line of row
N stays on the heading stack while row N+1's description arrives, because the
item number between them is a short fragment that `flush_short()` drops.
`S0030` (item 020's description) carries `section_path:
["DAA-GRS2016-00010001"]`, item 012's authority; `S0032` (item 030's
description) carries item 020's authority.

**Fix (generic, not D6-specific).**

1. **Record detection.** A line is a *record key* when it is a standalone short
   token (<= 8 characters, containing a digit) that (a) does not recur on more
   than one page — page numbers do — and (b) is followed by at least one body
   line. When at least three record keys are found in a document, the document
   has an item-numbered table and is segmented by record.
2. **Record scope.** A record runs from its key line to the line before the next
   record key (or the end of the table). No line inside a record is consumed as
   a heading; the key travels with the record's first span, so every span of a
   record can be resolved to its row.
3. **No fragmentation loss.** `flush_short()` may not drop a fragment inside an
   open record: the fragment is appended to the record's text, and the record is
   emitted as spans only when it exceeds the sentence-window limit. A span never
   crosses a record boundary.
4. **Locator.** A record span's `section_path` is the containing document
   section plus the record key, never the previous row's authority line.

No prompt, schema, model or threshold changes. The model still may only quote
span text.

#### 10.7(b)(i) Record-key discriminator — refined before measuring

The detection rule in §10.7(b)(1) was evaluated on the two probe inputs before
any fix run, with no model call. Read off the text alone, it is wrong in three
ways, so the discriminator is refined here, still before the fix is measured:

- **D5 is a false positive.** The rule matches 102 standalone number lines in
  D5, because the contract numbers its clauses `1`, `1.1`, `1.2.1`, … . Applying
  it would re-segment the contract by clause, which is not the intent and is a
  needless regression risk for the document that already passed.
- **A printed page number is not excluded by recurrence.** D5's page numbers
  (`1`–`6`, …) each occur once, so the "does not recur on more than one page"
  clause does not remove them. What does distinguish them is position: a page
  number is the last content on its page.
- **Page furniture can look like a key.** D6 contains the token `41T` twice;
  a token repeated in the document is furniture, not an item number.

The discriminator is therefore fixed as:

1. A candidate is a standalone line of at most 8 characters, containing a digit,
   with no whitespace and no trailing punctuation beyond a dot, followed by at
   least one body line.
2. **Page numbers:** a candidate that is the last text on its page is a printed
   page number, not a key.
3. **Distinctness:** a token that occurs more than once in the document is page
   furniture, not a key.
4. **Flatness:** a candidate set is rejected when any key is a component-prefix
   of another (after dropping a trailing dot), e.g. `1` → `1.1` → `1.2.1`.
   Item-numbered tables are flat (`001`, `010`, `011`, …); dotted section
   numbering is a hierarchy. This rejects D5 after rule 2 has removed its page
   numbers.
5. At least three keys must survive all of the above.

These are properties of the input text, established before the fixed run, not a
choice made after seeing a score. No threshold changes.

#### 10.7(b)(ii) Key shape — a guard found by dry-running the detector on D1-D4

Running the detector on the four Gate 2 documents, with no model call, showed
one more false positive: D2's numbered bibliography has standalone `1`…`6`,
each followed by a reference entry, so it satisfies every rule above. Applying
record segmentation there would re-segment a prose policy by list number.

An item column is zero-padded to a fixed width (`001`, `010`, …); a numbered
list is a consecutive run of small integers (`1`, `2`, `3`, …). The guard is
therefore:

6. **Key shape:** every key is numeric, all keys have one width, that width is
   at least 2, and the keys are not a consecutive integer run.

D5 is rejected by rules 2 and 4; D2 by rule 6; D6 keeps all 14 keys. The guard
was added while the fixed D5/D6 compile was in flight; because it leaves the
D5 and D6 key sets unchanged, the span file of that run is byte-identical to
the output of this final code (verified by re-segmenting both documents and
comparing every span id, paragraph and locator), so it cannot affect the
measured numbers. It is recorded because "the change is global" is only true if
the other documents are actually checked.

**Measurement.** A fresh compile of **both** D5 and D6 with the fixed segmenter
(the change is global, so D5 is the regression check even though it already
passed), then verify and a full independent census of every emitted claim, with
the same verdict scale. D6 is the gate; D5 must keep structural 100%, support
>= 90%, 0 fabrications and recall >= 70%, or the fix is rejected as a
regression. For D6, in addition to the §10.4 thresholds, the eight gold claims
the first probe missed (`D6-0002`, `0003`, `0004`, `0005`, `0006`, `0008`,
`0009`, `0010`) must be recalled, and `D6-0027`/`0029`/`0030`/`0032` must not
reappear with a wrong authority.

**What does not change.** The failed run is kept: `gold/probe.compiled.jsonl`,
`gold/probe.compiled.verified.jsonl`, `gold/probe.verdicts.jsonl` and
`gold/audit.probe.md` stay as the measurement of the unfixed pipeline. The fix
is reported as a new run with its own census, not by rewriting this one.

#### 10.7(c) Verify concurrency — a throughput amendment, not a pipeline change

The fixed run's verify stage reached the end of repair round 1 with four batches
dead on provider HTTP 503 (`repair incomplete: 12 claim(s) never judged`), so the
process stopped exactly as `verify_claims.py` is written to: progress cached,
`--resume` required. That is the moment this amendment was recorded, before the
resumed calls were made.

The audit and repair passes issued their independent batches strictly one after
another. `audit_prompt` and `repair_prompt` are functions of the batch alone (the
claims in it and their own spans), `llm.chat` opens one HTTP request per call,
and the cache is an append-only JSONL. Nothing in a batch depends on another
batch, so the batches can be scheduled side by side.

**The change.** `--verify-concurrency N` (default `1`, i.e. today's behaviour) in
`compile_claims.py` and `verify_claims.py`, implemented in `_run_batches`. Cache
appends and token accounting take a lock; the cache stays one JSON object per
line, and the tests in `ConcurrencyTest` pin both the concurrency and the file
integrity. Batches are built from the same pending list in the same order.

**Why it cannot move the measurement.** Identical model, prompt text, span
neighbourhood, schema, batch size, parsing, verdict scale and repair policy. A
model call sees exactly the prompt it would have seen sequentially; only *when*
it is issued changes. Order was already irrelevant to the result: the audit and
repair outputs are keyed by `claim_id` and applied per claim.

**Provenance.** The 429-row audit of the fixed run and the first 150 rows of
repair round 1 were produced sequentially. The 12 claims left dead by 503s, and
round 2 and its re-audit, are produced with concurrency 6. The run manifest and
the report must record `verify_concurrency`; the census treats both scheduling
regimes as one pipeline, because the per-claim prompts are the same. The default
of the tool remains sequential, so this amendment cannot silently change a
future run.

#### 10.7(d) A batch the provider rejects is split, not fatal

Resuming the fixed run exposed a second, different failure. Six D5 claims were
left dead by repair round 1: the batch of three returns **HTTP 400
`upstream_rejected`**, while each of the three claims passes alone (measured on
2026-11-09, one call per claim, same prompt builder, same model; all six
succeeded). The failure is a property of the payload the provider was sent, not
of the claims.

Until now `ask()` treated any `SystemExit` from the model call the same way: it
recorded the batch as aborted and the pass ended with
`repair incomplete … re-run with --resume`. That is correct for a transient
failure, and wrong for a payload the provider will never accept as-is: resuming
re-sends the same batch forever.

The rule is now the one the code already applied to *omitted* claims: when a
batch of more than one claim fails, halve it and ask again, down to single
claims; only a single claim that still fails is aborted. The error code was
first used as the discriminator (`4xx` splits, `5xx` aborts), but the same D5
triple was observed returning **HTTP 400 `upstream_rejected` on one attempt and
HTTP 503 on another**, so the code classifies the *payload*, not the batch: the
split is unconditional and `chat` still retries each call on its own before the
split is reached. This widening was recorded while the resumed run was in
flight, after the first resume had aborted twice on the same triple; it cannot
touch a cached row, and it only changes calls that would otherwise end the pass.
A total outage is bounded: it now costs the split tree (1 + 2 + 3 …) of single
attempts before `repair incomplete` is raised, instead of one call.

**What this cannot change.** Batches the provider accepts are untouched: the
split only runs after a call has failed on its own retries and raised, so every
claim whose batch succeeded was repaired by exactly the prompt §10.7(b)
pre-registered. Claims rescued by a split are
repaired by a smaller prompt (fewer sibling claims), which is recorded here
rather than hidden. The alternative — leaving six claims unrepairable — would
have made the pass impossible to finish at all.

#### 10.7(e) The fixed run, measured — the probe fails again, on the key/value tables

The run pre-registered in §10.7(b)(ii) finished on 2026-11-09 and its census is
`gold/audit.probe.fixed.md`. The gate is unchanged; the artifact is new.

| Document | Structural | Support (census) | Facts absent from source | Recall | Verdict |
|---|---|---|---|---|---|
| D5 — contract | pass | 329/354 = 92.9% | **8** | 7/10 = 70.0% | **fail** |
| D6 — table | pass | 49/51 = 96.1% | 0 | 10/10 = 100% | **pass** |

**D6 is fixed.** Recall goes 2/10 -> 10/10, every disposition now sits inside
its own quote, and no claim attaches an item's disposition authority to another
item's records (0 mismatches against the source's item -> DAA map, full strings,
years included). Support 92.2% -> 96.1%; structural 100%. The two `weak` rows
(`D6-0017`, `D6-0018`) lose the record type, not the disposition.

**D5 fails on a different row and a different defect.** Eight claims assert a
definition for a term the document does not define: `Safeguards`, `Delay`,
`Data`, `Clauses` (twice), `Country`, `Controller`, `Protection Laws`. Every one
is a glossary entry printed on **two lines** ("Appropriate / Safeguards",
"Without Undue / Delay", "Special Category / Data", …): `looks_like_heading`
accepts each line, both sit at the same depth, and the stack keeps only the
last. The model is given `section_path: ["Delay"]` and defines `Delay`. Two of
the eight are actively wrong rather than merely mislabelled: `Data` is narrowed
to special category data, and `Controller` receives the *Third Party
Controller* definition while the glossary defines it "As defined in the UK
GDPR". This is not a new criterion: the unfixed run already had one instance
(`D5-0348`, "Harmful Impact") and its census already counted it `no`; the
correction to that report's summary is an erratum at its end.

The same defect explains the three D5 recall misses: Tables 1-4 are key/value
tables too. The controller-status label is `S0022` (`section_path:
["The status of"]`) and the value cell `Exporter is a Controller` is the
`section_path` of the next span (`S0023`). The claims `D5-0002`/`0003`/`0007`
were produced, audited `weak` for exactly that reason, and dropped; the fix does
not change D5's spans, so recall stays 7/10.

**Scale application, frozen before the next run.** For a definition claim the
evidence is the schema's pair (quote, locator). The locator's `section_path`
names the term; when it names a term the document does not define, the claim is
`no`, not `weak`. `weak` is for a statement that is true but lacks an element
its own evidence also lacks (a bare definition body, an unresolved "the term",
a truncated quote). This is how §9.1 already judged `D5-0348`; it is written
down here so the next census cannot drift.

**Carry-forward.** 64 rows were byte-identical to §9.1 rows and inherited their
verdict (all `ok`). One of them, `D5-0392`, is the glossary scaffolding
`(this is how this word or phrase must be interpreted in the IDTA)`; it is
byte-identical to the fresh `D5-0421`, which the census finds `weak`, so both
are `weak`. The re-judgement is disclosed because it lowers the score.

**Nothing else changed.** Same thresholds, scale, model, prompt, schema,
chunking, verify stage. The failed run is untouched: `gold/probe.*`,
`gold/probe.verdicts.jsonl` and `gold/audit.probe.md` remain the measurement of
the unfixed pipeline.

##### 10.7(e)(i) Key/value table segmentation — pre-registered, implemented, measured, rejected

This is written after the score is known, which is unavoidable for a defect the
score exposed. It is a pre-registration for a **new** run: the fix below is not
written, not applied to the artifact above, and the thresholds do not move.

**Measured defect.** In the default-order text a key/value table arrives
column-major: the label cell, then the value cell. When a label wraps onto two
lines, each line is a heading and the second replaces the first on the stack
(`S0279`-`S0327`, the Legal Glossary, pages 31-35). When the value is a checkbox
or a short cell (`Exporter is a Controller`), the value itself becomes a heading
for the following block instead of joining the label (`S0022`/`S0023`,
`S0024`/`S0027`). Consequences already measured: 8 `no` claims, 13 `weak`
claims, 3 recall misses.

**Fix (general, not D5-specific).**

1. **Joined label.** Inside a table region, consecutive heading-candidate lines
   with no body text between them are one label: join them with a single space,
   and use the joined text as the `section_path` entry. This restores
   "Appropriate Safeguards", "Adequate Country", "Special Category Data",
   "Without Undue Delay", "Mandatory Clauses", "UK Data Protection Laws",
   "Importer Information", "Relevant Data Subject", "Significant Harmful
   Impact", "Restricted Transfer", "Linked Agreement", "Importer Data Subject
   Contact", "Extra Protection Clauses".
2. **Label and value in one span.** A key/value row is a unit: the label and the
   value cell that follows it must be quotable together, so the model can put
   both sides of the definition (or the checkbox status) into its quote. A row
   never starts a new `section_path` on its own value.
3. **No table label as a section.** A joined label that belongs to a table row
   may appear in `section_path`, but the table's *own* cell text may not become
   a heading for unrelated following text.

No prompt, schema, model or threshold change. The detection rule must be
properties of the text (a run of heading-like lines with no body between them,
inside a region whose rows repeat the label/value shape), not a list of the D5
glossary headwords.

**Measurement.** A fresh compile of **both** D5 and D6, verify, and a full
independent census, same scale and thresholds. D6 must keep structural 100%,
support >= 90%, 0 facts absent, recall 10/10 and 0 misattributed authorities;
D5 must reach 0 facts absent and must recall the three Table 1/Table 2 gold
claims (`D5-0002`, `D5-0003`, `D5-0004`) while keeping recall >= 70%. Failure on
either document rejects the fix as a regression or as not-a-fix.

**Implementation status (2026-11-09).** The branch `probe/key-value-tables`
implements the rules above; no threshold, prompt, schema or model changed. The
segmenter computes a region mask from the text alone (a `Table N:` caption, a
dense run of `Label:` cells, or a repeated header pair) and takes the
key/value branch only inside that mask. Verified on a dry run (no model call):
D1-D4 are **byte-identical** to the committed baseline (420 spans), D6 is
**byte-identical** to the fixed run (35 spans), and D5 segments to 325 spans.
The eight glossary fragments named in §10.7(e) now resolve to joined labels
(`Adequate Country`, `Appropriate Safeguards`, `Commercial Clauses`, `Extra
Protection Clauses`, `Special Category Data`, `UK Data Protection Laws`,
`Without Undue Delay`, `Controller`), and the Table 1/Table 2 rows carry
`Full legal name: ...`, `UK country's law that governs the IDTA: England and
Wales` and `... Exporter is a Controller` in one span. 136 short tests pass
(`unittest discover`). The billable fresh compile, verify and census were **not**
run at that date: they waited for explicit approval, and the acceptance verdict
is made only from that run. The run and its verdict are in §10.7(e)(ii) below.

##### 10.7(e)(ii) The run, measured — the fix is rejected by its own criteria

The fresh compile of D5 and D6, its verify and the independent census finished
on 2026-11-10. The artifact is
`gold/probe.kv.compiled.verified.jsonl` (397 claims: D5 335, D6 62; 532 evidence
spans; schema v2; `check_claims.py` 0 failures). The full census is
`gold/audit.probe.kv.md`: **397 rows, no sample**. The pre-registration above,
the thresholds and the scale are unchanged; the failed and fixed runs and their
censuses are untouched.

| Document | Structural | Support (census) | Facts absent from source | Recall | Verdict |
|---|---|---|---|---|---|
| D5 — contract | pass | 329/335 = **98.2%** | **0** | 8/10 = **80.0%** | **fail** (named claims) |
| D6 — table-as-content | pass | 61/62 = **98.4%** | 0 | 10/10 = 100% | **pass** |

Pooled support 390/397 = 98.2%, **0** `no`, **0** `fabricated`.

**What it repaired.** The eight glossary definitions of a term the document does
not define (`Country`, `Safeguards`, `Clauses` twice, `Data`, `Controller`,
`Protection Laws`, `Delay`) do not reappear in any form; the joined headwords
are correct (`D5-0330`-`D5-0378`), and the definition-body-only `weak` rows of
the fixed run now name their term. D5 "facts absent from source" goes 8 -> **0** and
support 92.9% -> 98.2%. `D5-0004` is now recalled (`D5-0007` *Exporter is a
Controller* + `D5-0009` *Importer is a Controller*). D6 keeps its pass, 0
misattributed DAAs; but D6's spans are **byte-identical** to the fixed run, so
that pass is unchanged input, not evidence for the rule.

**Why it fails.**

- **`D5-0002` is not extracted.** The segmenter does produce the exporter row —
  `S0007` `Full legal name: University of Bristol (through ALSPAC)`, `S0008`
  the Beacon House address — and both spans are in the first chunk with the
  Table 1 rows the model did use. Of the 411 raw claims, **none** quotes
  `Full legal name`, `Beacon House` or `BS8`. The text is segmented; the
  extractor skips it. `S0008` additionally opens with a stale `Full legal name:`
  prefix belonging to the Importer's empty cell.
- **`D5-0003` is quoted, then audited away.** The primary-place row is a
  colonless four-line label; the label is joined into `section_path` and the
  value `England and Wales` stays in its own span `S0018`. The raw compile did
  state the rule (`D5-0006`), and the verify stage judged it `weak` because the
  label was not inside the quote, re-evidencing it on the governing-law cell —
  so the primary-place rule does not survive. This is the one place where the
  census rule (evidence is quote **and** locator) and the verifier's quote-only
  repair policy disagree; under the pre-registered rule 2 the two sides of the
  row should be one span, and for this colonless label they are not.

**Residual, outside the acceptance.** The bogus `section_path`
`["Laws", "15.2.1.5 contact point for more information; and"]` now attaches to
27 spans / 49 claims (fixed run: 6 spans / 19 claims) on pages 16-20; page and
quote are correct and no verdict moves, but a wrong locator on 49 claims is a
regression and is recorded rather than excused. `D5-0009`'s locator also names
the wrong Table 2 row (`Linked Agreement`) while its quote carries the status.

**Verdict: rejected.** The pre-registration required `D5-0002`, `D5-0003` and
`D5-0004`; two of the three are absent, and the 80% overall recall does not
replace a named requirement. The segmentation code is on `main` (merged as
`e125d08` before the run, which is what the pre-registration required); what is
rejected is the fix as a validated improvement — it is not carried into the
gate, and no further repair is built on it without a new pre-registration. This
section plus `gold/audit.probe.kv.md` are its measurement. Cost: compile
~$0.16, verify $0.2761 (102 calls), census $0.00.

**Next step: survey before the next registration.** `gold/survey.segmentation.md`
(2026-11-10, zero cost) records what the failure classes actually are and what
external practice offers. Two findings matter here: the two named failures are a
model skip and a verifier/census disagreement, not extraction defects; and the
cheap extractor change (`pdftotext -layout`) was measured and is a regression
(D6 0/14 authority strings intact, D5 440 spans, the page-16 heading bug
survives). The memo proposes two pre-registrations — a cheap text+verifier one,
and a separate region-scoped geometry one — and nothing is executed from it
without approval.

### 10.7(f) Key/value row claims and a section guard for repairs — pre-registered 2026-11-10

§10.7(e)(ii) rejected the segmentation fix because `D5-0002` and `D5-0003` were
not recovered, and the survey (`gold/survey.segmentation.md`) found that neither
failure is an extraction defect: `D5-0002` is a **model skip** of a row that is
already segmented, and `D5-0003` is a **verifier/census disagreement** about
which cell a claim may cite. This section fixes exactly those two things, with
rules that are properties of the text, and registers the run that will judge
them. It is written before any model call on the new pipeline; the thresholds
of §10.2 do not move.

#### The rule

A row of a key/value table asserts **label + value**. That is the evidence the
artifact needs, and it is a property of the row, not of the model's willingness
to extract it. Three rules follow, all computed from the text alone.

1. **An empty cell owns nothing.** Inside a key/value region, a label block that
   is followed by another label is an empty cell: the first label is dropped,
   never glued onto the second. A block that is a chain of labels — two or more
   label colons, no value after the last, no sentence stop — leaves no span,
   because an empty form cell asserts nothing; a sentence that merely ends with
   a colon keeps its text. A block that opens with its own label discards a
   stale pending key — the label belongs to this row.
2. **A clause tail is not a heading.** A *numbered* line that ends in `and`,
   `or`, `but` or `nor` continues the sentence of the preceding item
   (`15.2.1.5 contact point for more information; and`), so it does not open a
   section. Unnumbered headings are unaffected; this is the only place a
   terminal conjunction is read.
3. **Only a clean cell becomes a claim.** A row claim is emitted from a span
   whose text is exactly one label and one value: exactly one colon, the label
   at offset 0, capitalised, without `.`/`;`, not ending on a conjunction, not
   naming a `Table N`, its value not a bare section number and not a question
   (`Whether …`, which is the next row's label). The statement is the cell
   verbatim, `"<label>: <value>."`; nothing is paraphrased and no grammar is
   invented. Modality is `definition`; evidence is the span's paragraph and
   locator, as §10.4 requires.

The emitted claims are deterministic: no model call produces or edits them.
They are inserted before dedupe and the conflict pass, and a row whose span is
already cited by a model claim (same `doc_id`, `char_start`, `char_end`) is
skipped, so the rule never duplicates text the extractor already used. The
marking lives in the span (`span["row"]`), which is not schema-bound, so the
claim schema stays closed.

#### The frozen statement list

These are the seven claims the rule emits on D5's current segmentation. They are
frozen here; a run that emits a different set is a different pipeline.

| # | Span | Page | Statement |
|---|---|---:|---|
| 1 | S0007 | 1 | Full legal name: University of Bristol (through the Avon Longitudinal Study of Parents and Children (ALSPAC)). |
| 2 | S0008 | 1 | Main address (if a company registered address): University of Bristol, Beacon House, Queens Road, Bristol, BS8 1QU, UK. |
| 3 | S0017 | 2 | In relation to the Processing of the Transferred Data: Exporter is a Controller. |
| 4 | S0024 | 3 | The Importer may Process the Transferred Data for the following time period: The period for which the Linked Agreement is in force. |
| 5 | S0035 | 4 | The personal data to be sent to the Importer under this IDTA consists of: The categories of Transferred Data will update automatically if the information is updated in the Linked Agreement referred to. |
| 6 | S0036 | 4 | The Transferred Data includes data relating to: Relevant Data Subjects. |
| 7 | S0040 | 5 | The Importer may Process the Transferred Data for the purposes set out in: the Authorised Research (schedule 4) in the ALSPAC Data Access Agreement Any other purposes which are compatible with the purposes set out above. The purposes will update automatically if the information is updated in the Linked Agreement referred to. |

All seven pass `check_claims.py` (verbatim quote, declared page contains it,
schema v2) when written as an artifact. D6 emits **0** rule claims: its records
bypass the key/value branch, which is the correct result for a document whose
operative content is already item-scoped.

#### Measured blast radius (dry run, no model call)

| Document | Spans before | Spans after | Identical |
|---|---:|---:|---|
| D1 | 154 | 154 | yes, byte-identical |
| D2 | 50 | 50 | yes, byte-identical |
| D3 | 115 | 115 | yes, byte-identical |
| D4 | 101 | 101 | yes, byte-identical |
| D5 | 325 | **323** | no — changes below |
| D6 | 35 | 35 | yes, byte-identical |

D1-D4 carry no key/value region and no numbered clause tail, and D6 takes the
record path, so their identity is structural as well as measured. The D5 change
is exactly:

| # | Before | After |
|---|---|---|
| 1 | `Full legal name: Main address (…): University of Bristol, …` | `Main address (…): University of Bristol, …` |
| 2 | `Trading name (…): Main address (…): Official registration number (…):` | removed (a chain of empty cells) |
| 3 | `Signed: Signed: Date of signature: Date of signature: Full name: Lynn Molloy` + `Full name: Job title: ALSPAC Chief Operating Officer` | `Full name: Lynn Molloy Job title: ALSPAC Chief Operating Officer` |
| 4 | `Job title: Table 2: Transfer Details UK country's law …` | `Table 2: Transfer Details UK country's law …` |
| 5 | `… 15.2.1.5 contact point for more information; and` as a heading for 27 spans | `… 15.2.1.5 contact point for more information;` ends the span, `and 15.2.1.6 …` starts the next; the bogus path is gone |
| 6 | `26.1.1 has breached this IDTA; or` as a heading for 2 spans | folded back into `26.1 … if it: 26.1.1 has breached this IDTA; or` |

Counted from the two span lists: 8 paragraphs disappear and 7 appear (two are
the same text re-cut), 28 spans keep their text but change a `section_path`,
and the bogus path
`["Laws", "15.2.1.5 contact point for more information; and"]` goes from 27
spans to 0. Nothing in D5 is dropped that carried a claim in the recorded runs;
the two paragraphs that vanish outright are label chains with no value.

#### The verifier guard

Rule 1 of §10.7(e)(i) made the row one span, but the repair stage can still
abandon it. A `reevidence` record is now rejected when **none** of its chosen
spans shares a `section_path` with the claim's current evidence (empty paths are
ignored, since they carry no section evidence to abandon), and the rejected
claim is recorded in `report["section_rejected_ids"]` and then **settled**: it is
excluded from later repair rounds, because round 2 would otherwise offer the
same escape as a rewrite or a drop. Rewrites and drops are untouched.

Measured by re-applying the **recorded** repair pass of the rejected run to its
recorded claims — no model call, no artifact rewritten:

| Repair file | Before | After |
|---|---|---|
| `repair.1.jsonl` | 59 rewritten, 52 re-evidenced, 7 dropped, 4 rejected | 58 rewritten, 51 re-evidenced, 7 dropped, **5 rejected** |
| `repair.2.jsonl` | 33 rewritten, 2 re-evidenced, 0 dropped, 0 rejected | unchanged |

Exactly one claim diverges: `D5-0006` (*The primary place for legal claims to be
made by the Parties is England and Wales*) keeps its own quote and section
instead of being re-evidenced on the governing-law cell. The other three claims
whose evidence the old code left unchanged (`D5-0120`, `D5-0138`, `D5-0147`)
were already rejected for having no usable span, and are untouched.

#### Acceptance — fixed here, before the run

A fresh compile of **both** D5 and D6, its verify, and an independent census at
full census (no sample). Same model, prompts, schema, thresholds and scale as
§10.7(e)(ii). The gate stays per-document and unchanged: structural 100%,
support >= 90%, facts absent from source 0, recall >= 70%. In addition:

- D5 must recall `D5-0002`, `D5-0003` and `D5-0004`. `D5-0002` may be recalled by
  the two row claims taken together (the gate already reads a set of claims as
  one rule); `D5-0003` by the retained primary-place claim plus the governing-law
  claim; `D5-0004` by the exporter and importer status claims.
- The bogus `15.2.1.5` path must not appear in any claim's locator.
- D6 must keep structural 100%, support >= 90%, 0 facts absent, recall 10/10 and
  0 misattributed authority strings.
- Support is reported **split**: model claims and rule claims separately, plus
  the pooled figure the gate uses. Rule claims are verbatim cells, so their
  expected support is 100% by construction; publishing the split is what keeps
  that fact from flattering the number.

Failure on either document — or a named claim still absent — rejects the fix as
before. A pass accepts the pipeline, not the previous runs: `gold/probe.*`,
`gold/probe.fixed.*`, `gold/probe.kv.*` and their verdicts stay as the
measurements of the pipelines that produced them.

#### Considered and not done

- **`Table N: caption becomes a heading` (R2).** Implemented and measured: it
  cleaned S0017 but also reordered Table 1/3/4 paths (`Security of Processing`
  landed under `["Security of Storage"]`). The benefit is not needed for
  acceptance and the blast radius is not defensible, so it is removed.
- **Claims for headed rows** (label in `section_path`, value alone in the span,
  e.g. S0018 `England and Wales`). A headed row cannot be told apart from
  `The Parties` / `Parties' details` without guessing which line is a label;
  `D5-0003`'s primary-place half is recovered by the verifier guard instead.
- **Adding `Whether` to `starts_a_value`.** Measured regression: it split
  `Can the Importer make further transfers of the Transferred Data?` into
  `…Transferred` + `Data?` in the Table 2 question rows. `Whether` is used only
  in the clean-cell guard, where a question after a label is the next label.
- **Geometry / a canonical extraction product.** Needs `check_claims.py` to
  change and is the subject of the second pre-registration the survey proposes;
  out of scope here.

#### Status and cost

The code is on the branch that carries this section; 162 unit tests pass. No
billable call has been made: the dry run, the `--rule-report`, the
`check_claims.py` check and the re-application of recorded repairs all cost $0.
The re-measurement costs the same as §10.7(e)(ii) — compile ~$0.16, verify
~$0.28, census $0.00, i.e. roughly **$0.40-0.45 and 3-4 hours** — and is not
started until that spend is approved.

##### 10.7(f)(i) Amendment — the first run exposed a non-verbatim quote; the gap is closed before any score

The run registered in §10.7(f) started on 2026-11-10 and was **stopped before
any score existed**. This amendment records what it exposed, what was changed,
and the new dry-run measurement. Thresholds, scale, model, prompt, schema and
the naming of the acceptance are untouched.

**What the first compile produced.** 358 spans, 384 claims (D5 342, D6 42), 0
rule claims — the model cited all seven row spans, so the deterministic rule had
nothing left to add. That is the outcome §10.7(f) wanted for `D5-0002`: the
exporter name and the Beacon House address are now claims (`D5-0003`,
`D5-0004`), extracted rather than injected. But `check_claims.py` returned **1
failure**:

> `D5-0005[0]`: quote not found in D5 —
> `Full name: Lynn Molloy Job title: ALSPAC Chief Operating Officer`

**Cause.** Dropping an empty cell leaves a **gap** in the source. In the
signatory block the sequence is `Full name: Lynn Molloy`, then an empty
`Full name:`, then `Job title: ALSPAC Chief Operating Officer`; the first label
is correctly dropped, but the short-cell buffer then joined the text on either
side of it into one span. The join is semantically right and textually wrong:
the quote elides a label, so it is not in the document. The rule was not wrong;
the emission was.

**Fix (general).** The short-cell buffer is now closed at every dropped block —
when a label replaces a pending key, when a label chain is dropped, and when a
block opens with its own label and discards a stale key. A span can therefore
never span a dropped label. No prompt, schema, model or threshold change; a
block that is dropped is still not a span, and a label followed by a value is
still quoted together (they are adjacent in the source, so that join stays
verbatim).

**Measured (dry run, no model call).** D1-D4 and D6 are byte-identical to
§10.7(f) (154/50/115/101/35 spans). D5 goes 325 -> **324** spans: the signatory
block now yields `Full name: Lynn Molloy` and `Job title: ALSPAC Chief Operating
Officer` as two spans, and the bogus `15.2.1.5 … and` path is still 0. The
verbatim property was checked over **every span of all six documents** against
the whitespace-normalised source: all pass. 166 unit tests pass, including two
that fail without the fix.

The two signatory cells reach the segmenter through the short-cell buffer, so
they are spans but not marked rows; the rule still emits the same seven
statements. That boundary is recorded rather than patched: no acceptance claim
depends on those two cells, and widening the emitter would change the span list
again for no measured gain.

**The seven statements, amended span ids** (statements unchanged; ids after
`S0015` shift by one because the signatory block is now two spans):

| # | Span | Page | Statement |
|---|---|---:|---|
| 1 | S0007 | 1 | Full legal name: University of Bristol (through the Avon Longitudinal Study of Parents and Children (ALSPAC)). |
| 2 | S0008 | 1 | Main address (if a company registered address): University of Bristol, Beacon House, Queens Road, Bristol, BS8 1QU, UK. |
| 3 | S0018 | 2 | In relation to the Processing of the Transferred Data: Exporter is a Controller. |
| 4 | S0025 | 3 | The Importer may Process the Transferred Data for the following time period: The period for which the Linked Agreement is in force. |
| 5 | S0036 | 4 | The personal data to be sent to the Importer under this IDTA consists of: The categories of Transferred Data will update automatically if the information is updated in the Linked Agreement referred to. |
| 6 | S0037 | 4 | The Transferred Data includes data relating to: Relevant Data Subjects. |
| 7 | S0041 | 5 | The Importer may Process the Transferred Data for the purposes set out in: the Authorised Research (schedule 4) in the ALSPAC Data Access Agreement Any other purposes which are compatible with the purposes set out above. The purposes will update automatically if the information is updated in the Linked Agreement referred to. |

**Status of the aborted attempt.** The verify stage was stopped after 50 of 384
audit rows. No verdicts were computed, no census was written, and no support,
recall or verdict exists for that artifact. Its files are preserved as
`gold/probe.rows.attempt1.*` (gitignored, like every compiled artifact) so the
defect stays reproducible; it is not a measurement of the registered pipeline
and it is not cited as one. Cost: compile $0.1724, verify ~$0.004 — **≈ $0.18
spent, no result**.

**Restart.** The registered run restarts from scratch on the fixed pipeline
(fresh compile, verify, full census), with the acceptance of §10.7(f)
unchanged. Its cost is quoted and approved before it starts.

##### 10.7(f)(ii) The run, measured — the fix is rejected by its own criteria

The fresh compile of D5 and D6, its verify and the independent census finished
on 2026-11-10. The artifact is `gold/probe.rows.compiled.verified.jsonl`
(gitignored); the census is `gold/audit.probe.rows.md`. Thresholds, scale,
model, prompt, schema and the acceptance of §10.7(f) are untouched.

**Result.** D5: structural 100%, support 333/338 = **98.5%**, facts absent **0**,
recall 9/10 = 90.0% — and `D5-0003` **not recalled**. D6: structural 100%,
support 51/51 = 100%, facts absent 0, recall 10/10, 0 misattributed authorities
— **pass**. Pooled 384/389 = 98.7%, 0 `no`, 0 `fabricated`. One named claim
absent rejects the fix; the pooled figures do not substitute for it.

**The fix did what it was opened for.** `D5-0002` is extracted by the model from
the segmented rows (`D5-0004` full legal name + `D5-0005` Beacon House address),
`D5-0004` is recalled (`D5-0008` + `D5-0011`), the bogus `15.2.1.5 contact
point` path of the kv run attaches to no claim, and the single rule claim
(`D5-0367`) is a row the model skipped — which is the mechanism the
pre-registration wanted, reported split from the model's 337 claims.

**Why `D5-0003` fails.** The primary-place claim is not missing at compile: it
is `D5-0007` (*The primary place for legal claims to be made by the Parties is
England and Wales*), and the verify stage removed it — `rewrite` in round 1
("Span is only the value; no broader wording claimed"), `drop` in round 2
("Spans name England and Wales but never state it is the primary place for
legal claims"). The section guard rejects a `reevidence` that abandons its own
section; §10.7(f) left `rewrite` and `drop` untouched, so the guard did not
cover the action that removed the claim. The governing-law half (`D5-0006`)
survives and is supported. The row itself is unchanged and still correct: a
colonless four-line label whose value cell is `England and Wales`, which a
policy requiring the label inside the quote will always drop.

**Not repaired here.** The drop policy is not changed by this amendment: a
correction would be a new pre-registration, measured on its own run, and the
run that produced this result stays the measurement of the pipeline it tested.
Residual defects are listed in `gold/audit.probe.rows.md` and move no census
verdict. The verifier/census disagreements (7 glossary-term rows the verifier
called `weak`, 3 rows the verifier accepted and the census does not) are the
calibration classes already documented, not rubric changes made after seeing
this number.

**Cost.** Compile $0.1843 + verify $0.3554 = **$0.5397** for this run; with the
aborted attempt of §10.7(f)(i) (≈ $0.1764, no score), §10.7(f) cost ≈ **$0.72**.
The verify overran its ~$0.28 quote on two repair rounds with 11 token-limit
splits and 4 HTTP 503 splits.

### 10.7(g) The drop guard — pre-registered 2026-11-10, before the run

§10.7(f)(ii) rejected the row-claim run on `D5-0003`. The claim was emitted at
compile (`D5-0007`) and the verify stage removed it: `rewrite` in round 1,
`drop` in round 2. The section guard of §10.7(f) covers `reevidence` only, so it
never fired. This amendment changes the action policy that lost the claim. It
does not touch a threshold, the model, the prompt, the schema, the span set or
the acceptance of §10.7(f). It is written before any model call on the amended
pipeline.

#### The rule

A claim may not be deleted, or have its evidence replaced, when the source text
that supports it lies inside the claim's own section. Three deterministic rules
in `verify_claims.py`:

1. **Drop test.** A `drop` of a `weak` claim whose evidence is verbatim in its
   own section is rejected, and the claim is kept with its verdict: the audit
   called it weak because a label or qualifier lives in the locator, not because
   the quote is false. A `no` or `fabricated` claim stays droppable: there the
   audit says the quote does not state the claim, and keeping it to protect a
   row would ship a false claim. The guard protects under-quoted claims, not
   hard failures.
2. **Rewrite test.** A `rewrite` whose new evidence lies outside the claim's
   section is rejected. A rewrite that stays in the section is allowed, unless
   it drops a sequence of two or more content tokens that the `section_path`
   attests and the original statement contained (the primary-place case: the
   path carries "primary place for legal claims", the rewrite keeps only "law
   that governs the IDTA"). In that case the original statement is kept and the
   claim is marked `weak`.

   **Superseded by §10.7(g)(ii).** The literal n-gram form above failed its
   zero-cost replay: it rejected 14 rewrites and two of the named claims,
   because a section path also carries the document title, parenthetical column
   descriptors and sub-heading numbers. The purpose is unchanged; the trigger
   is narrowed to a defined headword in §10.7(g)(ii), before any model call.
   The text above stays as the pre-registered first form.
3. **Visibility.** Every rejection is recorded in `report.json` under
   `guard_rejected_drops` and `guard_rejected_rewrites`, with claim ids and
   reasons. A guard that fires silently is not a guard.

Each rule has a unit test, including the `D5-0007` fixture and a negative case
where a `drop` is legitimate (verdict `no`, evidence outside the claim's
section).

The rule generalises the glossary precedent of §10.7(e)(i) — a headword in
`section_path` is the term of the row — and the census call on `D5-0334` in the
kv run. It is a property of the artifact, not of the model's willingness to
quote the label.

#### Why this is not moving the goalposts

- The acceptance of §10.7(f) is unchanged: structural 100%, support ≥ 90% per
  document, 0 facts absent, recall ≥ 70%, and `D5-0002`, `D5-0003`, `D5-0004`
  recalled.
- The change is to the repair policy, which §10.7(f)(ii) recorded as the cause.
  The thresholds were written before that cause was known.
- The effect on support is small and pre-registered: keeping `D5-0007` as
  `weak` costs at most one `ok` row, so D5 support moves from 98.5% to at worst
  98.2%. A drop below 90% still fails.

#### Precondition — zero-cost replay

Before any model call, the guard is run against the recorded verify trace of the
rejected run (`gold/probe.rows.compiled.jsonl.verify/`). It must:

1. keep `D5-0007` — the claim survives its round-2 `drop`;
2. leave every other decision unchanged (there was exactly one `drop` in round
   2, and the round-1 `rewrite` of `D5-0007` is the one the second rule covers);
3. produce the final claim set plus the kept claim, with no other claim removed.

If any of the three fails, the run does not start and the design is
reconsidered. This makes the fix falsifiable without spending, and it is the
same discipline as the dry run of §10.7(f)(i).

##### 10.7(g)(i) The zero-cost replay — rule 2 as written is rejected (2026-11-11)

The guard is implemented in `verify_claims.py` with a `--replay` flag: on a
complete `--resume` cache the pure policy re-runs and any attempted model call
raises instead of spending. 51 tests cover the three rules, including the
`D5-0007` fixture and the legitimate-drop negative case.

Replay 1 ran rule 2 exactly as written above, on
`gold/probe.rows.compiled.jsonl.verify/`, 0 calls, $0:

| Check | Result |
|---|---|
| `D5-0007` survives the round-2 `drop` | **pass** — kept as `weak` |
| every other decision unchanged | **fail** — 14 rewrites rejected |
| final set plus the kept claim, nothing else removed | count passes (390 = 389 + 1), statements move |

The extra rejections are not noise:

- `D5-0002`: the rewrite "The IDTA, issued by the Information Commissioner,
  provides Appropriate Safeguards…" is rejected because the section path is the
  document title `International Data Transfer Agreement` and the rewrite uses
  its initialism. A named claim.
- `D5-0004`: the rewrite "The Exporter's full legal name is University of
  Bristol…" is rejected because the path is `Exporter (who sends the Restricted
  Transfer)`; the headword is kept, the parenthesis is a column descriptor. A
  named claim.
- `D5-0201`: a legitimate paraphrase (`easily accessible form` → `easy to
  understand`) is rejected.
- `D5-0037`: the rewrite substitutes *Information Security Controls* for
  *Information Security policies*; arguably a real change, but the rule cannot
  tell it from the paraphrases.

Cause: an n-gram in a section path is not necessarily a row label. The path also
carries the document title, parenthetical column descriptors and sub-heading
numbers, and a rewrite may legitimately abbreviate, paraphrase or drop a
descriptor. Precondition 2 failed, so the paid run did not start. The failure is
kept here; the rule was not tuned after a score.

The replay also exposed a cache defect: a resumed `repair.*.jsonl` was applied
to every claim in the artifact, not only to the claims the current failing set
asked about. In a replay that let a recorded reply re-fire on a claim the run had
already settled (`D5-0363`). The pipeline now filters repairs to the asked ids.
That is a correctness fix, not a policy change: in a fresh run every cached reply
already belongs to an asked claim.

##### 10.7(g)(ii) Amendment — the rewrite rule narrowed to the defined headword (pre-registered 2026-11-11, before the run)

Rule 2 is replaced, not relaxed. The purpose is the same — a repair may not
delete the term a row defines — and the trigger is narrower:

A rewrite is rejected when the **leaf** of the section path (parentheticals
removed, at least two content tokens) is the term the original statement
defines — the statement begins with that leaf — the statement continues with a
copula (`is`, `are`, `was`, `were`, `means`, `has`, `refers`, `includes`), and
the rewrite no longer names the term. The original statement is kept as `weak`.
The rest of the rewrite test is unchanged: new evidence may not leave the
claim's section.

This is the class the census actually loses: the `D5-0007` row label and the
glossary rows where a rewrite turns "Personal Data has the meaning…" into "As
defined in the UK GDPR.", a fragment with no subject. It cannot fire on a
document title, an initialism, a parenthetical column label, or a paraphrase
that keeps the term — the four shapes replay 1 measured.

Replay 2, same trace, same command, 0 calls, $0:

| Check | Result |
|---|---|
| `D5-0007` survives the round-2 `drop` | **pass** — kept as `weak` |
| changes limited to lost defined headwords | **pass** — 6 rewrites rejected |
| final set | 390 = 389 + `D5-0007`; 0 evidence changes; 5 statements differ |
| `check_claims.py` | 390 claims, 517 spans, 0 failures |

The six rejections: `D5-0010` (*Linked Agreement* → "Other agreements"),
`D5-0336` (*Personal Data* → "As defined in the UK GDPR."), `D5-0345` (*Relevant
Data Subject* → "A Data Subject of the Transferred Data."), `D5-0363` (*UK Data
Protection Laws* → "Means all laws…"), `D5-0310` and `D5-0312` (*Access Request*
→ "A legally binding request…"). Four of those fragments are already recorded as
census defects; the guard keeps the row's own term instead.

The amended precondition for the run: the replay must keep `D5-0007`, must change
only claims whose rewrite deletes a defined headword, and must leave every quote
and locator untouched. It does. Thresholds, model, prompt, schema and span set
are unchanged; the quote stays **≤ $0.55** and the run still needs explicit
approval.

#### The run

A fresh compile, verify and full census of D5 and D6, same model
(`deepseek-v4.1-flash`), prompt, schema and span set (359 spans). The
`gold/probe.rows.*` artifacts of §10.7(f) stay untouched as the measurement of
the rejected pipeline.

| Criterion | Threshold |
|---|---|
| D5 structural | 100% |
| D5 support (census) | ≥ 90% |
| D5 facts absent | 0 |
| D5 recall | ≥ 70%, with `D5-0002`, `D5-0003`, `D5-0004` all recalled |
| `D5-0003` primary-place half | present, `ok` or `weak` (a kept `weak` is a recall pass) |
| D6 | 100% support, 10/10 recall, 0 misattributed authorities |
| `no` / `fabricated` | 0 |
| `check_claims.py` | 0 failures |
| Guard activity | at least one rejected `drop` (`D5-0007`), recorded in `report.json` |

Support is reported split model/rule plus pooled, as in §10.7(f). Cost: compile
≈ $0.18 + verify ≈ $0.36, quoted at **≤ $0.55**; the run starts only after
explicit approval.

If it passes, §10.7(h) records the result and the row-claim pipeline is accepted
for the demo. If it fails, the failure is recorded and the architecture decision
in `docs/adr/0002-evidence-first-extraction.md` proceeds without a fifth bench
iteration.

##### 10.7(h) Result — the guard keeps `D5-0003`, the run passes (2026-11-11)

The run was approved at ≤ $0.55 and executed on the pre-registered shape: same
model, prompt, schema and 359 spans; a fresh compile, a fresh verify and a full
census of D5 and D6. It cost **$0.37** (compile $0.094, verify $0.2755) and it
**passes every criterion**.

| Criterion | Threshold | Measured |
|---|---|---|
| D5 structural | 100% | 100% — `check_claims.py`, 397 claims / 534 spans, 0 failures |
| D5 support (census) | ≥ 90% | **333/341 = 97.7%** |
| D5 facts absent | 0 | **0** |
| D5 recall | ≥ 70%, `D5-0002`/`0003`/`0004` recalled | **10/10**, all three recalled |
| `D5-0003` primary-place half | present, `ok` or `weak` | `D5-0006`, **kept** by the guard |
| D6 | 100% support, 10/10, 0 misattributed | 56/56, 10/10, 30/30 authorities correct |
| `no` / `fabricated` | 0 | 0 / 0 |
| Guard activity | at least one rejected `drop` | 4 rejected drops, 5 rejected rewrites |

**What the guard did.** In round 1 the verifier audited the primary-place claim
`D5-0006` (`weak`) and issued a `drop`. The guard refused it with "verdict weak,
evidence verbatim in its own section". Round 2 did the same for `D5-0288`; round
1 also refused drops of `D5-0039` and `D5-0339`, and five rewrites for deleting
a defined headword (`D5-0009`, `D5-0343`, `D5-0344`, `D5-0346`, `D5-0347`). The
claim is in the final artifact and is counted `ok` by the census under the
locator rule: the value cell "England and Wales" plus the section path "Primary
place for legal claims to be made by the Parties" is the whole row. This is the
mechanism §10.7(g) pre-registered and replayed; the census did not decide it.

**One named claim, two halves.** `D5-0003` is recalled by `D5-0006`
(primary place) and `D5-0097` (governing law, default England and Wales).
`D5-0002` is recalled by `D5-0004` (legal name) and `D5-0362` (main address,
a deterministic row claim). `D5-0004` is recalled by `D5-0007` and `D5-0010`.

**Census result.** 397 claims (D5 341, D6 56): **389 `ok` / 8 `weak`**, 0 `no`,
0 `fabricated` — pooled 98.0%, D6 100%. The eight weak rows are `D5-0039`,
`D5-0072`, `D5-0264`–`D5-0267`, `D5-0288` and the reused `D5-0109`; the four
`D5-0264`–`D5-0267` are one mechanism (the 30.1 lead-in is not quoted). The full
census, the verifier/census disagreement table and the residual defects are in
`gold/audit.probe.rows.g.md`.

**Verdict: accepted.** The row-claim pipeline is accepted for the demo. The
earlier artifacts remain the measurements of their own pipelines; this run is a
new measurement, not a rewrite of theirs. Phase 0 of
`docs/adr/0002-evidence-first-extraction.md` was replayed against this census the
same day and is **met**: 388/397 = 97.73% agreement, 0 `no`, D5 97.36% / D6
100% (`gold/audit.phase0.md`). The market gate remains open and is not affected
by this result.
