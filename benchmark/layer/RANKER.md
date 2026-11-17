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
| the pool spends its slots on too few documents | 28 documents in the top 100, largest share 16,2 %, the gold document present for 85,4 % of questions; capping the pool at 2 claims per document raises its ceiling by 1,55 points, to 89,18 % | **false** — the documents are the right ones |

## 2.1 The first rung: +7,6 points, and where it stops

E1 (`select.py`) keeps the product's own pool — top 100 by the product's ranker —
the same k = 10 and the same one-quote shape, and changes only *which* ten of the
hundred are returned. Dev half, 0 $:

| selector | coverage | characters (median) | reference |
|---|---|---|---|
| `plain` — the pool cut at ten, what the product returns | 63,59 % | 5 088 | the baseline |
| `cover` — greedy over the question's own terms, IDF-weighted | 71,14 % | 4 912 | +7,55 pp |
| `mmr-l0.5` — relevance minus redundancy, no cap | 71,20 % | 4 343 | +7,61 pp |
| `mmr-l0.3` | 71,00 % | 4 236 | |
| `mmr-l0.5-c4` | 70,91 % | 4 343 | |
| `section_best` — best claim per section | 67,07 % | 4 418 | rejected |
| `doc_rr` — round-robin over documents | 66,97 % | 4 475 | rejected |

The paired interval on dev, questions resampled together (`interval.py`):

| comparison | difference | 95 % interval |
|---|---|---|
| `cover` − `plain` | **+7,6 pp** | [+5,6; +9,6] |
| `mmr-l0.5` − `plain` | **+7,6 pp** | [+6,2; +9,1] |

Two things in the table matter as much as the gain. **It is not volume**: `cover`
returns *fewer* characters than `plain` (4 912 against 5 088) and still covers
more facts. And **it stops at 71**, sixteen points under the pool's ceiling: two
different definitions of redundancy agree, and structure-based diversity
(section, document) is worse. So the ten claims are no longer paraphrases of each
other, but the pool's *order* is still BM25's, and the claim that carries the
fact is often not in the part of the order the chooser can reach.

That is H2, and it is what E2 is for: the same pool, the same selectors, a
different order.

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
  → **confirmed**: 63,59 → 71,14, +7,6 pp [+5,6; +9,6].
- **H2 — scoring.** Within the top 100, the order is poor because BM25 does not
  see paraphrase: the claim that carries the answer ranks 40th, not 1st.
  *Falsified if* a dense or cross-encoder rerank of the same 100 gains < 2
  points over H1's selection on dev.
  → **half true**: the dense order gains 2,1 pp [+0,6; +3,6]; the cross-encoder
  loses 1,9 pp. The order is worth two points, not the fourteen the pool holds.
- **H3 — locality.** The facts are carried by claims adjacent in the graph to the
  ones the lexicon finds (same section, same document path, `conflicts_with`).
  *Falsified if* expansion from the top 10 gains < 1 point on dev.
  → **falsified**: +0,23 pp [+0,02; +0,5], under its gate.
- **H4 — pool depth.** Ten claims from the top 100 cannot carry more than 87,6 %
  *without* gold knowledge, so the last 4 points to the tight ceiling need
  deeper candidates. *Tested only after* H1 and H2 plateau above 80 %.
  → **falsified**: retrieving across all 9 104 claims at depth 3 000 gains
  0,14 pp at 24× the cost.

H1 and H2 combine as expected, and stop where they stop: **a better selection
plus a better order is worth 9,6 points, and nothing in this ladder is worth
another one.** H3 was the differentiator a chunk layer cannot copy, and the
measurement says our graph does not currently differentiate: the neighbourhood is
where the bi-encoder already looks.

## 5. The ladder, E0–E5

Each experiment is a named ranker in a registry, scored on **dev only**, and
recorded as a JSON file under `runs/rankers/<name>-dev.json`. A ranker is not a
script that prints; it is an entry that another measurement can rerun. Every rung
keeps k = 10 and one quote per claim, so the row's shape does not move.

