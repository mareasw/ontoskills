# ADR 0003 — The document layer is served by the MCP runtime, and the benchmark measures that surface

- **Status:** Proposed
- **Date:** 2026-11-16
- **Supersedes:** nothing. Makes ADR 0002's query claim concrete and closes the
  gap between what the pilot measured and what a client can reach.
- **Deciders:** tech lead
- **Evidence:** `mcp/src/main.rs` (`tool_definitions`, one tool); `mcp/src/*.rs`
  (no reference to `claims.jsonl`, `graph.ttl` or the `doc:` vocabulary);
  `docs/adr/0002-evidence-first-extraction.md` lines 17 and 148;
  `benchmark/layer/answers.py` (`compiler.documents.ask`, the same modules
  `ontocore ask` calls); `benchmark/layer/LAYER.md` §7.

## Context

ADR 0002 states the product: every document the company owns is compiled into
claims with verbatim evidence, linked into a graph, and *"queried
deterministically — SPARQL through the MCP runtime — with a citation for every
answer"*, repeated at line 148 as *"through the existing MCP/SPARQL runtime and
citing the claims it used"*.

That runtime does not exist for documents. The MCP is a Rust server that loads a
skills ontology root and exposes **one** tool, `skill`
(`mcp/src/main.rs:897`): find or load a skill by id, or search skills. Its
`bm25_engine.rs` indexes skills, sections of skill documents, and knowledge
nodes. `Document` appears in that crate only as the `bm25` library's type. No
file in `mcp/src` mentions a knowledge base, a claim, or evidence.

Meanwhile the pilot's numbers come from the Python core. `answers.py` imports
`compiler.documents.ask` and `compiler.documents.store`, which are exactly the
modules `ontocore ask` uses (`core/src/cli/documents.py:592`). So the pilot is
honest about the code it measured — it measured the CLI — but the surface it
measured is not the surface ADR 0002 promises, and it is not the surface an
agent can use: an agent talks MCP, and MCP answers about skills.

Two consequences, and the second is the expensive one:

1. Today the layer is unreachable by the clients it was designed for. A user
   with a folder of contracts has a CLI and a static HTML view.
2. If the document tools are added later, as a second implementation of the
   ranking, the pilot's numbers stop describing the product. Two BM25
   implementations over the same claims will not agree, and the first symptom
   will be a customer asking why the MCP cites different passages than the
   document says it does. A benchmark that measures one implementation while
   the product runs another is worse than no benchmark: it is a claim with a
   number attached.

This ADR fixes the surface, the contract, and the acceptance gates, before any
code is written.

## Decision

### 1. Three tools, and only three, in v1

| tool | input | output |
|---|---|---|
| `documents_ask` | `q`, `kb`, `k` (default 10), `include_unverified` (default false) | citations in rank order: `claim_id`, `doc_id`, `statement`, `quote`, `locator`, `score`, `verdict`; `documents`; `refused` |
| `documents_claim` | `claim_id`, `kb` | the claim, **all** its evidence with roles and locators, the verifier verdict with reasons, `conflicts_with` |
| `documents_query` | `sparql`, `kb` | bound rows of a read-only `SELECT`/`ASK` |

No ingestion tool. Ingestion is a batch job with a budget and a cost the user
approves; exposing it as a tool would let an agent spend money on a request
nobody priced. No tool that mutates a knowledge base.

`documents_claim` exists because answering is cheap to get wrong in a way that
is invisible: a citation list tells you which claim was used, and the claim is
the thing a reviewer has to be able to open and disagree with. `locator` is
structured (`section_path`, `char_start`, `char_end`, `page`, `url`), not the
`' > '.join()` string the store emitted until this change — a string cannot be
followed to the passage.

### 2. One implementation of the ranking, and it is the one that was measured

`documents_ask` and `documents_claim` delegate to the core
(`ontocore ask --json`, and a new `ontocore claim --json`). They do **not**
re-implement BM25 in Rust in v1.

The reason is not effort, it is validity. The pilot's numbers — coverage 63,9 %,
support 46,6 %, 5 097 characters, 418 ms median — were produced by
`compiler.documents.ask` over the verifier's `ok` claims. Any second ranking is
a different system with the same name, and the difference will be invisible
until someone compares two outputs. Delegation makes parity true by
construction, and makes the pilot a statement about the served surface.

This is a deliberate dependency, and it has a declared failure mode: when the
core is not installed or the KB is unreadable, the tool returns a typed error
(`documents_unavailable`, with the reason and the paths tried), never an empty
answer. An empty citation list is a claim about the corpus and must not be used
to report an installation problem.

A native port is **not forbidden, it is gated**: a separate ADR may port the
ranking, and its acceptance criterion is a parity harness that asks the same 200
pilot questions through both implementations and requires the top-10 claim ids to
match. Until that harness exists and passes, two implementations do not ship.

### 3. `documents_query` is the reason the graph exists, so it is in v1

A vector store cannot answer *"which obligations in the annex contradict the
master agreement"*. A graph can, and that is the only capability the layer
claims that the BM25 floor does not have. So the SPARQL tool is not a nice-to-
have; without it the product is a retrieval system that costs more than the
floor and loses to it on lexical coverage (LAYER.md §7).

Contract:

- `SELECT` and `ASK` only. The query is parsed, not grepped: `INSERT`, `DELETE`,
  `LOAD`, `CLEAR`, `DROP`, `CREATE`, `SERVICE` and `DESCRIBE` are rejected with
  the keyword named.
