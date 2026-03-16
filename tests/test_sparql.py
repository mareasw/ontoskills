import pytest
from pathlib import Path
from rdflib import Graph, RDF, Literal
from rdflib.namespace import RDF as RDF_NS
from loader import create_ontology_graph, AG
from sparql import execute_sparql, format_results


@pytest.fixture
def sample_ontology(tmp_path):
    """Create a sample ontology for testing."""
    graph = create_ontology_graph()

    # Add some test skills
    skill1 = AG["skill_abc123"]
    graph.add((skill1, RDF.type, AG.Skill))
    graph.add((skill1, AG.nature, Literal("A testing skill")))
    graph.add((skill1, AG.resolvesIntent, Literal("test")))
    graph.add((skill1, AG.resolvesIntent, Literal("verify")))

    skill2 = AG["skill_def456"]
    graph.add((skill2, RDF.type, AG.Skill))
    graph.add((skill2, AG.nature, Literal("A documentation skill")))
    graph.add((skill2, AG.resolvesIntent, Literal("document")))

    # Save to temp file
    ontology_path = tmp_path / "skills.ttl"
    graph.serialize(ontology_path, format="turtle")

    return ontology_path


def test_execute_sparql_select(sample_ontology):
    """Test basic SELECT query."""
    query = "SELECT ?s ?n WHERE { ?s <http://agentic.web/ontology#nature> ?n }"
    results, vars = execute_sparql(sample_ontology, query)
    assert len(results) == 2


def test_execute_sparql_with_prefix(sample_ontology):
    """Test query with prefix declaration."""
    query = """
    PREFIX ag: <http://agentic.web/ontology#>
    SELECT ?skill WHERE { ?skill a ag:Skill }
    """
    results, vars = execute_sparql(sample_ontology, query)
    assert len(results) == 2


def test_execute_sparql_filter(sample_ontology):
    """Test query with FILTER."""
    query = """
    PREFIX ag: <http://agentic.web/ontology#>
    SELECT ?s WHERE {
        ?s a ag:Skill ;
           ag:nature ?n .
        FILTER(CONTAINS(?n, "testing"))
    }
    """
    results, vars = execute_sparql(sample_ontology, query)
    assert len(results) == 1


def test_execute_sparql_invalid_query(sample_ontology):
    """Test that invalid query raises error."""
    from exceptions import SPARQLError
    with pytest.raises(SPARQLError):
        execute_sparql(sample_ontology, "THIS IS NOT VALID SPARQL")


def test_format_results_table():
    """Test table formatting."""
    # Create mock results
    results = [
        {"s": "skill1", "n": "nature1"},
        {"s": "skill2", "n": "nature2"},
    ]
    output = format_results(results, "table", ["s", "n"])
    assert "skill1" in output
    assert "skill2" in output


def test_format_results_json():
    """Test JSON formatting."""
    results = [
        {"s": "skill1", "n": "nature1"},
    ]
    output = format_results(results, "json", ["s", "n"])
    import json
    data = json.loads(output)
    assert len(data) == 1
    assert data[0]["s"] == "skill1"


def test_format_results_turtle():
    """Test turtle formatting."""
    results = [
        {"s": "skill1", "n": "nature1"},
    ]
    output = format_results(results, "turtle", ["s", "n"])
    assert "skill1" in output
