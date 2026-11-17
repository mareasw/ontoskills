# The semantic-layer comparison

`benchmark/retrieval/PREFLIGHT.md` answers one question: given a corpus and a
question set, does the compiled claim layer reach the evidence as well as
keyword search, dense retrieval and their fusion. That is the baseline question.
It is not the commercial one.

The commercial question is: **a company already has documents, and there are
several products that promise to turn them into a layer an LLM can reason over.
Why this one?** Answering it needs a different measurement: the cost of building
the layer, the quality of what it answers, and what the artifact can do that the
others cannot. That is what this directory measures.

Nothing here is scored against a model's opinion. Every number is either a token
count from the provider, a byte count, a wall clock, or a lexical recall against
gold facts written by the dataset's authors.

## 1. What the pilot decides

The pilot is descriptive on purpose. It answers three questions with money
already spent, not with arithmetic:

1. does every candidate system ingest the same corpus at all;
2. what does each one actually consume, in tokens, minutes and bytes;
3. is the spread wide enough, on these questions, that the full run (every
   question, six systems, three repeats) is worth its budget.

It therefore has **no pass/fail bar**. A bar comes before the full run, in a
section appended to this file before the first full-run number exists, exactly
as `PREFLIGHT.md` §11 does for the retrieval claim. Fixing a bar now, on n = 8
per kind, would be picking a threshold from noise.

## 2. The corpus

The corpus is a deterministic slice of EnterpriseRAG-Bench (`MIT`,
Sun et al. 2026, arXiv:2605.05253): synthetic enterprise documents with gold
questions, gold documents and gold answer facts. Synthetic matters twice — the
licence genuinely allows redistribution, and no customer text is anywhere near
this repository.

Measured on the dataset:

| | |
|---|---|
| questions | 500, of which 480 answerable |
| questions naming a gold document | 470 |
| distinct gold documents behind those questions | 722 |
| gold answer facts | 2,407 |

So the question set rests on 722 documents, not on the 511,958 that make the
corpus. A slice is not a shortcut here; it is the whole question set over
six-hundredth of the material.

**Selection rule.** The 200 questions are stratified by kind, proportional to
how many of each kind the dataset carries, with the largest remainder allocated
by kind name. Within a kind the questions are taken in the dataset's own order,
so the choice never depends on what a system finds easy. Two kinds are admitted
even though the retrieval metrics cannot score them: `high_level` names gold
facts but no document, and `info_not_found` is the abstention row. Excluding
either would drop the test a semantic layer is most likely to fail.

| kind | selected | what it tests |
|---|---|---|
| basic | 70 | a fact stated in one document |
| semantic | 50 | a paraphrase of one |
| intra_document_reasoning | 16 | clauses combined inside a document |
| project_related | 16 | context assembled across documents |
| constrained | 12 | a fact filtered by attribute |
| conflicting_info | 8 | documents that contradict each other |
| completeness | 8 | every instance, not one |
| miscellaneous | 8 | — |
| high_level | 4 | an aggregate, gold facts and no gold document |
| info_not_found | 8 | a question the corpus cannot answer |

**The slice as built.**

```
questions 200        documents 279        characters 1,835,668
corpus digest a7d3102ee17806b4
```

Rebuild it, and the digest must match:

```
python3 -m benchmark.layer.corpus --questions 200 --out /tmp/layer/corpus
```

**The leak this admits.** The corpus is the gold documents of the selected
questions. A retriever therefore never has to reject a plausible wrong document;
it has to pick the right one out of 279 documents that are all relevant to
something. That inflates every system's retrieval numbers equally, which is why
no retrieval metric is reported from this slice — only what the *layer* answers.
The full run adds a fixed sample of distractors and reports both, because a
layer that only works when the corpus is already the answer is not a layer.

## 3. Which systems are eligible

A system is in the comparison if it ingests the same folder of `.txt` files and
answers the same questions **on the same model**. Being in it does not require
being good at it.

| system | version | input | in the pilot |
|---|---|---|---|
| OntoSkills | this repository, tag recorded with the result | folder of text | **yes** |
| GraphRAG | `microsoft/graphrag` 3.3.0, PyPI | folder of text | **yes**, if a run completes within budget |
| LightRAG | `lightrag-hku` 1.5.7, PyPI | text, via its Python API | **yes**, if a run completes within budget |
| vector RAG | this repository, `bm25`/dense path | folder of text | **yes** — the floor |
| NVIDIA Auto Ontology | `NVIDIA/auto-ontology`, Apache-2.0 | **relational database connections** | **no — different task** |
| Graphify | `Graphify-Labs/graphify`, Apache-2.0 | folder of files, **through Claude Code** | **no — cannot use the declared model** |

**NVIDIA Auto Ontology: not applicable, and this is checkable.** Its own README
lists ten connectors, all of them SQL engines (PostgreSQL, MySQL, Databricks,
Snowflake, ClickHouse, Trino, Kyuubi, HeavyDB, DuckDB, SQLite); it generates an
ontology from *database metadata* and answers by writing SQL, and its evaluation
(`auto-ontology-eval`) scores Text-to-SQL on BIRD. There is no document
ingestion path to point at a folder of prose. Reporting a quality score for it
here would be measuring a different task and calling the difference a loss. It
is ruled out on input, not on quality.

**Graphify: not applicable on the declared terms.** It ships as a Claude Code
skill: extraction of concepts and relationships runs through Claude, queries run
through `/graphify query` inside the agent, and its README requires Claude Code
and Python 3.10+. It cannot be run on `deepseek-v4.1-flash` through the
OpenAI-compatible endpoint every other system uses, so admitting it would break
fairness rule 3 (same model). Its published figure — *71,5× fewer tokens per
query* — is a reduction against **reading the raw files** on a 52-file mixed
code/papers/images corpus, which is a different comparison from this one: it
measures what the graph saves an agent that would otherwise paste the corpus
into context, not what the build costs nor whether the answer carries the gold
fact. That claim is interesting and remains untested here; the honest statement
is that it is not this measurement.

**Obsidian is not in this table.** It is not a semantic layer and it does not
compile anything; Graphify exports *to* it. Comparing the two as automatic
systems would be the straw man this whole document exists to avoid. If a human
baseline is wanted, it is a separate row measured in analyst hours, and it says
so.

Both exclusions are recorded with the reason and the evidence, never as a zero
in a quality column. A system that cannot ingest the corpus is a finding, not a
loss — and a system that needs a different model to answer is not comparable on
a comparison whose whole point is that the model is held still.

**The embedding sidecar.** GraphRAG and LightRAG both require an embedding model
at build time, and the gateway exposes chat models only. Rather than drop two
systems over a sidecar, the pilot serves the model the retrieval benchmark
already uses — `intfloat/e5-large-v2` at revision `f169b11e`, 1024 dimensions,
CPU — behind `POST /v1/embeddings` (`benchmark/layer/embed_server.py`). Two
choices are declared because they are part of the measurement: every input gets
the `passage: ` prefix, identically for both systems, because neither of them
distinguishes a document call from a query call; and inputs longer than the
model's 512 tokens are truncated by the tokenizer, which is the same head-512
treatment the dense benchmark applies. OntoSkills does not use the endpoint at
all — our build takes no vectors — so it exists only so the other two can be
measured at all, and it is written here rather than left implicit.

