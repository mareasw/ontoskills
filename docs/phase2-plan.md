# Phase 2 — the first end-to-end knowledge base

- **Status:** in progress (engineering complete, paid run pending approval)
- **Date:** 2026-11-11
- **Depends on:** ADR 0001 (document-first kernel), ADR 0002 Phase 0
  (deterministic verifier) and Phase 1 (evidence-first prompt), both accepted.
- **Exit criterion (ADR 0002):** `ingest` compiles a folder, and all three
  cross-document demo questions answer with citations from **at least two
  documents**.

## What Phase 2 is, and is not

Phase 2 is **engineering only**. The extraction prompt is the one accepted in
Phase 1, byte for byte; changing it is a new experiment with its own
pre-registration. No threshold is moved after a number is seen, and no claim is
made about extraction quality from the demo corpus: the demo has a structural
acceptance criterion (two documents per answer), not a score.

The one known extraction debt comes from Phase 1 and is deliberately not
addressed here: **16 of the 20 `weak` rows were sub-items whose parent span
supplied the actor, the modal or the condition** ("unquoted lead-in"). The fix is
structural — attach the parent span to the split — and belongs to the segmenter,
not to another prompt iteration. Phase 2 records it; Phase 3 fixes it.

## Architecture

The product pipeline lives in `core/src/documents/` (package
`compiler.documents`). The benchmark under `benchmark/docbench/` keeps frozen
copies, because its accepted artifacts must stay reproducible. A parity test
(`core/tests/test_documents_segment.py`) fails if the production segmenter
drifts from the frozen one on the same text.

| Module | Role |
|---|---|
| `model.py` | `Document`, manifest loading, SHA-256, stable doc ids |
| `extract.py` | PDF (`pdftotext`), DOCX (`soffice`), HTML (`bs4`, stdlib fallback), text |
| `segment.py` | span-first segmentation with locators; product copy of the validated segmenter |
| `prompt.py` | the Phase 1 `SYSTEM`, conflict prompt, prompt hash |
| `llm.py` | one OpenAI-compatible call, six attempts with backoff |
| `compile.py` | chunking, cache/resume, concurrency, JSON repair, claim build, dedupe, row claims, conflict pass |
| `verify.py` | six deterministic rules; `ok` / `weak` / `no` + notes |
| `store.py` | manifest, JSONL, Turtle graph, evidence CSV, atomic writes |
| `ask.py` | BM25 ranking, cross-document grouping, deterministic tensions |
| `web.py` | self-contained read-only HTML view with copy-citation |
| `cli/documents.py` | `ontocore ingest`, `ontocore ask`, `ontocore view` |

### Guarantees kept structural

- **The compiler never writes a quote.** The model returns span ids; the quote
  and the locator are copied from the span the segmenter produced.
- **The verifier is deterministic.** No model, no network, replayed in
  milliseconds. It is a hard gate on the artifact (`weak` / `no` rows are
  written and shown), not a judge of usefulness.
- **The answer is deterministic.** `ask` is BM25 over statement, actor,
  conditions and quotes; no model is called. A question that cannot be answered
  returns no citations rather than a guess.

## Knowledge-base layout

```
kb/
  manifest.json      name, model, prompt hash, counts, cost, licences
  documents.jsonl    one row per document (title, type, licence, SHA-256)
  spans.jsonl        every span the segmenter emitted
  claims.jsonl       schema v2 claims
  verifier.jsonl     one verdict per claim
  graph.ttl          documents, contexts, claims, evidence, conflicts
  evidence.csv       claims flattened for a spreadsheet
  text/<doc>.txt     the extracted text the citations point into
  view.html          static, read-only presentation
  cache/<doc>/*.json model replies, for `--resume`
```

`text/<doc>.txt` is not decoration: it is what the verifier checks every quote
against, and what the user opens when a citation looks wrong.

## The demo corpus

Fourteen public documents in `examples/demo-corpus/`, five types:

- **contract** — MSC Core Terms; Mid-Tier Core Terms.
- **schedule** — Mid-Tier Schedule 20 (Processing Data).
- **regulation** — EU SCCs (2021/914); GDPR; AI Act.
- **guidance / framework / standard** — UK AI Playbook; NIST CSF 2.0; NIST AI
  RMF 1.0; TNA contractual records; TNA accounting records; UK Cyber Security
  Standard; Summary of the Cloud Security Principles.
