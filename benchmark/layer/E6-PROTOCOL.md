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

### E6 — the budget curve on the test half

One family: the frozen ranker's ordering, with the cut determined by the
character budget instead of fixed at ten claims. The greedy path is
prefix-consistent, so every budget is the same deterministic ordering stopped
earlier or later. The family was designed on dev and read on test **once**; the
whole curve is published and no budget was chosen afterwards. The test half had
already been read once before, for the ten-claim operating point of the same
ranker.

| budget | this layer | floor BM25 | difference, paired |
|---|---|---|---|
| 5 000 | **74,21 %** (4 977 ch) | 71,44 % (4 800 ch) | **+2,77 [+0,3; +5,3]** |
| 10 000 | 79,54 % (9 960 ch) | 79,35 % (8 900 ch) | +0,19 [−2,0; +2,3] |
| 14 830 | 81,88 % (14 804 ch) | 84,08 % (13 286 ch) | −2,20 [−4,0; −0,4] |
| 20 000 | 83,80 % (19 958 ch) | 87,16 % (18 177 ch) | −3,36 [−4,8; −1,9] |
| 45 000 | 87,52 % (44 894 ch) | 92,17 % (42 614 ch) | −4,65 [−5,8; −3,5] |

At a five-thousand-character budget the claim layer returns more of the gold
answer facts than returning the passages, by 2,77 pp with an interval that
excludes zero — the first positive, significant result of the pilot, on the test
half, at a budget an agent actually uses. It is parity at ten thousand and it
loses above fourteen thousand, where returning whole documents simply carries
more text than any selective layer can.

That is the claim the pilot can defend: **in the small-context regime the
compressed layer is not just cheaper and faster, it is better; outside it, volume
wins.** Not superior overall, and not a state of the art.

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