## 4. What is measured

**Build cost** — from the provider's `usage` block, never estimated:

- input tokens and output tokens, per call, plus the HTTP status — a refused
  call stays visible in the table and costs nothing;
- cached and reasoning tokens as the gateway reports them, recorded and never
  added to the bill: `reasoning_tokens` is already inside `completion_tokens` —
  it is there to show *where* the output went, which §8 item 5 needs — and the
  price table has no cached discount, so `cached_tokens` is visibility, not a
  correction. A reply served from the local cache is counted separately as
  `replayed`, so a fresh bill is not flattered by replays. Both columns were
  added after the 279-document build: that row carries the prompt/completion
  split and is not back-filled;
- normalised dollars at **0,15 $/M in, 0,60 $/M out**, the price table at which
  the repository's existing compile figures were computed;
- wall clock to build, and the size of the artifact in bytes;
- number of model calls.

Every system is measured by the same instrument: `benchmark/layer/meter_proxy.py`
sits between the system and the gateway, forwards each request unchanged, and
appends one line per call with the tokens the gateway charged. A framework's own
accounting is recorded next to it and never used in its place — GraphRAG and
LightRAG are not asked how much they spent. The proxy also means a run that
forgets to report anything still has a cost column.

The model is `deepseek-v4.1-flash` for every system, through the same
OpenAI-compatible endpoint. Tokens are comparable because the model is; the
dollar column is a **price at a declared table**, not an invoice — this endpoint
reports `cost: 0`, so nobody "spent" anything and nobody is given credit for it.

**Answer quality** — `benchmark/retrieval/metrics.py`, reused rather than
reinvented, over the text each system returns:

- `answer_fact_coverage` — mean token recall of the gold facts against the union
  of what was returned;
- `answer_fact_support` — the same, but against the single best returned item:
  does one citation carry the fact on its own;
- `numeric_congruence` — every number in the fact appears in the evidence;
- abstention on `info_not_found`: refuses, or answers what it cannot support;
- false refusal rate on the answerable questions.

These are lexical and deterministic. The declared limitation: a correct
paraphrase scores below a verbatim quotation, so a system that copies its source
is favoured. That is mitigated, not hidden — the full run reports a 20-answer
spot check against a model judge, and the two are reported side by side.

**Two modalities, declared per run and never mixed.** A system either returns
one answer text per question (`answer`) or a ranked list of passages
(`evidence`). Coverage is measured over the union of what came back, support
over the single best item, and the list is cut at k = 10: without the cap a
system buys coverage by returning its whole corpus. A refusal is recorded as an
outcome, not as a zero-quality reply — `false_refusal_rate` over the answerable
questions and `abstention_rate` over `info_not_found` are two different
failures, and merging them would hide which one a system has.

`benchmark/layer/score.py` is the only implementation of this, and every system
is scored by the same file on the same `selection.json`.

Our own run file carries both the ranked quotes and the rendered answer, so our
row can be scored in either modality; GraphRAG and LightRAG return prose only.
The pilot therefore reports **our `evidence` row as the primary result** and, next
to the prose systems, our `answer` row as well — labelled, from the same run, so
the comparison between systems is always within one modality. A refusal from a
prose system is read out of the text by `benchmark/layer/text_refusal.py`, with
the raw answer kept in the run file; the patterns are few and specific, and the
same function is applied to both frameworks. That classification is a heuristic
and is reported as one: it decides `abstention_rate` and `false_refusal_rate`
only, never a quality score.

**Capability** — mechanical, and checkable by running the artifact, so no judge
is involved:

| probe | question |
|---|---|
| typed predicates | are statements typed, or only subject-predicate-object? |
| schema | can a validator accept or reject the artifact? |
| contradiction | can it say *which* documents disagree, and where? |
| verbatim quote | does every statement carry a quote that occurs in the source? |
| locator | does the quote resolve to a page and an offset? |
| graph | does the RDF artifact agree with its own vocabulary and with the text? |
| offline query | can a question be answered without a model call? |
| abstention | does it refuse when the corpus cannot answer? |

`benchmark/layer/capability.py` runs the artifact-side probes on a compiled
knowledge base and prints the numbers, with the two definitions it inherits from
the product named in its own output: **verbatim** is the pipeline's `norm`
(curly quotes and dashes folded to ASCII, whitespace collapsed) and the
byte-exact share is printed beside it, so a folded em dash is not sold as an
exact match; **offsets** index the normalised text, which `gaps.raw_offsets` maps
back to the bytes on disk. **graph** is a lint rather than a rate: the artifact
either agrees with its own vocabulary and its own text, or the probe names the
term that does not. It is the probe that caught `doc:hasSourceUrl` declared as a
datatype while the writer emitted an IRI, which is the class of defect a table of
percentages cannot see. The other two rows are outcomes of a run, not properties
of the artifact — **offline query** is the absence of a meter log during
`answers.py`, and **abstention** is `abstention_rate` in `score.py` — and are not
asserted here.

## 5. Fairness, written down once

1. Same corpus bytes, same 279 documents, digest published.
2. Same questions, same order, same 200.
3. Same model, same endpoint, temperature 0 where the system exposes one. A
   system that needs vectors gets the same pinned embedding model as every other
   system that needs them (§3), never a different one.
4. Tokens read from the provider's `usage`; a system that does not report usage
   is measured by the gateway, not by its own estimate.
5. Artifact size measured on disk after the build, excluding caches
   (`benchmark/layer/artifacts.py`, which reports an exclusion that matches
   nothing instead of quietly shrinking the number). A framework that leaves a
   400 MB embedding cache has not produced a 400 MB knowledge base.
6. Every run keeps its own directory: config, stdout, artifact, and the pinned
   commit of the system that produced it.
7. A run that fails is reported with its error, not deleted.
8. **Requests in flight are declared per system before its run, never more than
   eight, and only one build runs at a time.** The declared numbers are
   OntoSkills 8, the floor 0, GraphRAG 4, and the run records the number it used.
   GraphRAG's four are the build's, where the pool holds extraction and summary
   calls; the two hundred questions are asked one at a time, because local
   search is one question's latency and a pool of four would publish a
   throughput no user waits for.
   Concurrency is transport, not a quality knob, so no system is ever *rewarded*
   for asking fewer questions at once. What five attempts at GraphRAG established
   is that the ceiling was not concurrency at all: our gateway answers
   `503 upstream_unavailable` with a `retry_after_ms` of 45 000 when it is
   oversubscribed — which is what killed the first smoke at 25 in flight — and it
   closes **any non-streamed completion still running at 60 s** with
   `503 omniroute unavailable`. The second is what matters for long extractions,
   and the pilot's response is transport-level and applied to every system: `meter_proxy.py --stream-upstream` asks upstream for a stream and
   reassembles it, so a long generation is not cut at a minute, and every meter
   line records whether that happened. Transport retries remain each system's own;
   a system that turns a transient upstream error into a failed build is recorded
   as failing, with its log, and not scored as zero.
