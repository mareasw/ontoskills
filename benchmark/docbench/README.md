# DocBench (pre-flight)

**Status: representation validated (2026-11-07) and machine extraction validated
(Gate 2, 2026-11-08).** The compiler's claims pass an independent census at
**99.0% evidence support** (499/504), 0 fabrications, 97.6% gold recall, and B2
beats B1 on citation by +20.0 pp automatic / +21.9 pp blind. The
**second-corpus probe (2026-11-09/10) fails, four times**: the first run misses
D6 recall (2/10, disposition cells segmented as headings); the fixed run repairs
D6 (recall 10/10, support 96.1%) and **fails on D5**, where 8 claims define a
term the document does not define because glossary headwords wrap onto two
lines; the key/value fix removes all 8 and lifts D5 to 98.2% support with 0 facts
absent, but still misses `D5-0002` and `D5-0003`, so it is **rejected by its own
pre-registered criteria**. The third pre-registration (`PREFLIGHT.md` §10.7(f))
— deterministic claims read from clean key/value cells, plus a verifier guard
that refuses a re-evidence which abandons the claim's own section — recovers
`D5-0002` and lifts D5 to **98.5% support with 0 facts absent and 9/10 recall**,
but `D5-0003` is emitted at compile and then **dropped by the verify repair
policy**, which the guard (scoped to `reevidence`) does not cover; one named
claim absent means the fix is **rejected** again (§10.7(f)(ii)). The **market
gate is still open**. See
[`RESULTS.md`](RESULTS.md) for the numbers, the manual review, the blind re-score
and the limitations. The corpus and the full gold set stay local; the protocol
and the examples are public.

The claim shape is defined by [`schemas/claim.v2.schema.json`](../../schemas/claim.v2.schema.json) and [`docs/adr/0001-document-first-kernel.md`](../../docs/adr/0001-document-first-kernel.md): a claim carries an `evidence` list, not a single quote, so a rule with an exception or a two-sided conflict can cite every span it needs.

The goal is to test, on a small hand-built corpus, whether a compiled claim layer with per-claim evidence beats full-document reading and RAG on citation accuracy and answer accuracy with citation.

Read the full protocol first: [`PREFLIGHT.md`](PREFLIGHT.md).

## Where it stands

| Gate | Threshold | Measured |
|---|---|---|
| Structural validity of compiled claims | 100% | 504/504 claims, 586/586 spans, 0 failures |
| Evidence support (independent census) | ≥ 90% | **99.0%** (499/504), 0 fabricated |
| Gold-set recall proxy | ≥ 70% | 97.6% (40/41) |
| B2 − B1 citation | ≥ +15 pp | **+20.0 pp** automatic / **+21.9 pp** blind |
| B2 answer vs hand-built B2 | within 5 pp | blind 97.4% (−2.6 pp) |
| Market (interview / design partner) | evidence of demand | **not started** |

Second-corpus probe (`PREFLIGHT.md` §10, per document, 2026-11-09/10):

| Document | Type | Structural | Support | Facts absent | Recall | Verdict |
|---|---|---|---:|---:|---:|---|
| D5 — failed run | contract | 100% | 323/325 = 99.4% | 1 | 7/10 = 70.0% | **fail** |
| D6 — failed run | table-as-content | 100% | 47/51 = 92.2% | 4 | 2/10 = 20.0% | **fail** |
| D5 — fixed run | contract | 100% | 329/354 = 92.9% | 8 | 7/10 = 70.0% | **fail** |
| D6 — fixed run | table-as-content | 100% | 49/51 = 96.1% | 0 | 10/10 = 100% | **pass** |
| D5 — key/value fix | contract | 100% | 329/335 = 98.2% | 0 | 8/10 = 80.0% | **fail** |
| D6 — key/value fix | table-as-content | 100% | 61/62 = 98.4% | 0 | 10/10 = 100% | **pass** |
| D5 — row claims + guard | contract | 100% | 333/338 = 98.5% | 0 | 9/10 = 90.0% | **fail** |
| D6 — row claims + guard | table-as-content | 100% | 51/51 = 100% | 0 | 10/10 = 100% | **pass** |