- **tender** — Annex A5, draft framework contract.

Every entry has a public URL, a verified licence (OGL v3.0, EU reuse, or US
public domain) and a SHA-256 in `manifest.json`. `fetch.sh` downloads the bytes
and refuses a hash mismatch. **Binaries are not committed.**

The IDTA is deliberately absent: it sits inside the consolidated Model Services
Contract schedules and is not redistributable on these terms. The schedules are
excluded whole rather than trimmed. See `examples/demo-corpus/sources.md`.

### The three questions

1. How quickly must a personal-data breach be notified, and to whom?
   *MT_SCH20 (48 hours) · GDPR (72 hours) · EU_SCC · EU_TENDER_A5*
2. How long may contractual records be kept?
   *TNA_CONTRACTS (six years) · TNA_ACCOUNTING · GDPR storage limitation ·
   MT_SCH20 retention*
3. What must a supplier do when it uses a sub-processor for personal data?
   *MT_SCH20 · EU_SCC · GDPR · MSC_CORE*

Questions 1 and 2 are expected to raise a **tension**: two documents state
different numbers for the same topic. The answer reports both citations and
refuses to pick a winner; precedence is a later phase, and only with a rule.

## Commands

```bash
cd examples/demo-corpus && ./fetch.sh

ontocore ingest . -o kb --estimate          # no API calls
ontocore ingest . -o kb --resume            # the paid run
ontocore ask "How quickly must a personal-data breach be notified?" --kb kb
ontocore view --kb kb --questions-file questions.txt
```

`ingest` prints the estimate and stops on `--estimate`; it never spends money
without being asked to compile. `ask` and `view` never call a model.

## Cost

Measured, not guessed: Phase 1 cost **$0.145** for 364 claims (96,164 input,
217,937 output tokens at $0.15 / $0.60 per million). The demo corpus is
**514,414 input / 1,167,719 output tokens** by the dry run — **4,803 spans**
over **546 PDF pages**, plus three DOCX and one HTML document — for an estimated
**~$0.78**. The AI Act alone is 114 of the 375 chunks. The real figure is
recorded in `manifest.json` after the run, never inferred afterwards.

## Risks and how they are handled

| Risk | Handling |
|---|---|
| Gateway 503s during a long run | cache every reply; `--resume`; `failed` calls are an error, not a silent partial artifact |
| A chunk's reply outlives the client timeout | one reply is returned whole (no streaming); the per-attempt timeout is 600 s, measured against a 6,132-token chunk that took 175 s |
| A document silently changes upstream | SHA-256 in the manifest; `fetch.sh` and `ingest` both refuse a mismatch |
| HTML chrome becomes claims | extractor drops `nav/header/footer/aside/form` and feedback widgets; segmenter drops boilerplate phrases |
| Page numbers are unstable | page ranges only for published PDFs; DOCX documents carry section paths and offsets, not pages |
| Model drift | model id and prompt hash recorded in the manifest |
| A demo question cites one document | `ask` and `view` print a warning; the exit criterion is checked per question |
| The verifier passes a paraphrase | `weak` is not `ok`; the view shows the verdict next to the claim |

## Non-goals (unchanged from ADR 0001/0002)

No editing, redlining, negotiation or Word round-trip. No legal advice, no
decisions taken on a document, no sending or filing. The views are read-only
over the graph.

## Checklist

- [x] Product pipeline in `compiler.documents`
- [x] CLI `ingest`, `ask`, `view` registered
- [x] Verifier adapted to the KB layout
- [x] Static view with page / section / URL / copy-citation
- [x] Deterministic BM25 answerer with cross-document grouping and tensions
- [x] Demo corpus manifest, sources, fetch script (14 documents, hashes verified)
- [x] Schema v2 accepts stable doc ids (`^[A-Za-z][A-Za-z0-9_]*-\d{4}$`)
- [x] Tests: text, model, segmenter parity, compile, verify, ask, store, web, CLI
- [x] Core suite green
- [ ] Paid ingest run on the demo corpus (needs approval)
- [ ] Three cross-document questions validated on the real artifact
- [ ] `RESULTS.md` / `README.md` updated with the demo numbers
- [ ] PR merged with the four CI checks green