9. **The retrieval mode is declared per system, and it is the library's own
   default where the library has one.** LightRAG's adapter asks with `mix` —
   `QueryParam`'s default, which is the mode its own documentation recommends
   and the one a user gets without choosing. GraphRAG 3.3 ships no query CLI and
   therefore no default: its four search methods are a Python API and picking one
   is a real decision, not an implementation detail. The primary row is `local`,
   entity-anchored retrieval — the closest analogue to a compiled knowledge base
   answering one question — and `global`, which map-reduces community reports, is
   a different query shape; it is run as its own row over the corpus-level kinds
   (`completeness` and `high_level`, 12 questions) and never mixed into the
   primary number. A mode sweep on all 200 questions is future work, priced
   before it runs, for the same reason the abstention gate needs a disjoint
   split: choosing a mode on the questions it will be scored on is fitting.

## 6. Budget

The first real run replaced the estimate, and the two disagree by a factor of
eight. That is the reason the smoke run exists.

**Measured**, five documents, `deepseek-v4.1-flash`, 22,992 characters, final
configuration (`--chunk-size 15`, `--max-tokens 32000`, `--resume`):

| | measured | what the estimate said |
|---|---|---|
| calls | 21 | 8 |
| input tokens | 29,225 | 8,110 |
| output tokens | 115,243 | 16,400 |
| normalised cost | **0,0735 $** | 0,020 $ |
| claims | 144 | — |
| wall clock | 1,077 s serial for the first pass | — |

The 21 calls are not 21 chunks. Eight extract claims, five are the conflict pass
that sends each document's own claims back to the model, and the rest are splits.
The conflict pass is the call the estimate did not know about.

The ceiling matters. At 10,000 the same five documents produced 129 claims and
two replies were cut mid-JSON; at 16,000, 141 claims and one cut; at 32,000, 144
claims and none — and it cost *less*, because a wasted truncated reply is money
spent for claims that never arrive. A cut reply is not a cheap reply, it is a
reply with claims missing, so the pilot uses 32,000.

**Measured on the whole slice** — 279 documents, 1,835,668 characters, all
attempts included (one run was stopped at 18:08 after eleven documents and
resumed from its own cache):

| | |
|---|---|
| calls | 880 |
| input tokens | 1,418,617 |
| output tokens | 6,497,798 |
| normalised cost | **4,1115 $** |
| of which replayed from cache | 0,2092 $ (5%) |
| claims | 9,295 |
| verifier | 9,104 `ok`, 108 `weak`, 83 `no` |
| truncated chunk calls | 0 |
| truncated conflict passes | 5 |
| wall clock | 2 h 12 min |
| artifact on disk, caches excluded | 52,2 MB in 288 files |

The two projections said 4,60 $ and 5,90 $; the build cost 4,11 $. Both were
above the measurement because both scaled output per character, and the model
does not spend its output evenly: a conflict pass that gets cut off early, and a
document whose extraction the model answers briefly, both cost less than the
average. The pilot publishes the run's number, not the projection — the
projection's job was to decide whether to press the button.

**Per claim.** 9,295 claims for 4,11 $ is 0,00044 $ per claim, and 0,70 model
calls per claim; the artifact is 5,6 kB of JSONL per claim once caches are
excluded.

**Throughput**, measured on 24 documents (178,767 characters) with
`--concurrency 8` on a freshly cached corpus:

| | |
|---|---|
| wall clock | 17 min 39 s |
| per document | 44 s |
| 279 documents | **~3,4 h** |
| cost at the declared table | 0,444 $, which projects to **~4,60 $** |
| claims | 950, of which 946 verified `ok` and 4 `weak` |

The eight-times gap is a price at a table nobody bills. The real cost is the wall
clock: three hours on one machine, against a day if the documents were compiled
in a queue. Two independent projections put the build between 4,60 $ and 5,90 $
at the declared table; the pilot publishes the measured number from the full
build, not the projection.

`--concurrency` bounds the calls in flight. The pool holds documents, because a
corpus of short documents is one chunk each — parallelising chunks inside a
document leaves every worker but one idle. A single document still uses the
intra-document pool, which is the only parallelism it has.

A second, independent route gives the same input figure: building every chunk
prompt of the 279 documents and dividing by the measured 3,92 characters per
token gives 953 k tokens of prompt, and the smoke run shows that the control
calls and the retries multiply prompt traffic by 2,44 — 2,33 M. Two methods, one
number.

**Why the estimate was low.** `--estimate` counts the chunk prompts and adds 40
tokens per call. It does not count the conflict pass, which sends the whole
document's claims back to the model, and it does not know that this model's
completion includes `reasoning_tokens`. Output is 94% of the bill, so a ratio
assumed for Phase 1 was the whole error.

**What the dollars are.** The gateway reports `cost: 0`, so this comparison
spends nothing: the figures above are the same work priced at the declared table
(0,15 $/M in, 0,60 $/M out), which is what makes systems comparable. No budget
approval is consumed by running it; the machine time is the real constraint, and
`--concurrency` now fills the pool with documents, not with chunks.

| item | as measured or as it stands |
|---|---|
| our build, 279 documents | **4,11 $** at the declared table, 2 h 12 min |
| one competitor, same corpus | 13-18 $ projected for LightRAG from one measured document; GraphRAG running |
| pilot, three systems | **23-30 $** at the declared table (ours 4,11 measured; GraphRAG 6-8 and 13-18 LightRAG projected), 0 $ billed |
| full run, six systems, three repeats | 150-400 $ at the declared table, 0 $ billed |

The full run's number is the one to re-derive from the pilot, not to trust: it is
the reason the pilot exists. The one system whose cost this pilot cannot state
from a finished build is LightRAG, and §7 says what that costs and why it is a
decision rather than a default.

## 7. What the pilot measured

The tables below are not typed by hand. `benchmark/layer/report.py` renders them
from the meter logs, the build records and the score files, and every figure in
this section can be regenerated from the artifacts in `runs/`. A system whose
run is missing gets an em dash and its note — never a zero, which would read as a
bad score instead of an absent one.

<!-- PILOT-TABLE -->

## Build

| system | modality | calls | failed | in | out | $ at table | build | artifact |
|---|---|---:|---:|---:|---:|---:|---|---|
| ontoskills | evidence | 880 | 0 | 1 418 617 | 6 497 798 | 4,1115 | 2 h 12 min | 52,2 MB |
| graphrag | answer | — | — | — | — | — | — | — |
| lightrag | answer | — | — | — | — | — | — | — |
| vector-rag-floor | evidence | 0 | 0 | 0 | 0 | 0,0000 | 3 s | 2,0 MB |

## Query

| system | query calls | failed | in | out | $ at table | median reply |
|---|---:|---:|---:|---:|---:|---:|
| ontoskills | 0 | 0 | 0 | 0 | 0,0000 | 418 ms |
| graphrag | — | — | — | — | — | — |
| lightrag | — | — | — | — | — | — |
| vector-rag-floor | 0 | 0 | 0 | 0 | 0,0000 | 4 ms |

## Quality on the pilot slice

