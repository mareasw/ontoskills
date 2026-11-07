from types import SimpleNamespace
from unittest.mock import patch

import pytest

from compiler import llm


def _response(*, text=None, tool_calls=None, finish_reason="stop"):
    message = SimpleNamespace(content=text, tool_calls=tool_calls or [])
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason=finish_reason)]
    )


def _tool_call(call_id, name, arguments):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=arguments),
    )


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in (
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_MODEL",
    ):
        monkeypatch.delenv(var, raising=False)
    llm.reset_client()
    yield
    llm.reset_client()


def test_reads_openai_standard_names(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://gateway.test/v1")
    monkeypatch.setenv("OPENAI_MODEL", "gateway-model")

    assert llm.api_key() == "openai-key"
    assert llm.base_url() == "https://gateway.test/v1"
    assert llm.default_model() == "gateway-model"


def test_defaults_without_base_url_or_model(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    assert llm.base_url() is None
    assert llm.default_model() == llm.DEFAULT_MODEL


def test_chat_without_key_raises():
    with pytest.raises(llm.LLMError):
        llm.chat(messages=[{"role": "user", "content": "hi"}])


def test_chat_normalizes_text():
    fake = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=lambda **kwargs: _response(text="OK"))
        )
    )
    with patch("compiler.llm._get_client", return_value=fake):
        result = llm.chat(messages=[{"role": "user", "content": "hi"}], model="m")

    assert result.text == "OK"
    assert result.tool_calls == ()
    assert result.finish_reason == "stop"


def test_chat_parses_tool_calls():
    calls = [
        _tool_call("t1", "read_file", '{"path": "SKILL.md"}'),
        _tool_call("t2", "list_files", ""),
    ]
    fake = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=lambda **kwargs: _response(
                    text="thinking", tool_calls=calls, finish_reason="tool_calls"
                )
            )
        )
    )
    with patch("compiler.llm._get_client", return_value=fake):
        result = llm.chat(messages=[{"role": "user", "content": "hi"}], model="m")

    assert result.finish_reason == "tool_calls"
    assert result.tool_calls[0] == llm.ToolCall(
        id="t1", name="read_file", arguments={"path": "SKILL.md"}
    )
    assert result.tool_calls[1].arguments == {}


def test_invalid_tool_arguments_are_kept_raw():
    calls = [_tool_call("t1", "read_file", "{not json")]
    fake = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=lambda **kwargs: _response(tool_calls=calls)
            )
        )
    )
    with patch("compiler.llm._get_client", return_value=fake):
        result = llm.chat(messages=[{"role": "user", "content": "hi"}], model="m")

    assert result.tool_calls[0].arguments == {"_raw": "{not json"}


def test_chat_wraps_upstream_errors():
    def boom(**kwargs):
        raise llm.OpenAIError("429 insufficient balance")

    fake = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=boom))
    )
    with patch("compiler.llm._get_client", return_value=fake):
        with pytest.raises(llm.LLMError, match="insufficient balance"):
            llm.chat(messages=[{"role": "user", "content": "hi"}], model="m")


def test_tool_to_openai_maps_schema():
    tool = {
        "name": "read_file",
        "description": "Read a file",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    }
    converted = llm.tool_to_openai(tool)

    assert converted["type"] == "function"
    assert converted["function"]["name"] == "read_file"
    assert converted["function"]["parameters"] == tool["input_schema"]
