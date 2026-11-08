# ADR 0001 — The kernel is a document artifact, not a skill

- **Status:** Accepted
- **Date:** 2026-11-08
- **Supersedes:** the "skill as the central artifact" framing in `PHILOSOPHY.md` §0
- **Evidence:** `benchmark/docbench/RESULTS.md`, run `20261107T140843Z` + blind re-score

## Context

OntoSkills started as a compiler that turns `SKILL.md` into OWL 2 and a Rust
runtime that answers SPARQL over the result. DocBench was built to test whether
that is worth doing. The result was narrower and more useful than expected:

- On four public documents, a context made of **compiled claims with a quote and
  a locator** matched full-document reading (32/32 answerable questions) at
  **15% of the input tokens** (42,696 vs 281,246).
- It beat paragraph RAG by **+28 points** on citation accuracy, and the blind
  re-score reproduced that delta exactly.
- The only case where it beat full-document reading was an **abstention trap**:
  a fictional example inside a template that the full document invites you to
  read as a fact.

So the asset is not "skills as ontologies". It is **a claim, with the quote that
supports it, pointing into a document**. Skills are one thing you can build on
top of that; they are not the thing itself.

Two more signals point the same way:

- The public README sells a "deterministic enterprise AI agent platform" built
  on skills, while the only measured capability is document question answering
  with citations. The gap between the story and the evidence is a liability.