| system | n | k | chars | coverage | support | numeric | false refusal | abstention |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| ontoskills | 200 | 10 | 5 097 | 63,9 % | 46,6 % | 79,7 % | 0,0 % | 0,0 % |
| graphrag | — | — | — | — | — | — | — | — |
| lightrag | — | — | — | — | — | — | — | — |
| vector-rag-floor | 200 | 10 | 45 885 | 92,4 % | 77,7 % | 94,1 % | 0,0 % | 0,0 % |

## By question kind

**ontoskills**, by question kind (evidence, k=10):

| kind | n | coverage | support | numeric | refused |
|---|---:|---:|---:|---:|---:|
| basic | 70 | 70,1 % | 53,5 % | 83,7 % | 0,0 % |
| semantic | 50 | 59,7 % | 42,3 % | 70,1 % | 0,0 % |
| intra_document_reasoning | 16 | 67,6 % | 51,5 % | 79,2 % | 0,0 % |
| project_related | 16 | 60,0 % | 41,9 % | 88,2 % | 0,0 % |
| constrained | 12 | 51,8 % | 33,0 % | 71,0 % | 0,0 % |
| conflicting_info | 8 | 53,1 % | 41,0 % | 86,5 % | 0,0 % |
| completeness | 8 | 68,7 % | 48,5 % | 70,8 % | 0,0 % |
| miscellaneous | 8 | 66,4 % | 43,0 % | 93,8 % | 0,0 % |
| high_level | 4 | 53,3 % | 35,2 % | 100,0 % | 0,0 % |
| info_not_found | 8 | — | — | — | 0,0 % |

**vector-rag-floor**, by question kind (evidence, k=10):

| kind | n | coverage | support | numeric | refused |
|---|---:|---:|---:|---:|---:|
| basic | 70 | 94,1 % | 81,4 % | 93,9 % | 0,0 % |
| semantic | 50 | 91,2 % | 75,2 % | 90,5 % | 0,0 % |
| intra_document_reasoning | 16 | 95,8 % | 81,7 % | 97,9 % | 0,0 % |
| project_related | 16 | 94,3 % | 81,0 % | 99,1 % | 0,0 % |
| constrained | 12 | 86,2 % | 69,3 % | 94,6 % | 0,0 % |
| conflicting_info | 8 | 85,6 % | 69,8 % | 92,1 % | 0,0 % |
| completeness | 8 | 95,4 % | 78,4 % | 93,8 % | 0,0 % |
| miscellaneous | 8 | 93,1 % | 75,6 % | 100,0 % | 0,0 % |
| high_level | 4 | 79,8 % | 59,2 % | 100,0 % | 0,0 % |
| info_not_found | 8 | — | — | — | 0,0 % |

## Notes

- **graphrag** — build running since 21:09; no row until it finishes and the questions are asked
- **lightrag** — one document measured (0,0639 $, 597 s); full build not run, projected 13-18 $ and 12-23 h

<!-- /PILOT-TABLE -->

The 418 ms on the `ontoskills` row is `ontocore ask`'s per-question cost with the
corpus already in memory — the path the pilot was scored on. The same ranking,
served by the MCP over the same 200 questions, costs **3,5 ms p50 and 5,2 ms p95**
and returns the same claim ids in the same order; §10 is that measurement and the
eight gates it had to pass first.

### The floor is the strongest thing on this table, and that is the finding

On EnterpriseRAG-Bench's lexical metrics, a chunk-and-BM25 floor — 2,55 seconds
to build, zero model calls, zero dollars, 4 ms per question — covers **92,4 %**
of the gold facts at k=10, and our compiled layer covers **63,9 %**. Its support
(best single passage) is 77,7 % against our 46,6 %. The layer that costs 4,11 $
to build and 52,2 MB to keep is *behind* the free baseline on both numbers.

This is not a bug in the measurement, and the pilot does not hide it. Two things
explain it, and both are worth stating plainly:

1. **Volume.** At k=10 the floor returns a median of **45,885 characters**; we
   return **5,097**. Lexical coverage counts characters, so the floor starts the
   comparison with nine times our text. Holding the volume constant as well as
   `k` (`score.py --max-chars`) shrinks the gap but does not close it:

   | budget | ontoskills coverage | ontoskills support | floor coverage | floor support |
   |---:|---:|---:|---:|---:|
   | 5 000 chars | 62,2 % | 45,9 % | 71,1 % | 70,9 % |
   | 10 000 chars | 63,9 % | 46,6 % | 79,0 % | 74,5 % |
   | 20 000 chars | 63,9 % | 46,6 % | 87,0 % | 76,6 % |
   | 45 000 chars | 63,9 % | 46,6 % | 91,9 % | 77,6 % |

   Our curve is flat because ten quotes are five thousand characters: above that
   line the budget has nothing left to give us. The floor's curve keeps climbing
   because every extra character is more source text.

   A diagnostic, not the protocol: asked for **30** quotes instead of ten — the
   bound was fixed at ten before any run — our coverage rises from 63,9 % to
   **77,0 %** at a median of 14,557 characters, while the floor at the same volume
   reaches 83,9 % coverage and 76,0 % support against our 49,8 %. So the ranking
   is not broken and the shortfall is not only volume: at equal characters the
   floor still covers more gold text and supports it better.

2. **The metric is lexical.** A gold fact is a fragment of the source, and any
   chunk that contains that sentence scores for it. A claim layer does something
   different and, on this metric, worse: it ranks claims, returns the one span
   each claim stands on, and refuses to show the other four sentences of the
   paragraph. What it buys is not coverage. It is that the sentence is quoted, the
   quote resolves to an offset, and the claim is typed.

That is the honest reading, and it changes the public claim. **"Not inferior to a
BM25 baseline" is false on this table and must not be written anywhere.** What
the pilot supports is narrower and still worth having:

| what the layer adds | measured |
|---|---|
| every accepted quote is verbatim in the source | 12,310 of 12,310 under the declared normalisation |
| every accepted quote resolves to its offsets | 12,310 of 12,310 exactly |
| quotes that also match byte-for-byte | 2,192 of 12,310 (17,8 %) |
| claims linked to a claim they contradict | 150 claims in 82 pairs; none across documents — see below |
| predicates carrying a modality and an actor | 39,9 % (all 9,295 carry a modality; 3,676 carry an actor) |
| graph agrees with its own vocabulary and its own text | 100 % — every `doc:` term declared, 254 of 254 sections titled, 12,327 of 12,327 locators with offsets reproduce their quote read back out of the graph (94 quotes carry none) |
| model calls at query time | 0, at 0,42 s per question |
| build cost / artifact | 4,11 $ / 52,2 MB for 9,295 claims |

**How sure is one run.** The table reports means over 192 questions, and a mean
without an interval is a point pretending to be a measurement.
`benchmark/layer/interval.py` resamples the questions — not the facts, because the
facts of one question come from the same documents and are covered together — for
5,000 draws with a fixed seed, so the bounds are a property of the data and two
invocations print the same ones. The two systems are compared question by
question, which is what a paired design asks for:

