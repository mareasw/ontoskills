# The ranker: why we lose 27 points, and the ladder that closes them

The pilot's row is 63,94 % coverage. Two free measurements say that the facts are
in the knowledge base and that the claims carrying them are already retrieved —
and that we choose badly among them:

| measurement | value | what it means |
|---|---|---|
| ten claims chosen at best, each fact's candidates drawn from its 100 best lexical carriers (`oracle.py`) | **91,16 %** | the representation is not the bottleneck |
| ten claims chosen at best, no candidate restriction (E0, depth all) | 97,88 % | same, as a loose bound |
| ten chosen at best among the lexical **top 100**, chosen without a candidate restriction beyond the pool (E0, dev) | **87,63 %** | the pool the ranker already has is sufficient for most of the gap |
| what we return today (dev half) | 63,59 % | selection is worth ~24 points at fixed volume and pool |
| the floor, at our volume (~5 000 characters) | 71,1 % | a chunk layer with more text is not the target |

That is the diagnosis in one line: **the loss is selection, not representation,
and not primarily candidate generation.** The claims are in the top 100 of a
lexical ranking; a chooser that knew the facts would reach 87,6 % from that same
pool, at the same k and the same volume.

Everything here is scored by `benchmark.retrieval.metrics`, through the same
`returned_text` path `score.py` uses: one quote per claim, joined, cut at
k = 10. A candidate ranker is therefore comparable with the published row by
construction, not by a similar-looking script. The ceiling numbers are in
`runs/oracle.json`, the depth curve in `runs/e0-dev.json`.

## 1. The diagnosis, in numbers

Published row and the two oracles, all on the same 192 questions with gold
facts (`oracle.py`, 0 $, no model call):

| what | coverage | characters per question |
|---|---|---|
| what we return today: 10 claims, the first quote of each | **63,94 %** | 5 097 |
| those same 10 claims, every quote they carry | 68,40 % | 7 114 |
| the best *single* claim per fact, over all 9 104 verified claims | 54,79 % | — |
| **ten claims chosen at best, one quote each** | **91,16 %** | 5 097 |
| ten claims chosen at best, every quote | 92,97 % | 7 114 |
| the floor, at our volume (~5 000 characters) | 71,1 % | ~4 800 |
| the floor, unconstrained | 92,4 % | 45 885 |

Read the first and fourth rows together: the pool contains claims that carry
91 % of the facts, we return claims that carry 64 %. No tokeniser change, no
verifier change, no rebuild is needed for those 27,22 points to exist.

Two bounds deserve a note, because they differ by 6,7 points and the difference
is a choice:

- **91,16 %** is the tight bound: each fact's ten candidates are drawn from its
  100 best lexical carriers. It is the number a ranker whose pool is a lexical
  ranking can be compared with.
- **97,88 %** is the unconstrained greedy ten over all 9 104 claims. It is
  reachable only by a chooser that also looks outside any lexical pool.

The pilot uses the tight one as its headline, because the read path's pool *is* a
lexical ranking.

**The representation is better than the floor's, at equal volume.** 91,16 %
against 71,1 % on ~5 000 characters is the claim the pilot can make about the
claim layer independent of any ranker — and it is the reason to fix the ranker
rather than abandon the layer.

**Returning every quote of the claims we already choose is worth 4,46 points**
for 2 017 more characters. That is a real but small lever, and it changes the
row's shape, so it is a labelled extra row, never a silent substitution (§7).

## 2. The depth curve, and what it rules out

E0 (`rank.py`) rebuilds the pool with a declared BM25 — statement plus first
quote, k1 0,9, b 0,4 — and asks: *if the ten claims were chosen perfectly inside
the lexical top N, what would we get?* Dev half, 96 questions, 0 $.

| pool | ceiling within the pool | facts whose single best carrier is in the pool |
|---|---|---|
| top 10 | 65,60 % | 56,97 % |
| top 20 | 73,74 % | 63,43 % |
| top 50 | 82,92 % | 70,98 % |
| **top 100** | **87,63 %** | 76,68 % |
| top 500 | 94,55 % | 88,85 % |
| all 9 104 | 97,88 % | 100 % |

At N = 10 the pool is exactly what the ranker returns, so the curve starts at
that ranker's own coverage (65,60 % on dev, against the product's 63,59 %) —
a check that the harness measures the same thing the pilot does. From there it
rises steeply: **the top 100 already contains enough to reach 87,6 %**.

That is the number the plan is built on, and it changes the order of the repairs:

