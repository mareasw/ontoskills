# Retrieval benchmark

Public benchmarks, one metric layer, one statistical protocol. The protocol is
[`PREFLIGHT.md`](PREFLIGHT.md) and it is the document that governs everything
here; this file is only the operator's page.

Nothing in this directory measures our product's own corpora except the locator
check, which is a property test over compiled claims, not a question set. Nobody
writes questions: the gold is public and citable.

## What each file is

| file | what it does | command |
|---|---|---|
| `PREFLIGHT.md` | the protocol: claims, metrics, statistics, phases, criteria fixed in §11, Phase-0 record in §12 | — |
| `adapters.py` | six public datasets, normalised to one `Question`/`Benchmark` shape | `--check` |
| `metrics.py` | ranking metrics, evidence matching, answer-fact coverage, bootstrap/Wilcoxon/Holm, MDE | imported |
| `baselines.py` | Lucene BM25 over one or several fields, and the published-number reproduction | `--reproduce` |
| `dense.py` | B2/B3/B4: a pinned bi-encoder, RRF fusion and a cross-encoder rerank, with a content-addressed embedding cache | `--build`, `--stats` |
| `locator.py` | property test: every compiled claim's quote must be at its cited offset | `--check` |
| `partition.py` | the committed dev/holdout split and its digest | `--build`, `--verify` |
| `runner.py` | one dataset × one system × one split → artifact with per-question receipts | see below |
| `summarize.py` | the Phase-1 table from the run artifacts: spread, paired Δ, MDE, Holm | `--json` |
| `partitions/` | the committed splits, one JSON per dataset | do not edit by hand |
| `artifacts/` | Phase-0 evidence: instrument check, published-number reproduction | do not edit by hand |
| `runs/` | run outputs (created on demand) | — |

The retrieval suite is `benchmark/tests/test_retrieval_{locator,metrics,partition,runner,baselines,dense,summarize}.py`,
115 tests, no network and no key: `python3 -m pytest benchmark/tests/test_retrieval_*.py`.
The locator tests skip themselves when the compiled corpora are absent, which is
the case in CI — those corpora are derived artifacts and are not in the repo.

## The four commands that matter

```bash
# 1. every adapter reads its gold without loss
python3 benchmark/retrieval/adapters.py --check --json benchmark/retrieval/artifacts/instrument-check.json

# 2. the metric layer reproduces a published number (≈90 s)
python3 benchmark/retrieval/baselines.py --reproduce --json benchmark/retrieval/artifacts/reproduce-scifact.json

# 3. the split still describes the datasets
python3 benchmark/retrieval/partition.py --verify

# 4. one number
python3 benchmark/retrieval/runner.py --dataset scifact --split dev
```

Systems: `bm25` (S0/B1), `dense` (B2), `hybrid` (B3, RRF k = 60), `hybrid-rerank`
(B4, cross-encoder over the fused top 50). The dense systems need the GPU and the
model once; after that the embedding cache makes a run cheap:

```bash
python3 benchmark/retrieval/dense.py --dataset scifact --build   # embed + cache
python3 benchmark/retrieval/dense.py --dataset scifact --stats   # measured truncation share
python3 benchmark/retrieval/runner.py --dataset scifact --split dev --system hybrid
```

`--json` writes an artifact; without it the runner still prints the table and
writes `runs/<dataset>-<system>-<split>.json`.

## Rules this harness enforces on itself

- **The holdout is scored once.** `--split holdout` is for Phase 4. Every run
  records the partition digest it used, so a result can be traced to the exact
  split it saw.
- **A partition is verified before every run.** If the dataset changed, the run
  stops instead of scoring a split that no longer exists.
- **A missing metric is named, not zeroed.** Datasets without `answer_facts` have
  no AnswerFactCoverage, and the artifact lists it under `missing_metrics`.
- **Ties are broken by id**, so two runs are bit-identical and the determinism
  claim is about the system, not about Python's dict order.
- **Scoped questions never see outside their scope.** ContractNLI clauses,
  QASPER paragraphs and RAGBench sentences are ranked within their own document;
  IDF still comes from the whole collection, which is how within-document
  retrieval is measured everywhere else.

## Dependencies and where things land

`pip install -r benchmark/requirements.txt` adds `numpy`, `scipy` and
`snowballstemmer` to the existing benchmark requirements. Datasets stream from
the Hugging Face Hub; the cache is `~/.cache/ontoskills-bench` (override with
`ONTOSKILLS_BENCH_CACHE`). ContractNLI's original 65 MB zip — the only release
that keeps the evidence spans — is downloaded there once.

No API key at scoring time. The lexical systems are pure CPU and rebuild their
index from text; the dense ones need a GPU for the first encode of a corpus, then
read a content-addressed cache of the embeddings (model revision + token cut +
every document's text, so it cannot be stale).

## Known limits, stated rather than discovered later

- mMARCO Italian ships its 3.4 GB passage collection on demand
  (`mmarco_it(collection=True)`); `--check` validates only the query side by
  default and says so.
- EnterpriseRAG-Bench is the heavy corpus: 511,958 documents. The first BM25 build
  takes **~10 minutes and 16 GB of RAM**; every later run reuses a cached index
  (**~4.5 minutes, 11 GB**). The cache lives in
  `~/.cache/ontoskills-bench/index` and is **5.5 GB** for ERB — a key over every
  document, so it is never stale, and safe to delete at any time. `--limit` only
  shortens the question list; the index is always the whole corpus, because a
  baseline scored against a truncated corpus is not the baseline.
- The handle is `ONTOSKILLS_BENCH_WORKERS` (default: 8, capped at the CPU count);
  below 2,000 documents the index is built serially, because a process pool costs
  more than it saves there.
- Dense coverage is bounded by the hardware, and the protocol says so before any
  number: at the measured 4.4 documents/second, EnterpriseRAG-Bench (511,958
  documents) projects to **32 hours** and mMARCO Italian (8,840,000) to **23
  days** on this machine. Neither is run here; §13.5 of the protocol carries the
  arithmetic and the consequence for the non-inferiority claim.
- `--stats` reports the share of documents longer than the 512-token cut on a
  deterministic sample, because a truncated dense baseline is a statement about
  the first 512 tokens and should say so.
- The 30 frozen internal questions are a development-exposed regression check.
  They are never a gate and never enter this directory's numbers.