| | ontoskills | floor | difference |
|---|---:|---:|---:|
| coverage | 63,9 % [61,7; 66,1] | 92,4 % [91,5; 93,1] | **−28,4 pp [−30,4; −26,4]** |
| support | 46,6 % [44,3; 48,8] | 77,7 % [76,3; 79,1] | **−31,1 pp [−33,0; −29,1]** |
| numeric | 79,7 % [75,3; 84,1] | 94,1 % [91,1; 96,7] | −14,5 pp [−18,2; −10,9] |

So the ordering on this slice is not a sampling artefact: the paired intervals do
not cross zero, and the coverage gap is 28 points wide with a two-point margin on
each side. What the interval does **not** cover is the build: one build exists per
system, and a bootstrap over questions cannot invent the variance of a build that
was never run. Repeat builds are in the budget of the full run (§6), not of this
pilot.

Two of those rows are the ones a lexical metric cannot see and a reader of an
answer can: a quote you can open at a page and an offset, and a claim whose
subject and modality are separated from its prose.

One caveat on those two 100 % rows, because a 100 % invites it: the probe
applies the *same* rule the artifact's verifier applies, so the number says the
two agree — every quote the build kept is one the probe also finds — not that a
third party re-read the sources. What makes it worth publishing is the other
half of the same probe: on the whole artifact, including the 83 claims the
verifier rejected, verbatim falls to 99,2 % and the 94 quotes that fail belong
to exactly those 83 claims. Their spans are not contiguous in the source — 17
paragraphs that join blocks across an intervening heading — so the quote is a
real piece of the document that cannot be found as one substring of it. The
probe can fail, and it fails where the audit says it should. The byte-exact row
is the one nobody can accuse of circularity: 17,8 % of the quotes are literal
substrings of the raw file, and the rest only match after the declared
normalisation (curly quotes, dashes, collapsed whitespace), which is a product
definition the reader can check against `compiler.documents.text.norm`.

### What the pilot cannot claim yet

- **Contradictions are intra-document only.** 150 links, none of them between two
  documents, because the conflict pass reads one document's claims at a time. A
  corpus whose documents disagree with each other is exactly the case the feature
  is for, and it is not what this pass does. Fixing it is a product change, not a
  threshold.
- **Our system never abstains** (finding 4). 0 % on the eight `info_not_found`
  questions, and the same rule applies: a gate is fixed on a disjoint half first.
- **The floor's numbers are a ceiling for lexical metrics, not a floor for
  quality.** Nothing here says the floor answers better; it says it *covers* more
  gold text, which is what these three metrics count.
- **LightRAG has no finished row**, and the reason is cost: one document of 8,839
  characters measured 0,0639 $ (clean run, streamed) and took 597 s at two calls
  in flight, which projects to 13-18 $ and 12-23 h for 279 documents — 46 h if the
  build were held to two in flight, which was a caution taken while GraphRAG was
  running, not a property of the system. The decision, and the price of each
  alternative, is in §7.1.

### 7.1 The LightRAG decision, with its price on the table

| option | what it produces | cost at the declared table | wall clock |
|---|---|---:|---|
| full build, 279 documents | a scored row, comparable to the other two | ~13-18 $ | 12-23 h |
| declared subset, 40 documents | a row with a published digest and a smaller n | ~2,6 $ | 2-3 h |
| no build, measured single document | a cost row only: "0,0639 $ per document, one measured" | 0 $ more | none |

The subset is not the same thing as the full build and the table would have to
say so in its note: a 40-document subset has a different corpus digest from the
other rows, so its quality number answers a different question. A cost row with
no score is honest and comparable; a scored row on a different corpus is honest
only if the label is loud.

**Decision: the third option.** LightRAG stays a measured cost per document,
with no scored row. Two reasons, and neither survives being bought with time:
the full build costs **4,3 times our own** (17,8 $ against 4,11 $), and the row it
would produce is not comparable to ours anyway — it answers in prose, we return
evidence, and §5 forbids the cross-modality comparison. The transport fix in §8
item 6 does change the wall clock, from 46 hours at two calls in flight to 12-23
hours at four to eight, and that is worth stating plainly because it removes the
one part of the argument that was about patience rather than about value: the
build is affordable in time. It is the bill, and what the row would answer, that
decide it. The single document that was measured — 0,0639 $, one document,
counted by the same meter — is what the table publishes, and its note says
exactly that.

## 8. Status

- [x] corpus builder, deterministic and tested
- [x] scorer, deterministic and tested
- [x] slice built, digest `a7d3102ee17806b4`
- [x] cost estimated without a model call
- [x] smoke run on five documents, measured against the estimate (and the
      estimate was wrong by 8× — see §6)
- [x] our full build on the 279 documents: 9,295 claims, 4,11 $, 2 h 12 min,
      49,4 MB at build time, `prompt_hash` unchanged
- [x] the document vocabulary moved to its own namespace and its own spec —
      `core/src/specs/documents.ttl`, prefix `doc:`, version 1.0.0 — and `graph.ttl`
      regenerated from the same claims at zero model cost: `claims.jsonl` digest
      unchanged, 146,073 → 196,814 triples, and the 254 sections plus 12,421
      structured locators the old writer had flattened into a string are now
      resources. The artifact grew to 52,2 MB in the same 288 files; §5's rule 5
      is what that column means, so it is the artifact on disk and not the one the
      build wrote.
- [x] capability probes on the full knowledge base: verbatim and locator 100 %
      on the claims the verifier accepted, and the graph probe passing — every
      `doc:` term declared, 254 of 254 sections titled, 12,327 locators
      reproducing their quote when read back out of `graph.ttl` instead of out of
      `claims.jsonl`
- [x] the floor, measured over the whole slice at zero cost
- [x] answers to the 200 questions, scored in both modalities, no model at query
      time
- [ ] GraphRAG: ingest the folder and answer the 200 questions — needs the
      stream-upstream transport of §8 item 6, running
- [x] LightRAG: decided against the full build, with the measured cost published
      (§7.1)
- [x] pilot table rendered from the artifacts (§7)
- [x] the read path served by `ontomcp` in Rust, the compiler left in Python
      (`docs/adr/0003-documents-in-the-mcp-runtime.md`): 200 of 200 questions
      rank identically through the MCP, 279 of 279 documents tokenise
      identically, no quote outside its offsets, no knowledge-base file
      modified, the same answers inside an empty network namespace, p95 5,5 ms
      against a 300 ms gate — §10

### What the smoke run found, and what it cost to find

1. **The estimate was low by a factor of eight.** `--estimate` counts chunk
   prompts; the build also sends a conflict pass over every document's claims,
   and this model's completion includes reasoning tokens. The estimate now says
   so, and §6 carries the measured number.
2. **`raise --max-tokens` did nothing.** The cache key covered the prompt and the
   model but not the output ceiling, so a truncated reply was replayed as a hit
   and the advice in the truncation error was inert. Fixed: a cache record now
   stores its ceiling, and a truncated reply is reused only when the ceiling has
   not grown. Two tests pin it.
3. **`--concurrency` filled the pool with the wrong thing.** It parallelised the
   chunks of one document while the documents themselves were compiled in a
   queue, so a corpus of short documents — one chunk each — gained nothing. The
   pool now holds documents. Two tests pin the overlap and the determinism.

