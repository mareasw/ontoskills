# The documents fixture

A knowledge base small enough to commit, cut from a real one so that the Rust
read path in `mcp/src/documents/` can be compared with the Python one in
`core/src/documents/` question by question.

```
kb/manifest.json       what this slice is, and what wrote it
kb/documents.jsonl     three source documents
kb/claims.jsonl        77 atomic claims, unchanged from the build
kb/verifier.jsonl      their verdicts (75 ok, 2 weak)
kb/text/<doc_id>.txt   the source text, byte for byte
kb/graph.ttl           the graph, rebuilt from the slice by the real writer
golden.json            what the Python core answers, and how it tokenises
```

## Where the text comes from

The three documents are part of [EnterpriseRAG-Bench][erb]
(`onyx-dot-app/EnterpriseRAG-Bench`), released under the MIT licence. The text
under `kb/text/` and the quotes in `kb/claims.jsonl` are verbatim from that
dataset and remain under its licence; nothing in this fixture is a client
document. The claims are what `deepseek-v4.1-flash` extracted under prompt hash
`b4a1d4af…`, with the chunk size and overlap recorded in `kb/manifest.json`.

[erb]: https://huggingface.co/datasets/onyx-dot-app/EnterpriseRAG-Bench

## Why three documents and twenty-five questions

The slice is chosen for the rules a port can get wrong rather than for size: a
question that is nothing but stopwords, a word long enough to be stemmed, an
accented word, a quote with curly punctuation, a claim the verifier rejected,
and a document with several sections. `kb/graph.ttl` is rebuilt from the slice
rather than copied, because a graph pointing at a document that is not here
would make `documents_query` lie about what the fixture holds.

`golden.json` carries two things: the citations `ask()` returned for 25
questions — twenty drawn from the pilot selection, five written to probe the
edges above — and, per document, the SHA-256 of its text, the SHA-256 of its
normalised text, and its token stream. The Rust tests compare against both:

```
cargo test --offline --manifest-path mcp/Cargo.toml documents::
```

## Regenerating it

The fixture is generated, never edited by hand. It needs a compiled knowledge
base and the pilot's question selection:

```
python3 -m benchmark.layer.make_documents_fixture \
    --kb /path/to/kb --selection /path/to/selection.json \
    --out mcp/tests/fixtures/documents --force
```

The same script writes `mcp/src/documents/stopwords.rs` from
`compiler.documents.text.STOPWORDS` (`--stopwords-only`), because a list copied
across a language boundary by hand is a list that drifts.

Regenerating changes `golden.json` whenever the ranking changes, which is the
point: `benchmark/tests/test_layer_documents_fixture.py` recomputes those answers with
the current Python code, so a commit that changes the ranking without
regenerating fails on the Python side before the Rust side is asked to match it.