| hypothesis | measurement | verdict |
|---|---|---|
| the claims are not in the knowledge base | oracle ceiling 91,16 % | **false** |
| the representation is too coarse | ceiling at our volume beats the floor at our volume, 91,16 vs 71,1 | **false** |
| volume alone explains the gap | the floor needs 45 885 characters to reach 92,4 %; we return 5 097 | **partial** — it explains the floor's number, not ours |
| the field weights are the whole story | product 63,94 vs naive BM25 on the same shape 59,06–63,53 (§3) | **false** — the product's ranker is already the best lexical variant tested |
| candidate generation is the binding constraint | top 100 ceiling 87,63 at dev; we are at 63,59 | **false for the first 24 points** — it becomes true near 87,6 |
| the port is the problem | Python 418 ms vs Rust 3,5 ms, same ids (G1) | **false** — latency, not selection |
| the verifier is dropping the good claims | the oracle's pool *is* the verifier's `ok` set, 9 104 claims | **false** |

## 3. The lexical numbers, in the shape the pilot scores

A caveat that cost a documented inconsistency to find: a coverage number depends
on *which* quotes are returned, so BM25 variants must be compared at the same
shape. On the published shape — one quote per claim — the product's ranker is
not beaten by any naive variant:

| ranker on the same published shape | coverage (192 questions) |
|---|---|
| the product: field weights, stem 7, stopwords, first quote | **63,94 %** |
| BM25, quote only | 59,06 % |
| BM25, all quotes concatenated | 58,96 % |
| BM25, statement + first quote | 63,53 % |
| BM25, statement + the first quote twice | 61,28 % |

And when every quote is returned, the product is 68,40 % against 66,75–69,25 %
for the same naive variants. So field re-weighting is not the 27-point lever: it
is worth at most a point, and the product already has it.

The lesson is in the shape, not in the ranking: 63,94 → 68,40 comes from
returning more text, and 63,59 → 87,63 comes from choosing better.

## 4. Hypotheses, each stated so it can fail

- **H1 — selection.** The right claims are in the top 100, but a per-claim score
  cannot pick ten that *jointly* cover the facts: the top ten are ten paraphrases
  of one fact, or ten claims about the same section. *Falsified if* a
  diversity-aware selection over the same scores gains < 2 points on dev.
- **H2 — scoring.** Within the top 100, the order is poor because BM25 does not
  see paraphrase: the claim that carries the answer ranks 40th, not 1st.
  *Falsified if* a dense or cross-encoder rerank of the same 100 gains < 2
  points over H1's selection on dev.
- **H3 — locality.** The facts are carried by claims adjacent in the graph to the
  ones the lexicon finds (same section, same document path, `conflicts_with`).
  *Falsified if* expansion from the top 10 gains < 1 point on dev.
- **H4 — pool depth.** Ten claims from the top 100 cannot carry more than 87,6 %
  *without* gold knowledge, so the last 4 points to the tight ceiling need
  deeper candidates. *Tested only after* H1 and H2 plateau above 80 %.

H1 and H2 are expected to combine: a better selection (H1) applied to a better
order (H2). H3 is the differentiator a plain vector RAG cannot copy.

## 5. The ladder, E0–E5

Each experiment is a named ranker in a registry, scored on **dev only**, and
recorded as a JSON file under `runs/rankers/<name>-dev.json`. A ranker is not a
script that prints; it is an entry that another measurement can rerun. Every rung
keeps k = 10 and one quote per claim, so the row's shape does not move.

| # | change | what it tests | cost | acceptance |
|---|---|---|---|---|
| **E0** | none — the depth curve above | pool depth (done) | 0 $ | done: selection is binding for the first 24 points |
| **E1a** | greedy set cover over the query's terms inside the top 100: pick the claim that adds the most uncovered query tokens (idf-weighted), ten times | H1 | 0 $ | ≥ 2 points over 63,59 on dev |
| **E1b** | MMR over the same list with λ swept on dev; per-document cap | H1 | 0 $ | kept only if it beats E1a |
| **E2** | dense rerank of the top 100 (`e5-large-v2`, `passage:` statement + first quote, `query:` question), then E1a's selection on the fused order | H2 | 0 $, CPU | ≥ 2 points over E1a on dev |
| **E3** | fusion: RRF of the BM25 and dense orders before selection, weight swept on dev | whether the two disagree usefully | 0 $ | kept only if it beats E2 |
| **E4** | graph expansion: same-section and `conflicts_with` neighbours of the top claims added to the pool, then E2's scoring | H3 | 0 $ | ≥ 1 point over E2 on dev |
| **E5** | cross-encoder rerank of the top 50 (`bge-reranker-base`, ONNX, CPU) | whether a pairwise scorer beats a bi-encoder | 0 $, CPU, measured | only if E1–E4 plateau below 75 |

