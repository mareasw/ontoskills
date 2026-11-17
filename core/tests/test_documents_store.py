"""Tests for the knowledge-base store: JSONL, graph, CSV, atomic writes."""

from __future__ import annotations

import pytest

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
    assert "ex:doc_T1 a doc:Document" in graph
    assert "ex:claim_T1-0001 a doc:Claim" in graph
    assert "doc:hasQuote" in graph
    assert "The Supplier shall notify within 48 hours." in graph

    import rdflib

    parsed = rdflib.Graph()
    parsed.parse(data=graph, format="turtle")
    assert len(parsed) > 0


def test_graph_keeps_the_section_tree_and_a_structured_locator(tmp_path):
    """The data had sections; the graph must not flatten them into a string."""
    documents, spans, claims = _rows()
    claims[0]["evidence"].append(
        {
            "quote": "Notification is in writing.",
            "locator": {
                "kind": "text",
                "section_path": ["2. Notification", "2.1 Form"],
                "url": "https://example.org/t1",
                "char_start": 40,
                "char_end": 68,
            },
            "role": "context",
        }
    )
    kb = KnowledgeBase(tmp_path)
    kb.write(manifest={}, documents=documents, spans=spans, claims=claims)

    import rdflib
    from rdflib import Namespace, RDF

    doc = Namespace("https://ontoskills.sh/ontology/documents#")
    parsed = rdflib.Graph()
    parsed.parse(data=(tmp_path / "graph.ttl").read_text(encoding="utf-8"), format="turtle")

    sections = set(parsed.subjects(RDF.type, doc.Section))
    assert len(sections) == 2  # the parent, even without a claim of its own, and the child
    titles = {str(o) for s in sections for o in parsed.objects(s, doc.hasSectionTitle)}
    assert titles == {"2. Notification", "2.1 Form"}
    parent = next(s for s in sections if str(parsed.value(s, doc.hasSectionTitle)) == "2. Notification")
    child = next(s for s in sections if str(parsed.value(s, doc.hasSectionTitle)) == "2.1 Form")
    assert (parent, doc.hasSubsection, child) in parsed
    assert (next(iter(parsed.subjects(RDF.type, doc.Document))), doc.hasSection, parent) in parsed

    locators = list(parsed.subjects(RDF.type, doc.Locator))
    assert len(locators) == 2
    deep = next(s for s in locators if parsed.value(s, doc.hasCharStart) is not None and int(parsed.value(s, doc.hasCharStart)) == 40)
    assert int(parsed.value(deep, doc.hasCharEnd)) == 68
    assert (deep, doc.inSection, child) in parsed
    # Evidence says what the passage is doing, through a resource and not a string.
    roles = {str(o).rsplit("#", 1)[-1] for o in parsed.objects(None, doc.evidenceRole)}
    assert roles == {"supportsRole", "contextRole"}


def test_every_document_term_used_is_declared_in_the_spec(tmp_path):
    """A vocabulary that uses terms it does not declare is not an ontology."""
    from rdflib import Graph, Namespace, OWL, RDF

    doc = Namespace("https://ontoskills.sh/ontology/documents#")
    documents, spans, claims = _rows()
    kb = KnowledgeBase(tmp_path)
    kb.write(manifest={}, documents=documents, spans=spans, claims=claims)
    graph = Graph()
    graph.parse(data=(tmp_path / "graph.ttl").read_text(encoding="utf-8"), format="turtle")

    declared = set()
    for kind in (OWL.Class, OWL.ObjectProperty, OWL.DatatypeProperty, OWL.NamedIndividual):
        declared |= {
            term
            for term in graph.subjects(RDF.type, kind)
            if str(term).startswith(str(doc))
        }
    used = {p for p in graph.predicates() if str(p).startswith(str(doc))}
    used |= {
        o
        for s in graph.subjects()
        for o in graph.objects(s, RDF.type)
        if str(o).startswith(str(doc))
    }
    assert used - declared == set(), f"undeclared: {sorted(str(t) for t in used - declared)}"


def test_document_graph_does_not_borrow_the_skill_namespace(tmp_path):
    """Two different things, two namespaces: the collision that motivated the split."""
    documents, spans, claims = _rows()
    kb = KnowledgeBase(tmp_path)
    kb.write(manifest={}, documents=documents, spans=spans, claims=claims)
    graph = (tmp_path / "graph.ttl").read_text(encoding="utf-8")
    # Substring "oc:" also matches "doc:", so the check is on the declaration.
    assert "@prefix oc:" not in graph
    # And on the terms: the TBox comment is allowed to name the other namespace.
    import rdflib

    parsed = rdflib.Graph()
    parsed.parse(data=graph, format="turtle")
    skills = "https://ontoskills.sh/ontology#"
    borrowed = {
        str(term)
        for triple in parsed
        for term in triple
        if str(term).startswith(skills)
    }
    assert borrowed == set(), borrowed


def test_published_ontology_is_the_spec_byte_for_byte():
    """The site serves the TBox; a copy that drifts is a second definition."""
    from pathlib import Path

    from compiler.documents.store import ONTOLOGY_PATH

    published = Path(__file__).resolve().parents[2] / "site" / "public" / "ontology" / "documents.ttl"
    assert published.exists(), published
    assert published.read_bytes() == ONTOLOGY_PATH.read_bytes()


def test_graph_prefixes_are_declared_once(tmp_path):
    """The TBox is inlined for offline parsing; its own prefixes are stripped."""
    documents, spans, claims = _rows()
    kb = KnowledgeBase(tmp_path)
    kb.write(manifest={}, documents=documents, spans=spans, claims=claims)
    graph = (tmp_path / "graph.ttl").read_text(encoding="utf-8")
    assert graph.count("@prefix") == 8


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


def test_an_unknown_evidence_role_is_refused(tmp_path):
    """A role the vocabulary does not have must not be silently called support."""
    documents, spans, claims = _rows()
    claims[0]["evidence"][0]["role"] = "maybe"
    with pytest.raises(ValueError, match="evidence role 'maybe'"):
        KnowledgeBase(tmp_path).write(
            manifest={}, documents=documents, spans=spans, claims=claims
        )


def test_a_source_url_that_is_not_an_iri_is_refused(tmp_path):
    """The declared range is an IRI, so a malformed URL is an error, not a gap."""
    documents, spans, claims = _rows()
    documents[0]["url"] = "not a url"
    with pytest.raises(ValueError, match="not an IRI"):
        KnowledgeBase(tmp_path).write(
            manifest={}, documents=documents, spans=spans, claims=claims
        )
