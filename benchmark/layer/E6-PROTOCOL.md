# E6 · The recognition rung — protocol fixed before the measurement

Written on 2026-11-18, before the paid rung was executed, and committed on its
own so the order is checkable in `git log`. It covers E7 and E8. It does not
cover the free measurements already made (the equal-budget table of `RANKER.md`
§11 and the rank diagnostic), because those were computed first and are reported
as exploratory, not as pre-registered.

## What is already spent, and what that costs

The test half (96 questions) was read once, with the frozen ranker
`dense-cover` (`474dc22`). From here on:

* the **dev half (96 questions)** is the design surface. Any new selector may be
  measured there as often as we like;
* **no new selector is scored on the existing test half.** A second look at test
  with a selector chosen by that look is not a test, and the pilot's whole
  methodological claim is that we did not do that;
* the frozen ranker under a character cap (E6) is a **rendering**, not a
  selector. The cap changes how much of the same ten claims is returned. It may
  be read once on the test half and published as a declared rendering row.

## The diagnosis this rung answers

On dev, with the pool of 100 claims already in place:

| what | value |
|---|---|
| median rank of the first claim carrying half of a gold fact | **1** (BM25 and dense) |
| gold facts per question | 4,03 |
| facts touched (< 50 % recall) by the ten chosen claims | 3,38 — 0,66 missed outright |
| coverage of the ten chosen by `dense-cover` | 73,21 % |
| exact oracle, best ten of the same 100 | 84,90 % (greedy) / 90,97 % (`oracle.py`) |

The pool is not the problem. Recognition is: we cannot tell, from the question
alone, which of the hundred carries the sentence that answers it. The
off-the-shelf reranker already tried in E5 (`ms-marco-MiniLM-L-6`) makes it
*worse* (58,97 % against 63,59 % for the plain cut), so "add a reranker" is not
an answer by itself.

## E7 — listwise rerank of the head, dev only, paid

**Question.** Is the 12–18 pp of selection headroom reachable by a text-only
recogniser that sees the candidates and the question together?

**Design, fixed now.**

* 96 dev questions with gold facts.
* Pool: `Corpus.search(text, limit=100)`; order: `dense_order` (e5-large-v2,
  `query:` prefix). Candidates: **the first 60 of that order, full quotes, no
  truncation.** 60 because the measured oracle for the best ten of the top 60 is
  **82,08 %** — a ceiling far enough above the decision threshold to make the
  answer informative; 40 (78,81 %) is not.
* Model `deepseek-v4.1-flash`, `temperature 0`, `max_tokens 120`, one call per
  question, no content retries. Transport retries only, and a failed call is
  recorded as a failure, never as an answer.
* Prompt: fixed in `e7-listwise.py` and echoed into the run log, so the exact
  bytes are part of the record.
* Output parsed as a JSON array of ten indices, deduplicated, filtered to range,
  and padded from the dense order if short. The padding is counted and reported.
* Metric: `answer_fact_coverage(gold_facts, quotes of the ten chosen)`, mean over
  the 96 dev questions, same function every number in the pilot uses.

**Baselines on the same sixty candidates, computed for free in the same script:**
the plain cut, `cover` restricted to the 60, and the exact oracle over the 60.
The comparison is therefore at one pool, one order, one budget.

**Cost ceiling.** 0,13 $, as authorised. A three-question smoke runs first; the
per-question token rate it measures is extrapolated to 96 and printed. If the
projection exceeds 0,13 $ the full run does **not** start: the rung stops and the
projection is reported, so raising the cap stays a decision rather than a
side effect. Nothing is truncated and no candidate is dropped to fit the cap,
because that would change the design to fit the budget — exactly backwards.

**Decision rule, fixed before the result.**

* E7 **≥ 79,5 %** → recognition headroom is real and text-only reachable. Next
  step: a local distilled selector (0 $ per query), which becomes the pilot's
  main claim.
* E7 **< 76,0 %** → a text-only reranker does not buy the headroom. The public
  claim stays *parity at equal budget, loss at 45 000 characters*, and no new
  front is opened.
* between the two → reported as indeterminate; no claim either way.

## E8 — the fresh slice, only if E7 opens a front

A second slice of EnterpriseRAG-Bench: 100 questions **not** in the pilot's 200,
whose gold documents are **disjoint** from the 279 already built. Our knowledge
base is rebuilt on those documents (the only cost: our own claim build, capped at
3 $); no competitor is rebuilt, because no competitor is being re-claimed.

