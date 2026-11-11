"""Tests for the one model call: retries, usage parsing and timeouts.

No network: ``urlopen`` is replaced. What matters here is the policy the long
ingest depends on — a 503 is retried, a 400 is not, and a reply that arrives is
parsed into the three values the compiler needs.
"""

from __future__ import annotations

import io
import json
import urllib.error

import pytest

from compiler.documents import llm


class _Reply:
    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _payload(content: str = "[]", finish: str = "stop", usage: dict | None = None) -> dict:
    return {
        "choices": [{"message": {"content": content}, "finish_reason": finish}],
        "usage": usage or {"prompt_tokens": 10, "completion_tokens": 5},
    }


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://example.test", code, "error", {}, io.BytesIO(b""))


def test_reply_is_split_into_content_usage_and_finish(monkeypatch):
    monkeypatch.setattr(llm.urllib.request, "urlopen", lambda *a, **k: _Reply(_payload("[{}]")))
    content, usage, finish = llm.chat("https://example.test", "key", "model", [], 100)
    assert content == "[{}]"
    assert usage == {"input_tokens": 10, "output_tokens": 5}
    assert finish == "stop"


def test_a_retryable_error_is_retried_with_backoff(monkeypatch):
    replies = [_http_error(503), _http_error(503), _Reply(_payload())]
    sleeps: list[float] = []

    def fake_urlopen(*args, **kwargs):
        result = replies.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(llm.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(llm.time, "sleep", sleeps.append)
    content, _, _ = llm.chat("https://example.test", "key", "model", [], 100)
    assert content == "[]"
    assert sleeps == [3, 6]


def test_a_client_error_is_not_retried(monkeypatch):
    calls = []

    def fake_urlopen(*args, **kwargs):
        calls.append(1)
        raise _http_error(400)

    monkeypatch.setattr(llm.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(llm.ModelError, match="HTTP 400"):
        llm.chat("https://example.test", "key", "model", [], 100)
    assert len(calls) == 1


def test_exhausted_attempts_raise_a_model_error(monkeypatch):
    monkeypatch.setattr(
        llm.urllib.request,
        "urlopen",
        lambda *a, **k: (_ for _ in ()).throw(_http_error(503)),
    )
    monkeypatch.setattr(llm.time, "sleep", lambda _: None)
    with pytest.raises(llm.ModelError, match="after 6 attempts"):
        llm.chat("https://example.test", "key", "model", [], 100)


def test_missing_endpoint_or_model_fails_before_the_call():
    with pytest.raises(llm.ModelError, match="no base URL"):
        llm.chat("", "key", "model", [], 100)
    with pytest.raises(llm.ModelError, match="no model"):
        llm.chat("https://example.test", "key", "", [], 100)