Findings 2 and 3 are product defects that a five-dollar smoke run paid to
expose. That is what the pilot is for.

4. **Our own system never abstains.** Asking the two `info_not_found` questions
   produced ten citations each, with BM25 scores (12,3 and 14,0) as high as the
   answerable questions' — so this is not a threshold set too low, it is a
   missing gate. The pilot reports that as it is: `abstention_rate` 0 % on our
   row. A gate cannot be tuned on the eight questions that will be reported,
   because picking the threshold after seeing them is the leak this whole
   document exists to avoid. If a gate is added, the rule and its threshold are
   fixed on a disjoint half of the question set first, and the number reported
   is the other half.

### What the competitor smoke runs found, before any of them was scored

5. **This model spends most of its output on reasoning, and both frameworks
   assume it does not.** One GraphRAG extraction returned 603 characters of
   entities with `completion_tokens` 2,630, of which 2,466 were
   `reasoning_tokens`; two other units answered the whole extraction prompt with
   the twelve characters `<|COMPLETE|>` and spent 2,336 tokens saying nothing.
   Output is where the money is, so a ceiling tuned on a summarising model
   truncates this one while it is still thinking — and a framework that reads
   "no entities in the reply" as "the pipeline is broken" turns that into a
   failed build. GraphRAG does exactly that
   (`graphrag/index/workflows/extract_graph.py`, which raises *Graph Extraction
   failed. No entities detected during extraction* when the merged table has no
   rows), so a document the model found empty aborts a build that had already
   paid for every other document's extraction. The smoke run is recorded as a
   failure with its log, not as a zero.
6. **The gateway's ceiling is a timeout, not a concurrency limit.** GraphRAG's
   default is 25 requests in flight, and at 25 the gateway answered `503
   upstream_unavailable` with `retry_after_ms: 45 000` — which is what rule 8
   in §5 is about. But the 503s that actually stopped the build were not about
   concurrency. **Every non-streamed completion still running at 60,1 s is
   answered `503 omniroute unavailable, retry later`**, and the identical
   request streamed returns 200 after 111 s with 9 000 output tokens; four
   streamed generations in flight then finished together in 88-119 s. The
   gateway says so itself: while it waits it sends `id: chatcmpl-keepalive`
   frames with an empty `choices` list, which only makes sense on a connection
   it intends to hold open. Streaming is the supported path for a long
   generation; a non-streamed one is cut at a minute. GraphRAG's extraction
   asks for 5-30k output tokens and routinely needs more than a minute — an
   answer of 6,000 tokens took 56 s when asked by hand — so it was being
   scored against a transport limit rather than against its quality. Measured
   before the cause was known: four in flight made no progress (24 calls, 23
   refusals, one unit extracted in nine minutes), two in flight got one call
   in six through, one in flight got the short calls and lost the long ones.
   Every one of those numbers is a 60-second timeout, not a queue. The pilot's
   answer is `meter_proxy.py --stream-upstream`: the proxy asks upstream for a
   stream and reassembles the chunks into the single body the client asked
   for, for every system alike, and every line records that it did it
   (`upstream_streamed`). A framework with no streaming option for extraction
   is then measured on its extraction, not on our gateway. Our own compile ran
   eight non-streamed calls in flight for two hours without one 503 because
   none of its calls took a minute; the limit is per call, not per system,
   which is why it is stated here as a transport fact rather than hidden in a
   config. The meter records the HTTP status of every call, so a refused call
   appears in the cost table with its `failed` count instead of vanishing from
   a log that only counted tokens — and a 503 costs nothing, which is the only
   reason this lesson was cheap.

7. **LightRAG validates the embedding batch against the OpenAI default.** Its
   `openai_embed` is decorated with `embedding_dim=1536` and raises *Embedding
   dimension mismatch* on the flush, after the extraction has been paid for. The
   sidecar returns 1,024 dimensions for every system, so the adapter calls the
   undecorated function (`.func`) and declares the dimension once, where §3
   declares it. One document of 8,839 characters then ingests completely.
   It also produced the pilot's one number that a second measurement moved a
   long way, which is worth writing down. The first run — before the transport
   fix in item 6 — made 58 requests of which 25 recorded no usage at all, and
   billed **0,0816 $**: a run losing calls to the 60-second cut and paying for
   the retries. The clean rerun, streamed at two in flight, made **12 calls,
   48,813 input and 94,366 output tokens, 0,0639 $**, in 597 s, with no refusal:
   six chunks, 116 entities, 233 relations. That is the number the table
   publishes. Projected over the corpus two ways: **17,8 $** if every document
   cost what this one did, **13,3 $** by character count — the corpus mean is
   6,579 characters against this document's 8,839, so the honest range for the
   279 documents is **13-18 $**, not the 22,8 $ the first measurement suggested.
   Twelve calls for six chunks is also the shape of the cost: extraction asks for
   entities and relations per chunk with one gleaning pass, and the merge phase
   that reconciles 116 entities and 233 relations across chunks makes no model
   call at all. What is expensive is the extraction, not the summarising.

8. **The conflict pass is a third of our own bill.** Over 24 documents it cost
   0,1367 $ of the 0,4439 $ build — 215,948 output tokens for 47,835 input,
   against 950 claims from the extraction pass. Its output per document has a
   median of ~4,000 tokens for a JSON array of claim-id pairs, and 2 of the 24
   documents ran to the 32,000 ceiling; a reply cut mid-JSON yields no pairs at
   all, so those two calls were paid for and bought nothing. Capping the pass at
   8,000 tokens would have saved roughly a seventh of the build and would also
   have truncated the three documents that spent 8,500-11,900 tokens and
   returned usable pairs. That is a real trade in *capability* — contradiction
   links are one of the probes in §4 — so the ceiling stays where it was
   measured, and lowering it is future work to be chosen on a disjoint split,
   for the same reason as the abstention gate in finding 4.


## 9. Reproduce

In order, with the pins that matter. `set -a; . ./.env; set +a` loads
`OPENAI_BASE_URL`, `OPENAI_API_KEY`, `OPENAI_MODEL`; the graphrag and lightrag
interpreters are their own, because the two libraries disagree about their
dependencies. Everything below writes to `/tmp/layer`, so nothing here touches
the repository.

```
# 1. the slice: 200 questions, 279 documents, and the digest that proves it
python3 -m benchmark.layer.corpus --questions 200 --out /tmp/layer/corpus
#    -> questions 200, documents 279, characters 1,835,668, digest a7d3102ee17806b4

# 2. embeddings, pinned, on CPU: every system uses this one endpoint
python3 -m benchmark.layer.embed_server --port 8091

# 3. the meter; every paid call in the pilot goes through it
python3 -m benchmark.layer.meter_proxy --port 8094 --upstream "$OPENAI_BASE_URL" \
    --label build --log /tmp/layer/meter-build.jsonl \
    --append --capture-failures /tmp/layer/failures.jsonl --stream-upstream
```

`--stream-upstream` is not a convenience. The gateway realises a 60-second
ceiling on a non-streamed reply and answers 503 past it, which for a long
extraction means paying for retries that were never the model's fault (§8, item
6). Without the flag the costs in this document are not reproducible; with it
they are, and the meter records `upstream_streamed` on every line so the two
kinds of run can be told apart after the fact.