| # | change | what it tests | cost | acceptance |
|---|---|---|---|---|
| **E0** | none — the depth curve above | pool depth (done) | 0 $ | done: selection is binding for the first 24 points |
| **E1a** | greedy set cover over the query's terms inside the top 100: pick the claim that adds the most uncovered query tokens (idf-weighted), ten times | H1 | 0 $ | **done: 71,14 %, +7,6 pp [+5,6; +9,6]** |
| **E1b** | MMR over the same list with λ swept on dev; per-document cap | H1 | 0 $ | **done: 71,20 % at λ 0,5, +7,6 pp; no gain over E1a** |
| **E2** | dense rerank of the top 100 (`e5-large-v2`, `passage:` statement + first quote, `query:` question), then E1a's selection on the fused order | H2 | 0 $, GPU, measured | **done: 73,21 %, +2,1 pp [+0,6; +3,6] over E1a — frozen** |
| **E3** | fusion: RRF of the BM25 and dense orders before selection, weight swept on dev | whether the two disagree usefully | 0 $ | **done: 72,71 %, −0,5 pp, rejected** |
| **E4** | graph expansion: same-section and `conflicts_with` neighbours of the top claims added to the pool, then E2's scoring | H3 | 0 $ | **done: 73,44 %, +0,2 pp, under the 1-point gate; rejected** |
| **E5** | cross-encoder rerank of the top 50 (`ms-marco-MiniLM-L-6-v2`, CPU) | whether a pairwise scorer beats a bi-encoder | 0 $, CPU, measured | **done: 71,29 %, −1,9 pp [−3,3; −0,6] and 13,5 s per question; rejected** |

Stop rule: the ladder stops at the first rung that reaches the target band. The
target is a band, not a number to hit: **75–80 %** coverage at k = 10 and one
quote per claim, which is what a real chooser can reach against a ceiling that
knows the facts. A rung that lands below 70 is reported as a negative result, not
tuned until it passes.

**E1a was first because it is the cheapest and the most Rust-portable**: it is a
deterministic greedy over integers, it needs no model, no vector and no new
artifact, and it can be ported to the read path without an ADR. It moved a third
of the 24 points and then stopped, which is why E2 exists.

### What every rung measured

All of it on dev, one quote per claim, k = 10, 0 $ of model spend, through
`select.py`, which scores with the published metric in the published shape:

| rung | what changed | dev coverage | chars | verdict |
|---|---|---:|---:|---|
| the product | BM25, the pool cut at ten | 63,59 % | 5 088 | the baseline to beat |
| **E1a** `cover` | which ten, greedy over the question's terms | **71,14 %** | 4 912 | +7,6 pp [+5,6; +9,6] |
| **E1b** `mmr-l0.7` / `l0.5` | which ten, relevance minus redundancy | 71,43 / 71,35 % | 4 401 | same as `cover`, no gain |
| **E2** `dense-cover` | the order, then `cover` | **73,21 %** | 5 122 | +2,1 pp [+0,6; +3,6] over `cover` |
| E2 `dense-plain` | the order only, cut at ten | 65,28 % | 5 272 | the dense order alone is worth 1,7 |
| E2 `dense-cover`, `passage:` | the query prefix a library without one has | 71,16 % | 5 034 | `query:` is worth 2,1 pp |
| E2 `dense-cover`, depth 500 / 1 000 | a bigger pool | 73,37 / 73,03 % | 5 398 | no gain over 100 |
| **E3** `rrf-cover` | fuse the two orders | 72,71 % | 5 084 | −0,5 pp vs E2, rejected |
| **E4** `expand-cover` | section and conflict neighbours of the dense head | 73,44 % | 5 128 | +0,2 pp [+0,02; +0,5], under the 1-point gate |
| E4 `global-cover` | dense over all 9 104 claims, cut at 3 000 | 73,35 % | 5 454 | 1 140 ms/q for +0,14 pp, rejected |
| **E5** `rerank-cover` | cross-encoder over the head of the fused order | 71,29 % | 5 186 | −1,9 pp [−3,3; −0,6], rejected |
| E5 latency, 50 pairs | `ms-marco-MiniLM-L-6-v2` | — | — | 13,5 s median on CPU, 16,0 s p95 |
| labelled row | E2's ten claims, every quote | **76,18 %** | 7 115 | +2,97 pp for +39 % volume |

Four things in that table are the result.

**1. Every mechanism plateaus at 73.** Better selection (+7,6), a dense order
(+2,1), fusion (−0,5), graph expansion (+0,2), whole-corpus retrieval (+0,14),
a cross-encoder (−1,9): five different signals, one ceiling. The pool's ceiling
is 87,63 % and the artifact's is 91,16 %, so the last fourteen points are not a
matter of trying one more order. What every rung shares is that it scores a
claim against the *question*; what the ceiling requires is scoring a claim
against a *fact* the question implies but does not contain. That is a generator's
job, not a ranker's, and it is outside this ladder and its zero-dollar budget.

**2. The cross-encoder is worse, not merely expensive.** `ms-marco-MiniLM-L-6-v2`
is trained to prefer a fluent passage that answers a web question; this corpus is
contract and incident text, and the claim quote is the sentence the claim stands
on, not the answer to a question. It reorders the head towards prose and away
from the fact, and the interval says that is not noise: [−3,3; −0,6]. It also
costs 13,5 s per question on CPU against a 300 ms gate — 45× over — and 276 ms
median on a GPU the read path does not have. A rung that loses quality and blows
the latency budget is rejected twice over.