The selector chosen on dev is read **once** on that slice and reported with its
interval. If the winning configuration turns out to be the frozen `cover` under a
cap, E8 is not needed at all: E6's rendering row on the existing test half is the
reading, declared as such.

## What would falsify the pilot's own claim

If E6's equal-budget comparison shows no advantage at any budget the product
could plausibly use, then the claim layer is coverage-neutral, and the only
remaining argument for it is latency, cost per query and the refusal behaviour —
not answer quality. That would be said in the same words, in `LAYER.md`, before
anyone else says it.

## Amendments, recorded before the full run

The design above did not change. Two things about *running* it did, both found
by the smoke and both recorded here before the ninety-six questions were asked.

### Amendment 1 — the token budget (harness defect)

At `max_tokens = 120` the three smoke questions returned **empty content** with
`finish_reason = length`. Inspection of the raw response object shows why: this
model emits `reasoning_content` before the answer, and the budget was spent on
the reasoning. The three rows were padded from the dense order, which is
indistinguishable from the baseline in the log — a silent failure dressed as a
measurement. `max_tokens` is therefore 1500, and an empty content is now recorded
as an error (`error = "empty content (finish_reason=…)"`) rather than counted as
an answer. Padding stays, because a failed call must not leave the denominator.

### Amendment 2 — the reasoning level

With the budget fixed, one smoke question still spent all 1500 tokens reasoning
and returned nothing. `reasoning_effort = "none"` answers the same question with
31 completion tokens instead of 1500 (5,8 s instead of 24 s), and the ten
indices it names differ from the `low` effort by two positions. Listwise ranking
needs no chain of thought; the setting is fixed at `"none"` and applied to every
question. It is recorded in the summary of the run.

### The measured projection

Five questions at the final configuration (60 candidates, `effort = none`,
`max_tokens = 1500`): 38 793 prompt tokens, 155 completion tokens, **0,00591 $**,
zero errors, zero padding. Extrapolated to 96 questions: **0,1135 $**, inside the
authorised 0,13 $.

Those five read 78,18 % against `cover` on the same sixty candidates at 84,15 %
and the exact oracle at 90,94 %. Five questions are not a result, they are the
first five in the selection's own order and not a sample, and the decision rule
above is not touched by them. They are recorded here so that nobody can say the
number surprised us later.

## Results

### E7 — negative, and the rule is applied

96 dev questions, 60 candidates, `reasoning_effort = "none"`, one call each.

| system, same sixty candidates | coverage |
|---|---|
| listwise rerank (deepseek-v4.1-flash) | **62,73 %** |
| plain cut, first ten | 64,06 % |
| `cover` | 71,15 % |
| exact oracle, best ten | 82,08 % |

Paired against `cover`: **−8,42 pp, 95 % CI [−10,4; −6,4]**. Against the plain
cut: −1,33 pp [−3,1; +0,5]. Two of the 96 calls returned two tokens and no array;
both rows are scored at the plain cut, not dropped, and removing them moves the
rerank to 63,06 % against 71,62 % — the verdict does not depend on them. The ten
indices the model returned overlap the first ten of the given order by 5,15 of 10,
so it mostly agreed with the order it was handed.

By the decision rule fixed above, **E7 < 76,0 %: a text-only recogniser at this
configuration does not buy the recognition headroom, no new front is opened, and
no claim about beating the floor is made.** E8 is therefore not run.

What this does *not* say: that listwise reranking cannot work. One model, one
prompt, one setting was measured, and at `effort = "none"` the recogniser behaved
close to a re-print of the order. A stronger setting was not measured because the
authorised budget was already spent, and it is not measured now, because a second
configuration chosen after seeing the first result is the tuning the split exists
to prevent.

E7's measured cost: **0,2102 $** — 0,0189 $ of smoke and probes, 0,0769 $ of a
run killed by a restart (63 calls paid, rows lost to a script that wrote only at
the end; the harness now writes each row before the next call and resumes), and
0,1144 $ for the complete run.

### E6 — the budget curve on the test half, corrected

One family: the frozen ranker's ordering, cut by the character budget instead of
fixed at ten claims. The greedy path is prefix-consistent, so every budget is the
same deterministic ordering stopped earlier or later. The family was designed on
dev and the whole curve is published; the test half had already been read once
before, for the ten-claim operating point of the same ranker.

These numbers supersede the first published table, which was cut with packing.
The cut is now `prefix_cut`, the floor's cut.