- The graph is parsed once and cached in memory, invalidated on `graph.ttl`'s
  mtime. 16 MB of Turtle is 1-2 s to parse and that cost belongs to the first
  query, not to every query.
- The served vocabulary is `core/specs/documents.ttl` at version 1.0.0, inlined
  into the binary at build time from the spec file. A knowledge base whose graph
  uses a `doc:` term the server does not know is refused with the term named:
  a version mismatch is an error, not something to guess through.
- Results are capped (2 000 rows, 2 s wall clock), and both caps are in the
  error when they are hit. A tool that times out silently teaches an agent that
  the graph is empty.

### 4. The verifier filter is part of the contract

`documents_ask` cites only claims the verifier passed (`ok`), unless the caller
asks for the rest, in which case each citation carries its verdict. The pilot's
false-refusal rate is 0,0 % because the system never refuses; v1 preserves that
behaviour exactly. Improving it is a product change with its own measurement, not
something to slip in while wiring a transport.

### 5. Configuration and safety

- KB root: the tool's `kb` argument, else `ONTOSKILLS_KB_ROOT`. The server does
  not embed user documents: `catalog.rs` embeds *skills* as source strings, and
  that trick must not be reused for customer text.
- Every KB path is resolved and must live under the configured root; `..` is
  refused. The KB is opened read-only, and a test asserts no file mtime changes
  after 200 asks.
- No network at query time, no model call, no rewriting of a quote on the way
  out.

### 6. Acceptance gates

The work is done when all of these are true and checkable in CI:

- **G1 — parity, exact.** `documents_ask` over the MCP and `ontocore ask --json`
  return the same `claim_id`s in the same order for all 200 pilot questions.
  Exact, because it is the same code path; a threshold would hide a wiring bug.
- **G2 — the quote is real.** Every citation's quote occurs in its document at
  the reported offsets, checked on all 200 questions with the same function the
  compiler's verifier uses.
- **G3 — the graph is read-only by construction.** Every mutation keyword and
  `SERVICE` is rejected; a query over the caps fails with its cap named.
- **G4 — vocabulary.** A graph built against a different `doc:` version is
  refused with the unknown term named.
- **G5 — latency, published.** p95 per `ask` ≤ 1 500 ms on the pilot KB on the
  reference machine, measured and written into LAYER.md §10 next to the 418 ms
  offline figure, with the gap explained (process start plus import).
- **G6 — read-only.** No KB file is modified by 200 asks.

## Work breakdown

| step | deliverable | evidence it is done |
|---|---|---|
| D1 | this ADR, reviewed | approved or amended |
| D2 | `ontocore claim --json` (tiny, tested) | `core/tests/test_documents_cli.py` |
| D3 | the three tools in Rust, delegation, typed errors | `cargo test`, e2e over stdio |
| D4 | `benchmark/layer/mcp_parity.py` + CI job | G1, G2 green on 200 questions |
| D5 | SPARQL tool with the vocabulary and cap gates | G3, G4 green |
| D6 | docs: MCP README, `docs/agents`, LAYER.md §10 | G5, G6 recorded |

Until D4 is green, LAYER.md keeps saying what it says today: the numbers describe
the CLI. That sentence is the honest one and it is already in §1 and §7.

## Consequences

**Good.** The pilot becomes a statement about the surface a client uses. The
graph stops being decoration: `documents_query` is the only capability the
comparison table cannot reproduce. A user with a folder of documents gets an
agent-reachable layer without writing Python.

**Costs.** The MCP gains a dependency on the core being installed, and a
subprocess per ask (measured, G5). The binary gains a build-time dependency on
`core/specs/documents.ttl`, so a spec change must rebuild the server — which is
the point of versioning the vocabulary.

**What this does not fix.** Coverage is still 63,9 % against the floor's 92,4 %
on lexical metrics with non-overlapping intervals. Serving the layer better does
not make it better, and this ADR must not be cited as if it did.

## Alternatives considered

1. **Port the ranking to Rust now.** Rejected for v1: parity is unproven, and
   an unproven second implementation is exactly how a benchmark stops meaning
   anything. Available later behind G1's harness.
2. **Embed the KB in the binary, as `catalog.rs` does with skills.** Rejected:
   customer text is not source code; the binary would grow per knowledge base
   and would ship confidential documents in a downloadable artifact.
3. **Keep documents on the CLI and declare MCP out of scope.** Rejected: ADR
   0002 already promises the runtime, and agents cannot rely on shelling out.
   If that promise is withdrawn, ADR 0002 must be amended, not quietly ignored.
4. **Add a natural-language answer tool that calls a model at query time.**
   Rejected: it changes the measured system, costs money per question, and makes
   the pilot's zero-query-cost row incomparable.

## Open questions

- Is exact parity (G1) the right gate, or should a port be allowed to differ on
  ties? Ties are the only place where two BM25 implementations can diverge
  without a defect, and the harness should compare sets within a tie group.
- Should `documents_query` ship with saved queries (the "views" of ADR 0002) or
  bare SPARQL? Bare SPARQL first: a saved query is a product decision per
  customer.
- Does the section tree need its own tool (`documents_sections`) or is one
  `SELECT` over `doc:hasSection` enough? Start with the query; add a tool only
  if agents demonstrably fail to write it.
