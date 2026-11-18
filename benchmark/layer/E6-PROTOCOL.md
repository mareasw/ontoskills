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