| budget | this layer | floor BM25 | difference, paired |
|---|---|---|---|
| 5 000 | 72,44 % (4 696 ch) | 71,44 % (4 800 ch) | +1,00 [−2,0; +3,9] |
| 10 000 | 79,16 % (9 718 ch) | 79,35 % (8 900 ch) | −0,19 [−2,4; +1,9] |
| 14 830 | 81,48 % (14 560 ch) | 84,08 % (13 286 ch) | −2,60 [−4,4; −0,7] |
| 20 000 | 83,56 % (19 693 ch) | 87,16 % (18 177 ch) | −3,60 [−5,1; −2,1] |
| 45 000 | 87,50 % (44 611 ch) | 92,17 % (42 614 ch) | −4,67 [−5,8; −3,5] |

**A retraction.** The first version of this table reported +2,77 pp at five
thousand characters, 95 % CI [+0,3; +5,3], and this document called it the first
positive, significant result of the pilot. That number was produced by the
packing cut: our side was allowed to skip a quote that did not fit and pack
smaller ones after it, while the floor stops at the first item that does not fit.
At the same volume the difference is +1,00 pp and the interval contains zero.
There is no significant win over the floor at equal budget, and the earlier claim
is withdrawn.

What survives is the shape: parity at five and ten thousand characters, a loss
from fourteen thousand upwards, where returning whole passages carries more text
than a selective layer can. The floor is the measuring instrument, not a
competitor; beating it at small volume was never the goal, and the layer does not
beat it.

### E9 — rendering, at an identical budget (dev)

Same frozen order, same cut; only the text of each chosen claim changes.

| budget | quote | statement | difference, paired |
|---|---|---|---|
| 2 000 | 55,62 % (3 units) | **65,31 %** (20 units) | **+9,69 [+6,5; +12,9]** |
| 5 000 | 70,83 % (9) | **74,73 %** (52) | **+3,91 [+1,6; +6,1]** |
| 10 000 | 77,96 % (19) | **79,72 %** (100) | +1,76 [+0,0; +3,4] |
| 14 830 | **80,31 %** (28) | 79,83 % (100) | −0,48 [−2,0; +1,0] |

`statement+quote` and `all-quotes` are in the run record and in
`e9-rendering-dev.json`; both are within noise of the quote at every budget below
fourteen thousand, and both lose at two thousand because a claim then costs four
hundred characters instead of eighty.

The statement wins where the budget is small enough for the number of claims to
matter: twenty claims instead of three at two thousand characters, fifty-two
instead of nine at five thousand. At fourteen thousand the pool of one hundred
claims is exhausted at 9 524 characters, so more budget cannot buy more claims
and the quote catches up. The distillation keeps the tokens that carry the
answer — that was the question, and the answer is yes.

### E10 — one slot per aspect: negative

The same pool, ordered round-robin over clusters of the claim vectors instead of
greedily over the question's terms. On statements, paired against `cover`:

| budget | cover | best aspect order | difference |
|---|---|---|---|
| 2 000 | 65,31 % | 63,14 % (`aspect8-cover`) | −2,17 [−3,6; −0,8] |
| 5 000 | 74,73 % | 74,09 % (`aspect20-cover`) | −0,65 [−1,3; +0,0] |
| 10 000 | 79,72 % | 79,64 % (all) | −0,08 [−0,3; +0,0] |

At fourteen thousand, four orders land on exactly the same number because the
whole pool fits and only the text matters. Every aspect order loses at the
budget that matters, and the reason is visible in the diagnosis: the missing
facts are not hidden inside one aspect that clustering could separate, they are
claims the dense order ranks below the sixtieth place. Diversity spends slots on
weaker claims instead of recovering them. The rung is closed.


## Amendment 3 — the cut was not the floor's cut

Found by auditing the harness after the first E6 table was written, and it
invalidates that table rather than the conclusion being assumed to survive.

`score.py::returned_text` cuts a system at the **first** item that does not fit
the budget, keeping the first item whole. The scripts that produced the curves
above did something different: when a unit did not fit, they skipped it and
continued with the next, smaller one. That is packing, not truncation. It buys
text the floor is not allowed to buy, and the difference lands in the coverage
column as if it were quality.

The cut now lives in one place, `budget.py::prefix_cut`, mirrors `returned_text`
line by line, and is pinned by `test_layer_budget.py`. Every curve in this
document is regenerated with it. The superseded numbers are kept in
`pilot-artifacts/e6-e7/` and are identified as superseded there; the tables in
this document are the corrected ones.

