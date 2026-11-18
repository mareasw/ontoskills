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
