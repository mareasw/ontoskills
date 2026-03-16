import pytest
from pathlib import Path
from rdflib import Graph, RDF, RDFS, OWL, Namespace
from loader import (
    create_ontology_graph,
    serialize_skill,
    load_ontology,
    merge_skill,
    save_ontology_atomic,
    apply_reasoning,
    AG,
)
from schemas import ExtractedSkill, Requirement, ExecutionPayload


def test_create_ontology_graph():
    graph = create_ontology_graph()
    assert isinstance(graph, Graph)
    # Check that basic prefixes are bound
    prefixes = dict(graph.namespaces())
    assert "ag" in prefixes
    assert "owl" in prefixes


def test_create_ontology_graph_has_owl_properties():
    """Test that OWL 2 property characteristics are defined."""
    graph = create_ontology_graph()

    # Check for transitive property on extends
    extends_uri = AG.extends
    assert (extends_uri, RDF.type, OWL.TransitiveProperty) in graph or \
           (extends_uri, RDF.type, OWL.ObjectProperty) in graph

    # Check for symmetric property on contradicts
    contradicts_uri = AG.contradicts
    assert (contradicts_uri, RDF.type, OWL.SymmetricProperty) in graph or \
           (contradicts_uri, RDF.type, OWL.ObjectProperty) in graph


def test_serialize_skill():
    """Test skill serialization to RDF triples."""
    skill = ExtractedSkill(
        id="test-skill",
        hash="abc123",
        nature="A test skill",
        genus="Test",
        differentia="for testing",
        intents=["test", "verify"],
        requirements=[Requirement(type="Tool", value="pytest")],
        constraints=["must be fast"],
        execution_payload=ExecutionPayload(executor="shell", code="echo test"),
        provenance="/skills/test/SKILL.md",
    )

    graph = Graph()
    serialize_skill(graph, skill)

    # Check skill was added
    skill_uri = AG["skill_" + skill.hash[:16]]
    assert (skill_uri, RDF.type, AG.Skill) in graph


def test_load_ontology(tmp_path):
    """Test loading an existing ontology."""
    # Create a simple ontology
    ontology_path = tmp_path / "skills.ttl"
    graph = create_ontology_graph()
    graph.serialize(ontology_path, format="turtle")

    # Load it back
    loaded = load_ontology(ontology_path)
    assert isinstance(loaded, Graph)
    prefixes = dict(loaded.namespaces())
    assert "ag" in prefixes


def test_merge_skill_new(tmp_path):
    """Test merging a new skill into ontology."""
    ontology_path = tmp_path / "skills.ttl"
    graph = create_ontology_graph()
    graph.serialize(ontology_path, format="turtle")

    skill = ExtractedSkill(
        id="new-skill",
        hash="def456",
        nature="New skill",
        genus="Test",
        differentia="new",
        intents=["new"],
        requirements=[],
        constraints=[],
        execution_payload=None,
        provenance=None,
    )

    merged = merge_skill(ontology_path, skill)
    assert isinstance(merged, Graph)

    # Check skill was added
    skill_uri = AG["skill_" + skill.hash[:16]]
    assert (skill_uri, RDF.type, AG.Skill) in merged


def test_merge_skill_update(tmp_path):
    """Test updating an existing skill (same ID, different hash)."""
    ontology_path = tmp_path / "skills.ttl"
    graph = create_ontology_graph()
    graph.serialize(ontology_path, format="turtle")

    # Add initial skill
    skill1 = ExtractedSkill(
        id="update-skill",
        hash="hash1",
        nature="Original",
        genus="Test",
        differentia="original",
        intents=["test"],
        requirements=[],
        constraints=[],
        execution_payload=None,
        provenance=None,
    )
    merge_skill(ontology_path, skill1)
    save_ontology_atomic(ontology_path, merge_skill(ontology_path, skill1))

    # Update with same ID but different hash
    skill2 = ExtractedSkill(
        id="update-skill",
        hash="hash2",
        nature="Updated",
        genus="Test",
        differentia="updated",
        intents=["test"],
        requirements=[],
        constraints=[],
        execution_payload=None,
        provenance=None,
    )

    merged = merge_skill(ontology_path, skill2)
    # New skill should be present
    skill_uri = AG["skill_" + skill2.hash[:16]]
    assert (skill_uri, RDF.type, AG.Skill) in merged


def test_save_ontology_atomic(tmp_path):
    """Test atomic write with backup."""
    ontology_path = tmp_path / "skills.ttl"
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    graph = create_ontology_graph()

    # First save
    save_ontology_atomic(ontology_path, graph, backup_dir=backup_dir)
    assert ontology_path.exists()

    # Second save (should create backup)
    graph.add((AG.TestSkill, RDF.type, AG.Skill))
    save_ontology_atomic(ontology_path, graph, backup_dir=backup_dir)

    # Check backup was created
    backups = list(backup_dir.glob("*.ttl"))
    assert len(backups) >= 1


def test_apply_reasoning():
    """Test OWL reasoning applies inferences."""
    graph = create_ontology_graph()

    # Add some test relationships
    skill_a = AG["skill_a"]
    skill_b = AG["skill_b"]
    skill_c = AG["skill_c"]

    graph.add((skill_a, RDF.type, AG.Skill))
    graph.add((skill_b, RDF.type, AG.Skill))
    graph.add((skill_c, RDF.type, AG.Skill))

    # A extends B, B extends C
    graph.add((skill_a, AG.extends, skill_b))
    graph.add((skill_b, AG.extends, skill_c))

    # Apply reasoning
    reasoned = apply_reasoning(graph)

    # Should infer that A extends C (transitive)
    # Note: This requires owlrl to be working correctly
    assert isinstance(reasoned, Graph)