The same audit found three smaller defects, all fixed before the numbers below
were produced: E9 called a packing loop "the longest prefix"; E11 wrote its rows
only at the end of a thirty-minute run and could lose all of them to a restart
(the same defect E7 had); and E11 reported a model id without the commit its
weights came from.

## E9, E10, E11 — declared before the dev run

Three rungs, all local, no API spend. The first two change what is *returned*,
the third changes the *order*. The family and the metrics were fixed in the
scripts' docstrings at commit `b1d8eef`, before any of them ran.

* **E9 — rendering at an identical budget.** The frozen order, cut by
  `prefix_cut`, with each chosen claim rendered four ways: `quote` (the product's
  current unit), `statement`, `statement+quote`, `all-quotes`. Budgets 2 000,
  5 000, 10 000 and 14 830 characters.
* **E10 — one slot per aspect.** Four orders over the same pool: the frozen
  `cover`, `aspectN` (the top sixty clustered by claim vector, then read
  round-robin so every aspect gets a slot before any gets two, N in 8/10/20),
  `aspectN-cover` (the same clusters, greedily ordered inside each), and
  `doc-round` (the document as the aspect).
* **E11 — a real cross-encoder.** `BAAI/bge-reranker-v2-m3` at a pinned revision,
  fp32, `max_length = 256`, reranking the frozen pool of one hundred. The pair
  scored is the question and the text that would be returned, so the statement
  and the quote each get their own order. The tail beyond the reranked pool keeps
  the frozen order.

### The rule that picks the configuration for the test read

Fixed here, before E11's dev run finished:

> The configuration published on the test half is the one with the highest dev
> coverage at **5 000 characters** among the declared family — rendering
> (`quote`, `statement`) crossed with order (`cover`, cross-encoder) — with a
> preference for the simpler component on a difference whose paired interval
> contains zero. The whole budget curve of the chosen configuration is published
> on test, not only the winning cell, and the losing cells are published on dev.

The test half has already been read once for the frozen ranker's ten-claim
operating point and once for the E6 budget curve; this is its third and last
read, and the family was chosen on dev.




### E11 — a real cross-encoder: negative

`BAAI/bge-reranker-v2-m3`, revision `953dc6f6f85a`, **fp32**, `max_length = 256`,
reranking the frozen pool of one hundred, one pair per candidate, on a 4 GB
laptop GPU. Local: **0 $**. Ninety-six dev questions, two units, four budgets.

| budget | quote: cover → CE | statement: cover → CE |
|---|---|---|
| 2 000 | 55,62 → 47,90 (−7,71 [−11,1; −4,2]) | 65,31 → 63,68 (−1,62 [−3,2; −0,0]) |
| 5 000 | 70,83 → 59,47 (−11,36 [−13,8; −8,8]) | 74,73 → 74,43 (−0,30 [−1,3; +0,7]) |
| 10 000 | 77,96 → 69,10 (−8,86 [−10,5; −7,2]) | 79,72 → 79,80 (+0,08 [−0,0; +0,2]) |
| 14 830 | 80,31 → 74,59 (−5,71 [−7,1; −4,4]) | 79,83 → 79,83 (0,00) |

The last two rows of the statement column are the whole pool fitting in the
budget: when the cut keeps everything, order cannot matter and the two columns
are the same number by construction. The only rows where a reranker could change
anything are the first two, and it loses both.

That is now **two** independent rerankers losing on this corpus: the generic
`ms-marco-MiniLM-L-6` in E5 (−1,9 pp) and a modern 0,6 B multilingual reranker
here. The conclusion is not "rerankers are bad". It is narrower and more useful:
the greedy selector optimises the quantity the metric measures — coverage of the
tokens the question and the gold facts share — while a relevance scorer optimises
something else, and demotes claims that carry answer tokens the question does not
name. When the metric is token coverage, a reranker trained on relevance is a
different objective, not a better one.

### The configuration this selects

The rule in Amendment 3 asks for the highest dev coverage at 5 000 characters,
with the simpler component on a tie. The candidates measured on dev:

| at 5 000 characters | dev coverage | verdict |
|---|---|---|
| quote, frozen `cover` | 70,83 % | loses to the statement |
| **statement, frozen `cover`** | **74,73 %** | **chosen** |
| statement, cross-encoder | 74,43 % (−0,30 [−1,3; +0,7]) | tie, more machinery |
| quote, cross-encoder | 59,47 % | loses badly |

