# ADR 0002 — Evidence-first extraction and a deterministic verifier

- **Status:** Proposed
- **Date:** 2026-11-10
- **Supersedes:** nothing. Extends ADR 0001 and answers the failure recorded in
  `benchmark/docbench/PREFLIGHT.md` §10.7(f)(ii).
- **Deciders:** tech lead
- **Evidence:** `benchmark/docbench/RESULTS.md` (four second-corpus runs),
  `benchmark/docbench/gold/audit.probe.rows.md` (389-row census)

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
| Final support | 98.7% pooled | **≥ 95%** | Keep the measured quality while cutting the cost |
| Fabricated | 0 | **0** | Non-negotiable |
| Deterministic verifier vs. census agreement | not measured | **≥ 95%** on the 389-row artifact, replay only | The verifier replaces the audit; it must earn it |
| Named claims of §10.7(f) | 2/3 | **3/3** | The gate that rejected the last run |

## Demo

One command, one document, one visible result:

```
ontoskills extract contract.pdf --out claims.jsonl --ttl contract.ttl
```

- local run with a single API key, no upload by default;
- web view: every claim shows its quote, page and section, with a copy-citation
  control;
- three canned questions answered through the existing MCP/SPARQL runtime, each
  answer citing the claims it used;
- export JSONL, TTL, and a CSV evidence pack for an audit file.

The demo corpus is **public and redistributable**: 12–15 documents from SEC
EDGAR exhibits, gov.uk model contracts, EU standard contractual clauses and
public tender documents, with the licence checked per document. No private
corpus, no IDTA, no NARA text in the public demo.

## Rollout

| Phase | Work | Exit criterion | Cost |
|---|---|---|---|
| 0 | Replay the deterministic verifier on the 389-claim artifact; no model calls | ≥ 95% agreement with the census; `D5-0007` survives the drop guard | $0 |
| 1 | Evidence-first prompt + token attestation on D5 and D6 | First-pass support ≥ 90%, 3/3 named claims | ≤ $0.30 |
| 2 | CLI subcommand + web claim view + public corpus | The demo runs end to end on a document we can redistribute | engineering only |
| 3 | Five design-partner documents (memo: `docs/market/beachhead-2026-11.md`) | A consultant uses the pack in a real engagement | pilot |

Phase 0 is a precondition: if the deterministic verifier cannot reproduce the
census on data we already have, the architecture is wrong and we do not spend on
Phase 1.

## Risks

- **Token attestation too strict.** Legal paraphrase is normal ("the Parties shall"
  vs "each Party must"). Mitigation: lemmatisation, a closed connective list, and
  a measured false-rejection rate on the existing artifact before Phase 1.
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

Redlining, negotiation, legal advice, autonomous actions on documents. The
product produces verifiable claims and evidence; the professional keeps the
judgement. This boundary is also the liability boundary and must be stated in
the pilot contract.

## Open questions

1. Does the LLM audit disappear entirely, or stay as a sampled QA instrument?
   Phase 0's agreement number decides.
2. Do we need bbox coordinates for the web view, or are page + section enough
   for a first demo? Start with page + section.
3. Claim identity across document versions (ADR 0001, open question 3) becomes
   urgent at the first pilot with a contract repository.
4. How do we price the per-contract cost inside a consultancy subscription
   without metering surprises? Decide after the first three pilots.
