# DocBench (pre-flight)

**Status: pre-flight.** This directory is a protocol and a set of examples, not a working benchmark yet.

The goal is to test, on a small hand-built corpus, whether a compiled claim layer with per-claim evidence beats full-document reading and RAG on citation accuracy and answer accuracy with citation.

Read the full protocol first: [`PREFLIGHT.md`](PREFLIGHT.md).

## Layout

```
benchmark/docbench/
├── README.md
├── sources.md              # the three documents, URLs, hashes, licences
├── private/                # local copies of source documents (gitignored)
├── gold/
│   ├── schema.json         # JSON schema for claims and questions
│   ├── claims.example.jsonl
│   └── questions.example.jsonl
└── runs/                   # local run outputs (gitignored)
```

## Scripts

```bash
# Validate every claim: verbatim quote, PDF page, JSON schema
python benchmark/docbench/check_claims.py

# Fix PDF page numbers in place (only when the quote is correct)
python benchmark/docbench/check_claims.py --fix-pages

# Build the minimal Turtle graph (documents, contexts, claims, evidence)
python benchmark/docbench/build_ttl.py --out benchmark/docbench/runs/docbench.ttl
```

The generated graph can be queried with the files in `queries/`.

## Rules

1. **No quote, no claim.** A claim without a verbatim quote and a resolving locator is invalid.
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
3. Annotate 10 claims in `gold/claims.jsonl`, following `schema.json`.
4. Write 10 questions in `gold/questions.jsonl`: 5 direct, 3 multi-hop/conditional, 2 unanswerable.
5. Run the three baselines and write results into `runs/<date>/`.

## Status

- [x] D1 annotated (10 claims)
- [x] D2 annotated (10 claims)
- [x] D3 annotated (10 claims)
- [x] D4 annotated (11 claims, including the deadline conflict)
- [x] 40 questions written (5 direct, 3 multi-hop, 2 unanswerable per document)
- [x] Minimal Turtle graph builds and parses (41 claims, 767 triples)
- [ ] B0/B1/B2 run
- [ ] Scored
- [ ] Go/no-go decision recorded

The full annotations (`gold/claims.jsonl`, `gold/questions.jsonl`) and the
generated graph (`runs/`) are local and gitignored because they quote
third-party documents. The committed `*.example.jsonl` files show the format.