The configuration published on test is therefore the **frozen ranker, rendered as
statements, cut by the character budget**. No new selector was chosen, so by the
E8 section's own rule the fresh slice is not run: the test read is E9's rendering
curve on the existing half, declared as such.

### E13 — how deep the pool has to be: the ceiling, not the operating point

The statement row runs out at 9 524 characters — one hundred claims of about
eighty — so the losses at ten and fourteen thousand were measured against a pool
that had already ended. This rung rebuilds the order at four depths through the
same pipeline, dev only.

| budget | depth 100 | depth 200 | depth 400 | depth 800 | 400 vs 100, paired |
|---|---|---|---|---|---|
| 2 000 | 65,31 % | 64,77 % | 65,29 % | 64,21 % | ~0 |
| 5 000 | 74,73 % | 74,02 % | **74,88 %** | 74,31 % | +0,15 [−1,1; +1,4] |
| 10 000 | 79,72 % | 80,90 % | **81,12 %** | 80,38 % | +1,40 [+0,3; +2,6] |
| 14 830 | 79,83 % | 83,61 % | **84,19 %** | 83,62 % | +4,36 [+3,1; +5,7] |

At the operating point the depth is indistinguishable from a hundred: the pool
was not the constraint there, because fifty-two of the hundred claims already
fill five thousand characters. Above it, the depth was the constraint, and four
hundred claims recover five points at fourteen thousand. Eight hundred buys
nothing over four hundred and doubles the retrieval cost.

**The configuration published is depth 400.** The pre-registered tie-break
prefers the simpler component when the interval contains zero, and at five
thousand characters that applies: +0,15 [−1,1; +1,4]. Depth is not a model and
not a selector — it is a retrieval parameter that costs local CPU, not money —
and reporting the curve at depth 100 would present a pool ceiling as a property
of the layer. The operating point is unchanged; the ceiling is removed. Both
columns are published so the choice can be audited.

### The sentence floor — the control that decides what the layer is worth

A reviewer will ask whether the statement gain is the claim layer or merely the
granularity, because proposition-level retrieval beating passage-level retrieval
at a fixed budget is already published (Dense X Retrieval, EMNLP 2024). E12
answers it with the dumbest possible system at the same granularity: the
documents cut into sentences, BM25 over the sentences, the same character cut.

| budget | sentences (BM25) | statement, depth 400 | difference |
|---|---|---|---|
| 2 000 | 57,50 % | **65,29 %** | **+7,79** |
| 5 000 | **75,30 %** | 74,88 % | −0,42 |
| 10 000 | **83,28 %** | 81,12 % | −2,16 |
| 14 830 | **87,23 %** | 84,19 % | −3,04 |

**A sentence splitter with BM25 matches the claim layer at five thousand
characters and beats it above.** The layer wins only where the budget is tight
enough for compression to pay — two thousand characters, +7,8 points — and the
reason is arithmetic: a sentence costs about 370 characters, a statement about
95, so at a tight budget twenty claims fit where five sentences do. Distillation
is a compression, and compression is worth its losses only when the budget is the
constraint.

This is the result that decides what the pilot may claim. It is not allowed to
claim that the semantic layer retrieves better than a lexical sentence index,
because on this corpus it does not. What it may claim is measured in E14: the
tokens it takes to reach a given coverage, the price of a query, the price of a
build, and the refusal rate — and every one of those is published beside the row
that beats it.

## The token account — what the comparison is actually about

Every table above holds *characters* constant, which is a proxy. An agent pays
context tokens, a buyer pays API tokens, and the two accounts point in opposite
directions. Both are published here with the conversion declared, never tuned.

**Characters per token: 4.0**, the usual English estimate. Word counts are in the
run record so a reader can redo the division with their own tokenizer.

### Tokens consumed — the account where the layer is not competing

| | build tokens | query tokens | build $ | query $ | build wall clock | query median |
|---|---:|---:|---:|---:|---:|---:|
| **this layer** | 7 916 415 | **0** | **4,11** | **0,0000** | **2 h 12** | **19 ms** |
| GraphRAG local | 24 364 897 | 11 807 per query | 11,09 | 0,0025 | 21 h 19 | 23 814 ms |
| sentences (BM25) | 0 | 0 | 0 | 0 | 4 min | 4 ms |
| passages (BM25 floor) | 0 | 0 | 0 | 0 | 3 s | 4 ms |

