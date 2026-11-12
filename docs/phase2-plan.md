# Phase 2 — the first end-to-end knowledge base

- **Status:** complete and measured (real run 2026-11-12: 5,680 claims, $1.27).
  The structural exit criterion is met — all three questions cite at least two
  documents. The retrieval gate added during Phase 2 is **not** met; see
  *Retrieval* below.
- **Date:** 2026-11-11 (engineering), 2026-11-12 (run)
- **Depends on:** ADR 0001 (document-first kernel), ADR 0002 Phase 0
  (deterministic verifier) and Phase 1 (evidence-first prompt), both accepted.
- **Exit criterion (ADR 0002):** `ingest` compiles a folder, and all three
  cross-document demo questions answer with citations from **at least two
  documents**.

## What Phase 2 is, and is not

Phase 2 is **engineering only**. The extraction prompt is the one accepted in
Phase 1, byte for byte; changing it is a new experiment with its own
pre-registration. No threshold is moved after a number is seen, and no claim is
made about extraction quality from the demo corpus: the demo's acceptance
criterion is structural (two documents per answer), not a score. Retrieval *is*
scored, against a gold set and a gate committed before the first measurement;
see *Retrieval* below.

The one known extraction debt that came from Phase 1 — **16 of the 20 `weak` rows
were sub-items whose parent span supplied the actor, the modal or the condition**
("unquoted lead-in") — was addressed here, structurally and without touching the
prompt: a list item now carries the span that opens its list as `context`
evidence, with its own locator. Ten `weak` remain, each documented in
`RESULTS.md`; none is a fabricated statement, and `ask` does not answer them.

A second defect surfaced with the same repair: a PDF running header
(`L 119/29`, `OJ L, 12.7.2024`) was taken for a heading, so everything below it
carried a page number where the article should be. Section paths are now repaired
after compilation (`sections.py`), on spans and claims that no longer feed a model
call, so the frozen prompt and the parity-tested segmenter are untouched.

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
| `sections.py` | repairs section paths after compilation: page furniture is not a heading |
| `prompt.py` | the Phase 1 `SYSTEM`, conflict prompt, prompt hash |
| `llm.py` | one OpenAI-compatible call, six attempts with backoff |
| `compile.py` | chunking, cache/resume, concurrency, JSON repair, claim build, dedupe, row claims, conflict pass |
| `verify.py` | six deterministic rules; `ok` / `weak` / `no` + notes; quantities vs structural references |
| `store.py` | manifest, JSONL, vectors, Turtle graph, evidence CSV, atomic writes |
| `ask.py` | BM25 ranking, optional local-embedding fusion, cross-document grouping, deterministic tensions |
| `vector.py` | pinned MiniLM embedder (offline), cosine, reciprocal rank fusion |
| `eval.py` | hit / recall / MRR over a gold set, and the pre-registered gate |
| `web.py` | self-contained read-only HTML view with copy-citation |
| `cli/documents.py` | `ontocore ingest`, `ontocore ask`, `ontocore view` |

### Guarantees kept structural

- **The compiler never writes a quote.** The model returns span ids; the quote
  and the locator are copied from the span the segmenter produced.
- **The verifier is deterministic.** No model, no network, replayed in
  milliseconds. It is a hard gate on the artifact (`weak` / `no` rows are
  written and shown), not a judge of usefulness.
- **The answer is deterministic.** `ask` ranks with BM25 over statement, actor,
  conditions and quotes. When the KB carries `vectors.jsonl` it also ranks with a
  pinned local embedding model and fuses the two by reciprocal rank: same KB and
  same model give the same answer, and neither path calls a paid API. A question
  that cannot be answered returns no citations rather than a guess.

## Knowledge-base layout

```
kb/
  manifest.json      name, model, prompt hash, counts, cost, licences
  documents.jsonl    one row per document (title, type, licence, SHA-256)
  spans.jsonl        every span the segmenter emitted
  claims.jsonl       schema v2 claims
  verifier.jsonl     one verdict per claim
  rejected.jsonl     claims refused at construction, with the reason (only if any)
  vectors.jsonl      header line + one embedding per claim (`ingest --semantic`)
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
ontocore ingest . -o kb --resume --semantic # + local vectors, no network
ontocore ask "How quickly must a personal-data breach be notified?" --kb kb
ontocore ask "…" --kb kb --no-semantic      # BM25 only, ignore vectors.jsonl
ontocore view --kb kb --questions-file questions.txt
python examples/demo-corpus/eval_retrieval.py --kb kb [--semantic]
```