**3. The graph expansion is real and tiny.** Section and conflict neighbours of
the dense head add 0,2 pp with an interval that excludes zero, and the
neighbour-only pool reaches 50 % on its own. So the graph carries signal — but
the dense order already covers it: cutting the expanded pool back to its best 100
returns exactly E2's number, which means every neighbour ranks below the claims
the retriever found. The mechanism is not adopted, and that is a measurement
about our graph as much as about rankers: section adjacency adds nothing a
bi-encoder does not already have.

**4. The candidate generator was never the constraint.** Retrieving across all
9 104 claims instead of the lexical top 100 moves the number by 0,14 pp at 24×
the cost. Everything the pilot needs is inside the pool the product already
builds; the defect was always which ten of it came back.

**At one volume, the floor and the new ranker are level.** Under the pilot's own
5 000-character budget — the `score.py --max-chars` mechanism that produced the
floor's 71,1 % — the frozen ranker reaches **70,62 %** and the lexical rung 69,39 %
against the product's 62,2 %. At 10 000 characters the floor pulls ahead again
(79,0 against 73,2): its curve keeps climbing because every extra character is
more source text, ours is flat because ten quotes are what it has to say. So the
floor's lead in the headline row is volume, as §7 of `LAYER.md` says — and the
pilot still does not claim to beat it, because at the same budget it does not.

**What is left, honestly.** 73,21 % on dev is inside neither the 75–80 band nor
the "below 70, publish the negative" rule. The band is reached by the labelled
row only, at 39 % more volume (76,18 at 7 115 characters), and the pilot will
report both: the primary row keeps one quote per claim, the extra row says what
the quotes are worth, and neither is presented as the other.

### E2's declared encoding, fixed before it is measured

- Model: `intfloat/e5-large-v2`, revision `f169b11e`, 1024 dimensions — the same
  model the pilot already serves on 8091 for GraphRAG and LightRAG. Our ranker
  using a different model would make the comparison against those two ambiguous.
- Claim text embedded: `passage: ` + statement + the first quote. One text per
  claim, no per-field vectors, so scoring one candidate is one dot product.
- Query: `query: ` + the question, no expansion before E2.
- Prefix control: `query: ` is how e5 was trained, and a library that cannot send
  a query prefix is stuck with `passage: `. The same rung is run both ways on dev,
  because the difference is a real capability gap between us and GraphRAG's or
  LightRAG's use of the same model, and it belongs in the row rather than in a
  footnote. If it moves the number, both are published.
- Scope: the top 100 of the lexical ranking are reranked, not the whole corpus.
  If E2 wins, the same vectors also allow a global dense retrieval, which is a
  separate rung (H4) and a separate cost.
- Storage: ids + `float32` matrix, 9 104 × 1024 = 37,3 MB. This is an **index**,
  not a cache: §5 rule 5 counts it in the artifact, and the row says so.
- Throughput: measured on a 200-claim sample first, then extrapolated, because
  the sidecar has only been timed on long community reports (0,35–0,6 vectors/s)
  and claim-sized inputs are a different regime. Measured: 0,69 claims/s on CPU
  (3 h 45 min for the pilot, rejected) and **10,86 claims/s on the Quadro T2000**
  — 9 295 claims in **856 s**, 39,8 MB on disk, one query in 0,09 s. The build is
  a one-off, so the GPU number is the one that matters.
- Determinism: the matrix is written once and read by every later experiment;
  the file's digest goes in the run record.

### The freeze, decided before the test half is read

The rule was written into §7 as G-R1 and G-R2 and is applied here as stated:
**among the rungs whose dev result is inside one point of the leader, the one with
the fewest moving parts is frozen.**

- `expand-cover` leads by 0,23 pp. Its own gate was ≥ 1 point, it delivers a
  fifth of a point, and it needs the section map and the conflict edges at
  ranking time. **Not adopted.**
- `dense-cover` at depth 100 is the leader that survives: the product's own pool,
  one dense order over it, the `cover` chooser, k = 10, one quote per claim.

| frozen artifact | value |
|---|---|
| ranker | `benchmark/layer/select.py`, `dense-cover`, depth 100, k 10 |
| claim vectors | `claim-vectors.npz`, sha256 `d12c7ec9…c92d`, 9 295 × 1 024, 39,8 MB |
| model | `intfloat/e5-large-v2` @ `f169b11e22de`, `query: ` on questions, `passage: ` on claims |
| split | `split.json`, sha256 `60f23c9a…1a1b`, salt `ontoskills-ranker-v1`, 100 / 100 |