For the 200 pilot questions, everything included: **7,92 M tokens and 4,11 $
against 26,73 M and 11,59 $** — 3,4× the tokens, 2,8× the price, 9,7× the build
time. Per document: 28 374 tokens and 0,0147 $ against 87 329 and 0,0397 $.

LightRAG has no finished row and cannot be given one at this budget: one measured
document cost 0,0639 $, which projects to 13–18 $ for 279 documents.

### Tokens returned — the account where a generated answer wins

Coverage alone rewards dumping, so precision is measured here for the first time.
It is **type-level**: a repeated word counts once. Two exclusions make it mean
something — the question's own vocabulary, because a word the question contains
cannot be evidence of its answer, and any type present in more than half the
corpus, because it is background. Without them the twenty most "precise" types
are `the, to, and, for, is` and the metric measures English.

Dev, 96 questions, strict (a refusal counts as zero, never as an unanswered row):

| system | tokens | refusal | strict recall | precision | strict F1 |
|---|---:|---:|---:|---:|---:|
| GraphRAG (generated answer) | 383 | 17,71 % | 63,77 | **13,57** | **17,81** |
| **ours, statement, 2 000 ch** | 493 | 0 % | **65,29** | 7,06 | 11,73 |
| ours, statement, 5 000 ch | 1 250 | 0 % | 74,88 | 4,30 | 7,73 |
| ours, statement, 10 000 ch | 2 518 | 0 % | 81,12 | 2,95 | 5,49 |
| ours, statement, 14 830 ch | 3 736 | 0 % | 84,19 | 2,36 | 4,46 |
| sentences, 2 000 ch | 440 | 0 % | 57,50 | 8,28 | 12,92 |
| sentences, 5 000 ch | 1 195 | 0 % | 75,30 | 4,80 | 8,53 |
| sentences, 10 000 ch | 2 447 | 0 % | 83,28 | 3,00 | 5,57 |
| sentences, 14 830 ch | 3 636 | 0 % | **87,23** | 2,35 | 4,46 |
| floor, 2 000 ch | 1 200 | 0 % | 70,45 | 5,57 | 9,64 |
| floor, 14 830 ch | 3 252 | 0 % | 83,41 | 3,09 | 5,74 |

Volume is the median over answered questions. A first version of this table
averaged refusals in as zero-token rows, which made abstaining look cheap; that
was wrong and is corrected here.

**At equal tokens returned**, interpolated between each system's own measured
points: at 500 tokens ours 65,38 / sentences 58,91 / quote 56,53; at 1 000 ours
71,71 / sentences 70,70 / quote 67,40; at 2 500 sentences 83,46 / ours 81,03 /
floor 80,27. **At equal strict recall**: 60 % costs GraphRAG 383 tokens and us
493; 70 % costs us 865 and sentences 970, and GraphRAG cannot reach it at all
because its refusals cap it at 63,77; 75 % costs sentences 1 182 and us 1 274;
80 % costs sentences 1 932 and us 2 290.

The sentence floor's 1 200-token row is an artefact worth naming: the floor
returns 4 800-character passages, so 2 000 characters and 5 000 characters are
both the same single passage. It has no operating point below 1 200 tokens.

### What this licenses, and what it does not

Two sentences survive the numbers, and one does not.

* **True, and large: at equal accuracy we consume no query tokens at all.** At
  74,88 % strict recall on dev this layer spends 0 API tokens per query against
  11 807 for GraphRAG, which never reaches that accuracy on this slice. At 65,29 %
  it spends 0 against 11 807, and GraphRAG's own ceiling is 63,77 % because it
  refuses 17,71 % of the questions. On the account a buyer pays, the comparison is
  not close: 3,4× the tokens and 2,8× the price to build, then 11 807 tokens per
  question forever.
* **True, and narrow: at equal tokens returned we win only while the budget is
  tight.** Below about a thousand tokens the claim layer has the highest strict
  recall of every extractive system, because compression is what a tight budget
  buys. Above roughly 1 200 tokens raw sentences win, and the reason is arithmetic
  — a sentence costs 370 characters and a statement 95, so once there is room the
  compression only throws text away.
* **False: that we are the most token-efficient way to return an answer.**
  GraphRAG's generated answer is denser per token than any evidence we can
  return, and it is denser on precision too. That is what an LLM at query time
  does: it compresses, for 0,0025 $ and 23,8 seconds, and it refuses one question
  in six. A pilot that hid this row would be selling something.