**Ours**, then every other system, then the scoring:

```
export OPENAI_BASE_URL=http://127.0.0.1:8094/v1     # so the build is metered
ontocore ingest /tmp/layer/corpus -o /tmp/layer/kb --resume
python3 -m benchmark.layer.answers --kb /tmp/layer/kb \
    --selection /tmp/layer/corpus/selection.json \
    --out /tmp/layer/runs/ontoskills.answers.jsonl --limit 10
python3 -m benchmark.layer.score --selection /tmp/layer/corpus/selection.json \
    --answers /tmp/layer/runs/ontoskills.answers.jsonl --mode evidence --k 10 \
    --json /tmp/layer/runs/ontoskills.score.json
```

`--mode answer` runs on the same answers file and prints the 66,1 / 66,1 / 79,7
row quoted in §7:

```
python3 -m benchmark.layer.score --selection /tmp/layer/corpus/selection.json \
    --answers /tmp/layer/runs/ontoskills.answers.jsonl --mode answer --k 10 \
    --json /tmp/layer/runs/ontoskills.answer-mode.score.json
```

The file carries both an `answer` and its `evidence`, so the same paid run can be
read in the modality a competitor answers in without another call. Two properties
of that reading are stated rather than discovered later: the "prose" is the
artifact's own restatement of each claim next to the quote it cites, not a model's
paragraph; and `support` is measured over a single item — the whole answer — so it
equals `coverage` by construction in `answer` mode, for every system. The two
modalities are never compared to each other.

**The floor**, which costs nothing:

```
python3 -m benchmark.layer.run_floor --corpus /tmp/layer/corpus \
    --selection /tmp/layer/corpus/selection.json \
    --out /tmp/layer/runs/floor.jsonl --k 10
python3 -m benchmark.layer.score --selection /tmp/layer/corpus/selection.json \
    --answers /tmp/layer/runs/floor.jsonl --mode evidence --k 10 \
    --json /tmp/layer/runs/floor.score.json
```

**GraphRAG**, at the settings published in `benchmark/layer/config/`, behind a
meter from the first call:

```
graphrag init --root /tmp/layer/graphrag --model deepseek-v4.1-flash \
    --embedding e5-large-v2
cp benchmark/layer/config/graphrag.settings.yaml /tmp/layer/graphrag/settings.yaml
cp /tmp/layer/corpus/*.txt /tmp/layer/graphrag/input/
python3 -m benchmark.layer.meter_proxy --port 8094 \
    --upstream "$OPENAI_BASE_URL" --label graphrag-build \
    --log /tmp/layer/meter-graphrag-full.jsonl --stream-upstream &
GRAPHRAG_API_KEY="$OPENAI_API_KEY" graphrag index --root /tmp/layer/graphrag
```

The questions are a second meter in front of a second root: the build's tables
by symlink, the build's settings with one address changed. Editing the build's
own `api_base` after the fact would put a query cost inside a build cost.

```
mkdir -p /tmp/layer/graphrag-query
ln -s ../graphrag/input /tmp/layer/graphrag-query/input
ln -s ../graphrag/output /tmp/layer/graphrag-query/output
sed 's|127.0.0.1:8094|127.0.0.1:8095|' /tmp/layer/graphrag/settings.yaml \
    > /tmp/layer/graphrag-query/settings.yaml
python3 -m benchmark.layer.meter_proxy --port 8095 \
    --upstream "$OPENAI_BASE_URL" --label graphrag-query \
    --log /tmp/layer/meter-graphrag-query.jsonl --stream-upstream &
python3 -m benchmark.layer.run_graphrag --root /tmp/layer/graphrag-query \
    --selection /tmp/layer/corpus/selection.json --method local \
    --out /tmp/layer/runs/graphrag.answers.jsonl
```

Every answer is flushed as it is paid for, and `--resume` continues a run that
died — a reboot, a closed terminal — from the rows already on disk, asking only
the questions whose `qid` is missing. A half-written last line is dropped rather
than trusted: it names no question, so at most one answer is bought twice and no
truncated one is published.

Five questions first, on a third meter and the same root shape:

```
python3 -m benchmark.layer.meter_proxy --port 8096 \
    --upstream "$OPENAI_BASE_URL" --label graphrag-smoke-query \
    --log /tmp/layer/meter-graphrag-smoke-query.jsonl --stream-upstream &
python3 -m benchmark.layer.run_graphrag --root /tmp/layer/graphrag-smoke-query \
    --selection /tmp/layer/corpus/selection.json --limit 5 \
    --out /tmp/layer/runs/graphrag.smoke.jsonl
```

A local search that cannot answer five is not ready for two hundred, and the
five must not sit inside the query row. Then the score and the interval:

```
python3 -m benchmark.layer.score --selection /tmp/layer/corpus/selection.json \
    --answers /tmp/layer/runs/graphrag.answers.jsonl --mode answer --k 10 \
    --json /tmp/layer/runs/graphrag.score.json
python3 -m benchmark.layer.interval --score /tmp/layer/runs/graphrag.score.json \
    --label graphrag --json /tmp/layer/runs/graphrag.intervals.json
cp /tmp/layer/meter-graphrag-full.jsonl /tmp/layer/runs/graphrag.meter.jsonl
cp /tmp/layer/meter-graphrag-query.jsonl /tmp/layer/runs/graphrag.query.jsonl
```

GraphRAG writes no manifest, so both of its published numbers come from outside
it. Its calls and dollars are the meter's, one JSON line per paid call, failed
ones included — not its cache records, which count answers that were kept and
have no line for the calls that failed. Its wall clock is the framework's own
log, `logs/indexing-engine.log`, from the first timestamp of the attempt that
produced the artifact to the last, passed with `--wall-clock`:

```
python3 -m benchmark.layer.build_record --root /tmp/layer/graphrag \
    --wall-clock <seconds from the attempt's first timestamp to the log's last> \
    --exclude cache logs input prompts \
    --out /tmp/layer/runs/graphrag.build.json --name graphrag
```

The log also carries three earlier attempts that died on the gateway's ceiling
before the streaming transport existed, and counting them would publish time the
artifact never took. §7.2 says what this run's number was and how the build
reached it.

**LightRAG**, two phases, because building costs money and asking costs time:

```
python3 -m benchmark.layer.run_lightrag --phase ingest \
    --corpus /tmp/layer/one-document --working-dir /tmp/layer/lightrag
python3 -m benchmark.layer.run_lightrag --phase ask \
    --working-dir /tmp/layer/lightrag \
    --selection /tmp/layer/corpus/selection.json \
    --out /tmp/layer/runs/lightrag.jsonl
```

**The numbers on the page**, assembled and given their intervals:

```
python3 -m benchmark.layer.capability --kb /tmp/layer/kb \
    --json /tmp/layer/runs/capability.json
python3 -m benchmark.layer.interval \
    --score /tmp/layer/runs/ontoskills.score.json \
    --score /tmp/layer/runs/floor.score.json \
    --json /tmp/layer/runs/intervals.json
python3 -m benchmark.layer.report --manifest /tmp/layer/manifest.json \
    --into benchmark/layer/LAYER.md
```

