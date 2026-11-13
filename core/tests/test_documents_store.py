"""Tests for the knowledge-base store: JSONL, graph, CSV, atomic writes."""

from __future__ import annotations

from compiler.documents.store import KnowledgeBase


def _rows():
    documents = [
        {
            "doc_id": "T1",
            "title": "Test contract",
            "kind": "text",
            "url": "https://example.org/t1",
            "licence": "CC0",
            "doc_type": "contract",
            "version": "v1",
        }
    ]
    spans = [
        {
            "span_id": "S0001",
            "doc_id": "T1",
            "paragraph": "The Supplier shall notify within 48 hours.",
            "locator": {"kind": "text", "section_path": ["2. Notification"], "url": "https://example.org/t1"},
        }
    ]
    claims = [
        {
            "claim_id": "T1-0001",
            "doc_id": "T1",
            "schema_version": 2,
            "statement": "The Supplier shall notify within 48 hours.",
            "modality": "obligation",
            "evidence": [
                {
                    "quote": "The Supplier shall notify within 48 hours.",
                    "locator": {"kind": "text", "section_path": ["2. Notification"], "url": "https://example.org/t1"},
                    "role": "supports",
                }
            ],
            "context": {"source": "Test contract", "doc_type": "contract"},
        }
    ]
    return documents, spans, claims


def test_roundtrip(tmp_path):
    documents, spans, claims = _rows()
    kb = KnowledgeBase(tmp_path / "kb")
    kb.save_texts({"T1": "The Supplier shall notify within 48 hours."})
    kb.write(
        manifest={"name": "test"},
        documents=documents,
        spans=spans,
        claims=claims,
        verifier_rows=[{"claim_id": "T1-0001", "doc_id": "T1", "verdict": "ok", "reasons": [], "notes": []}],
    )
    assert kb.exists()
    assert kb.documents() == documents
    assert kb.spans() == spans
    assert kb.claims() == claims
    assert kb.verifier()[0]["verdict"] == "ok"
    assert kb.text("T1").startswith("The Supplier")
    assert kb.manifest()["prompt_hash"]


def test_graph_contains_document_claim_and_quote(tmp_path):
    documents, spans, claims = _rows()
    kb = KnowledgeBase(tmp_path)
    kb.write(manifest={}, documents=documents, spans=spans, claims=claims)
    graph = (tmp_path / "graph.ttl").read_text(encoding="utf-8")
    assert "ex:doc_T1 a oc:Document" in graph
    assert "ex:claim_T1-0001 a oc:Claim" in graph
    assert "oc:hasQuote" in graph
    assert "The Supplier shall notify within 48 hours." in graph

    import rdflib

    parsed = rdflib.Graph()
    parsed.parse(data=graph, format="turtle")
    assert len(parsed) > 0


def test_csv_has_one_row_per_claim(tmp_path):
    documents, spans, claims = _rows()
    kb = KnowledgeBase(tmp_path)
    kb.write(
        manifest={},
        documents=documents,
        spans=spans,
        claims=claims,
        verifier_rows=[{"claim_id": "T1-0001", "doc_id": "T1", "verdict": "weak", "reasons": [], "notes": []}],
    )
    lines = (tmp_path / "evidence.csv").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert "T1-0001" in lines[1]
    assert "weak" in lines[1]


def test_write_is_atomic_and_leaves_no_temp_files(tmp_path):
    documents, spans, claims = _rows()
    kb = KnowledgeBase(tmp_path)
    kb.write(manifest={}, documents=documents, spans=spans, claims=claims)
    assert not list(tmp_path.glob(".tmp-*"))


def test_missing_claims_means_no_knowledge_base(tmp_path):
    assert not KnowledgeBase(tmp_path).exists()


class _FakeEmbedder:
    """A stand-in for the model: the store's job is the file, not the encoding."""

    def encode(self, texts):
        return [[float(len(text)), 1.0] for text in texts]


def test_vectors_roundtrip_with_a_header(tmp_path):
    from compiler.documents.store import write_vectors
    from compiler.documents.vector import DIM, MODEL, REVISION

    _, _, claims = _rows()
    kb = KnowledgeBase(tmp_path)
    written = write_vectors(kb, claims, _FakeEmbedder())

    assert written == 1
    vector = kb.vectors()["T1-0001"]
    assert len(vector) == 2 and vector[1] == 1.0 and vector[0] > 0
    assert list(kb.vectors()) == ["T1-0001"]
    header = kb.vectors_header()
    assert (header["model"], header["revision"], header["dim"]) == (MODEL, REVISION, DIM)


def test_no_vectors_file_means_no_vectors(tmp_path):
    kb = KnowledgeBase(tmp_path)
    assert kb.vectors() == {}
    assert kb.vectors_header() == {}