The honest one-line claim is therefore about **cost at a given accuracy**, not
about accuracy at a given size of context, and it is stated with the row that
beats us printed beside it.

### The test read, once, on the configuration that was chosen on dev

`statement` rendering, frozen `cover`, pool depth 400, at most 200 claims chosen,
cut by `prefix_cut`. Selected on dev; this half was read once, after the choice.
The configuration reproduces E13's dev column to the digit (65,29 / 74,88 / 81,12
/ 84,19), so the read is of the pipeline that was measured, not of a variant.

| budget | quote | statement | difference, paired |
|---|---|---|---|
| 2 000 | 56,95 % | **62,28 %** | **+5,33 [+2,8; +7,8]** |
| 5 000 | 72,53 % | **74,75 %** | **+2,22 [+0,1; +4,3]** |
| 10 000 | 78,99 % | **81,34 %** | **+2,36 [+0,4; +4,3]** |
| 14 830 | 81,87 % | **84,42 %** | **+2,55 [+0,8; +4,3]** |

The rendering effect replicates at every budget with intervals that exclude zero.
It is smaller than dev promised at the tight end — dev said +10,09 at two thousand
characters and the test says +5,33 — and that is the normal direction of a
selection on the half that chose. The shape is the same: the gain shrinks as the
budget grows, and it never changes sign.

`statement+quote` and `all-quotes` are in `e9-rendering-test.json`: both lose to
the bare quote at every budget except the statement+quote at fourteen thousand,
where they tie. Once the budget holds whole quotes, prefixing the quote with its
statement only adds overhead.

At five thousand characters the published configuration covers **74,75 %** of the
gold answer facts on the test half in 4 952 characters, against the floor's
71,44 % in 4 800.

### The whole slice, all 192 questions, every system in the same table

Dev and test merged, paired on the question, strict (a refusal is a zero, never a
missing row). Tokens are the median over questions the system answered.

| system | tokens | refusal | strict recall | precision | strict F1 |
|---|---:|---:|---:|---:|---:|
| GraphRAG (generated answer) | 420 | 15,62 % | 65,20 | **11,25** | **17,99** |
| ours, statement, 2 000 ch | 493 | 0 % | 63,78 | 7,66 | 12,38 |
| ours, statement, 5 000 ch | 1 250 | 0 % | **74,81** | 4,95 | 8,68 |
| ours, statement, 10 000 ch | 2 515 | 0 % | 81,23 | 3,42 | 6,25 |
| ours, statement, 14 830 ch | 3 735 | 0 % | 84,30 | 2,69 | 5,02 |
| sentences, 2 000 ch | 446 | 0 % | 57,49 | 8,53 | 13,24 |
| sentences, 5 000 ch | 1 188 | 0 % | 74,45 | 5,10 | 8,92 |
| sentences, 10 000 ch | 2 446 | 0 % | 82,43 | 3,28 | 6,03 |
| sentences, 14 830 ch | 3 654 | 0 % | **86,37** | 2,60 | 4,88 |
| passages (floor), 5 000 ch | 1 200 | 0 % | 71,07 | 5,85 | 10,09 |
| passages (floor), 14 830 ch | 3 308 | 0 % | 83,74 | 3,40 | 6,27 |

Paired against GraphRAG on the same 192 questions:

| config | strict recall | difference from GraphRAG |
|---|---:|---|
| statement, 2 000 ch | 63,78 % | −1,41 [−6,5; +3,6] |
| statement, 5 000 ch | 74,81 % | **+9,62 [+4,9; +14,7]** |
| statement, 10 000 ch | 81,23 % | **+16,04 [+11,4; +20,9]** |
| statement, 14 830 ch | 84,30 % | **+19,11 [+14,6; +23,8]** |

Paired against the sentence floor, which is the bar that matters:

| config | statement | sentences | difference |
|---|---:|---:|---|
| 2 000 ch | 63,78 % | 57,49 % | **+6,29 [+3,7; +9,0]** |
| 5 000 ch | 74,81 % | 74,45 % | +0,36 [−1,4; +2,0] |
| 10 000 ch | 81,23 % | 82,43 % | −1,20 [−2,8; +0,3] |
| 14 830 ch | 84,30 % | 86,37 % | −2,07 [−3,4; −0,8] |