The probe fails on all four runs, for different reasons. The first run fails D6
recall; the fixed run fixes D6 and fails D5 on "facts absent from source" — 8
glossary claims define a term the document does not define, because two-line
headwords keep only their last line as the section heading; the key/value fix
removes those 8 and takes D5 to 98.2% support with 0 facts absent, but D5 still
does not recall `D5-0002` (the exporter's name and address: segmented, never
extracted) or `D5-0003` (the primary place: quoted in the raw compile, then
re-evidenced away by the quote-only repair), so the fix is **rejected by its own
pre-registered criteria** rather than shipped. D6's evidence in that run is
byte-identical to the fixed run, so its pass is unaffected input, not evidence
for the key/value rule. The row-claim run recovers `D5-0002` (the exporter name
and address) and lifts D5 to 98.5% support, but `D5-0003` is emitted at compile
(`D5-0007`) and then dropped by the verify repair policy — `rewrite`, then
`drop`, neither of which the section guard covers — so `D5-0003` is absent
again and the fix is **rejected** (§10.7(f)(ii)). D6's 35 spans are again
byte-identical, so its pass is a control. The support misses and all four
mechanisms are named in
[`gold/audit.probe.md`](gold/audit.probe.md),
[`gold/audit.probe.fixed.md`](gold/audit.probe.fixed.md),
[`gold/audit.probe.kv.md`](gold/audit.probe.kv.md) and
[`gold/audit.probe.rows.md`](gold/audit.probe.rows.md); the fixes are
pre-registered as `PREFLIGHT.md` §10.7(b) (applied), §10.7(e)(i) (applied,
rejected on measurement, §10.7(e)(ii)) and §10.7(f) (applied, rejected on
measurement, §10.7(f)(ii)); the code is on `main`, none of the fixes is
accepted. All four runs are kept as measured.

Gate 2's thresholds and method were fixed in `PREFLIGHT.md` §9 before the run;
the four amendments that got it there (§9.1–§9.4) each answer a measured defect
and are recorded with the number they moved. The census is
[`gold/audit.run4.md`](gold/audit.run4.md).

## Layout

```
benchmark/docbench/
├── README.md
├── sources.md              # the six documents, URLs, hashes, licences
├── private/                # local copies of source documents (gitignored)
├── compile_claims.py       # span-first compiler: segment -> extract -> validate -> emit
├── verify_claims.py        # audit each claim against its own evidence, repair it, drop only what is unsupported
├── llm.py                  # one OpenAI-compatible call, with the retry policy both stages share
├── gold/
│   ├── schema.json         # v1 schema (single quote + locator), kept for the 2026-11-07 run
│   ├── claims.example.jsonl
│   └── questions.example.jsonl
├── tests/                  # stdlib unittest for the claim model
└── runs/                   # local run outputs (gitignored)
```

## Scripts

```bash
# Validate every claim: verbatim quote (every evidence span), PDF page, JSON schema
python benchmark/docbench/check_claims.py

# Convert a v1 claim file to the v2 evidence-list shape (lossless)
python benchmark/docbench/migrate_claims_v2.py gold/claims.jsonl -o gold/claims.v2.jsonl

# Compile a document into claims (span-first; --estimate costs nothing)
python benchmark/docbench/compile_claims.py --estimate
python benchmark/docbench/compile_claims.py --out gold/claims.compiled.jsonl
python benchmark/docbench/check_claims.py gold/claims.compiled.jsonl

# Compile and verify in one command: audit every claim against its own evidence,
# repair or drop what fails, write <out>.verified.jsonl
python benchmark/docbench/compile_claims.py --out gold/claims.compiled.jsonl --verify

# Verify an existing artifact (resumable; the cache lives in <out>.verify/)
python benchmark/docbench/verify_claims.py \
  --claims gold/claims.compiled.jsonl --resume

# Fix PDF page numbers in place (only when the quote is correct)
python benchmark/docbench/check_claims.py --fix-pages

# Build the minimal Turtle graph (documents, contexts, claims, evidence)
python benchmark/docbench/build_ttl.py --out benchmark/docbench/runs/docbench.ttl

# Inspect the three baseline prompts without calling a model
python benchmark/docbench/run_baselines.py --dry-run

# Run against an OpenAI-compatible endpoint, with no SDK required
python benchmark/docbench/run_baselines.py \
  --backend http \
  --base-url http://localhost:11434/v1 \
  --model <model>

# Run with the Anthropic or OpenAI SDK (requires the SDK in the environment)
python benchmark/docbench/run_baselines.py --backend anthropic --model <model>
python benchmark/docbench/run_baselines.py --backend openai --model <model>

# Score the latest run
python benchmark/docbench/score.py

# Blind re-score: strip the condition label, then compare after unblinding
python benchmark/docbench/build_blind_sheet.py --run "$RUN" \
  --gold benchmark/docbench/gold/questions.jsonl --out "$RUN/blind"
python benchmark/docbench/compare_blind.py --run "$RUN"
python benchmark/docbench/blind_metrics.py --run "$RUN"

# Claim model tests (stdlib unittest, no extra dependencies)
python -m unittest discover -s benchmark/docbench/tests -v
```

`--backend http` works with any OpenAI-compatible server: Ollama
(`http://localhost:11434/v1`), vLLM (`http://localhost:8000/v1`), LM Studio
(`http://localhost:1234/v1`), LocalAI, or a remote compatible provider. If the
server needs a key, set `OPENAI_API_KEY`; local servers usually do not.

The generated graph can be queried with the files in `queries/`. The
`--backend mock` option exists only to test the plumbing; mock answers are
never a real evaluation.

## Baselines