Stop rule: the ladder stops at the first rung that reaches the target band. The
target is a band, not a number to hit: **75–80 %** coverage at k = 10 and one
quote per claim, which is what a real chooser can reach against a ceiling that
knows the facts. A rung that lands below 70 is reported as a negative result, not
tuned until it passes.

**E1a is first because it is the cheapest and the most Rust-portable**: it is a
deterministic greedy over integers, it needs no model, no vector and no new
artifact, and it can be ported to the read path without an ADR. If E1a alone
moves the number by a large part of the 24 points, the dense path waits.

### E2's declared encoding, fixed before it is measured

- Model: `intfloat/e5-large-v2`, revision `f169b11e`, 1024 dimensions — the same
  model the pilot already serves on 8091 for GraphRAG and LightRAG. Our ranker
  using a different model would make the comparison against those two ambiguous.
- Claim text embedded: `passage: ` + statement + the first quote. One text per
  claim, no per-field vectors, so scoring one candidate is one dot product.
- Query: `query: ` + the question, no expansion before E2.
- Scope: the top 100 of the lexical ranking are reranked, not the whole corpus.
  If E2 wins, the same vectors also allow a global dense retrieval, which is a
  separate rung (H4) and a separate cost.
- Storage: ids + `float32` matrix, 9 104 × 1024 = 37,3 MB. This is an **index**,
  not a cache: §5 rule 5 counts it in the artifact, and the row says so.
- Throughput: measured on a 200-claim sample first, then extrapolated, because
  the sidecar has only been timed on long community reports (0,35–0,6 vectors/s)
  and claim-sized inputs are a different regime. Expected 15–40 min on CPU; if
  the sample says otherwise, the estimate is replaced before the full run.
- Determinism: the matrix is written once and read by every later experiment;
  the file's digest goes in the run record.

### What is deliberately not in the ladder

- **No query-time model call.** Every rung is local and 0 $ at query time. A
  rung that needs a paid call is a different product and a different budget line.
- **No LLM judge, no answer synthesis.** The pilot measures evidence, and adding
  a generator would make the row incomparable with GraphRAG's `local`.
- **No fitting on the 200 questions.** E1–E5 see dev; the test half is read once.

## 6. The split, fixed before the first experiment

`benchmark/layer/splits.py`, salt `ontoskills-ranker-v1`: 100 dev, 100 test, cut
by the SHA-256 of `salt:qid`, so the order of the selection file cannot decide
the halves. The split is written to `runs/split.json` and its digest is part of
the record.

The rule, in one sentence: **E1–E5 read dev; the chosen ranker is run on test
once; the published table reports both numbers and says which is which.**

A ranker that is changed after looking at test invalidates the test number, and
the document says so rather than publishing the better of two looks.

## 7. The gates a ranker must pass before its row is published

1. **G-R1 — paired dev win.** Coverage on dev beats the current ranker with a
   paired bootstrap interval (10 000 resamples, `interval.py`) that excludes 0.
2. **G-R2 — test read once.** The test number is produced by the ranker frozen
   by G-R1, committed by hash, and never re-tuned afterwards.
3. **G-R3 — the row is what the server answers.** The MCP must return the same
   claim ids, position by position, as the ranker being scored (G1 of §10,
   extended to the new ranker). A quality row the read path cannot serve is a
   benchmark result, not a product result, and must be labelled as such.
4. **G-R4 — zero cost and zero network at query time.** No paid call, no socket.
   Measured in an empty network namespace, as G8 already does.
5. **G-R5 — latency.** `documents_ask` p95 ≤ 300 ms on the pilot artifact,
   release build. E2–E5 add a query embedding and a dot product over 100
   candidates; the budget is checked per rung, not assumed at the end.
6. **G-R6 — determinism.** Two runs on the same artifact produce byte-identical
   rankings; ties broken by claim id.
7. **G-R7 — no artifact rewrite.** The ranker reads `claims.jsonl` and, if it
   needs it, the vectors it wrote itself; it never recompiles the knowledge base,
   so a ranker change costs 0 $ and no rebuild.

**G-R3 is the hard one, and it is an architectural decision, not a test.** The
current read path is Rust with no model inside: it has no way to embed a query.
So the ladder splits in two at that boundary:

- **Lexical rungs (E1a, E1b, E4's lexical part, E3's BM25 half) port to Rust as
  they are.** They are the only rungs that can be published without touching the
  ADR.