Two rows read the test half once, and neither choice depends on what it says:

1. **`dense-cover`** — the best ranker the ladder produced. It needs a query
   encoder at read time, which the Rust path does not have, so it is published as
   a benchmark row and labelled as one (§7, G-R3).
2. **`cover` over the product's lexical pool** — 71,14 % on dev, no model, no
   vector, no new artifact. It is the rung the read path can serve tomorrow, and
   it exists so the pilot does not have to choose between "the best number we can
   measure" and "the best number we can ship".

The test numbers are computed by the code committed at the freeze and are not
re-tuned afterwards. If they disagree with dev, they are published as they are.

### What the test half said, read once

Committed at `474dc22`, then run on the 96 test questions that carry gold facts:

| ranker | dev | test | 192 questions | interval over the product |
|---|---:|---:|---:|---|
| the product (BM25 top ten) | 63,59 % | 64,29 % | 63,94 % | — |
| `cover`, lexical | 71,14 % | 72,81 % | 71,98 % | +8,03 pp [+6,6; +9,5] |
| `dense-cover` | 73,21 % | 73,62 % | 73,42 % | +9,48 pp [+8,0; +11,0] |
| the product, every quote | 68,19 % | 68,26 % | 68,23 % | — |
| `dense-cover`, every quote | 76,18 % | 76,50 % | 76,34 % | +8,11 pp [+6,6; +9,6] |

Both halves agree, and the product's own row reproduces the published 63,94 %
exactly. `dense-cover` holds its dev number on questions it never saw, so the
ladder did not overfit the split.

**But the dense order does not hold its advantage over the lexical chooser**:
`dense-cover` − `cover` is +2,1 pp [+0,6; +3,6] on dev, +0,8 pp [−0,4; +2,1] on
test, +1,44 pp [+0,5; +2,4] over all 192. On the questions that were not used to
choose it, half a point and an interval that admits zero.

That decides the product question in §7 G-R3 without an opinion being involved:
**the read path ships the lexical chooser, and no ADR 0004 is opened for an ONNX
encoder.** A model file, a parity gate and a latency budget are not bought with
half a point that the held-out half cannot distinguish from noise. The dense row
stays in the table, labelled, with the test number that made the decision.

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
| `ontoskills` (ranker v2, `dense-cover`) | the primary row: the frozen ranker, dev and test numbers, the split's digest, labelled a benchmark row because the read path has no encoder yet |
| `ontoskills` (ranker v2, `cover` lexical) | the shippable rung: +7,6 pp on dev over the product's own ranker, no model, no vector, no new artifact |
| `ontoskills`, every quote | the +2,97-point lever of §5, at 7 115 characters, as its own row |
| `vector-rag-floor` | unchanged, still the measurement of how easy the corpus is |

The claim that may be written in public: *the same knowledge base, the same
quotes, a different selection, +X points with an interval that excludes zero on
held-out questions.* The claim that may not be written: SOTA, "beats BM25", "non
inferiority", or any comparison of coverage across different volumes without
saying the volume.

## 9. Costs

| item | cost | when |
|---|---|---|
| E0–E5, dev and test, all rungs | **0 $** | done |
| claim embeddings (E2) | 0 $, 856 s on the Quadro T2000 (10,86 claims/s), 39,8 MB | done |
| reranker model (E5) | 0 $, model download only | done, rejected |
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

1. **E0 — done.** Free: selection is binding for the first 24 points.
2. **E1a, E1b — done.** +7,6 pp on dev, Rust-portable, the rung that can ship.
3. **E2 — done.** Claim vectors built once (856 s on the GPU, 39,8 MB);
   `dense-cover` 73,21 % on dev, +2,1 pp over `cover`.
4. **E3, E4, E5 — done, all rejected.** Fusion −0,5, graph expansion +0,2,
   cross-encoder −1,9 with a 13,5 s CPU latency. Every mechanism plateaus at 73.
5. **Freeze — done** (§5): `dense-cover` and lexical `cover`, both read the test
   half once.
6. **Write the rows** — dev, test, both intervals, the labelled all-quotes row,
   the footnote on the `query:` prefix, and the statement that the dense row is
   not yet served by the read path.
7. **ADR 0004 — only if the dense row is to become a product row.** An ONNX
   encoder on disk, no network, CPU only, model size in the artifact, G1 parity
   and G-R5 latency re-measured. Until then the product keeps the lexical ranker
   and the row says which is which.
8. **Then** the PR merge, the final report, and any public comment — with the
   link to `main` and the numbers above.