`ingest` prints the estimate and stops on `--estimate`; it never spends money
without being asked to compile. `ask` and `view` never call a paid model. `ask`
fuses the local ranking automatically when `vectors.jsonl` is present and the
optional runtime imports, and prints one dim line and stays on BM25 when it is
not. The eval script prints hit@12, recall@12 and MRR@12, the gate line, and
exits non-zero when the gate fails.

## Cost

Measured, not guessed: Phase 1 cost **$0.145** for 364 claims (96,164 input,
217,937 output tokens at $0.15 / $0.60 per million). The demo corpus was
estimated at 514,414 input / 1,167,719 output tokens by the dry run and cost
**$1.27** in the real run: **1,004,607 input / 1,856,731 output tokens** for
5,680 claims, 4,803 spans, 556 PDF pages, 375 chunks and 14 conflict passes.
The AI Act alone is 114 of the 375 chunks. The planning figure was 1.9x low on
input; it is left as it was and the manifest carries the measured numbers — a
rebuild from cache reports them too (`$0.000` only when nothing was cached).

## Retrieval

The demo's structural criterion says an answer cites two documents. It says
nothing about whether the *right* claim was retrieved, so retrieval is measured
separately, against a gold set written and committed **before** the baseline was
run: 20 questions, 41 expectations, 14 of 14 documents, 10 questions with
expectations in more than one document. An expectation is a
`(document, verbatim fragment)` pair, the fragment at least 40 characters and
copied from a claim's own quote, so the metric survives re-segmentation and
cannot be gamed by ranking.

The gate (not moved after the number was seen): **hit@12 ≥ 18 of 20** and
**mean recall@12 ≥ 0.60**; MRR@12 is reported but not gated.

| configuration | hit@12 | recall@12 | MRR@12 | gate |
|---|---:|---:|---:|---|
| BM25 | 13/20 (0.650) | 0.467 | 0.467 | **FAIL** |
| BM25 + local MiniLM, RRF k=60 | 16/20 (0.800) | 0.592 | 0.588 | **FAIL** |

The hybrid closes three of the seven baseline misses and regresses none, and
still lands two hits and 0.008 recall short. Two causes, both diagnosed from the
claims: a singular/plural mismatch (`voucher` vs `vouchers`) means `tokens` gives
a relevant claim no lexical score at all, and reciprocal rank fusion then buries
a semantic-only hit; the other three misses ask for two or three specific rules
at once, and twelve slots fill before all of them appear. The next step is a new
measurement — light morphological normalisation and a fusion that does not
drown a semantic-only match — not a re-tuning of this one.

The local model is MiniLM (`all-MiniLM-L6-v2`, pinned by revision), 384
dimensions, 22 MB for 5,680 claims, 702 s to embed the corpus once on CPU and
~105 s to load in a fresh process. `ask` works without it.

## Risks and how they are handled

| Risk | Handling |
|---|---|
| Gateway 503s during a long run | cache every reply; `--resume`; a document whose chunks keep failing is skipped, the rest is written, and the command exits non-zero, so `--resume` retries only what is missing |
| A chunk's reply outlives the client timeout | every call streams; the 600 s ceiling is per socket read, and a stream that ends without `stop`/`length` is retried instead of being parsed into half a claim array |
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
- [x] Paid ingest run on the demo corpus (approved, 2026-11-12)
- [x] Three cross-document questions validated on the real artifact
- [x] `RESULTS.md` / `README.md` updated with the demo numbers
- [x] List items carry their lead-in as `context` evidence
- [x] Page furniture removed from section paths
- [x] Structural references noted, unquoted quantities refused at construction
- [x] 20-question gold set and retrieval gate, pre-registered
- [x] Retrieval measured (BM25 and hybrid) — **gate not met**, diagnosis recorded
- [ ] Light morphological normalisation and a fusion that keeps semantic-only hits
- [ ] PR merged with the four CI checks green
