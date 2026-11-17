# Retrieval benchmark — pre-flight

- **Status:** protocol only. Nothing measured yet. No criterion in this file may
  be changed after a number is seen; if it must change, it is an amendment with
  its own date and its own re-measurement, exactly as in
  [`benchmark/docbench/PREFLIGHT.md`](../docbench/PREFLIGHT.md).
- **Date:** 2026-11-14
- **Owner:** repository owner. The implementer does not score his own grounding
  claims; the audit in §4 is done by someone else.
- **Depends on:** ADR 0001 (document-first kernel), ADR 0002 (deterministic
  verifier), `docs/phase2-plan.md` (the gate that failed), and the measured
  facts in `benchmark/docbench/RESULTS.md` § Phase 2.

## 1. What is being claimed, in one falsifiable sentence

> On the **public benchmarks that match the task shape** (EnterpriseRAG-Bench,
> SciFact, ContractNLI), on **Italian retrieval** (mMARCO) and on a **locator
> test over every compiled claim**, this system retrieves the evidence that
> answers the question **within a pre-declared non-inferiority margin of a
> strong dense/hybrid retrieval baseline**, while **every returned statement
> carries a verbatim quote and a locator verified by a deterministic checker**,
> and **no remote model and no paid call at query time**.

Everything above is measurable, and every clause can fail independently. That is
the point: a claim that cannot fail is marketing.

### 1.1 What is explicitly not claimed

- Not state of the art on BEIR overall, on MTEB, or on any leaderboard where the
  task is "retrieve a document for a short web query". Those tasks have their own
  SOTA and thousands of GPU-hours behind it.
- Not better *answers* than a frontier LLM. The claim is about the evidence path
  and the grounding, not about prose.
- Not "always finds the right sentence". That is not a property of any retrieval
  system; the protocol replaces it with a number, an interval and a paired test.

### 1.2 Why a single threshold is not used

The previous gate ("18 of 20, recall ≥ 0.60") is a point estimate over 20 items:
at the observed 14/20 its 95% interval is ±19 points (Wilson, 0.481–0.855). It
cannot distinguish a real improvement
from noise, and it rewards tuning against itself. This protocol replaces it with:

- **paired** comparisons on the same queries (the only design that removes
  question difficulty from the comparison),
- **confidence intervals** from a paired bootstrap,
- a **pre-declared non-inferiority margin** for "as good as", and
- a **decision rule** a third party can recompute from the released artifacts.

A threshold may still appear as a *reporting* line. It is never the decision.

### 1.3 Two shipping configurations, two claims

A local cross-encoder (§6, S4) is a model that runs at query time. Pretending
otherwise would make the sentence above false, so the protocol separates:

- **D — deterministic mode.** No neural component at all: BM25F, passage
  grouping, duplicate collapse, structured-field boosts. Output is bit-identical
  across runs and machines. Today's README promise is this mode.
- **L — local-rerank mode.** D plus a pinned cross-encoder reranking the top 50.
  Still no network and no paid call, but one model executes per question, and
  bit-identity holds only on the same build and machine.

Both are measured. The determinism claim belongs to **D**; the retrieval claim
belongs to whichever mode is shipped. **L ships only if it beats D by at least
1.0 metric point with a CI excluding zero on the public dev splits** — otherwise the
determinism property is worth more than the points.

## 2. Two measurements, kept apart

Retrieval quality and citation faithfulness are different properties and are
measured separately, because a system can win one and lose the other.

| | **R — evidence retrieval** | **G — grounding** |
|---|---|---|
| question | is the answering evidence in the returned set? | is every returned statement backed by its quote? |
| unit | query → ranked evidence set | returned claim → its own quote, locator, numbers |
| benchmarks | public IR/QA datasets, plus a 30-item internal regression check | own corpora (demo, pilot), plus an independent audit |
| judge | gold qrels / annotated evidence, not ours | deterministic verifier + independent human audit |
| baseline | BM25 → hybrid → cross-encoder rerank | LLM RAG with citations (same corpus, same questions) |
| metric | nDCG@10, Recall@k, EvidenceRecall@12 | citation precision / recall / support, fabrication count |

The product claim in §1 is the conjunction. A win on R alone does not support it;
a perfect G with poor R is a well-cited wrong answer.

## 3. Benchmark suite

### 3.1 Public, citable, not authored here

Sizes below were read from the HuggingFace datasets server on **2026-11-14**; the
download manifest records the revision and checksum of everything actually used,
and re-checks the counts at download.

| Benchmark (HF id) | Rows, 2026-11-14 | Shape | Role |
|---|---|---|---|
| **EnterpriseRAG-Bench** (`onyx-dot-app/EnterpriseRAG-Bench`) | 500 questions over 500k+ enterprise documents (Confluence, GitHub, Drive, …) | question → expected doc ids, gold answer, **`answer_facts`**; 10 question types including *Info Not Found* (20), *Conflicting Info* (20), *Completeness* (20), *Intra-Document Reasoning* (40) | **primary**, and the closest public analogue of this product: it tests abstention, cross-document completeness and conflicting sources natively |
| **SciFact** (`BeIR/scifact`) | 5,183 abstracts · 1,109 test queries | claim → supporting abstract; the original release annotates rationale sentences | **primary**: claim-shaped retrieval, published BM25 and dense baselines |
| **ContractNLI** (`kiddothe2b/contract-nli`) | 20,107 rows | hypothesis → contract span, entailment / contradiction / not-mentioned | **primary**: clause-level evidence |
| **QASPER** (`allenai/qasper`) | 1,585 papers | question → evidence paragraphs in a long paper | secondary: long documents |
| **RAGBench** (`galileo-ai/ragbench`) | 95,381 rows, 12 configs | question → relevant docs with utilisation labels | secondary: per-document relevance |
| **CUAD** (`theatticusproject/cuad`) | 84,325 rows | clause extraction with spans | secondary: clause-level evidence |
| **FinanceBench** (`PatronusAI/financebench`) | 150 questions | question over filings, evidence pages, answerable flag | secondary: abstention on real filings |
| **DocFinQA** (`kensho/DocFinQA`) | 7,437 rows | long finance documents with evidence | secondary |
| **MultiHopRAG** (`yixuantt/MultiHopRAG`) | 2,556 questions · 609 docs | multi-document, multi-hop | secondary: cross-document |
| **BRIGHT** (`mteb/BrightRetrieval`) | 12 domains | reasoning-intensive retrieval | secondary: the hardest lexical gap |
| **BEIR short-query trio** (`BeIR/nfcorpus`, `BeIR/fiqa`, `BeIR/arguana`) | 3,633 · 57,638 · 8,674 docs | web-style short queries | reported only; a gap here is expected |
| **mMARCO, Italian** (`unicamp-dl/mmarco`) | ~8.8M passages, dev queries + qrels | translated MS MARCO, Italian collections and queries | **secondary, Italian**: the only public Italian retrieval benchmark; a proxy, and reported as one |
| **CRAG** (`Quivr/CRAG`) | 2,700 | includes unanswerable and false-premise questions | abstention |
| **ALCE / ASQA** | public | answer with citations | grounding only |

Licences are checked per dataset before any number is published; the text is
never redistributed, and results are reported as deltas against baselines
measured in this harness.

**Verified through the adapter on 2026-11-15** (`adapters.py --check`):
EnterpriseRAG-Bench carries 500 questions — basic 175, semantic 125,
intra_document_reasoning 40, project_related 40, constrained 30, completeness 20,
conflicting_info 20, info_not_found 20, miscellaneous 20, high_level 10 — and
**2,407 answer facts** across the 480 answerable rows. The 20 abstention rows carry
instruction-shaped "facts" ("the answer must state that this is not answerable");
the adapter drops them and labels the rows unanswerable, so a system cannot score
by echoing the instruction.

Selection rule, declared now: a benchmark enters the suite only if (a) it is
public and citable, (b) its gold is not authored by this project, (c) it has a
question/evidence shape this system can consume without changing the system, and
(d) either a published BM25 and a published dense baseline exist for it, or both
baselines are re-measured in this harness on the same split — in which case the
comparison is reported as within-harness and never as a comparison with
literature. Rule (d) is what makes "non-inferiority" checkable rather than
self-referential.

