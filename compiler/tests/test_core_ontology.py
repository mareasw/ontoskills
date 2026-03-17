"""
Tests for the core_ontology module.

These tests verify the OntoClaw core ontology (TBox) creation including:
- Namespace configuration
- Core class definitions (Skill, State, Attempt, ExecutionPayload)
- State transition properties
- Execution payload properties
- Skill relationship properties
- Predefined core and failure states
"""
import pytest
from pathlib import Path
from rdflib import Graph, RDF, RDFS, OWL, Namespace

from compiler.core_ontology import get_oc_namespace, create_core_ontology
from compiler.config import BASE_URI, CORE_STATES, FAILURE_STATES


class TestGetOcNamespace:
    """Tests for get_oc_namespace function."""

    def test_returns_namespace(self):
        """Test that get_oc_namespace returns a Namespace instance."""
        oc = get_oc_namespace()
        assert isinstance(oc, Namespace)

    def test_namespace_uses_base_uri(self):
        """Test that namespace uses configured BASE_URI."""
        oc = get_oc_namespace()
        assert str(oc) == BASE_URI

    def test_namespace_can_create_uris(self):
        """Test that namespace can create URI references."""
        oc = get_oc_namespace()
        skill_uri = oc.Skill
        assert str(skill_uri) == BASE_URI + "Skill"


class TestCreateCoreOntology:
    """Tests for create_core_ontology function."""

    def test_creates_graph(self, tmp_path):
        """Test that create_core_ontology returns a Graph."""
        output_path = tmp_path / "ontoclaw-core.ttl"
        graph = create_core_ontology(output_path)
        assert isinstance(graph, Graph)

    def test_creates_file(self, tmp_path):
        """Test that create_core_ontology creates the output file."""
        output_path = tmp_path / "ontoclaw-core.ttl"
        create_core_ontology(output_path)
        assert output_path.exists()

    def test_creates_parent_directories(self, tmp_path):
        """Test that create_core_ontology creates parent directories if needed."""
        output_path = tmp_path / "nested" / "dir" / "ontoclaw-core.ttl"
        create_core_ontology(output_path)
        assert output_path.exists()
        assert output_path.parent.is_dir()

    def test_uses_default_output_path(self, tmp_path):
        """Test that create_core_ontology uses default path when None provided."""
        # When output_path is None, it uses OUTPUT_DIR/ontoclaw-core.ttl
        # This test verifies the function doesn't error with None
        graph = create_core_ontology(None)
        assert isinstance(graph, Graph)

    def test_graph_has_triples(self, tmp_path):
        """Test that the created graph has triples."""
        output_path = tmp_path / "ontoclaw-core.ttl"
        graph = create_core_ontology(output_path)
        assert len(graph) > 0


class TestCoreClasses:
    """Tests for core class definitions in the ontology."""

    @pytest.fixture
    def core_ontology(self, tmp_path):
        """Fixture that creates core ontology and returns graph."""
        output_path = tmp_path / "ontoclaw-core.ttl"
        graph = create_core_ontology(output_path)
        return graph

    @pytest.fixture
    def oc(self):
        """Fixture that returns the OntoClaw namespace."""
        return get_oc_namespace()

    def test_skill_class_defined(self, core_ontology, oc):
        """Test that oc:Skill class is defined."""
        assert (oc.Skill, RDF.type, OWL.Class) in core_ontology
        assert (oc.Skill, RDFS.label, None) in core_ontology

    def test_executable_skill_class_defined(self, core_ontology, oc):
        """Test that oc:ExecutableSkill class is defined as subclass of Skill."""
        assert (oc.ExecutableSkill, RDF.type, OWL.Class) in core_ontology
        assert (oc.ExecutableSkill, RDFS.subClassOf, oc.Skill) in core_ontology

    def test_declarative_skill_class_defined(self, core_ontology, oc):
        """Test that oc:DeclarativeSkill class is defined as subclass of Skill."""
        assert (oc.DeclarativeSkill, RDF.type, OWL.Class) in core_ontology
        assert (oc.DeclarativeSkill, RDFS.subClassOf, oc.Skill) in core_ontology

    def test_state_class_defined(self, core_ontology, oc):
        """Test that oc:State class is defined."""
        assert (oc.State, RDF.type, OWL.Class) in core_ontology

    def test_attempt_class_defined(self, core_ontology, oc):
        """Test that oc:Attempt class is defined."""
        assert (oc.Attempt, RDF.type, OWL.Class) in core_ontology

    def test_execution_payload_class_defined(self, core_ontology, oc):
        """Test that oc:ExecutionPayload class is defined."""
        assert (oc.ExecutionPayload, RDF.type, OWL.Class) in core_ontology


