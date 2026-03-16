import pytest
from schemas import Requirement, ExecutionPayload, ExtractedSkill


def test_schemas_validation():
    req = Requirement(type="EnvVar", value="API_KEY")
    assert req.optional is False

    payload = ExecutionPayload(executor="shell", code="echo 'hello'")
    assert payload.timeout is None

    skill = ExtractedSkill(
        id="test-skill",
        hash="abcdef",
        nature="A test skill",
        genus="Test",
        differentia="that tests",
        intents=["testing"],
        requirements=[req],
        constraints=["must test"],
        execution_payload=payload,
        provenance="/path",
    )
    assert skill.id == "test-skill"
