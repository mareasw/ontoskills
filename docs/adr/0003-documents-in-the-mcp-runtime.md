# ADR 0003 — The document layer is served by the MCP runtime, and the benchmark measures that surface

- **Status:** Accepted (2026-11-17: the read path is ported; delegation rejected)
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
   number attached. This is the risk the decision below takes on deliberately,
   and gate G1 is what pays for it: a second implementation is allowed only with
   a harness that proves, on 200 questions, that it is not a different system.

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

### 2. The read path is Rust. The compiler stays Python.

The server reads the artifact; it never builds one. That split is the decision,
and it comes from two facts that are easy to conflate:

- **Compiling is a batch job.** Segmenting a document, calling a model for every
  chunk, verifying quotes and writing a knowledge base is offline work measured
  in hours and dollars. It belongs to `ontocore`, the Python package, because
  that is where the pipeline already lives and because a compiler in Rust buys
  nothing a user can feel.
- **Serving is a hot path.** An agent asks a question and waits. The MCP is a
  single local binary that must answer without Python installed, without a
  virtualenv, and without a subprocess per question.

So `documents_ask`, `documents_claim` and `documents_query` are implemented in
Rust, over the files `ontocore documents` writes. Nothing is delegated to the
Python core at query time, and the server does not depend on `ontocore` being
installed.

**What the port covers** — and only this:

| piece | why it is in the port |
|---|---|
| `claims.jsonl`, `documents.jsonl`, `verifier.jsonl`, `manifest.json`, `text/*.txt` | the artifact; read-only |
| `norm`, `tokens`, the stopword list, the 7-character stem | the ranking rests on them; parity is token-level |
| BM25 (same K1/B and IDF), the `score > 0` filter, dedup by normalised statement | the measured ranking |
| citation assembly: quote, locator, section path, url, verdict | the reason to use the layer instead of chunks |
| contradiction links (`durations`, `topic_of`, `find_tensions`) | the capability the floor does not have |
| SPARQL over `graph.ttl` via `oxigraph` | already a dependency of the server |

**What it does not cover:** ingestion, segmentation, extraction, verification,
the HTML view, the CSV export, embeddings. The MCP has no tool that spends
money and no tool that writes to a knowledge base.

**The Python ranking stays, and it is a reference, not a second product.** The
CLI keeps `ontocore ask` because it is how a knowledge base is inspected while
being built. Two implementations of one formula is a risk, so it is turned into
a test: `benchmark/layer/mcp_parity.py` asks the same 200 pilot questions through
both and fails on the first difference in the top-k claim ids. If a future
change to either side is not made on both, CI says so. That is not parity by
construction — it is parity by measurement, and the difference is stated here
instead of being hidden in a claim.

**Why not delegate.** Delegation (an earlier version of this ADR) would have
made parity true by construction, and it was rejected for three reasons: the
binary would depend on a Python runtime and a package version for a few hundred
lines of arithmetic; a user who installs a single binary would silently get a
feature that only works on machines with a virtualenv; and the latency floor
would be a Python import (measured: 3,8 s cold without embeddings, 8,4 s with
them) rather than an in-process call.

**Why not skip Rust and improve the Python ranking.** The ranking is not the
part that needs improving — it is measured, and it loses to a BM25 floor on
lexical coverage (§7 of LAYER.md). What was missing is that no client could
reach it. This ADR fixes reachability, and deliberately does not pretend it
fixes quality.

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
- The served vocabulary is `core/src/specs/documents.ttl` at version 1.0.0,
  inlined into the binary at build time from the spec file. A knowledge base
  whose graph uses a `doc:` term the server does not know is refused with the
  term named: a version mismatch is an error, not something to guess through.
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
  out. The KB is loaded once per root and cached by the manifest's mtime.

### 6. Acceptance gates

The work is done when all of these are true and checkable in CI:

- **G1 — parity, exact.** `documents_ask` over the MCP and `ontocore ask --json`
  return the same `claim_id`s in the same order for all 200 pilot questions.
  Ties are compared as sets within a tie group, because two float
  implementations may legitimately break a tie differently; anything outside a
  tie group is a defect.
- **G2 — the quote is real.** Every citation's quote occurs in its document at
  the reported offsets, checked on all 200 questions with the same function the
  compiler's verifier uses.
- **G3 — the graph is read-only by construction.** Every mutation keyword and
  `SERVICE` is rejected; a query over the caps fails with its cap named.