class TestStateTransitionProperties:
    """Tests for state transition property definitions."""

    @pytest.fixture
    def core_ontology(self, tmp_path):
        """Fixture that creates core ontology and returns graph."""
        output_path = tmp_path / "ontoclaw-core.ttl"
        graph = create_core_ontology(output_path)
        return graph

    @pytest.fixture
    def oc(self):
        """Fixture that returns the OntoClaw namespace."""
        return get_oc_namespace()

    def test_requires_state_property(self, core_ontology, oc):
        """Test oc:requiresState property (Skill -> State)."""
        assert (oc.requiresState, RDF.type, OWL.ObjectProperty) in core_ontology
        assert (oc.requiresState, RDFS.domain, oc.Skill) in core_ontology
        assert (oc.requiresState, RDFS.range, oc.State) in core_ontology

    def test_yields_state_property(self, core_ontology, oc):
        """Test oc:yieldsState property (Skill -> State)."""
        assert (oc.yieldsState, RDF.type, OWL.ObjectProperty) in core_ontology
        assert (oc.yieldsState, RDFS.domain, oc.Skill) in core_ontology
        assert (oc.yieldsState, RDFS.range, oc.State) in core_ontology

    def test_handles_failure_property(self, core_ontology, oc):
        """Test oc:handlesFailure property (Skill -> State)."""
        assert (oc.handlesFailure, RDF.type, OWL.ObjectProperty) in core_ontology
        assert (oc.handlesFailure, RDFS.domain, oc.Skill) in core_ontology
        assert (oc.handlesFailure, RDFS.range, oc.State) in core_ontology

    def test_has_status_property(self, core_ontology, oc):
        """Test oc:hasStatus property (Attempt -> State)."""
        assert (oc.hasStatus, RDF.type, OWL.ObjectProperty) in core_ontology
        assert (oc.hasStatus, RDFS.domain, oc.Attempt) in core_ontology
        assert (oc.hasStatus, RDFS.range, oc.State) in core_ontology


class TestExecutionPayloadProperties:
    """Tests for execution payload property definitions."""

    @pytest.fixture
    def core_ontology(self, tmp_path):
        """Fixture that creates core ontology and returns graph."""
        output_path = tmp_path / "ontoclaw-core.ttl"
        graph = create_core_ontology(output_path)
        return graph

    @pytest.fixture
    def oc(self):
        """Fixture that returns the OntoClaw namespace."""
        return get_oc_namespace()

    def test_has_payload_property(self, core_ontology, oc):
        """Test oc:hasPayload property (Skill -> ExecutionPayload)."""
        assert (oc.hasPayload, RDF.type, OWL.ObjectProperty) in core_ontology
        assert (oc.hasPayload, RDFS.domain, oc.Skill) in core_ontology
        assert (oc.hasPayload, RDFS.range, oc.ExecutionPayload) in core_ontology

    def test_executor_property(self, core_ontology, oc):
        """Test oc:executor datatype property."""
        assert (oc.executor, RDF.type, OWL.DatatypeProperty) in core_ontology
        assert (oc.executor, RDFS.domain, oc.ExecutionPayload) in core_ontology

    def test_code_property(self, core_ontology, oc):
        """Test oc:code datatype property."""
        assert (oc.code, RDF.type, OWL.DatatypeProperty) in core_ontology
        assert (oc.code, RDFS.domain, oc.ExecutionPayload) in core_ontology

    def test_timeout_property(self, core_ontology, oc):
        """Test oc:timeout datatype property."""
        assert (oc.timeout, RDF.type, OWL.DatatypeProperty) in core_ontology
        assert (oc.timeout, RDFS.domain, oc.ExecutionPayload) in core_ontology


