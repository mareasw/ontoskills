from unittest.mock import patch
from compiler.transformer import (
    OPENAI_TOOLS,
    execute_tool,
    tool_use_loop,
    TOOLS,
    build_sub_skill_context_prompt,
)
from compiler.llm import LLMResponse, ToolCall, tool_message
from compiler.schemas import ExtractedSkill


def test_tools_defined():
    """Test that all required tools are defined."""
    tool_names = [t["name"] for t in TOOLS]
    assert "list_files" in tool_names
    assert "read_file" in tool_names
    assert "extract_skill" in tool_names


def test_tool_message():
    """Test tool result message creation (OpenAI shape)."""
    result = tool_message("tool_123", '{"files": ["SKILL.md"]}')
    assert result["role"] == "tool"
    assert result["tool_call_id"] == "tool_123"
    assert result["content"] == '{"files": ["SKILL.md"]}'


def test_openai_tools_shape():
    """Canonical tools are converted to OpenAI function specs."""
    names = [t["function"]["name"] for t in OPENAI_TOOLS]
    assert names == [t["name"] for t in TOOLS]
    for tool in OPENAI_TOOLS:
        assert tool["type"] == "function"
        assert tool["function"]["parameters"]["type"] == "object"


def test_execute_tool_list_files(tmp_path):
    """Test list_files tool execution."""
    skill_dir = tmp_path / "test-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# Test Skill")
    (skill_dir / "references").mkdir()
    (skill_dir / "references" / "guide.md").write_text("Guide")

    import json
    result = execute_tool("list_files", {}, skill_dir)
    data = json.loads(result)
    assert "SKILL.md" in data["files"]
    assert "references/guide.md" in data["files"]


def test_execute_tool_read_file(tmp_path):
    """Test read_file tool execution."""
    skill_dir = tmp_path / "test-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# Test Skill\n\nContent here")

    import json
    result = execute_tool("read_file", {"path": "SKILL.md"}, skill_dir)
    data = json.loads(result)
    assert data["content"] == "# Test Skill\n\nContent here"
    assert data["path"] == "SKILL.md"


def test_execute_tool_read_file_not_found(tmp_path):
    """Test read_file tool with non-existent file."""
    import json
    result = execute_tool("read_file", {"path": "nonexistent.md"}, tmp_path)
    data = json.loads(result)
    assert "error" in data


def test_execute_tool_extract_skill(tmp_path):
    """Test extract_skill tool returns success."""
    import json
    extraction_data = {
        "id": "test-skill",
        "hash": "abc123",
        "nature": "A test skill",
        "genus": "Test",
        "differentia": "for testing",
        "intents": ["testing"],
        "requirements": [],
        "constraints": [],
        "execution_payload": None,
        "provenance": None,
    }
    result = execute_tool("extract_skill", extraction_data, tmp_path)
    data = json.loads(result)
    assert data["status"] == "success"


@patch("compiler.transformer.chat")
def test_tool_use_loop_success(mock_chat, tmp_path):
    """Test successful tool-use loop."""
    skill_dir = tmp_path / "test-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# Test")

    extraction = {
        "id": "test-skill",
        "hash": "abc123",
        "nature": "Test",
        "genus": "Test",
        "differentia": "test",
        "intents": ["test"],
        "requirements": [],
        "constraints": [],
        "execution_payload": None,
        "provenance": None,
    }

    responses = [
        LLMResponse(
            text="",
            tool_calls=(ToolCall(id="t1", name="list_files", arguments={}),),
            finish_reason="tool_calls",
        ),
        LLMResponse(
            text="",
            tool_calls=(
                ToolCall(id="t2", name="read_file", arguments={"path": "SKILL.md"}),
            ),
            finish_reason="tool_calls",
        ),
        LLMResponse(
            text="",
            tool_calls=(
                ToolCall(id="t3", name="extract_skill", arguments=extraction),
            ),
            finish_reason="tool_calls",
        ),
    ]

    # Snapshot the messages at call time: the loop mutates the same list.
    seen: list[list[dict]] = []

    def fake_chat(**kwargs):
        seen.append(list(kwargs["messages"]))
        return responses.pop(0)

    mock_chat.side_effect = fake_chat

    result = tool_use_loop(skill_dir, "abc123hash", "test-skill")
    assert isinstance(result, ExtractedSkill)
    assert result.id == "test-skill"

    # Every tool call must be preceded by the assistant turn and followed by
    # a tool-result message (OpenAI rejects orphan tool messages).
    second_call = seen[1]
    assert second_call[-2]["role"] == "assistant"
    assert second_call[-2]["tool_calls"][0]["id"] == "t1"
    assert second_call[-1] == tool_message(
        "t1", '{"files": ["SKILL.md"]}'
    )


def test_system_prompt_includes_state_extraction():
    """Test that SYSTEM_PROMPT includes state transition extraction instructions."""
    from compiler.transformer import SYSTEM_PROMPT
    assert "STATE TRANSITION EXTRACTION" in SYSTEM_PROMPT
    assert "requiresState" in SYSTEM_PROMPT
    assert "yieldsState" in SYSTEM_PROMPT
    assert "handlesFailure" in SYSTEM_PROMPT
    assert "oc:SystemAuthenticated" in SYSTEM_PROMPT
    assert "oc:PermissionDenied" in SYSTEM_PROMPT
    assert "URIs" in SYSTEM_PROMPT


@patch("compiler.transformer.chat")
def test_tool_use_loop_sets_generated_by(mock_chat, tmp_path):
    """Test that tool_use_loop sets generated_by field."""
    from compiler.config import LLM_MODEL

    skill_dir = tmp_path / "test-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# Test")

    extraction = {
        "id": "test-skill",
        "hash": "abc123",
        "nature": "Test",
        "genus": "Test",
        "differentia": "test",
        "intents": ["test"],
        "requirements": [],
        "constraints": [],
        "execution_payload": None,
        "provenance": None,
    }
    mock_chat.return_value = LLMResponse(
        text="",
        tool_calls=(ToolCall(id="t1", name="extract_skill", arguments=extraction),),
        finish_reason="tool_calls",
    )

    result = tool_use_loop(skill_dir, "abc123hash", "test-skill")
    assert result.generated_by == LLM_MODEL


def test_build_sub_skill_context_prompt():
    """Test that context prompt includes parent and sibling info."""
    context = build_sub_skill_context_prompt(
        filename="planning.md",
        parent_skill_id="obra/superpowers/brainstorming",
        sibling_names=["review.md", "setup.md"]
    )

    assert "planning.md" in context
    assert "obra/superpowers/brainstorming" in context
    assert "review" in context
    assert "setup" in context
    assert "dependsOn" in context or "depends_on" in context.lower()


def test_tool_use_loop_signature_accepts_parent_context():
    """Verify tool_use_loop accepts parent_context parameter."""
    import inspect
    from compiler.transformer import tool_use_loop

    sig = inspect.signature(tool_use_loop)
    params = list(sig.parameters.keys())

    assert "parent_context" in params or "parent_skill_id" in params