| Condition | Context |
|---|---|
| **B0** | The full document |
| **B1** | Top-5 paragraphs retrieved with BM25 |
| **B2** | The compiled claims for the document, with quote and locator |

All three use the same system prompt, the same question, temperature 0 and the
same JSON output contract. Only the context differs.

## Rules

1. **No quote, no claim.** A claim without at least one verbatim evidence span and a resolving locator is invalid. Evidence is a list: a rule with an exception, or a two-sided conflict, cites every span it needs.
2. **Do not commit source documents.** Download them into `private/` and commit only URLs, SHA-256 hashes, and short quotes used as annotation examples.
3. **One claim per atomic assertion.** Split conjunctions; keep conditions separate.
4. **Same model, same prompt, same output format** across the three baselines.
5. **Blind scoring.** The scorer must not know which baseline produced the answer.

## Metrics

| Metric | Definition |
|---|---|
| Evidence span accuracy | Share of claims whose quote matches the source verbatim |
| Claim precision | Share of annotated claims that are correct and supported |
| Claim recall | Share of gold claims found (obligations weighted highest) |
| Locator accuracy | Share of locators that resolve to the quote |
| Answer accuracy with citation | Share of answers that are correct and cite a supporting quote |
| Correct abstention | Share of unanswerable questions answered `UNKNOWN` |
| Tokens per correct answer | (Input + output tokens) / correct answers |
| Latency p95 | 95th percentile wall-clock time per question |

## How to add a document

1. Download it into `private/` (do not commit it).
2. Record URL, licence, SHA-256 and a one-line rationale in `sources.md`.
3. Annotate 10 claims in `gold/claims.jsonl`, following `schemas/claim.v2.schema.json`.
4. Write 10 questions in `gold/questions.jsonl`: 5 direct, 3 multi-hop/conditional, 2 unanswerable.
5. Run the three baselines and write results into `runs/<date>/`.

## Status

- [x] D1 annotated (10 claims)
- [x] D2 annotated (10 claims)
- [x] D3 annotated (10 claims)
- [x] D4 annotated (11 claims, including the deadline conflict)
- [x] 40 questions written (5 direct, 3 multi-hop, 2 unanswerable per document)
- [x] Minimal Turtle graph builds and parses (41 claims, 767 triples)
- [x] B0/B1/B2 harness builds and dry-runs (120 prompts, ~456k input tokens)
- [x] End-to-end plumbing tested with the mock backend
- [x] OpenAI-compatible HTTP backend tested against a local stub
- [x] B0/B1/B2 run with a real model (`deepseek-v4.1-flash`, 120 calls)
- [x] Scored: automatic triage + manual review of all 120 answers
- [x] Independently re-scored by a reviewer who did not see the condition labels: 117/117 answers agree; B2 − B1 citation delta reproduced at +28.1 pp
- [x] Claim schema v2 (`evidence: [...]`) defined, migrated and tested
- [x] Second corpus annotated: D5 contract + D6 table (20 claims, 16 questions)
- [x] Machine extraction compiled, verified and fully censused on six documents
- [x] Second-corpus probe measured: **fail** — D5 pass, D6 fail (recall 2/10)
- [x] Table-record segmentation (`PREFLIGHT.md` §10.7(b)) written, measured on a fresh D5+D6 run and fully censused
- [x] Fixed run measured: **still fail** — D6 fixed (recall 10/10), D5 fails on 8 facts absent (two-line glossary headwords)
- [x] Key/value table segmentation (`PREFLIGHT.md` §10.7(e)(i)) written and measured: D5 98.2% support, 0 facts absent, but `D5-0002`/`D5-0003` still missed — **rejected** (§10.7(e)(ii))
- [x] Row claims + repair section guard (`PREFLIGHT.md` §10.7(f)) measured on a fresh D5+D6 run: D5 98.5% support, 0 facts absent, 9/10 recall — **rejected**, `D5-0003` emitted at compile then dropped by the verify repair policy, which the guard (scoped to `reevidence`) does not cover (§10.7(f)(ii)); first attempt stopped before any score and preserved
- [ ] Drop/rewrite guard (`PREFLIGHT.md` §10.7(g)) — pre-registered, zero-cost replay pending, paid run only after approval
- [ ] Evidence-first pipeline + public demo (`../../docs/adr/0002-evidence-first-extraction.md`): ≤ $0.05 and ≤ 60 s per 60-page document, first-pass support ≥ 90%
- [ ] Five design-partner conversations (`../../docs/market/beachhead-2026-11.md`)
- [ ] Machine-extracted claims replace the hand-built gold set (the real extraction gate)
- [ ] Go/no-go decision recorded (technical gate passed; market gate open)

The full annotations (`gold/claims.jsonl`, `gold/questions.jsonl`) and the
generated graph (`runs/`) are local and gitignored because they quote
third-party documents. The committed `*.example.jsonl` files show the format.
