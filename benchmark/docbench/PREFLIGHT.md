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