**Primary and secondary, declared before measuring.** The primary family is
**EnterpriseRAG-Bench, SciFact and ContractNLI**: between them they cover a
question answered from one passage, a claim that needs its supporting sentence,
a clause that entails or contradicts a hypothesis, questions whose answer is not
in the corpus, and questions whose answer is spread across several documents.
Those are the five shapes this product claims to handle. **QASPER, RAGBench,
CUAD, FinanceBench, DocFinQA, MultiHopRAG, BRIGHT and mMARCO Italian** are
secondary and reported with their intervals. **NFCorpus, FiQA and ArguAna** are
short-query web IR: a gap there is expected and stated rather than hidden,
because beating a dense retriever on that shape is a different product. **ALCE**
and the CRAG/FinanceBench abstention cases belong to the grounding and abstention
measurements.

**What this removes.** The public suite carries the statistical weight and the
external referee role, so **this project authors no questions at all**: Italian
comes from mMARCO, locators are tested mechanically, contradictions and
abstention come from EnterpriseRAG-Bench, and the only internal items are the 30
already frozen in earlier phases, labelled development-exposed.

**Out of scope, deliberately:** MS MARCO (web passages, saturated), Natural
Questions (open-domain, answer generation), anything requiring a GPU at query
time.

### 3.2 The five things public data does not measure, and how each is covered without authoring

Nobody writes questions for this benchmark. Every product-specific property has
either a public dataset or a mechanical test:

| property | how it is measured | what it costs |
|---|---|---|
| **Italian retrieval** | `unicamp-dl/mmarco`, Italian split (translated MS MARCO: ~8.8M passages, dev queries and qrels). Scored on the full corpus for BM25, and on a declared sub-corpus for the dense baseline — all qrels positives plus a deterministic random negative sample — because embedding 8.8M passages exceeds this machine's 4 GB GPU. A proxy, reported as one, and not gated | disk and CPU, no authoring |
| **Locator accuracy** | deterministic property test over every compiled claim: re-open the source at the cited page, section and offset and require the quote to be there. Demo (5,680 claims) + pilot (298) = 5,978 checks | $0, no questions |
| **Cross-document contradiction** | EnterpriseRAG-Bench *Conflicting Info* (20) and *Completeness* (20) | $0 |
| **Abstention** | EnterpriseRAG-Bench *Info Not Found* (20), CRAG, FinanceBench's answerable flag | $0 |
| **Behaviour on our own documents** | the two sets authored and frozen before this protocol: demo 20 (English) and pilot 10 (Italian) | $0 |

Consequences, stated plainly:

- **No sealed set authored by a third party.** The external referee role moves
  entirely to the public suite, where the gold was written by people who never
  saw this code. That is a stronger position than a 40-question set someone
  writes in two hours, and anyone can reproduce it from a download.
- **The internal 30 are a regression check, not a gate.** They were used during
  development; presenting them as a test would be dishonest. Their numbers are
  published beside the public ones and labelled *development-exposed*.
- **Set-valued matching** still applies: any claim whose evidence overlaps the
  gold span at token level counts, never a specific claim id. This is the
  correction for the three gold defects found on 2026-11-14 (q06, q15, q20).
- **The old numbers are not rewritten.** The 20-question demo gate keeps its
  frozen result; the new protocol reports it as history.

## 4. Metrics, defined

Let `E(q)` be the gold evidence set, `R_k(q)` the top-k returned claims.

- **EvidenceRecall@k** = fraction of the gold evidence items that at least one of
  the top-k returned items reaches, with a **one-to-one** assignment: the ranking
  is walked in order, each returned item is credited to at most one gold item, and
  the denominator is always |E(q)| so an item nobody could reach counts against
  the system. What "reaches" means is stated per source, because it differs:
  - *Public datasets*: the returned unit's id equals the gold unit's id
    (document, paragraph, caption or sentence — whatever the dataset calls a unit).
  - *Our own corpora*: the returned claim cites the same document and the range it
    quotes covers **≥ 50% of the gold span** (`metrics.span_cover`). The gold is
    the reference, so a longer returned span that contains the gold scores 1.0.

  This is not Hit@k with a product term: Hit@k credits one returned item with
  satisfying every gold item, which is exactly the multi-rule case where the
  system fails.
- **Hit@k** = 1 if any gold item is reached. Reported, never gated.
- **nDCG@10** with graded relevance, for the public datasets, computed by the
  dataset's own convention (binary for BEIR, so the number is comparable to the
  published ones) and with ties broken by id, so a run is reproducible exactly.
- **MRR@10** — reported, never gated (it rewards sharpness and invites re-ranking
  the gold).
- **CitationPrecision** = fraction of returned claims whose quote supports the
  statement, per the deterministic verifier **and** a blinded human audit of a
  10% sample. Two numbers, because the verifier is ours.
- **CitationRecall** (ALCE definition) = fraction of answer-bearing statements
  with at least one supporting citation.
- **AnswerFactCoverage** (primary at the answer level) = mean over the gold atomic
  facts (EnterpriseRAG-Bench `answer_facts`) of `fact_token_recall(fact, ∪R_k)`:
  the fraction of the fact's tokens — lower-case alphanumeric, length > 1, **no
  stopword list and no threshold** — present in the multiset union of the returned
  claims at the dataset's k (10 public, 12 own). Token multiplicity counts: a
  number repeated in the fact must be present twice to count twice.

  **Granularity is the dataset's own unit, and that bounds what the number can
  mean.** Where the unit is a sentence (RAGBench) or a paragraph (QASPER) the
  metric discriminates; where it is a whole document (EnterpriseRAG-Bench,
  SciFact, mMARCO) ten returned documents nearly always contain every fact's
  tokens, so the value saturates near 1.0 for every system and is an upper bound,
  not a ranking. It is reported for those datasets and never gated; the gated
  number at the document-level datasets is nDCG@10 and EvidenceRecall@k, which is
  also what their published figures use.
- **AnswerFactSupport** (secondary, stricter) = mean over the same facts of the
  best **single** returned claim's `fact_token_recall`. Coverage says the answer
  can be assembled from what was returned; support says one citation carries the
  fact on its own. A fact covered only by the union is real but weaker, so both
  numbers are reported and only coverage is pre-registered as primary.
- **NumericCongruence** = fraction of facts whose every numeric token also appears
  in the returned evidence. Reported separately, because a reply can cover the
  sentence and still get the number wrong, and averaging that away is how a wrong
  answer scores well.
- **LocatorValidity** = fraction of compiled claims whose quote is found again in
  the source at the cited offset, and the fraction whose page and section are
  independently correct. Measured over all 5,978 claims of the demo and pilot
  corpora; a failure is a compiler bug, not a ranking result.
- **AbstentionAUC** = AUC of the answerability signal against the labelled
  answerable/unanswerable split; plus the risk–coverage curve at coverage 0.8.
- **Determinism** = SHA-256 of the rendered answer over two runs, identical, on
  configuration D (§1.3). Binary, not a metric.

