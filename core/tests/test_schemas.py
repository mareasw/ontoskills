import pytest
from pydantic import ValidationError
from compiler.schemas import Requirement, ExecutionPayload, ExtractedSkill, StateTransition


def test_skill_type_computed_as_executable():
    """Test that skill_type is 'executable' when execution_payload exists."""
    skill = ExtractedSkill(
        id="test",
        hash="abc123",
        nature="Test",
        genus="Test",
        differentia="test",
        intents=["test"],
        requirements=[],
        generated_by="claude-opus-4-6",
        execution_payload=ExecutionPayload(executor="python", code="print('hi')")
    )
    assert skill.skill_type == "executable"


def test_skill_type_computed_as_declarative():
    """Test that skill_type is 'declarative' when no execution_payload."""
    skill = ExtractedSkill(
        id="test",
        hash="abc123",
        nature="Test",
        genus="Test",
        differentia="test",
        intents=["test"],
        requirements=[],
        generated_by="claude-opus-4-6"
    )
    assert skill.skill_type == "declarative"


def test_state_transition_model():
    """Test StateTransition model with valid URIs."""
    st = StateTransition(
        requires_state=["oc:SystemAuthenticated", "oc:UserLoggedIn"],
        yields_state=["oc:DocumentCreated"],
        handles_failure=["oc:PermissionDenied", "oc:ResourceNotFound"]
    )
    assert st.requires_state == ["oc:SystemAuthenticated", "oc:UserLoggedIn"]
    assert st.yields_state == ["oc:DocumentCreated"]
    assert st.handles_failure == ["oc:PermissionDenied", "oc:ResourceNotFound"]


def test_state_transition_defaults():
    """Test StateTransition model with empty lists (defaults)."""
    st = StateTransition()
    assert st.requires_state == []
    assert st.yields_state == []
    assert st.handles_failure == []


def test_state_transition_uri_validation():
    """Test that invalid URIs raise ValidationError."""
    with pytest.raises(ValidationError) as exc_info:
        StateTransition(requires_state=["invalid-uri"])
    assert "state URIs" in str(exc_info.value).lower() or "pattern" in str(exc_info.value).lower()

    with pytest.raises(ValidationError) as exc_info:
        StateTransition(yields_state=["oc:invalid", "oc:AnotherInvalid"])
    assert "state URIs" in str(exc_info.value).lower() or "pattern" in str(exc_info.value).lower()

    with pytest.raises(ValidationError) as exc_info:
        StateTransition(handles_failure=["oc:123InvalidStart"])
    assert "state URIs" in str(exc_info.value).lower() or "pattern" in str(exc_info.value).lower()


def test_schemas_validation():
    req = Requirement(type="EnvVar", value="API_KEY")
    assert req.optional is False

    payload = ExecutionPayload(executor="shell", code="echo 'hello'")
    assert payload.timeout is None

    state_transition = StateTransition(
        requires_state=["oc:SystemAuthenticated"],
        yields_state=["oc:DocumentCreated"],
        handles_failure=["oc:PermissionDenied"]
    )

    skill = ExtractedSkill(
        id="test-skill",
        hash="abcdef",
        nature="A test skill",
        genus="Test",
        differentia="that tests",
        intents=["testing"],
        requirements=[req],
        state_transitions=state_transition,
        generated_by="gpt-4",
        execution_payload=payload,
        provenance="/path",
    )
    assert skill.id == "test-skill"
    assert skill.generated_by == "gpt-4"
    assert skill.state_transitions.requires_state == ["oc:SystemAuthenticated"]


# ============================================================================
# KnowledgeNode Tests (10-Dimensional Epistemic TBox)
# ============================================================================


def test_knowledge_node_model():
    """Test KnowledgeNode model with valid data."""
    from compiler.schemas import KnowledgeNode, SeverityLevel

    kn = KnowledgeNode(
        node_type="AntiPattern",
        directive_content="Never modify the spreadsheet without preserving formulas",
        applies_to_context="When editing any Excel file",
        has_rationale="Formula corruption breaks the spreadsheet's computational integrity",
        severity_level=SeverityLevel.CRITICAL
    )
    assert kn.node_type == "AntiPattern"
    assert kn.severity_level == SeverityLevel.CRITICAL


def test_knowledge_node_without_severity():
    """Test KnowledgeNode model without optional severity_level."""
    from compiler.schemas import KnowledgeNode

    kn = KnowledgeNode(
        node_type="Heuristic",
        directive_content="Use absolute paths for file operations",
        applies_to_context="Always",
        has_rationale="Relative paths can break when cwd changes"
    )
    assert kn.severity_level is None


def test_knowledge_node_invalid_type():
    """Test that invalid node_type raises ValidationError."""
    from compiler.schemas import KnowledgeNode

    with pytest.raises(ValidationError):
        KnowledgeNode(
            node_type="InvalidType",
            directive_content="test",
            applies_to_context="test",
            has_rationale="test"
        )


def test_severity_level_enum():
    """Test SeverityLevel enum values."""
    from compiler.schemas import SeverityLevel

    assert SeverityLevel.CRITICAL.value == "CRITICAL"
    assert SeverityLevel.HIGH.value == "HIGH"
    assert SeverityLevel.MEDIUM.value == "MEDIUM"
    assert SeverityLevel.LOW.value == "LOW"


def test_extracted_skill_with_knowledge_nodes():
    """Test ExtractedSkill with knowledge_nodes field."""
    from compiler.schemas import ExtractedSkill, KnowledgeNode

    skill = ExtractedSkill(
        id="test-skill",
        hash="abc123",
        nature="Test",
        genus="Test",
        differentia="test",
        intents=["test"],
        requirements=[],
        generated_by="claude-opus-4-6",
        knowledge_nodes=[
            KnowledgeNode(
                node_type="Standard",
                directive_content="Always validate input",
                applies_to_context="Before processing",
                has_rationale="Prevents injection attacks"
            )
        ]
    )
    assert len(skill.knowledge_nodes) == 1
    assert skill.knowledge_nodes[0].node_type == "Standard"