class TestSkillRelationshipProperties:
    """Tests for skill relationship property definitions."""

    @pytest.fixture
    def core_ontology(self, tmp_path):
        """Fixture that creates core ontology and returns graph."""
        output_path = tmp_path / "ontoclaw-core.ttl"
        graph = create_core_ontology(output_path)
        return graph

    @pytest.fixture
    def oc(self):
        """Fixture that returns the OntoClaw namespace."""
        return get_oc_namespace()

    def test_depends_on_property(self, core_ontology, oc):
        """Test oc:dependsOn asymmetric property with inverse."""
        assert (oc.dependsOn, RDF.type, OWL.ObjectProperty) in core_ontology
        assert (oc.dependsOn, RDF.type, OWL.AsymmetricProperty) in core_ontology
        assert (oc.dependsOn, OWL.inverseOf, oc.enables) in core_ontology

    def test_enables_property(self, core_ontology, oc):
        """Test oc:enables property (inverse of dependsOn)."""
        assert (oc.enables, RDF.type, OWL.ObjectProperty) in core_ontology

    def test_extends_property(self, core_ontology, oc):
        """Test oc:extends transitive property."""
        assert (oc.extends, RDF.type, OWL.ObjectProperty) in core_ontology
        assert (oc.extends, RDF.type, OWL.TransitiveProperty) in core_ontology

    def test_is_extended_by_property(self, core_ontology, oc):
        """Test oc:isExtendedBy property (inverse of extends)."""
        assert (oc.isExtendedBy, RDF.type, OWL.ObjectProperty) in core_ontology

    def test_contradicts_property(self, core_ontology, oc):
        """Test oc:contradicts symmetric property."""
        assert (oc.contradicts, RDF.type, OWL.ObjectProperty) in core_ontology
        assert (oc.contradicts, RDF.type, OWL.SymmetricProperty) in core_ontology


class TestAdditionalSkillProperties:
    """Tests for additional skill property definitions."""

    @pytest.fixture
    def core_ontology(self, tmp_path):
        """Fixture that creates core ontology and returns graph."""
        output_path = tmp_path / "ontoclaw-core.ttl"
        graph = create_core_ontology(output_path)
        return graph

    @pytest.fixture
    def oc(self):
        """Fixture that returns the OntoClaw namespace."""
        return get_oc_namespace()

    def test_generated_by_property(self, core_ontology, oc):
        """Test oc:generatedBy datatype property for LLM attestation."""
        assert (oc.generatedBy, RDF.type, OWL.DatatypeProperty) in core_ontology
        assert (oc.generatedBy, RDFS.domain, oc.Skill) in core_ontology

    def test_content_hash_property(self, core_ontology, oc):
        """Test oc:contentHash datatype property."""
        assert (oc.contentHash, RDF.type, OWL.DatatypeProperty) in core_ontology
        assert (oc.contentHash, RDFS.domain, oc.Skill) in core_ontology

    def test_nature_property(self, core_ontology, oc):
        """Test oc:nature datatype property."""
        assert (oc.nature, RDF.type, OWL.DatatypeProperty) in core_ontology
        assert (oc.nature, RDFS.domain, oc.Skill) in core_ontology

    def test_differentia_property(self, core_ontology, oc):
        """Test oc:differentia datatype property."""
        assert (oc.differentia, RDF.type, OWL.DatatypeProperty) in core_ontology
        assert (oc.differentia, RDFS.domain, oc.Skill) in core_ontology

    def test_resolves_intent_property(self, core_ontology, oc):
        """Test oc:resolvesIntent datatype property."""
        assert (oc.resolvesIntent, RDF.type, OWL.DatatypeProperty) in core_ontology
        assert (oc.resolvesIntent, RDFS.domain, oc.Skill) in core_ontology

    def test_has_constraint_property(self, core_ontology, oc):
        """Test oc:hasConstraint datatype property."""
        assert (oc.hasConstraint, RDF.type, OWL.DatatypeProperty) in core_ontology
        assert (oc.hasConstraint, RDFS.domain, oc.Skill) in core_ontology