`k = 12` for the own set (the product's answer size); `k = 10` for public
datasets, matching their published conventions.

## 5. Statistical protocol

Declared now, computed on the released artifacts, reproducible by anyone:

1. **Unit of observation:** one query. All comparisons are paired on the same
   query set.
2. **Interval:** 95% CI by paired bootstrap, 10,000 resamples, percentile method.
3. **Test:** two-sided Wilcoxon signed-rank on per-query differences; a paired
   bootstrap p-value as a cross-check. Report both, and the effect size (mean
   difference, in metric points).
4. **Multiplicity:** Holm–Bonferroni across the pre-declared family of
   comparisons (systems × datasets, plus ablations). The family is fixed in §6
   before the runs and does not grow afterwards.
5. **Non-inferiority:** the alternative is declared in advance — margin
   **δ = 2.0 nDCG@10 points** and **δ = 2.0 pp EvidenceRecall@12**. Non-inferior
   means the lower bound of the 95% CI on the paired difference is above −δ. This
   is a different question from "not significantly worse", and it is the one that
   matters for a product.
6. **Power:** the minimum detectable effect is computed from the observed
   per-query variance and reported next to every non-significant result. No
   claim of "no difference" without it.
7. **No peeking:** dev metrics only until §8 Phase 4. One test run. If the test
   run is repeated for any reason, the reason is recorded and the result is
   reported as a second run, not as the first.
8. **Dev and holdout partition, fixed before the first run.** Every dataset in
   the suite is partitioned by the same committed rule — including the ones that
   publish a dev split, where the partition is a second, independent cut on top of
   it, not a substitute: tuning sees the dev half of the questions the harness
   actually scores, and the holdout half is scored once, in Phase 4.

   The rule, stated exactly (`benchmark/retrieval/partition.py`,
   `sha256-rank-alternate-v1`): strata are the dataset's own question types;
   inside each stratum the question ids are ordered by
   `sha256("ontoskills-retrieval-2026-11-15" + "\x00" + qid)` and assigned
   alternately, even positions to dev and odd to holdout, so every stratum differs
   by at most one and odd strata leave the extra question on the **dev** side,
   where the noise costs less. The salt is fixed by the protocol and a build with
   any other salt is refused. The file stores every assignment, its stratum and a
   SHA-256 over the algorithm, salt, dataset and all assignments; `--verify`
   re-derives the partition from the live dataset and fails if the assignment, a
   stratum, or the digest has moved.

   **Amendment 2026-11-15, before any run:** this replaces the earlier
   `sha256(question_id) % 2`. That rule is unbiased in expectation and badly
   unbalanced at these sizes: EnterpriseRAG-Bench has families of 20 questions,
   where independent hashing gives 11/9 about a quarter of the time and 13/7 about
   3% of the time, so a 20-question family could be split 65/35 while the file
   still looked principled. Rank-then-alternate keeps the two properties that
   matter — independence from input order and from anything a person could nudge —
   and removes the third that was never wanted. The amendment was made before the
   first measurement and does not depend on any result: no score had been computed
   on either half at the time of writing.

## 6. Systems under test and baselines

Same corpus, same queries, same k, same harness. Model ids and revisions pinned;
weights hashed.

| id | system | why it is here |
|---|---|---|
| S0 | BM25 over claims (today) | the honest baseline; the current product |
| S1 | BM25F over claims, per-field normalisation | removes the field-weight repetition hack |
| S2 | S1 + passage/rule grouping | the structural fix for the three real misses |
| S3 | S2 + near-duplicate collapse | frees slots that duplicates steal |
| S4 | S3 + local cross-encoder rerank of top 50 | closes the lexical gap ("third country" vs "third party outside the EU"); configuration L, so it must earn its place against D's determinism |
| S5 | S4 + structured fields (actor, modality, deadline) as boosts/filters | the advantage a claim layer has over a text index |
| B1 | BM25 over raw passages, no claims | proves the claim layer adds retrieval value, or does not |
| B2 | dense bi-encoder (BGE-M3 or E5-large, pinned) | the strong dense baseline |
| B3 | B2 + BM25, RRF | the strong hybrid baseline — the non-inferiority target |
| B4 | B3 + cross-encoder | the "SOTA-shaped" baseline; if we cannot approach it, we say so |
| B5 | LLM RAG with citations | the G-side comparison: same questions, same corpus, free-form answer |

Query-time model calls: S0–S3 and S5 = 0 (configuration **D**). S4 adds one local
cross-encoder (configuration **L**). B2–B4 call a local encoder, never a paid one.
B5 is the only paid system and runs on a capped budget, declared before the run.

## 7. Contamination, blindness, reproducibility

- **Gold is never shown to the ranker.** No system in S0–S5 sees question ids,
  gold spans or dev/test labels; the harness passes only the question string.
- **Adapters, not rewrites.** Public corpora are indexed as text by the same
  ranking code, so the retrieval claim is measured without paying to compile
  thousands of documents into claims. Claim-layer gains are measured separately
  on our corpora.
- **Determinism:** two runs of configuration D must hash identically. The
  embedding path is pinned by revision; the model output cache is content-keyed
  (the sampler answers differently even at temperature 0 — measured 2026-11-13).
- **One command per table.** Every number in the final report is produced by a
  script in this directory, with the dataset checksums, so a third party can
  recompute it without our machine.
- **Release:** harness, adapters, gold *schema*, protocol, dataset revisions and
  checksums, and the dev/holdout partition file are public. Everything needed to
  recompute every table is a download and one command; nothing is local-only, so
  the measurement can be audited rather than trusted.

## 8. Phases, gates and kill criteria

Every phase states its decision rule **before** it runs.

**Status 2026-11-16:** Phase 0 is closed and recorded in §12. All six adapters
pass `--check`; the metric layer reproduces Anserini BM25 on SciFact within one
point (0.6614 vs 0.665); the locator property test finds every quote at its cited
offset on both compiled corpora. Phase 1 (the baseline table) is closed and
recorded in §13: the lexical column on all five datasets, the dense/hybrid/rerank
column on the four whose corpora this machine can encode, with §13.5 stating in
arithmetic why the other two are not in the table. §13.8 records the MDE and the
measured power at δ before Phase 3 begins.

Phase 2 is closed and recorded in §14: the Italian analyser reproduces mMARCO's
published BM25 pair — MRR@10 0.1479 against 0.153, R@1000 0.7617 against 0.753 —
inside the same one-point tolerance, on 8.8M passages. The pair quoted here before
the analyser was corrected was 0.1478/0.7614; §14.4 keeps both runs and says what
moved. The locator half of the
Phase-2 gate is the run already in §12.2: 5,978 compiled claims, every offset and
every page correct, the six heading crossings enumerated by class. The 30 frozen
internal items named in the Phase-2 row are **not** part of this gate and are not
scored here: they are a development-exposed regression check, and §3.1 keeps every
number that decides something on public, citable data. Dropping them removes a
private number; it adds no threshold, and §11 forbids adding one after a result.

| Phase | Work | Gate / decision rule |
|---|---|---|
| **0** (2 days) | Harness: dataset loaders and adapters for the six public datasets, metric implementations with unit tests against published values, determinism check, artifact manifest | Metric code reproduces a published BM25 number on one dataset within 1 point; a deliberately wrong ranker fails the tests; every adapter reads its gold fields without loss (300 sample rows each). Otherwise stop and fix the instrument first. |
| **1** (2–3 days) | Run S0, B1, B2, B3, B4 on the public suite, nothing tuned | Recorded as the reference table. No decisions taken from it except the MDE and the baseline spread. |
| **2** (2–3 days) | Load mMARCO Italian and the 30 frozen internal items; run the locator property test over the 5,978 compiled claims. No collection, no annotation | The Italian split loads with its qrels and reproduces the published BM25 run within tolerance; the locator test finds the quote at the cited offsets for 100% of claims, and page/section mismatches are enumerated by class. Otherwise the instrument is wrong, not the system. |
| **3** (5–7 days) | Implement S1–S5 one at a time, ablated on dev only | Each step must beat the previous one by ≥1.0 metric point on dev with a CI excluding 0, or it is dropped and reported as a negative result. |
| **4** (1 day) | Unseal, one run of the best dev system and of B5, full statistics | Non-inferiority vs B3 on the three **primary** datasets; the secondary sets are reported with their intervals and gaps. If non-inferiority fails on two or more primaries, the SOTA claim is withdrawn from the README and replaced by the measured statement. |
| **5** (2 days) | Public report, reproduction script, README numbers | A reader with the repo and no credentials reproduces every table. If not, the report is not published. |

**Kill criterion (declared in advance).** If, after Phase 3, no system beats S0
by the Phase-3 rule on the public dev splits, the work stops, the negative result is
published, and the product keeps its current wording — which claims grounding,
not retrieval. That outcome is acceptable and is written here so it cannot be
quietly renegotiated later.

## 9. Threats to validity, and the counter for each

| Threat | Effect | Counter |
|---|---|---|
| no authored gold | the metric can only speak about public tasks | the five product shapes are covered by the primary datasets; the 30 internal items are labelled development-exposed and are never a gate |
| substring matching rewards lucky quotes | inflated hits | token-overlap matching plus a 10% blinded audit of both hits and misses |
| the internal 30 were used during development | optimistic | reported separately and never used for a gate; every gate runs on public holdouts |
| EnterpriseRAG and mMARCO publish one split | tuning leaks into scoring | fixed-seed partition committed before any run; the holdout half is scored once |
| BEIR is a well-worn benchmark | absolute numbers flatter everyone | the claim is the *delta* against BM25 and dense baselines measured in our own harness, not the absolute position |
| embedding model trained on web text | hides domain gaps | dense baselines are only a comparison, never a component of the product claim; ablation with a second encoder |
| the verifier is ours | self-graded grounding | independent human audit on a sample, plus ALCE-style citation metrics |
| claim segmentation changes retrieval units | mixing two variables | S0–S3 all use the same compiled artifact; segmentation is not touched in this protocol |
| small internal set | wide intervals on our own documents | it is a regression check, not a gate; the public suite carries the statistical weight, with CIs and MDE reported |
| one model, one run | no generalisation | model identity recorded; every system in the suite is model-free or locally pinned |

## 10. Cost and time

- Public suite: downloads and CPU only. **$0 of paid API**: corpora are indexed as
  text, queries are local.
- B5 (LLM RAG) is the only paid run: the 30 frozen internal questions plus a
  250-question sample of the public holdouts, capped at **$30** and declared
  before the run; if the cap is hit, the run stops and reports what it has.
- Nobody writes questions. The only human time is the blinded grounding audit
  (§4): a 10% sample, about **two hours of reading**. If nobody can do it, the
  audit is reported as missing and the grounding number is labelled
  verifier-only — it is not quietly dropped.
- End to end: ~3 weeks part-time, most of it downloads, CPU and statistics.
- **Hardware, declared:** 12 cores, 30 GB RAM (18 free in practice), 4 GB GPU,
  145 GB free disk. That is enough for BM25 over every corpus in the suite and for
  the cross-encoder on the top 50, and it is *not* enough to embed 8.8M Italian
  passages. The Italian dense comparison therefore runs on the declared sub-corpus
  above; saying otherwise would be a number nobody could reproduce.
- No spend outside the Phase-10 numbers. A run that would exceed them is an
  amendment, not an overrun.

## 11. Decisions, fixed now

These three are fixed **before Phase 0 runs**, so that nothing in this protocol
can be adjusted after a number is seen. The owner may amend any of them before
the first measurement; an amendment after it is a new protocol, with its own
date.

1. **Non-inferiority margin: δ = 2.0 nDCG@10 points and 2.0 pp EvidenceRecall@12.**
   A product judgement ("below two points a reader cannot tell"), not a
   statistical one.
2. **README wording if Phase 4 passes**, for configuration D: *"Evidence
   retrieval within 2 points of a hybrid dense baseline, every statement
   verbatim-grounded, no neural component and no paid call at query time."* If L
   ships instead, the last clause becomes *"no remote model and no paid call at
   query time"*, and the determinism claim is dropped. If Phase 4 fails:
   *"retrieval is not competitive; grounding is."*
3. **The only spend: up to $30** for the LLM-RAG baseline (B5), capped and
   declared before the run. Everything else is downloads and CPU at $0. If the
   cap is not authorised, B5 is dropped and the grounding comparison is against
   the deterministic verifier only — reported as such.

Nothing above is measured. The criteria in §4, §5 and §11 were written before any
number; §12 records what the instrument did when it was finally pointed at data.

## 12. Phase-0 record, measured 2026-11-15

Phase 0 asks one question: *is the instrument real?* Three things had to hold —
the metric layer reproduces a published number, every adapter reads its gold
without loss, and the citation locators in our own compiled corpora address the
text they cite. All three were checked before any system was scored.

### 12.1 It reproduces a published number

`benchmark/retrieval/baselines.py --reproduce` — Lucene BM25 (`k1 = 0.9`,
`b = 0.4`), Porter stemming, Lucene stop words, title and text indexed as two
fields with the scores summed: the BEIR/Anserini configuration.

| dataset | queries | documents | nDCG@10 | published | difference |
|---|---|---|---|---|---|
| BEIR/SciFact | 300 | 5,183 | **0.6614** | 0.665 | −0.0036 |

Gate (|difference| ≤ 1.0 point): **PASS**. Artifact:
`artifacts/reproduce-scifact.json`.

The variants below were measured **after** the gate passed. They are recorded for
transparency only; none of them selected the baseline configuration, a threshold
or a criterion, and the pre-registered configuration stays the multi-field one.

| configuration | nDCG@10 |
|---|---|
| single field, Porter, Lucene stop words | 0.6796 |
| single field, Porter, no stop words | 0.6819 |
| single field, English stemmer, Lucene stop words | 0.6813 |
| single field, no stemming, Lucene stop words | 0.6616 |
| **multi-field, Porter, Lucene stop words (pre-registered)** | **0.6614** |
| multi-field, no stemming, Lucene stop words | 0.6392 |

What this says: separating title from text costs about 1.8 points here
(0.6796 → 0.6614), and that 1.8 points is the difference between passing and
failing a one-point gate. The published 0.665 is a property of the *field layout*
as much as of BM25, and a harness that reproduces the number without reproducing
the layout has reproduced something else.

### 12.2 The locator property test passes on both compiled corpora

Coordinate space, restated because it is the trap: `char_start`/`char_end` index
`norm(raw)` — curly quotes and dashes folded to ASCII, every whitespace run
collapsed to one space, stripped — not `kb/text/*.txt`. A page number comes from
the form feeds in the raw extraction, so a document without form feeds cannot
legitimately carry one. The checker reimplements the folding independently of
`documents.text.norm`, and a test asserts the two agree on every source file, so a
bug inside `norm` shows up as a disagreement instead of hiding from its own check.

| corpus | claims | evidence | offset | page | section | heading crossings |
|---|---|---|---|---|---|---|
| demo (`examples/demo-corpus/kb`) | 5,680 | 6,457 | 6,457/6,457 | 5,346/5,346 | 6,457/6,457 | 0 |
| pilot (private corpus, `ONTOSKILLS_PILOT_CORPUS`) | 298 | 388 | 388/388 | 388/388 | 388/388 | 6 in 2 spans |

The pilot's six crossings are one compiler defect class, enumerated rather than
hidden: in two documents of the pilot, two spans (S0004 and S0017) each contain a
heading that opens the next section, so the span belongs to two sections and no single `section_path` is
right. They are reported as `heading_crossing`, which is not a citation failure;
what would be a failure is the checker assuming they cannot exist.

### 12.3 Every adapter reads its gold without loss

`adapters.py --check`, one run, exit 0. Artifact:
`artifacts/instrument-check.json`, which carries a digest of every question set so
a later drift is visible.

| dataset | questions | answerable | unanswerable | gold units | scoped |
|---|---|---|---|---|---|
| EnterpriseRAG-Bench | 500 | 480 | 20 | 742 | 0 |
| BEIR/SciFact | 300 | 300 | 0 | 339 | 0 |
| ContractNLI (test) | 2,091 | 1,188 | 903 | 2,404 | 2,091 |
| QASPER (test) | 1,451 | 1,352 | 99 | 3,726 | 1,451 |
| RAGBench (`emanual`, test) | 132 | 132 | 0 | 870 | 132 |
| mMARCO Italian (dev) | 6,980 | 6,980 | 0 | 7,437 | 0 |

### 12.4 The traps the adapters found

Each of these was a real defect in the first version of the loader, and each would
have produced a plausible number:

- **EnterpriseRAG-Bench `info_not_found`.** The 20 abstention rows carry
  `answer_facts` that are instructions to the answerer ("state that this is not
  answerable"), not content. Kept as gold they would let a system score by echoing
  the instruction, so they are dropped and the rows are marked unanswerable — the
  abstention metric is what scores them.
- **ContractNLI is not corpus-level retrieval.** The same hypothesis is true of
  hundreds of NDAs, so no ranking over 607 documents could reach its own ideal.
  The task scored is within-document clause retrieval over the document's own
  `spans`, which is what the annotators marked. `NotMentioned` pairs become the
  unanswerable half. The evidence spans exist only in the original release, not in
  the HF conversions, so the adapter reads the authors' zip.
- **QASPER evidence is not only paragraphs.** 222 of the citations name a section
  heading and the rest include figure and table captions, which the dataset writes
  as `"FLOAT SELECTED: <caption>"`; 78 answerable annotations cite nothing at all.
  Headings and captions are indexed as units, the `FLOAT SELECTED:` prefix is
  stripped, whitespace is squashed before comparing (the extractor and the
  annotator wrap lines differently), and the 78 evidence-less answers are excluded
  from evidence recall rather than counted as misses nobody could fix.
- **RAGBench sentence keys already carry their document index** (`"0a"`, `"2e"`),
  so prefixing the index again produced keys that resolved for nothing. Nine of
  the 870 relevance keys in `emanual` carry a trailing full stop (`"0b."`); that
  one variant is retried and nothing else is.
- **mMARCO's `dev` files are misnamed.** `italian_queries.dev.tsv` holds 101k
  queries in MS MARCO's *train* id space, with `qrels.dev.tsv` pairing to them
  (55k judged). The standard 6,980-query dev evaluation — the one every mMARCO
  number is quoted on — is the `.small` pair. The first version silently measured
  a different, non-comparable set.

### 12.5 The tests that make the checks mean something

132 unit tests, 131 green and one that skips itself when the two local corpora are
absent, all without a GPU, a network call or an API key:

| file | tests | what makes them tests and not assertions |
|---|---|---|
| `test_retrieval_metrics.py` | 28 | every metric is compared with a value computed by hand in the test, and a deliberately reversed ranker must lose |
| `test_retrieval_locator.py` | 19 | a shifted offset, an edited quote, a wrong page, a wrong section and a non-span range must each be caught by name |
| `test_retrieval_partition.py` | 15 | an edited partition file, a changed question set and a changed stratum must each be refused |
| `test_retrieval_runner.py` | 15 | a missing or drifted partition stops the run instead of scoring; an empty corpus is refused rather than scored as zeros; a question with facts and no gold document scores on what it has and is listed; a scoped question never retrieves its out-of-scope distractor; a backwards ranker moves the digest and loses points |
| `test_retrieval_baselines.py` | 31 | four workers must produce a bit-identical index — including one built with the Italian analyser, whose language must reach the worker or serial and parallel builds disagree; a cached index must be the same index; an edited corpus, a different analysis and a truncated cache file must each miss; one 2,000-character token must not inflate the cache; the fast top-k path must return exactly what `metrics.rank` returns, down to the tie it cuts; the Italian gate must fail on a corpus that is not the published one; and editing one stop word must invalidate the cached index, because a key that cannot see the analyser is a verification that verifies nothing |
| `test_retrieval_summarize.py` | 9 | the spread is the best minus the worst, the pairing uses the intersection of the questions each system scored, and Holm never lowers a p-value |
| `test_retrieval_dense.py` | 15 | RRF is checked against a value computed by hand; a truncated embedding cache and a wrong-width one must each miss; a reranker may reorder only what it read, and never promote an unread document over a read one |

Three gaps were found by these tests, all in the harness rather than in the
datasets. `partition.verify` compared assignments but not strata, so moving every
question into one stratum passed. `runner.run` let a missing partition file
surface as a bare `FileNotFoundError`, which reads like a bug; it is now a
refusal that names the command that fixes it, because a split nobody wrote down
is not a split. And metric availability was assumed per dataset rather than per
question, so a question carrying gold facts but no gold document — 10 of
EnterpriseRAG-Bench's 480 answerable ones — aborted the run inside `ndcg`.

### 12.6 The baseline had to be made fast before it could be run at all

The first attempt to score EnterpriseRAG-Bench did not fail a gate, it failed to
finish: after fifteen minutes it was still tokenising, and a profile put the full
corpus at **seventeen hours**. A baseline nobody can afford to run is not a
baseline, so three things were fixed — and each fix is bounded by a test that it
changed no number.

| what was slow | measured | after |
|---|---|---|
| `datasets` streaming, per row | 31 ms/document → 4.3 h | parquet read in batches, 0.07 ms/document (×440) |
| pure-Python Snowball, per token | 76 µs/token → 12.6 h | memoised by surface form, 4.7 ms/document (×19) |
| one core, rebuilt every run | 40 min × every run | process pool above 2,000 documents, and a cached index |

The three fixes meet at one design point: the index is built by **one chunked
code path**, serial when there is one chunk and pooled when there are more, with
workers keeping local vocabularies that the parent merges *in document order*. The
global term numbering is therefore the same as a serial build's — which is why
`test_a_parallel_index_is_bit_identical_to_a_serial_one` can assert equality of
the vocabulary, the postings and the idf, rather than the weaker "the scores
agree". The cache is keyed by a SHA-256 over every document id and text **and over the
analyser's own behaviour** — stemmer, tokeniser, elision rule and the stop set's
contents — so a cached index cannot be a stale one; a truncated cache file is a
miss. The second half was added on 2026-11-16 and it is worth saying why: the key
used to be a description string, which stayed identical when the analyser under it
changed, so a re-run after an analyser fix would have reproduced the old index and
been read as a verification of the new analyser. A test now edits a stop list and
requires a cache miss. The key also stopped carrying `k1` and `b`: they score the
postings rather than build them, so a sensitivity probe over them now reuses the
index instead of rebuilding it once per value. A test asserts that too.

Measurements, this machine:

| | first build | from cache |
|---|---|---|
| EnterpriseRAG-Bench, 511,958 documents, BM25 porter-stop | 588 s | 265 s |
| peak RSS | 16.2 GB | 11.1 GB |
| index cache on disk | 1.22 GB | — |

That row said 5.5 GB until 2026-11-16, which was true of the older index
encoding and stopped being true when `4910220` replaced it: the same corpus and
analyser now occupy 1.22 GB. The figure was left behind by that commit rather
than measured again.

What proves the speed-up is not a redefinition:

- `baselines.py --reproduce` still returns **nDCG@10 = 0.6614** (was 0.6614), and
  now takes 27.5 s instead of 89.0 s.
- The two ERB runs — built and cached — produced the same ranking digest
  `20d04ea5763fefcd` and identical per-metric values.
- `adapters.py --check --only enterpriserag` returns the same question digest
  `d9e53820d4d84736` through the parquet loader as through the streaming one.

One measurement from that smoke run belongs in §4 rather than here: BM25 over ten
whole ERB documents scores `answer_fact_coverage = 0.9459`. That is the
saturation §4 warns about — ten documents contain almost any fact's tokens — and
it is why the metric is reported and not gated at document granularity.


## 13. Phase-1 record: the reference table

Phase 1 is "run S0, B1, B2, B3, B4 on the public suite, nothing tuned", and its
only outputs are the baseline spread and the MDE. Everything in 13.1–13.5 was
written **before** the first dense number existed, because a model choice, a cut
and a fusion constant are exactly the things that can be tuned afterwards to make
a claim survive.

### 13.1 What the public suite can measure, and what it cannot

On the public datasets there is no claim layer: the retrieval unit is the
dataset's own (passage, paragraph, document). **S0 and B1 are therefore the same
run there**, and the difference between them is identically zero by construction.
The public suite measures the *backends* — lexical, dense, hybrid, reranked. The
value of the claim layer is measured where claims exist, in Phase 2 (the Italian
corpus with claims) and Phase 3 (ablations), not here.

Writing that down prevents the most likely misreading of the table: a reader
seeing B1 − S0 = 0 must not conclude the claim layer adds nothing.

### 13.2 The dense model: which of the two §6 allows, and why

§6 allows "BGE-M3 or E5-large, pinned". The choice is `intfloat/e5-large-v2` at
revision `f169b11e22de` (resolved 2026-11-15), 1024 dimensions, 512-token cut.
BGE-M3 is 568M parameters and multi-vector; on the 4 GB card this harness runs
on it cannot cover a 512k-document corpus at any usable rate, and a baseline that
cannot cover the corpus is not a baseline.

Three details that are part of the model, not of the wiring:

* **E5's prefixes.** `query: ` and `passage: ` are applied (`ModelSpec`), because
  E5 without its prefixes is a several-point loss that reads as "dense is weak".
* **The cut is 512**, the model's own maximum. It truncates, so truncation is
  measured rather than assumed away: `dense.py --stats` reports, on a
  deterministic 500-document sample, the share of documents longer than the cut.
  That share is reported next to every dense number, because a corpus that is
  60% truncated makes the dense baseline a statement about its first 512 tokens.
* **Normalized embeddings, cosine via dot product**, float32, on the corpus in
  id order, in fixed batches. The embedding cache is content-addressed over the
  model revision, the cut and every document's text.

Throughput measured on this machine before committing to a plan: **4.4
documents/second** (fp32, batch 16, 512 tokens, Quadro T2000 4 GB). Half
precision is *slower* here (1.5 docs/s), so fp32 is used — a decision that
changes no number.

### 13.3 Fusion and rerank constants

| constant | value | why this value |
|---|---|---|
| RRF `k` | 60 | Cormack et al. 2009; the published default, not tuned here |
| rerank depth | 50 | §6 says "top 50"; fixed there before this file existed |
| cross-encoder | `cross-encoder/ms-marco-MiniLM-L-6-v2` @ `233902d2`, 512 tokens | the standard pair for this depth; small enough to run where the bi-encoder does |

`reciprocal_rank_fusion` is written here and checked against a value computed by
hand in a test, rather than imported: the fused order *is* the B3 number.

### 13.4 What determinism means for a float matmul

BM25 is bit-identical, including across machines, and the tests assert it. A
dense ranking is not claimed to be: float matmul order depends on BLAS and on the
device. What is claimed is that **the same machine and the same library build
reproduce the same ranking**, which `metrics.ranking_digest` makes checkable in
one rerun, and that the cache cannot be a stale one — it is keyed by the corpus
text and the model revision, and a truncated cache file is a miss, not a crash.

This is a weaker claim than BM25's, and it is the strongest one available.

### 13.5 What this machine cannot run, stated as arithmetic

At 4.4 documents/second, measured above and before any dense run:

| corpus | documents | projected encode time | verdict |
|---|---|---|---|
| SciFact | 5,183 | 20 min | run |
| ContractNLI | 10,061 | 38 min | run |
| RAGBench | 3,916 | 15 min | run |
| QASPER | 28,355 | 1 h 47 min | run |
| EnterpriseRAG-Bench | 511,958 | **32 h** | not run here |
| mMARCO Italian | 8,840,000 | **23 days** | not run here |

Two consequences, both uncomfortable and both better stated now than discovered
in Phase 4:

1. **The dense baseline on EnterpriseRAG-Bench is out of reach of this machine.**
   It is one of the three primary datasets, so the Phase-4 non-inferiority claim
   against B3 cannot be evaluated on it without a rented GPU. The public table
   will say so in the cell, and the claim is scoped to the datasets where B3
   exists.
2. **The Italian proxy keeps BM25 only.** mMARCO's Phase-2 gate asks that the
   Italian split load with its qrels and reproduce the published BM25 run — it
   never required dense — so this costs the gate nothing, but it does mean no
   dense number is claimed for Italian.

An estimate converted into a decision *here*, with the hardware named, is not a
result being explained away later.

### 13.6 The lexical column, measured

BM25 (k1 = 0.9, b = 0.4, Porter + Lucene stop words), dev split, k = 10,
`sha256-rank-alternate-v1` partition. Intervals are paired bootstrap, 10,000
resamples, over questions.

| dataset | scored | unanswerable | no gold doc | nDCG@10 [95% CI] | recall@10 | digest |
|---|---|---|---|---|---|---|
| SciFact | 150 | 0 | 0 | **0.6828** [0.6195, 0.7434] | 0.8091 | `ac8b1e7f98981df5` |
| EnterpriseRAG-Bench | 241 | 10 | 5 | **0.5433** [0.4880, 0.5975] (n = 236: five of them carry no gold document) | 0.6307 | `512a555b51455966` |
| ContractNLI | 594 | 452 | 0 | **0.5641** [0.5381, 0.5900] | 0.7006 | `abfae64dd971ac27` |
| RAGBench | 66 | 0 | 0 | **0.6175** [0.5602, 0.6736] | 0.5978 | `3e027f2c3e5a40b3` |
| QASPER | 676 | 50 | 0 | **0.4090** [0.3850, 0.4334] | 0.5900 | `1ed5346306d5a042` |

mMARCO Italian is Phase 2 and is not in this table.

SciFact's dev figure, 0.6828, is *not* comparable with the Phase-0 reproduction
figure of 0.6614: that one is the published 300-query BEIR evaluation, this one
is the 150-query dev half. Both are recorded rather than one being presented as
the other.

EnterpriseRAG-Bench also carries the answer-level metrics, which no other public
dataset in the suite has: `answer_fact_coverage` 0.9300, `answer_fact_support`
0.8037, `numeric_congruence` 0.9506 (n = 241). The first is the saturated one of
§4 and is not gated; it is in the table because omitting it would look like a
choice made after seeing it.

Two structural facts, recorded because they explain a number that otherwise looks
like a bug: 452 of ContractNLI's 1,046 dev questions are unanswerable by
construction (the three-label NLI task), so 594 are scored; 10 of
EnterpriseRAG-Bench's 251 dev questions are `info_not_found`, and 5 of the 241
answerable ones name a fact with no source document — they are scored on the
answer-level metrics and listed under `no_gold_docs` in the artifact.

### 13.7 The table, measured

Same corpus, same queries, same split, same k = 10 for all four systems. Systems:
`bm25` (§13.6), `dense` (B2), `hybrid` (B3, RRF k = 60), `hybrid-rerank` (B4,
cross-encoder over the fused top 50). Artifact: `artifacts/phase1-summary.json`;
per-question receipts in `runs/` (ignored by git, reproducible).

| dataset | system | n | nDCG@10 [95% CI] | recall@10 | digest |
|---|---|---|---|---|---|
| SciFact | bm25 | 150 | 0.6828 [0.6195, 0.7434] | 0.8091 | `ac8b1e7f98981df5` |
| SciFact | dense | 150 | 0.7270 [0.6672, 0.7851] | 0.8437 | `ece997fadc9db47e` |
| SciFact | hybrid | 150 | **0.7365** [0.6810, 0.7904] | 0.8887 | `d69bea38f1d2b476` |
| SciFact | hybrid-rerank | 150 | 0.7055 [0.6453, 0.7642] | 0.8351 | `4f31642c66ae143b` |
| ContractNLI | bm25 | 594 | 0.5641 [0.5381, 0.5900] | 0.7006 | `abfae64dd971ac27` |
| ContractNLI | dense | 594 | 0.5134 [0.4883, 0.5388] | 0.6957 | `db1037e47c5c91ae` |
| ContractNLI | hybrid | 594 | **0.5832** [0.5583, 0.6077] | 0.7356 | `42b70888d572fb32` |
| ContractNLI | hybrid-rerank | 594 | 0.5821 [0.5571, 0.6067] | 0.7356 | `021f25ffcea4829c` |
| QASPER | bm25 | 676 | 0.4090 [0.3850, 0.4334] | 0.5900 | `1ed5346306d5a042` |
| QASPER | dense | 676 | 0.4764 [0.4525, 0.5003] | 0.6547 | `88df39ba61524bff` |
| QASPER | hybrid | 676 | 0.4789 [0.4556, 0.5030] | 0.6716 | `c45097fa9e58191d` |
| QASPER | hybrid-rerank | 676 | **0.4932** [0.4690, 0.5183] | 0.6728 | `fb601f3220cc5aa7` |
| RAGBench | bm25 | 66 | 0.6175 [0.5602, 0.6736] | 0.5978 | `3e027f2c3e5a40b3` |
| RAGBench | dense | 66 | 0.6451 [0.5954, 0.6936] | 0.6593 | `e0ba0ec247701f25` |
| RAGBench | hybrid | 66 | 0.6526 [0.6015, 0.7030] | 0.6544 | `8550e0d8a9424faa` |
| RAGBench | hybrid-rerank | 66 | **0.6668** [0.6130, 0.7187] | 0.6518 | `a43a9d3d4c4dd1d6` |
| EnterpriseRAG-Bench | bm25 | 236 | 0.5433 [0.4880, 0.5975] | 0.6307 | `512a555b51455966` |
| EnterpriseRAG-Bench | dense, hybrid, hybrid-rerank | — | **not run here** (§13.5: 32 h of GPU on this machine) | — | — |

Paired differences against the lexical baseline, with the MDE of each comparison
and Holm across the four datasets that have one:

| dataset | comparison | Δ nDCG@10 [95% CI] | MDE | p (Wilcoxon) | p (Holm) | spread |
|---|---|---|---|---|---|---|
| SciFact | dense − bm25 | +0.0442 [+0.0022, +0.0859] | 0.0603 | 0.0284 | 0.0569 | 0.0537 |
| SciFact | hybrid − bm25 | +0.0537 [+0.0269, +0.0810] | 0.0383 | 0.0001 | **0.0004** | 0.0537 |
| SciFact | hybrid-rerank − bm25 | +0.0227 [−0.0182, +0.0627] | 0.0576 | 0.2874 | 0.2874 | 0.0537 |
| ContractNLI | dense − bm25 | −0.0507 [−0.0755, −0.0258] | 0.0352 | 0.0000 | **0.0001** | 0.0698 |
| ContractNLI | hybrid − bm25 | +0.0191 [+0.0050, +0.0330] | 0.0199 | 0.0165 | **0.0330** | 0.0698 |
| ContractNLI | hybrid-rerank − bm25 | +0.0180 [+0.0037, +0.0321] | 0.0202 | 0.0303 | 0.0607 | 0.0698 |
| QASPER | dense − bm25 | +0.0675 [+0.0440, +0.0904] | 0.0330 | 0.0000 | **0.0000** | 0.0842 |
| QASPER | hybrid − bm25 | +0.0700 [+0.0548, +0.0851] | 0.0215 | 0.0000 | **0.0000** | 0.0842 |
| QASPER | hybrid-rerank − bm25 | +0.0842 [+0.0678, +0.1004] | 0.0234 | 0.0000 | **0.0000** | 0.0842 |
| RAGBench | dense − bm25 | +0.0276 [−0.0190, +0.0740] | 0.0669 | 0.1723 | 0.1723 | 0.0493 |
| RAGBench | hybrid − bm25 | +0.0352 [+0.0059, +0.0646] | 0.0432 | 0.0192 | **0.0330** | 0.0493 |
| RAGBench | hybrid-rerank − bm25 | +0.0493 [+0.0113, +0.0868] | 0.0546 | 0.0024 | **0.0071** | 0.0493 |

Four findings, none of them tuned for:

1. **The hybrid is the strongest system on every dataset where it runs**, and it
   beats lexical search by 1.9 to 7.0 points with Holm-adjusted p ≤ 0.033 on each.
   The non-inferiority target of §6 is therefore a real baseline, not a straw one.
2. **Dense alone loses 5.1 points on ContractNLI** while winning elsewhere. That
   dataset is a within-document clause-matching task: a bi-encoder asked for a
   single passage vector blurs a clause with the contract around it, while exact
   clause wording is exactly what lexical matching is good at. A dense baseline
   that won everywhere would have been suspicious.
3. **The cross-encoder helps only where the fusion is open-domain**: +1.4 points
   over hybrid on QASPER and +1.4 on RAGBench, −3.1 on SciFact and −0.1 on
   ContractNLI. The two datasets where it hurts are the two whose candidates are
   ranked *within a document* (§7), so the reranker is reordering near-duplicates
   of the same source with 512-token truncation. Reported as measured; nothing in
   the protocol predicted the sign.
4. **The spread between the four systems, per dataset, is 4.9 to 8.4 points.** With
   a pre-registered δ of 2.0 points (§11), a system sitting 2 points above the
   baseline is inside the spread of the baselines themselves — which is why the
   gate is a paired comparison and not a comparison of means.

### 13.8 What Phase 1 bought, and the one thing it changed

§8 says Phase 1 may decide nothing except the MDE and the baseline spread. Here
they are, and the second one has a consequence that must be written before Phase 3
runs rather than after it disappoints.

**Measured MDE** (nDCG@10, α = 0.05 two-sided, 80% power) for the comparisons
above: **2.0 to 6.7 points**. The paired difference between lexical and hybrid is
the least correlated pair available in this table, so these are upper bounds on
what a Phase-3 comparison will face.

**Power at δ.** With δ = 1.0 point as the protocol's bar, the power to detect a
true effect of exactly δ in these comparisons is **7% to 29%**:

| dataset | comparison | MDE | power at δ = 1.0 pt |
|---|---|---|---|
| ContractNLI | hybrid − bm25 | 0.0199 | 0.29 |
| QASPER | hybrid − bm25 | 0.0215 | 0.26 |
| SciFact | hybrid − bm25 | 0.0383 | 0.11 |
| RAGBench | hybrid − bm25 | 0.0432 | 0.09 |
| SciFact | dense − bm25 | 0.0603 | 0.07 |
| RAGBench | dense − bm25 | 0.0669 | 0.06 |

That is the honest reading of a dev split of this size, and it is not a reason to
move δ. Lowering the bar after seeing that it is hard to clear is the exact move
§11 exists to prevent. Three consequences, fixed now:

1. **δ stays at 1.0 point.** It is the materiality bar: a gain smaller than that
   does not change the product's sentence.
2. **A Phase-3 step that does not clear the bar is reported as "not established",
   with its CI and its MDE — never as "no effect", and never dropped.** At this
   power, a null result at 1 point is uninformative, and saying so is the result.
3. **The remedy for weak power is more questions, not a smaller bar.** If a step
   lands at +1 point with a CI that straddles zero, the answer is to add the pooled
   secondary datasets to the *MDE* — pooled by family, never pooled into the gate,
   because the datasets answer different questions and averaging them would let a
   good QASPER hide a bad ContractNLI.

Phase 3 starts from this table, with the numbers in `artifacts/phase1-summary.json`
and the reproduction path in `--reproduce` and `runner.py` unchanged.

## 14. Phase-2 record: the Italian analyser, against a published number

§8 asks Phase 2 to show that the harness is not an English instrument. This is
that record: one gate on one dataset, not a system comparison — and the reason it
is not a comparison is the arithmetic already written down in §13.5, not a
shortage of enthusiasm.

### 14.1 What is being checked, and what is not

mMARCO Italian is 8,841,823 passages (3.4 GB) with the 6,980-query `dev.small`
set. Both sides are machine-translated and the judgements stay the English ones,
so it is a proxy for Italian, not a native benchmark. It is also the only public
Italian passage-retrieval set carrying a published BM25 row, which is exactly
what an instrument gate needs: a number we did not produce.

Published (Bonifacio et al., arXiv:2108.13897, Table 2, the Google Translate
row): BM25 **MRR@10 = 0.153**, **R@1000 = 0.753**. That table's English row is
0.184, the same number Anserini's MS MARCO passage regression reports at
k1 = 0.9, b = 0.4 — which is why this gate uses the parameters the BEIR gate
already used instead of a set tuned for this corpus.

Two things this is not. **It is not a comparison**: at the measured 4.4
documents/second, the dense column on 8.8M passages is 23 days on this machine
(§13.5), so no dense and no hybrid number exists for Italian, and the Italian
half of §3 is a lexical statement. **It is not a holdout**: the gate scores all
6,980 queries against the published pair, so those queries are spent. mMARCO is
an instrument check and stays out of every Phase-3/4 comparison; saying it now is
cheaper than discovering it when someone wants a clean split later.

### 14.2 The analyser, and the two places it differs from Lucene's

Lucene's `ItalianAnalyzer` — what Pyserini applies for `--language it` — is, read
from the source rather than remembered: `StandardTokenizer` → `ElisionFilter` with
the 21 `DEFAULT_ARTICLES` (a `CharArraySet` built with `ignoreCase = true`, which
is why a sentence-initial `Dell'articolo` is elided there too) → `LowerCaseFilter`
→ `StopFilter` with the 279-word Snowball Italian list that ships inside Lucene →
`ItalianLightStemFilter`. Everything in that chain is reproduced. Two
approximations are declared, and the gate is what bounds their combined size.

**Word boundaries are `[^\W_]+`, not UAX #29.** Hyphenated compounds split in both
(`e-mail` → `e`, `mail`); numeric sequences do not (`3.14`, `1.000` are two tokens
here and one there), and an apostrophe-joined non-elision stays whole in Lucene and
splits here. This is the same tokeniser the English gate uses, and that gate
reproduces 0.6614 against 0.665 — so the approximation is validated where it can
be validated, and replacing it now would break Phase-1 comparability for a
difference smaller than the tolerance it already clears.

**Snowball `italian` instead of `ItalianLightStemFilter`**, the more aggressive of
the two, declared before the measurement. It is the deviation to hold in mind for
§14.3, because it predicts a direction: more stems means a wider candidate pool and
more collisions.

Both stop lists are copied verbatim and a test asserts their sizes (279 and 21),
because a stop list that drifts is a number that drifts.

#### What writing this section found

**The articles were in the wrong place.** They had been added to the *stop set*,
which deletes them wherever they appear, instead of implemented as an elision rule,
which deletes them only before an apostrophe. Eight of the twenty-one are not in
the 279-word list (`coll`, `pell`, `gl`, `d`, `m`, `s`, `t`, `v`), so standalone
tokens Lucene keeps were being dropped: **0.11% of all tokens** in a
200,000-passage sample — 13,648 of 12,052,063, mostly `s` and `d` from
abbreviations like `s.` and `d.`. Elision is now a rule over the text and the stop
set is the 279 words; §14.4 reports what the correction moved instead of quietly
replacing the number with the better one.

**The cache key could not see the analyser.** The key was the analyser's
description string, which does not change when the code under it does — so the run
meant to verify this fix would have reloaded the index built before it and
reproduced the old number, and that rerun would have been read as a verification.
The key is now a fingerprint of the analyser's behaviour (§12.6), and a test edits
one stop word and requires a cache miss.

**The workers had no language.** They rebuild the analyser from their payload
instead of receiving it, and the payload did not carry the language, so every
worker would have indexed Italian with the English stop list while the parent's key
claimed `lucene-italian`. The language travels with the chunk now, and a test
builds 2,100 Italian documents serially and through the pool and requires a
bit-identical index.

### 14.3 Measured, before the correction

This is the run made while the analyser was wrong in the three ways §14.2
describes. It is kept rather than replaced: it is what a description-keyed cache
would have gone on reporting, and §14.4 measures the distance between it and the
corrected one. Nothing in this section is superseded as a *description of this
run*; the number to quote is in §14.4.

Configuration: `stemmer=italian stopwords=lucene-italian k1=0.9 b=0.4`,
retrieval depth 1,000. One run, `--reproduce-marco --workers 4`.

| metric | measured | published | difference | gate (\|Δ\| ≤ 0.01) |
|---|---|---|---|---|
| MRR@10 | 0.1478 | 0.153 | −0.0052 | PASS |
| R@1000 | 0.7614 | 0.753 | +0.0084 | PASS |
| nDCG@10 | 0.1829 | — | — | reported, not gated |

The corpus and the cost, so the next person can plan rather than discover:
8,841,823 passages, 1,299,318 distinct terms, **250,171,784 postings** (28.3 per
passage, mean length 37.4 tokens). Index build **885 s** with four workers
(9,990 passages/s); scoring 6,980 queries **1,325 s** (0.19 s each, through the
`top_ids` path that avoids a million-entry dict per query); load 71 s; whole run
**2,280 s — 38 minutes — peak RSS 12.7 GB**. The index cache is **2.19 GB**, so a
second run skips the build and pays only the scoring. Ranking
digest of the top-10 lists, all 6,980 of them: **`2e06af8bb33f2af7`** — the
pre-fix digest, replaced in §14.4 by `152ba964950ad159`.

Two differences, opposite signs, one mechanism: Snowball stems more
aggressively than ItalianLight, which widens the candidate pool — R@1000 goes up
— and adds lexical collisions that push a relevant passage a place or two down —
MRR@10 goes down. That is a hypothesis that fits both signs; it is not something
this run alone proves, and it is not a reason to switch stemmers after seeing the
numbers. What the run does prove is narrower and sufficient: the Italian path —
tokeniser, stop list, stemmer, worker payload, exact top-k on 8.8M passages —
lands inside the same 0.01 that §12.1 fixed for English, on a corpus 17× the size
of EnterpriseRAG-Bench.

**Determinism, measured rather than asserted.** A second run — the index read
back from the cache in 99 s instead of 885 s, then the same 6,980 queries — gives
the same digest, `2e06af8bb33f2af7`, and the same three metrics to four decimals:
1,492 s and 9.3 GB peak. So the number is a property of the corpus and the
analyser, not of the build that happened to produce the index, and the cache is
the same index rather than a similar one.

The tolerance was not adjusted for this row. On a 0.153 baseline, 0.01 is 6.5%
relative — looser than the BEIR gate's 1.5% — and it is the tolerance that was
already fixed, which is the only defensible reason to use it. Including R@1000 in
the gate is what keeps a single loose metric from hiding a systematic shift: a
stemmer that bought recall by reorganising everything would show as one difference
large and positive and the other large and negative.

### 14.4 What the correction moved, measured

Two runs of the same command, on the same machine, with a cold index both times.
Between them: the elision rule, the stop set's contents, the language in the
worker payload and the cache key. Nothing else changed.

| metric | §14.3, pre-fix | corrected | published | difference | gate (\|Δ\| ≤ 0.01) |
|---|---|---|---|---|---|
| MRR@10 | 0.1478 | **0.1479** | 0.153 | −0.0051 | PASS |
| R@1000 | 0.7614 | **0.7617** | 0.753 | +0.0087 | PASS |
| nDCG@10 | 0.1829 | 0.1831 | — | — | reported, not gated |
| ranking digest | `2e06af8bb33f2af7` | `152ba964950ad159` | — | — | changes by construction |

The bug cost 0.0001 MRR and 0.0003 recall. The index grew from 250,171,784 to
250,636,962 postings, +0.19%, with six more distinct terms and a mean length of
37.4337 against 37.4. So the 0.11% of tokens that were being dropped were, for
this gate, invisible — and a tolerance of 0.01 on a 0.153 baseline, 6.5% relative,
was never going to see a token-level difference. What catches it is the assertion
on the stop list's 279 words and the elision rule's own tests. Passing a gate is
evidence about a system, not a proof about its parts, and this is the row where
that distinction has a number attached.

The cost of being correct, same corpus, same four workers:

| | pre-fix | corrected |
|---|---|---|
| index build | 885 s (9,990 passages/s) | 1,651 s (5,355 passages/s) |
| scoring, 6,980 queries | 1,325 s | 1,619 s |
| load | 71 s | 98.5 s |
| whole run | 2,280 s | **3,369 s — 56 minutes** |
| peak RSS | 12.7 GB | 12.7 GB |
| index cache on disk | 2.19 GB | 2.19 GB |

Elision is a regex pass over every passage before it is tokenised, and it is not
free. On a 60,000-passage sample of the same collection (21.3M characters), with
the stemmer off so only tokenisation and the elision rule are in play, the analysis
step measures 10.57 s with the rule, 5,678 passages/s, against 6.90 s without it,
8,697 passages/s: ×1.53, with the substitution alone accounting for 4.42 s. The
build grew by ×1.87, not ×1.53, and the scoring phase of the same run grew 22%
against an index 0.19% larger. Those two ratios multiply to 1.87, which fits, but
it is an inference from one run each, not a decomposition: the analyser and the
machine are both candidates and nothing here separates them, though the run below
sizes the machine's part at 11% of a scoring phase on identical postings. What is
measured, and what a plan should use, is the shipped configuration: 56 minutes
cold, 28 of them scoring, and a cache key that now changes when the analyser does.

**Determinism, on the corrected analyser.** A second run with the index read back
from the cache returns the same digest, `152ba964950ad159`, and the same three
metrics to four decimals: load 77.2 s, cache read 108.3 s, scoring 1,448.0 s,
**1,633.5 s in total — 27 minutes — peak 9.3 GB**. The number is therefore a
property of the corpus and the analyser, not of the build that produced the index,
and the cached file is the same index, not a reconstruction of it. The scoring phase
was also 171 s faster than in the cold run, on the same 6,980 queries and the same
postings: an 11% run-to-run spread that has nothing to do with the analyser, and
that is the honest size of the machine component the cost table above cannot
separate.

**The control.** EnterpriseRAG-Bench was re-run with a cold cache after the change,
on the same day. Its analyser is unchanged, and so is its output: digest
`512a555b51455966` and the same figures to four decimals as §13.6 and §13.7 —
nDCG@10 0.5433, recall@10 0.6307, MRR@10 0.5470, hit@10 0.6992,
`answer_fact_coverage` 0.9300, `answer_fact_support` 0.8037,
`numeric_congruence` 0.9506 — in 740.5 s end to end, peak 11.8 GB. The fingerprint
also says why: `_ELISION.pattern` enters the key only for a language in `ELIDING`,
so the English cache key did not move and the Italian one did. The two files under
`~/.cache/ontoskills-bench/index/` are `9697242d…` for EnterpriseRAG-Bench (1.22 GB)
and `ba9335a6…` for mMARCO (2.19 GB), which is how a later run can be checked
against the right index instead of a similar one.

To quote: **0.1479 / 0.7617**. §14.3 stays as the record of the run that was
wrong, including its digest, so an old table can be recognised as old rather than
argued with.