**The read path the client actually sees** (ADR 0003), with its gates:

```
cargo build --release --offline --manifest-path mcp/Cargo.toml
python3 -m benchmark.layer.mcp_parity --kb /tmp/layer/kb \
    --selection /tmp/layer/corpus/selection.json \
    --binary mcp/target/release/ontomcp --out /tmp/layer/runs/mcp-parity-200.json
python3 -m benchmark.layer.mcp_parity --kb /tmp/layer/kb \
    --selection /tmp/layer/corpus/selection.json --tokenizer      # G7, 279 documents
unshare -rn python3 -m benchmark.layer.mcp_parity ...              # G8, same command
```

The first command is G1, G2, G5 and G6 at once; the second writes the Python
token stream of every document and has the Rust test compare itself to it; the
third is the first one with no route off the machine, which is G8.

`interval.py` is the one step whose absence would be easiest to miss and hardest
to defend: it is what turns three point estimates into a claim about the
ordering, and it resamples questions rather than facts because a question's facts
are covered or missed together.

**What is not reproducible, and why it is not a gap in the table.** The model is
sampled, so no run reproduces the bytes of another: that is what the prompt hash
and the corpus digest are for, not a claim that a rerun is identical. Two knobs
are not recorded and both affect the wall clock rather than the requests: our
build's `--concurrency`, which changes how long 880 calls take and nothing else,
and the wall clock of any build that ran in more than one attempt, which
`build_record.py --wall-clock` takes from the command line because a resumed
build's own timer covers only the attempt that finished. A repeat build, and the
variance it would measure, is in §6's full-run budget, not in this pilot.

## 10. The read path in the MCP

`docs/adr/0003-documents-in-the-mcp-runtime.md` decided that the layer's
client-facing surface is three tools in `ontomcp` — `documents_ask`,
`documents_claim`, `documents_query` — and that the ranking they answer with is a
Rust port of `compiler.documents.ask`, not a call into Python. The compiler is
untouched: `ontocore documents ingest` still writes the artifact, and the server
only reads it — no model call, no network, no file written.

| tool | input | answer |
|---|---|---|
| `documents_ask` | `q`, `kb`, `k` (10), `include_unverified` (false) | citations in rank order, each with its quote, locator, score and verdict; the documents they come from; the durations the corpus disagrees about |
| `documents_claim` | `claim_id`, `kb` | every evidence item with role, quote and locator — each quote re-checked against the document at query time — the verifier's reasons and notes, `conflicts_with`, the source document |
| `documents_query` | `sparql`, `kb` | the bound rows of a read-only `SELECT` or `ASK` over `graph.ttl` |

A second implementation of the ranking is acceptable only if something proves it
is not a different system, so eight gates are the price of the port. All eight
are green on the pilot artifact, and the reports are
`runs/mcp-parity-200.json` and `runs/mcp-parity-200-netns.json`:

| gate | what it checks | measured |
|---|---|---|
| **G1** parity, exact | 200 questions through the MCP against `ontocore ask`, claim ids position by position; ties compared as sets inside a tie group, because two float implementations may break a tie differently | **0 mismatches** in 200 |
| **G2** the quote is real | every citation's quote at the offsets it reports, normalised the way the compiler's verifier normalises | **0 of 2 000** citations off |
| **G3** read-only by construction | `INSERT`, `DELETE`, `LOAD`, `CLEAR`, `DROP`, `CREATE`, `SERVICE`, `DESCRIBE` refused with the keyword named; a query whose *literal* or prefixed name contains `delete` still runs; both caps named when hit | 8 keywords refused, each naming itself; refusal **0 ms**; `2000 rows` and `2 s` named when hit |
| **G4** vocabulary | a graph using a `doc:` term the binary does not know is refused, term named | test green; the pilot graph passes — 196 814 triples, 0 unknown terms |
| **G5** latency, published | p95 per `ask` ≤ 300 ms on the pilot KB, release build | **p50 3,5 ms, p95 5,2 ms, max 8,6 ms** over 200 questions |
| **G6** read-only at runtime | no knowledge-base file modified by the run | sizes and mtimes identical before and after |
| **G7** tokenizer parity | the Rust token stream equals the Python one for **every** text file, not a sample | **279 of 279** documents, byte for byte |
| **G8** no network | the 200 asks inside an empty network namespace | same answers, same ids, same order; p50 3,4 ms, p95 5,8 ms |

### What the port costs and what it bought

| operation | cost (release build, pilot artifact) |
|---|---|
| first `documents_ask` of a process — artifact load plus the lexical index build, once | **1,16 s** |
| `documents_ask`, steady state | **3,5 ms p50, 5,2 ms p95, 8,6 ms max** |
| first `documents_query` of a process — 16,7 MB of Turtle parsed and the vocabulary checked, once | **2,76 s** |
| `documents_query`, steady state (SELECT, ASK, GROUP BY over 196 814 triples) | **1-17 ms** |
| a refused mutation | **0 ms** — the guard runs before the graph is opened |
| a query over the row cap | 19 ms, and the error says `2000 rows` |

The 418 ms in §7's Query table is the same ranking computed by the Python
implementation the pilot was scored on, and the difference is worth stating
precisely rather than as a speed-up. `Corpus.search` rebuilds every claim's term
counts on every question — 1,4 M tokens revisited per question — while the Rust
index is inverted and built once. G1 is what makes this a statement about *the
same answers*: the work moved, the ranking did not. Nothing in §7's quality table
changes because the port is faster.

Three of the Python behaviours the port reproduces are the kind that look like
defects and are deliberately kept, because they are what was measured: the
`max(limit * 4, limit)` window is applied *before* duplicate statements are
dropped; a claim the verifier does not mention is `ok`; and there is no `refused`
field — an empty citation list is the answer, and the pilot's 0,0 % false
refusal rate exists because the system never abstains. `mcp/docs/documents-read-path.md`
records all fourteen suspected defects and the thirty-four traps, with the
location of each in the Python source.

### What these numbers do not say

- They describe **this artifact on this machine**. The gate is a command, not a
  promise: another corpus is checked by running the same harness, `--tokenizer`
  included, and a corpus that fails G7 fails loudly with the document named.
- They are a **parity** result, not a quality result. Coverage is still 63,9 %
  against the floor's 92,4 % with non-overlapping intervals (§7), and serving the
  layer in 3,5 ms instead of 418 ms does not move it by a character. The ADR says
  this in its own words and §5's rule is what stops the port from being cited as
  an improvement in quality.
- `documents_query` speaks `SELECT` and `ASK`, capped at 2 000 rows and 2 s, and
  refuses `CONSTRUCT` and `DESCRIBE` because they return a graph rather than
  bound rows. No SPARQL conformance suite was run: nine tests and the pilot's own
  probes — claims per document, sections, contradictions, `FILTER NOT EXISTS` —
  are what is green. A query language this large has corners this pilot never
  touches, and the honest description of the tool is "the queries the probes use,
  plus whatever else the standard gives for free".