class TestPredefinedStates:
    """Tests for predefined core and failure states."""

    @pytest.fixture
    def core_ontology(self, tmp_path):
        """Fixture that creates core ontology and returns graph."""
        output_path = tmp_path / "ontoclaw-core.ttl"
        graph = create_core_ontology(output_path)
        return graph

    @pytest.fixture
    def oc(self):
        """Fixture that returns the OntoClaw namespace."""
        return get_oc_namespace()

    def test_core_states_defined(self, core_ontology, oc):
        """Test that all core states are defined as subclasses of State."""
        for state_name, state_fragment in CORE_STATES.items():
            state_uri = oc[state_fragment.lstrip('#')]
            assert (state_uri, RDF.type, OWL.Class) in core_ontology
            assert (state_uri, RDFS.subClassOf, oc.State) in core_ontology

    def test_failure_states_defined(self, core_ontology, oc):
        """Test that all failure states are defined as subclasses of State."""
        for state_name, state_fragment in FAILURE_STATES.items():
            state_uri = oc[state_fragment.lstrip('#')]
            assert (state_uri, RDF.type, OWL.Class) in core_ontology
            assert (state_uri, RDFS.subClassOf, oc.State) in core_ontology

    def test_core_states_have_labels(self, core_ontology, oc):
        """Test that core states have RDFS labels."""
        from rdflib import Literal
        for state_name, state_fragment in CORE_STATES.items():
            state_uri = oc[state_fragment.lstrip('#')]
            assert (state_uri, RDFS.label, Literal(state_name)) in core_ontology

    def test_failure_states_have_labels(self, core_ontology, oc):
        """Test that failure states have RDFS labels."""
        from rdflib import Literal
        for state_name, state_fragment in FAILURE_STATES.items():
            state_uri = oc[state_fragment.lstrip('#')]
            assert (state_uri, RDFS.label, Literal(state_name)) in core_ontology


class TestOntologyHeader:
    """Tests for ontology header/metadata."""

    @pytest.fixture
    def core_ontology(self, tmp_path):
        """Fixture that creates core ontology and returns graph."""
        output_path = tmp_path / "ontoclaw-core.ttl"
        graph = create_core_ontology(output_path)
        return graph

    def test_ontology_has_type(self, core_ontology):
        """Test that the ontology has OWL.Ontology type."""
        from rdflib import URIRef
        base_uri = URIRef(BASE_URI.rstrip('#'))
        assert (base_uri, RDF.type, OWL.Ontology) in core_ontology

    def test_ontology_has_title(self, core_ontology):
        """Test that the ontology has a title."""
        from rdflib import URIRef
        from rdflib.namespace import DCTERMS
        base_uri = URIRef(BASE_URI.rstrip('#'))
        assert (base_uri, DCTERMS.title, None) in core_ontology

    def test_ontology_has_description(self, core_ontology):
        """Test that the ontology has a description."""
        from rdflib import URIRef
        from rdflib.namespace import DCTERMS
        base_uri = URIRef(BASE_URI.rstrip('#'))
        assert (base_uri, DCTERMS.description, None) in core_ontology

    def test_namespaces_bound(self, core_ontology):
        """Test that required namespaces are bound in the graph."""
        prefixes = dict(core_ontology.namespaces())
        assert "oc" in prefixes
        assert "owl" in prefixes
        assert "rdf" in prefixes
        assert "rdfs" in prefixes
        assert "dcterms" in prefixes
        assert "skos" in prefixes
        assert "prov" in prefixes
