"""OpenAI-compatible LLM access.

The compiler talks to any OpenAI Chat Completions endpoint, configured with
the standard names:

    OPENAI_BASE_URL / OPENAI_API_KEY / OPENAI_MODEL

Point `OPENAI_BASE_URL` at OpenAI, at the Cascade inference plane, or at any
other OpenAI-compatible gateway — the client does not need to know which.

Only the small surface the compiler needs is exposed: one `chat()` call that
returns text plus parsed tool calls, and an `LLMError` that callers translate
into their own domain errors.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any

from openai import OpenAI, OpenAIError

from compiler.env import load_local_env

load_local_env()

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-4o-mini"


class LLMError(Exception):
    """Raised when the upstream LLM call fails."""


@dataclass(frozen=True)
class ToolCall:
    """A tool invocation requested by the model."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class LLMResponse:
    """Normalized response: text, tool calls and finish reason."""

    text: str
    tool_calls: tuple[ToolCall, ...]
    finish_reason: str


_client: OpenAI | None = None


def api_key() -> str | None:
    """Return the configured API key, if any."""
    return os.getenv("OPENAI_API_KEY")


def base_url() -> str | None:
    """Return the configured base URL, if any (None means api.openai.com)."""
    return os.getenv("OPENAI_BASE_URL")


def default_model() -> str:
    """Return the configured default model."""
    return os.getenv("OPENAI_MODEL") or DEFAULT_MODEL


def reset_client() -> None:
    """Drop the cached client (tests change env between cases)."""
    global _client
    _client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        key = api_key()
        if not key:
            raise LLMError("nessuna API key: imposta OPENAI_API_KEY")
        _client = OpenAI(api_key=key, base_url=base_url())
    return _client


def _parse_arguments(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("tool arguments non-JSON, passati grezzi al chiamante")
        return {"_raw": raw}
    return parsed if isinstance(parsed, dict) else {"_raw": parsed}


def chat(
    *,
    messages: list[dict[str, Any]],
    model: str | None = None,
    max_tokens: int = 4096,
    tools: list[dict[str, Any]] | None = None,
    temperature: float | None = None,
    timeout: float | None = None,
) -> LLMResponse:
    """Run one Chat Completions call and normalize the response.

    Raises:
        LLMError: on any upstream/API failure.
    """
    kwargs: dict[str, Any] = {
        "model": model or default_model(),
        "messages": messages,
        "max_tokens": max_tokens,
    }
    if tools:
        kwargs["tools"] = tools
    if temperature is not None:
        kwargs["temperature"] = temperature
    if timeout is not None:
        kwargs["timeout"] = timeout

    try:
        response = _get_client().chat.completions.create(**kwargs)
    except OpenAIError as exc:
        raise LLMError(str(exc)) from exc

    if not response.choices:
        raise LLMError("risposta senza choices")

    choice = response.choices[0]
    message = choice.message
    calls = tuple(
        ToolCall(
            id=call.id,
            name=call.function.name,
            arguments=_parse_arguments(call.function.arguments),
        )
        for call in (message.tool_calls or [])
    )
    return LLMResponse(
        text=message.content or "",
        tool_calls=calls,
        finish_reason=choice.finish_reason or "stop",
    )


def tool_to_openai(tool: dict[str, Any]) -> dict[str, Any]:
    """Convert the compiler's canonical tool spec to OpenAI's shape."""
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool["description"],
            "parameters": tool["input_schema"],
        },
    }


def assistant_tool_message(
    text: str, tool_calls: tuple[ToolCall, ...]
) -> dict[str, Any]:
    """Build the assistant message that precedes tool results."""
    return {
        "role": "assistant",
        "content": text or None,
        "tool_calls": [
            {
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": json.dumps(call.arguments),
                },
            }
            for call in tool_calls
        ],
    }


def tool_message(tool_call_id: str, content: str) -> dict[str, Any]:
    """Build a tool-result message."""
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": content,
    }
