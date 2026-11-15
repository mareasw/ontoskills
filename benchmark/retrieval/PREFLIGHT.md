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

**Status 2026-11-15:** Phase 0 is closed and recorded in §12. All six adapters
pass `--check`; the metric layer reproduces Anserini BM25 on SciFact within one
point (0.6614 vs 0.665); the locator property test finds every quote at its cited
offset on both compiled corpora. Phase 1 (the baseline table) has not started.

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
| pilot (`pilot/kb-final5`) | 298 | 388 | 388/388 | 388/388 | 388/388 | 6 in 2 spans |

The pilot's six crossings are one compiler defect class, enumerated rather than
hidden: `POLICY-0001` S0004 and S0017 each contain a heading that opens the
next section, so the span belongs to two sections and no single `section_path` is
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

88 unit tests, all green without a GPU, a network call or an API key:

| file | tests | what makes them tests and not assertions |
|---|---|---|
| `test_retrieval_metrics.py` | 28 | every metric is compared with a value computed by hand in the test, and a deliberately reversed ranker must lose |
| `test_retrieval_locator.py` | 19 | a shifted offset, an edited quote, a wrong page, a wrong section and a non-span range must each be caught by name |
| `test_retrieval_partition.py` | 15 | an edited partition file, a changed question set and a changed stratum must each be refused |
| `test_retrieval_runner.py` | 12 | a missing or drifted partition stops the run instead of scoring; a scoped question never retrieves its out-of-scope distractor; a backwards ranker moves the digest and loses points |
| `test_retrieval_baselines.py` | 14 | four workers must produce a bit-identical index, a cached index must be the same index, and an edited corpus, a different analysis and a truncated cache file must each miss |

Two gaps were found by these tests, both in the harness rather than in the
datasets. `partition.verify` compared assignments but not strata, so moving every
question into one stratum passed. `runner.run` let a missing partition file
surface as a bare `FileNotFoundError`, which reads like a bug; it is now a
refusal that names the command that fixes it, because a split nobody wrote down
is not a split.

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
agree". The cache is keyed by a SHA-256 over every document id and text, so a
cached index cannot be a stale one; a truncated cache file is a miss.

Measurements, this machine:

| | first build | from cache |
|---|---|---|
| EnterpriseRAG-Bench, 511,958 documents, BM25 porter-stop | 588 s | 265 s |
| peak RSS | 16.2 GB | 11.1 GB |
| index cache on disk | 5.5 GB | — |

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

