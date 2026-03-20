"""Tests for embeddings module."""

import json
import tempfile
from pathlib import Path

import pytest
from rdflib import Graph, Namespace, Literal, RDF

from compiler.embeddings.exporter import extract_intents_from_ontology, export_embeddings, MODEL_NAME, EMBEDDING_DIM


OC = Namespace("https://ontoskills.sh/ontology#")


class TestExtractIntents:
    """Tests for intent extraction from ontology."""

    def test_extract_intents_single_skill(self, tmp_path: Path):
        """Extract intents from a single skill."""
        # Create test ontology
        g = Graph()
        g.bind("oc", OC)

        skill = OC["test-skill"]
        g.add((skill, RDF.type, OC.Skill))
        g.add((skill, OC.resolvesIntent, Literal("create_pdf")))

        ontology_path = tmp_path / "test.ttl"
        g.serialize(ontology_path, format="turtle")

        # Extract intents
        intents = extract_intents_from_ontology(ontology_path)

        assert len(intents) == 1
        assert intents[0]["intent"] == "create_pdf"
        assert "test-skill" in intents[0]["skills"]

    def test_extract_intents_multiple_skills_same_intent(self, tmp_path: Path):
        """Multiple skills can resolve the same intent."""
        g = Graph()
        g.bind("oc", OC)

        skill1 = OC["skill-a"]
        skill2 = OC["skill-b"]
        g.add((skill1, RDF.type, OC.Skill))
        g.add((skill1, OC.resolvesIntent, Literal("send_email")))
        g.add((skill2, RDF.type, OC.Skill))
        g.add((skill2, OC.resolvesIntent, Literal("send_email")))

        ontology_path = tmp_path / "test.ttl"
        g.serialize(ontology_path, format="turtle")

        intents = extract_intents_from_ontology(ontology_path)

        assert len(intents) == 1
        assert intents[0]["intent"] == "send_email"
        assert len(intents[0]["skills"]) == 2

    def test_extract_intents_no_intents(self, tmp_path: Path):
        """Return empty list when no intents exist."""
        g = Graph()
        g.bind("oc", OC)

        skill = OC["orphan-skill"]
        g.add((skill, RDF.type, OC.Skill))
        # No resolvesIntent

        ontology_path = tmp_path / "test.ttl"
        g.serialize(ontology_path, format="turtle")

        intents = extract_intents_from_ontology(ontology_path)

        assert intents == []


class TestExportEmbeddings:
    """Tests for full embedding export."""

    @pytest.mark.integration
    def test_export_embeddings_creates_files(self, tmp_path: Path):
        """Export creates all required files."""
        # Create test ontology with intents
        g = Graph()
        g.bind("oc", OC)

        skill = OC["pdf"]
        g.add((skill, RDF.type, OC.Skill))
        g.add((skill, OC.resolvesIntent, Literal("create_pdf")))
        g.add((skill, OC.resolvesIntent, Literal("export_document")))

        ontology_root = tmp_path / "ontoskills"
        ontology_root.mkdir()
        (ontology_root / "index.ttl").write_text(g.serialize(format="turtle"))

        output_dir = tmp_path / "embeddings"

        export_embeddings(ontology_root, output_dir)

        assert (output_dir / "intents.json").exists()

        with open(output_dir / "intents.json") as f:
            data = json.load(f)

        assert data["model"] == MODEL_NAME
        assert data["dimension"] == EMBEDDING_DIM
        assert len(data["intents"]) == 2

        for intent_entry in data["intents"]:
            assert "intent" in intent_entry
            assert "embedding" in intent_entry
            assert len(intent_entry["embedding"]) == EMBEDDING_DIM
            assert "skills" in intent_entry