- **Dense rungs (E2, E3, E5) need a query encoder in the read path.** If they
  win, the price is an ADR 0004 and an ONNX encoder loaded from disk: no network,
  no API, CPU only, model file counted in the artifact and its size published.
  If the encoder cannot meet G-R5 on this machine, the honest outcome is that the
  improvement stays a benchmark row and the product keeps the lexical ranker —
  written down, not hidden.

Nothing here is allowed to become "we publish a number the MCP cannot answer".

## 8. What the published table will look like

One primary row per system, unchanged in shape: evidence, k = 10, one quote per
claim, 192 questions with gold facts, paired intervals against the current
ranker. Additions, each labelled:

| row | why it exists |
|---|---|
| `ontoskills` (ranker v2) | the primary row: the frozen ranker, dev and test numbers, the split's digest |
| `ontoskills`, every quote | the 4,46-point lever of §1, at 7 114 characters, as its own row |
| `vector-rag-floor` | unchanged, still the measurement of how easy the corpus is |

The claim that may be written in public: *the same knowledge base, the same
quotes, a different selection, +X points with an interval that excludes zero on
held-out questions.* The claim that may not be written: SOTA, "beats BM25", "non
inferiority", or any comparison of coverage across different volumes without
saying the volume.

## 9. Costs

| item | cost | when |
|---|---|---|
| E0–E5, dev and test, all rungs | **0 $** | now |
| claim embeddings (E2) | 0 $, 15–40 min CPU, measured on a sample first | after E1a/E1b |
| reranker model (E5) | 0 $, model download only | only if needed |
| a held-out ERB slice to confirm the winner is not slice-specific | 2–4 $ projected, needs approval | after the test number is frozen |
| GraphRAG `global` on the 12 corpus-level questions | already budgeted | when the main run finishes |
| LightRAG full row | 13–18 $ projected, 12–23 h, needs approval | after the ladder |

The ladder itself cannot spend money, which is the point: every rung is a
deterministic transformation of artifacts already paid for.

## 10. Competitors: what the comparison will be able to say

The real comparison is with systems that build a semantic layer over the same
documents, not with the floor. For each, the plan records what would make a row
legitimate and what it would cost; no row is written before its run.

| system | what it does | eligible on these terms | cost to a row |
|---|---|---|---|
| GraphRAG `local` | entity graph + community reports, answers by local search | yes, same corpus, same model, embeddings served on 8091 | build measured; 200 questions running |
| GraphRAG `global` | map-reduce over community reports | yes, but a different query shape (corpus-level) | same build, query cost only |
| LightRAG `mix` | dual-level graph + vector retrieval | yes | 13–18 $ projected, needs approval |
| Nano-GraphRAG | minimal GraphRAG, same idea at small scale | yes if it ingests a folder and takes the model | small, to be measured |
| RAPTOR | recursive summary tree over chunks | yes, no graph | embedding + summary calls, to be measured |
| HippoRAG | personalized PageRank over an entity graph | yes | extraction + embeddings, to be measured |
| Cognee | graph + vector pipeline with its own ontology | yes | to be measured |

Our advantage, if the ladder works, is not "a better model" — it is that the
compiled layer answers with **verified claims and locators**, at 0 $ per query,
and the plan's job is to make the selection worthy of it. If the selection cannot
beat the floor at equal volume, the finding is that a claim layer without a dense
retriever is not competitive, and that is what gets published.

## 11. The abstention track, separately

The pilot's `abstention_rate` is 0 % on the eight `info_not_found` questions. A
threshold chosen on those eight is a leak, so the gate lives on its own track:
choose the rule and its threshold on the 4 dev questions, evaluate once on the 4
test questions, report both numbers and the rule. It is not part of the ranker
ladder and it does not change any coverage number; it changes whether a citation
list is returned at all. A ranker that returns excellent claims for an
unanswerable question is still wrong, and the two failures are reported
separately.

## 12. Order of work

1. E0 — done, free: selection is binding for the first 24 points.
2. E1a — greedy query-term coverage on the top 100, then E1b MMR. Both free,
   both Rust-portable. **This is the first rung that can ship.**
3. E2 — claim embeddings, 0 $, checkpointed; measure throughput on a sample
   first.
4. E3, E4 — fusion and graph expansion, dev only.
5. E5 — only if the ladder plateaus below 75.
6. Freeze the best ranker, run test once, write the row and its interval.
7. If dense wins: ADR 0004, ONNX encoder in `ontomcp`, G1 parity, G-R5 latency.
   If it does not: ship the lexical rung, publish the negative dense result.
8. Only then the PR merge, the final report, and any public comment — with the
   link to `main` and the numbers above.