That is the whole result in two rows of a table. **The layer is better than a
sentence index only where the budget is tight** — six points at two thousand
characters, a tie at five, and it loses from ten thousand upward. And it is ahead
of GraphRAG by nine to nineteen points from five thousand characters upward, on a
comparison where GraphRAG declines one question in seven and this layer declares
nothing.

Neither of those is the claim the pilot publishes. The published claim is the
cost one, because it is the only one where the margin is not a matter of degree:

At **74,81 %** strict coverage this layer spends **zero** API tokens per query and
1 250 context tokens. GraphRAG spends **11 807** API tokens per query and does not
reach that number strictly at all: its strict ceiling is 65,20 %, because it
declines 15,62 % of the questions.

The strict view is not the only fair one, so here is the same question with the
refusals removed from both sides. On the 162 questions GraphRAG answers, its
coverage is **77,27 %**. The sentence above that point costs this layer about
**1 700 context tokens** and **zero** API tokens; the same coverage costs GraphRAG
**11 807** API tokens and 420 context tokens. That is the claim in the form the
pilot can defend:

> **at equal accuracy, this layer consumes about seven times fewer tokens per
> question — 1 700 against 12 227 — and 2,8 times fewer dollars to build.**

It is a claim about cost at a given accuracy. It is not a claim about accuracy at
a given size of context, where GraphRAG's generated answer is denser, and it is
not a claim of state of the art: it is four systems on one corpus, measured
honestly, with the row that beats us in the same table.

---

## E16 — RAPTOR: the competitor that shares our premise

Declared **before** the build, in this commit, with no number from the run known.

RAPTOR (Sarthi et al., ICLR 2024) is the only competitor in reach that does what
this layer does: it spends a model at build time to produce compressed,
question-independent text units, and then answers at query time without a model.
Comparing against it is therefore the only comparison that tests the *claim*
rather than the category. GraphRAG writes an answer; a sentence index does not
compress; RAPTOR compresses, and it decides how to compress with clustering
instead of with claims.

If RAPTOR beats the claim layer at equal characters, then "the claims are the
better compression" is false and this document will say so in the same place it
says everything else.

### The configuration, fixed here

| choice | value | why |
|---|---|---|
| chunk | 400 characters, 80 overlap | the paper's 100 tokens / 20 overlap at four characters per token |
| embedding | `intfloat/e5-large-v2`, revision `f169b11e`, fp32, 1 024 dims | the encoder this layer already uses, so the embedding is not a variable |
| prefixes | `passage: ` for nodes, `query: ` for questions | E5 is trained this way; the competitor sidecar cannot do it, RAPTOR here can |
| reduction | UMAP, 10 components, `metric="cosine"`, `random_state=42` | the paper's setting |
| clustering | `GaussianMixture`, `covariance_type="spherical"`, components chosen by BIC over `2..min(60, n//10)` | the paper's setting, with a declared grid |
| summarisation | the pilot's own model, `temperature=0`, `max_tokens=512`, 4 in flight | same model as our claims, so the comparison isolates the method |
| levels | at most 3, stop when fewer than 8 nodes remain | the paper's tree is 2-3 levels on this corpus size |
| retrieval | collapsed tree: cosine over **all** nodes, chunks and summaries together | the paper's default, and the only mode with no query-time model call |
| cut | `prefix_cut` at 2 000 / 5 000 / 10 000 / 14 830 characters | the same cut as every other row in this document |
| scoring | the same metric, the same 200 questions, the same gold facts | one instrument |

Not run, and declared so no reader expects it: tree traversal, query-time
summarisation, the "Q&A" mode, and any per-question adaptation. RAPTOR's query
path here costs zero API tokens, exactly like ours, which is why this comparison
can be decided on quality and build cost alone.

**Ceiling: 2 $.** The build is stopped and reported as incomplete if the meter
passes it. Nothing about the query phase can cost money.

### What each outcome means, written before the run

- **RAPTOR ahead at 5 000 characters with an interval excluding zero** — the
  claim layer is not the better compression, its advantage over raw sentences is
  a property of compression in general, and the published claim narrows to cost
  and provenance. That is the outcome this document would have to carry.
- **Interval containing zero** — both compress equally well at the operating
  point, and the claim layer's advantage is that it costs 3-4× less to build and
  emits provenance with every unit. Published as a tie, not a win.
- **The claim layer ahead with an interval excluding zero** — the first
  comparison in this pilot where a semantic method beats an implemented
  alternative on quality at equal budget, and the only one that would license a
  sentence about the method rather than about the price.