- External contributions (e.g. PR #74) arrive shaped by the `skill` abstraction
  because that is the only vocabulary the repository defines. Without a written
  kernel we keep receiving skill-shaped work and paying to review it.

## Decision

**The kernel is a document artifact.** A compiler run produces a
`KnowledgeArtifact`: a set of `Claim`s, each carrying its own `Evidence`, inside
a `Context`. `Skill` is demoted to a **profile** — a projection over claims that
groups them into an executable unit.

### Primitives

| Primitive | Definition | Identity |
|---|---|---|
| `KnowledgeArtifact` | The output of compiling one source document: claims + context + provenance | `artifact:<doc_id>@<version>` |
| `Context` | Everything needed to judge a claim: source, version, jurisdiction, document type, validity window | `context:<doc_id>@<version>` |
| `Claim` | One atomic assertion that can be true or false, permitted or prohibited | `claim_id` (`D4-0006`) |
| `Evidence` | A verbatim span of the source that supports, qualifies or contradicts the claim | `evidence_id` within claim |
| `Locator` | A machine-resolvable pointer to that span (page, section path, character offsets, quote anchors) | inside evidence |

### Normative rules

1. **No quote, no claim.** A claim without at least one evidence span that
   resolves to the source is invalid and must be rejected at compile time.
2. **Atomicity.** A conjunction becomes two claims sharing the same evidence.
   Exceptions become separate claims with `modality: condition` linked to the
   rule they scope.
3. **Evidence is a list, not a field.** A claim may need more than one span: one
   for the rule, one for the exception that scopes it. Modeling evidence as a
   single `quote` string is the bug that `D4-Q06` exposed — two conflicting
   deadlines, and only one of them could be cited.
4. **Conflicts are first-class.** When two claims in the same context disagree,
   both are kept and linked with `conflicts_with` **in both directions**. The
   compiler never smooths a contradiction; surfacing it is the product.
5. **The model cites claims; the system resolves evidence.** The answer contract
   is `{answer, claim_ids}`. The evidence shown to the user is read from the
   claim store, never re-typed by the model. This removes the largest class of
   fabricated citations by construction.
6. **Never infer.** If the document does not say it, it is not a claim. An
   example inside a template is not a fact about the world.
7. **A negative about the document needs evidence too.** "There is no
   inconsistency" is a claim and must be supported or refused. The blind review
   found paragraph RAG making exactly this error (`D4-Q06`): having retrieved
   five paragraphs, it asserted the document contained no conflict.

### Vocabulary anchors (do not invent terms)

We reuse published vocabularies instead of inventing parallel ones, so that the
output can interoperate with tools in the field:

| Our field | Anchor | Rationale |
|---|---|---|
| `modality` | [LegalRuleML](https://docs.oasis-open.org/legalruleml/legalruleml-core-spec/v1.0/os/legalruleml-core-spec-v1.0-os.html) deontic operators `[OBL]`/`[PER]`/`[FOR]`/`[RIGHT]`, plus `recommendation`, `definition`, `procedure_step` | The document class we win on is normative; LegalRuleML is the OASIS standard for it, including defeasibility (which rule wins in a conflict) |
| `Locator` | [W3C Web Annotation Data Model](https://www.w3.org/TR/annotation-model/#text-quote-selector) — `oa:TextQuoteSelector` (`exact`, `prefix`, `suffix`) and `oa:TextPositionSelector` (`start`, `end`) | A quote plus prefix/suffix survives text extraction differences and re-pagination |
| provenance | [PROV-O](https://www.w3.org/TR/prov-o/) — `prov:Entity`, `prov:wasDerivedFrom`, `prov:atLocation` | Artifact → document → span derivation is exactly what PROV models |
| answer + attribution | Attributed QA (Bohnet et al., 2023) / ALCE (Gao et al., 2023) | "Answer + pointer into a fixed corpus" is the established task; our contribution is compiling the corpus into claims, not a new task definition |

## Schema

The normative contract is `schemas/claim.v2.schema.json`. The v1 shape
(single `quote` + `locator`) remains readable for reproducing the 2026-11-07
run; `check_claims.py` accepts both and `migrate_claims_v2.py` converts.

```json
{
  "claim_id": "D4-0002",
  "doc_id": "D4",
  "statement": "Electronic proposers must submit via eVA no later than 2 p.m. on January 22, 2026.",
  "modality": "obligation",
  "actor": "proposers submitting electronically",
  "deadline": "2026-01-22T14:00",
  "conditions": ["electronic submission via eVA"],
  "polarity": "affirmed",
  "evidence": [
    {
      "quote": "Proposers must submit one (1) complete copy of the proposal ...",
      "locator": {"kind": "pdf", "page": 6, "section_path": ["3.0 Terms and Proposal Content and Format", "3.b electronic submissions"], "url": "https://..."},
      "role": "supports"
    }
  ],
  "conflicts_with": ["D4-0001", "D4-0004"],
  "context": {"source": "Greene County RFP 2026-001", "version": "2026-01", "doc_type": "rfp", "jurisdiction": "US-VA-Greene"}
}
```

`role` is one of `supports` (the span asserts the claim), `qualifies` (the span
scopes or excepts it) or `contradicts` (the span asserts the opposite — used
only in pairs, with `conflicts_with`).

## Compile pipeline

```
source ──► loader ──► segmenter ──► claim extractor ──► validator ──► emitter
           (bytes)     (spans +      (LLM, schema-       (verbatim,     (TTL /
                        locators)     constrained)        locator,       JSON)
                                                            conflicts)
```

Two invariants make the pipeline falsifiable:

- **Span-first.** The segmenter produces spans with locators *before* the model
  runs. The extractor may only select existing spans; it cannot invent text.
  This turns the verbatim check from a post-hoc audit into a structural
  guarantee.
- **Round-trip.** The emitted TTL must load in `ontomcp` and answer the DocBench
  queries. A claim that cannot be queried back is a claim that was not compiled.

## Consequences

**Positive**

- One vocabulary for code, benchmark and docs. A contribution either produces
  claims with evidence or it is out of scope.
- The public claim becomes defensible: "compiled claims with quoted evidence",
  not "deterministic agent platform".
- `Skill` becomes a projection, so skill-shaped work (PR #74) has a defined
  place instead of competing with the kernel.

**Negative / accepted costs**

- The compiler pipeline is more work than the current skill extractor: spans and
  locators must be computed before extraction, and PDF locators need page
  geometry.
- Evidence lists make the schema and the store more complex than a single
  `quote` field.
- Existing skill ontologies are no longer the kernel; they are a derived view.
  Some of `core/` will need to be re-pointed at this pipeline rather than
  extended.

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| Keep `Skill` as the kernel, add citations as metadata | The benchmark measures claims, not skills; the abstraction would remain unvalidated |
| Single `quote` + `locator` (v1) | Cannot represent a two-sided conflict (`D4-Q06`) nor a rule with an exception |
| Free-form citation authored by the model (v1 answer contract) | Produces fabricated or partial quotes; the system can resolve evidence mechanically and should |
| Paragraph RAG over claims | The claims *are* the retrieval unit; adding a paragraph layer re-introduces the failure the claims fixed |

## Open questions

1. **Extraction quality at scale.** The 2026-11-07 result used hand-built claims.
   The next gate is machine extraction: ≥90% of claims valid (verbatim quote +
   resolvable locator) on the same four documents, with B2 still ahead of B1.
2. **Locator fidelity for PDFs.** Page + section path is enough for the
   benchmark; character offsets into extracted text are not stable across
   extractors. Decide whether to store `bbox` (WADM allows it) or to freeze the
   extraction.
3. **Claim identity across versions.** When a document is revised, is
   `D4-0002` the same claim with new evidence, or a new claim? Needed before
   versioning claims in `ontostore`.
4. **Conflict adjudication.** We surface conflicts. Do we also carry a
   precedence rule (LegalRuleML defeasibility), or is adjudication always the
   reader's job? Surfacing without adjudication is defensible; adjudicating
   wrongly is not.
