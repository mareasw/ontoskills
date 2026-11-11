# ADR 0002 — Evidence-first extraction and a deterministic verifier

- **Status:** Proposed
- **Date:** 2026-11-10
- **Supersedes:** nothing. Extends ADR 0001 and answers the failure recorded in
  `benchmark/docbench/PREFLIGHT.md` §10.7(f)(ii).
- **Deciders:** tech lead
- **Evidence:** `benchmark/docbench/RESULTS.md` (five second-corpus runs),
  `benchmark/docbench/gold/audit.probe.rows.md` (389-row census of the rejected
  run) and `benchmark/docbench/gold/audit.probe.rows.g.md` (397-row census of
  the accepted run)

## What the product is

The product is an **enterprise knowledge base**: every document the company owns
or receives is compiled into claims with verbatim evidence, linked into a graph,
and queried deterministically — SPARQL through the MCP runtime — with a citation
for every answer.

"Contract review", "policy Q&A", "audit evidence pack", "onboarding assistant"
are **views** over that graph: a saved query plus a presentation layer. They are
not separate products, and they must never grow their own ingestion pipeline.
The architecture below exists to make the knowledge base cheap enough to ingest
everything, not to build a better review tool than the incumbents.

This distinction is the line the project must not cross: a review tool edits
documents and competes on Word integration; a knowledge base produces claims and
evidence and competes on being right. The first is a feature market with
distribution already won; the second is the asset.

## Context

Four runs of the second-corpus probe have produced the same shape of result:
support is high (98.5% on D5, 0 fabricated, 0 facts absent) and the pipeline
still misses a named claim. The misses are no longer extraction failures in the
naive sense:

- `D5-0002`: a correctly segmented row the model skipped. Fixed by the row rule.
- `D5-0003`: a claim **written** by the model and then **removed by the verify
  policy**, because the statement contained an element (the label "primary
  place for legal claims") that lives in the section path, not in the quote.
- The census's five `weak` rows are all the same shape: an actor, a qualifier or
  a label that is true of the source but absent from the quote.

The pipeline is built in the wrong order. The model writes a sentence first and
cites afterwards, so the verifier's job is to detect the gap between the
sentence and its evidence. It detects it, and then the repair policy removes the
claim instead of fixing the evidence. That is a structural cost, not a bug to
patch one more time.

The cost profile confirms it: the last run used 132 model calls and $0.54 for
389 claims across two documents, with two audit-repair rounds and hours of wall
time. As a product this is unshippable, whatever the support number says.

## Decision

**Invert the order: the evidence is the input to the statement, and a
deterministic verifier is the gate.**

### 1. Evidence-first generation

The extraction unit becomes a pair `(selection, statement)`:

- `selection`: the span ids the model has chosen as the evidence, from the spans
  the segmenter already produces;
- `statement`: one atomic claim, written **only** from the text of the selected
  spans.

The compiler enforces the constraint mechanically: after normalisation (case,
whitespace, morphology, a closed list of connectives and articles), every
content token of `statement` must occur in the selected spans or in the section
path. A statement with an unattested content token is rejected and retried once
with the offending token named. The model cannot assert an element it did not
select.

This removes the entire class of `weak` rows the census keeps finding, by
construction rather than by repair.

### 2. Deterministic verifier

The LLM audit stops being a pipeline stage. A deterministic verifier runs in
milliseconds and produces `ok | weak | no | fabricated` with a machine-readable
reason:

| Check | Rule | Failure |
|---|---|---|
| Verbatim | Every quote is a substring of the normalised source | `no` |
| Locator | The span exists, the page matches, the section path is a real path | `no` |
| Attestation | Every content token of the statement is in the selected evidence or the section path | `weak` |
| Modality | `must`/`may`/`must not` in the statement is present in the evidence or the section path | `weak` |
| Numbers and dates | Every number, date and defined term in the statement appears verbatim | `no` |
| Section | The evidence lies in the claim's own section (§10.7(g) rule) | `no` |
| Contradiction | Two claims with the same subject and predicate carry incompatible modalities or values | flagged, not dropped |

The first six are hard gates; contradiction is a report, not a verdict, until we
have a precedence rule (ADR 0001, open question 4).

The LLM audit survives only as **sampled QA**: a stratified 10% sample, used to
calibrate the deterministic verifier and to catch what rules cannot see. It never
gates a document.

### 3. One repair pass, with the drop guard

Only `no` and `fabricated` trigger a repair, and only once. `weak` is kept and
reported: a claim whose missing element is attested by the section path is a
locator fact, not a lie. `drop` and `rewrite` are subject to the same section test
as `reevidence`, per §10.7(g); a claim is never silently deleted to raise the
support number.

### 4. Output contract unchanged

The artifact stays schema v2 (`schemas/claim.v2.schema.json`): claims with an
`evidence` list. The graph builder, the MCP runtime and the store do not change.
The pipeline produces the same kind of object at a different cost.

## Targets

These are the acceptance criteria for the demo, not aspirations. Measured on the
fixed six-document eval set, then on the public demo corpus.

| Metric | Current | Target | Why |
|---|---:|---:|---|
| Model cost per 60-page document | ≈ $0.27 (compile + verify, two docs) | **≤ $0.05** | A 30-contract pilot must cost single-digit euros, not hundreds |
| p95 latency per 60-page document | hours (132 sequential calls) | **≤ 60 s** | A consultant tries it in a meeting or not at all |
| First-pass support, no repair | 72% (284/394 at first audit) | **≥ 90%** | Repair must be the exception, not the engine |
| Final support | 98.0% pooled (accepted run) | **≥ 95%** | Keep the measured quality while cutting the cost |
| Fabricated | 0 | **0** | Non-negotiable |
| Deterministic verifier vs. census agreement | not measured | **≥ 95%** on the 397-row accepted artifact, replay only | The verifier replaces the audit; it must earn it |
| Named claims of §10.7(f) | 3/3 (accepted run) | **3/3** | The gate that rejected the last run |
| Cross-document demo questions | 0 | **3/3, each citing claims from ≥ 2 documents** | The demo must prove a corpus index, not a single-file reader |

## Demo

One command ingests a folder, because the unit of the product is the corpus, not
the document:

```
ontoskills ingest docs/ --out kb/      # every PDF/DOCX/TXT in the folder
ontoskills ask "which contracts let us audit the sub-processor?"
```

- local run with a single API key, no upload by default;
- the output is one graph over the whole folder: claims from different documents
  share subjects and land in the same query surface;
- web view: every claim shows its quote, page, section and source document, with
  a copy-citation control;
- **three questions that only a cross-document index can answer**, each answered
  through the existing MCP/SPARQL runtime and citing the claims it used:
  1. *Which suppliers have a breach-notification window shorter than 72 hours?*
     (answer assembled from several contracts, one row per contract);
  2. *Where does this DPA conflict with our own retention policy?*
     (a conflict between a received document and an internal one);
  3. *What must we tell a sub-processor before they can use a new AI vendor?*
     (an obligation chain that crosses a contract, an annex and a policy);
- export JSONL, TTL, and a CSV evidence pack for an audit file.

The demo corpus is **public and redistributable**: 12–15 documents from SEC
EDGAR exhibits, gov.uk model contracts, EU standard contractual clauses and
public tender documents, with the licence checked per document. It must contain
at least three document types (contract, policy, annex or tender) so the
cross-document questions are real, not staged. No private corpus, no IDTA, no
NARA text in the public demo.

## Rollout

| Phase | Work | Exit criterion | Cost |
|---|---|---|---|
| 0 | Replay the deterministic verifier on the 397-claim accepted artifact; no model calls | **Met, 2026-11-11**: 388/397 = 97.73% agreement, 0 `no` (no false rejection), D5 97.36% / D6 100%; `D5-0006` survives the drop guard (`PREFLIGHT.md` §10.7(g)(ii), §10.7(h)). Tool: `benchmark/docbench/verify_deterministic.py`; measurement: `benchmark/docbench/gold/audit.phase0.md` | $0 |
| 1 | Evidence-first prompt + token attestation on D5 and D6 | **Met, 2026-11-11**: compile-only first pass, D5 296/315 = 93.97%, D6 48/49 = 97.96%, 0 facts absent, 10/10 recall with all three named claims, $0.145 (`PREFLIGHT.md` §10.8, `gold/audit.phase1.md`) | $0.145 |
| 2 | CLI `ingest` + web claim view + public multi-document corpus | The demo ingests a folder and all three cross-document questions answer with citations from ≥ 2 documents | engineering only |
| 3 | Five design-partner documents (memo: `docs/market/beachhead-2026-11.md`) | A consultant uses the pack in a real engagement | pilot |

Phase 0 is a precondition: if the deterministic verifier cannot reproduce the
census on data we already have, the architecture is wrong and we do not spend on
Phase 1.

### Phase 0 result (2026-11-11)

The bar is met, with two qualifications that shape Phase 1. Agreement is
**97.73%** (388/397) and the verifier emits **0 `no`**, so it rejects nothing the
census accepts. Its nine misses are one-sided: 7 of the census's 8 `weak` rows
are called `ok`, all of them because the operative element sits in an unquoted
lead-in or sibling span (`D5-0039`, `D5-0072`, `D5-0109`, `D5-0264`–`D5-0267`,
`D5-0288`); the other 2 are glossary rows called `weak` (`D5-0315`,
`D5-0318`). The attestation tolerance (25% of content tokens) is calibrated on
this artifact, but it holds on both halves of D5 (97.7% / 97.1%) and on D6
(100%), and the boundary band is empty (accepted rows ≤ 24% unattested, flagged
rows ≥ 30%). Modality was demoted from a verdict to a note: as a verdict it cost
8 false `weak` and caught none of the census `weak`.

So the deterministic verifier can replace the audit as the **hard gate**
(verbatim, locator, page, section, numbers), but not as the judge of `weak`: the
unquoted lead-in is exactly the class the LLM audit exists for. Phase 1 keeps the
ADR's sampled QA (10% stratified) for support, not the verifier alone.

### Phase 1 result (2026-11-11)

The bar is met on both documents, at $0.145 against a $0.30 ceiling. The run is
a true first pass: compile only, no repair, no drop. D5 is 296/315 = **93.97%**,
D6 is 48/49 = **97.96%**; 0 facts are absent from the source, no claim is `no` or
`fabricated`, recall is 10/10 on both documents with the three named claims
(exporter name and address, governing law and primary place, both parties
Controllers), and the prompt is kept.

The four new rules did what they were written for: the primary-place fact is
emitted at first pass with the correct section path, the Mandatory Clauses
exception keeps the full `5.1.1 to 5.1.3` range that §10.7(g) had narrowed, and
the 104 definition claims name their headword. They did not close the unquoted
lead-in: 16 of the 20 `weak` rows are a sub-item whose parent span supplies the
actor, the modal or the condition, and the weak rate rose from 2.0% to 5.5%
because atomic splitting multiplies that exposure. The deterministic verifier
caught 3 of the 20 and missed all 16 lead-in rows, reproducing Phase 0's
one-sided bias.

That is the Phase 1 answer to the open question: the LLM audit stays, the
verifier stays the hard gate, and the lead-in class is a **structural** debt —
the fix is to attach the parent span when a clause is split, not another prompt
paragraph. Phase 2 proceeds with the claim graph, the CLI, the web view and the
public corpus; a further prompt attempt would need its own pre-registration.

## Risks

- **Token attestation too strict.** Legal paraphrase is normal ("the Parties shall"
  vs "each Party must"). Mitigation: inflection matching (shared stem of four
  characters) plus a 25% paraphrase allowance, measured on the accepted artifact
  in Phase 0: **0 false rejections**, 2 false `weak` (0.5%), 97.73% agreement
  (`benchmark/docbench/gold/audit.phase0.md`).
- **PDF extraction.** Page and section fidelity depends on the extractor. Keep
  page + section paths (ADR 0001, open question 2); do not promise character
  offsets.
- **Long documents.** Token budget per chunk and the number of chunks set the
  cost. Chunk size stays a measured parameter, not a constant.
- **Model drift.** The verifier is deterministic but the compiler is not. Keep a
  pinned model for the eval set and record the version in the manifest, as the
  bench already does.
- **Multilingual.** The public corpus and the first pilots are English and
  Italian; the attestation normaliser must handle both before Phase 3.

## Non-goals

**Editing and negotiation.** No redlining, no clause generation, no tracked
changes, no Word round-trip, no "accept this suggestion" button. The views are
read-only over the graph: they select, order and cite claims; they never write
back into a document. A review view that starts editing has become the
incumbent's product and lost the only thing we have — that it cannot say
something the source does not say.

**Advice and autonomous action.** No legal advice, no decisions taken on a
document, no sending, filing or accepting anything on the user's behalf. The
product produces verifiable claims and evidence; the professional keeps the
judgement. This boundary is also the liability boundary and must be stated in
the pilot contract.

**A separate pipeline per view.** Every view is a saved query. If a use case
needs a new ingestion stage, it is a different product, not a feature.

## Open questions

1. Does the LLM audit disappear entirely, or stay as a sampled QA instrument?
   Phase 0's agreement number decides.
2. Do we need bbox coordinates for the web view, or are page + section enough
   for a first demo? Start with page + section.
3. Claim identity across document versions (ADR 0001, open question 3) becomes
   urgent at the first pilot with a contract repository.
4. How do we price the per-contract cost inside a consultancy subscription
   without metering surprises? Decide after the first three pilots.