- **G4 — vocabulary.** A graph built against a different `doc:` version is
  refused with the unknown term named.
- **G5 — latency, published.** p95 per `ask` ≤ 300 ms on the pilot KB on the
  reference machine (in-process, KB pre-loaded), measured and written into a new
  LAYER.md §10 next to the 418 ms offline figure the CLI reports.
- **G6 — read-only.** No KB file is modified by 200 asks.
- **G7 — tokenizer parity, token-level.** For every text file of the pilot KB,
  the Rust token stream equals the Python one, and the same for the stopword
  filter and the stem. This is the gate that catches a Unicode class that is one
  character wider in one language than the other.
- **G8 — no network.** The 200 asks run with the network namespace empty (or with
  an env-var guard that fails on egress) and produce the same answers.

## Work breakdown

| step | deliverable | evidence it is done |
|---|---|---|
| D1 | this ADR, reviewed | approved or amended |
| D2 | `mcp/src/documents/text.rs`: `norm`, `tokens`, stopwords, stem | G7 green on the pilot corpus |
| D3 | `mcp/src/documents/kb.rs`: loading, index, mtime cache, path guard | `cargo test`, no writes |
| D4 | `mcp/src/documents/rank.rs`: BM25, dedup, citations, tensions | G1 green on 200 questions |
| D5 | the three tools, typed errors, `documents_query` with caps | `cargo test`, e2e over stdio |
| D6 | `benchmark/layer/mcp_parity.py` + CI job | G1-G8 green, numbers in LAYER.md §10 |
| D7 | docs: MCP README, `docs/agents`, LAYER.md §10 | published |

Until D6 is green, LAYER.md keeps saying what it says today: the numbers describe
the CLI. That sentence is the honest one and it is already in §1 and §7.

## Consequences

**Good.** The pilot becomes a statement about the surface a client uses, and the
server stays a single binary with no Python at runtime. The graph stops being
decoration: `documents_query` is the only capability the comparison table cannot
reproduce. The claimed split — Python compiles, Rust serves — is the one the
repository already had for skills, now applied to documents.

**Costs.** Roughly 600-800 lines of Rust to port and a permanent second
implementation of the ranking in Python, guarded by a parity harness that runs
on every change. The port is 6-8 days of work, and the pilot's numbers must be
re-measured through the MCP before any of them is published again.

**What this does not fix.** Coverage is still 63,9 % against the floor's 92,4 %
on lexical metrics with non-overlapping intervals. Serving the layer better does
not make it better, and this ADR must not be cited as if it did.

## Alternatives considered

1. **Delegate to the Python core (an earlier version of this ADR).** Rejected:
   parity by construction, at the cost of a second runtime, a package-version
   dependency and a multi-second cold path. The cheapness of the first day is
   paid for by every user who installs only the binary.
2. **Port the whole pipeline, including ingestion, to Rust.** Rejected: it is
   offline batch work with a model call per chunk, it already exists and is
   measured, and a second compiler is a second thing to keep correct for no
   user-visible gain.
3. **Embed the KB in the binary, as `catalog.rs` does with skills.** Rejected:
   customer text is not source code; the binary would grow per knowledge base
   and would ship confidential documents in a downloadable artifact.
4. **Keep documents on the CLI and declare MCP out of scope.** Rejected: ADR
   0002 already promises the runtime, and agents cannot rely on shelling out.
   If that promise is withdrawn, ADR 0002 must be amended, not quietly ignored.
5. **Add a natural-language answer tool that calls a model at query time.**
   Rejected: it changes the measured system, costs money per question, and makes
   the pilot's zero-query-cost row incomparable.

## Open questions

- Is exact parity (G1) the right gate, or should a port be allowed to differ on
  ties? Ties are the only place where two BM25 implementations can diverge
  without a defect, and the harness compares sets within a tie group.
- Should the Python CLI eventually call the Rust crate (PyO3/maturin) so that
  one implementation serves both? It would remove the duplicate, at the cost of
  a native wheel on three platforms. Deferred until the port exists and the
  parity harness can prove the move.
- Should `documents_query` ship with saved queries (the "views" of ADR 0002) or
  bare SPARQL? Bare SPARQL first: a saved query is a product decision per
  customer.
- Does the section tree need its own tool (`documents_sections`) or is one
  `SELECT` over `doc:hasSection` enough? Start with the query; add a tool only
  if agents demonstrably fail to write it.
