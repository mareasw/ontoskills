"""One OpenAI-compatible chat call, with the retry policy the gateway needs.

Two things about this gateway are measured, not assumed:

* a long reply arrives through the streaming endpoint in ~1.2x the time of a
  short one, while the non-streaming endpoint occasionally parks a request in a
  queue and answers ``503`` exactly 60 seconds later — the same prompt sent with
  ``stream: true`` is served normally. The ingest therefore streams every call
  and reassembles the content here.
* the gateway drops long runs with 503s. Six attempts with a widening backoff is
  cheaper than losing a run that has already spent twenty minutes extracting.

Credentials are read by the caller; this module never prints them.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

RETRYABLE = {408, 409, 429, 500, 502, 503, 504}
ATTEMPTS = 6

# The timeout is per socket read. The model streams, so a healthy call keeps
# sending data; only a dead connection waits this long.
TIMEOUT = 600


class ModelError(RuntimeError):
    pass


def _read_stream(response) -> tuple[str, dict, str]:
    """Collect one SSE chat completion into (content, usage, finish_reason)."""
    parts: list[str] = []
    usage: dict = {}
    finish = ""
    for raw in response:
        line = raw.decode("utf-8", errors="ignore").strip()
        if not line or line.startswith(":"):
            continue
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            break
        try:
            event = json.loads(data)
        except json.JSONDecodeError:
            continue
        if event.get("usage"):
            usage = event["usage"]
        for choice in event.get("choices") or []:
            piece = (choice.get("delta") or {}).get("content")
            if piece:
                parts.append(piece)
            if choice.get("finish_reason"):
                finish = str(choice["finish_reason"])
    return "".join(parts), {
        "input_tokens": usage.get("prompt_tokens", 0),
        "output_tokens": usage.get("completion_tokens", 0),
    }, finish


def chat(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict],
    max_tokens: int,
    *,
    temperature: float = 0,
    timeout: int = TIMEOUT,
    attempts: int = ATTEMPTS,
) -> tuple[str, dict, str]:
    """POST one chat completion. Returns ``(content, usage, finish_reason)``."""
    url = (base_url or "").rstrip("/")
    if not url:
        raise ModelError("no base URL: set OPENAI_BASE_URL or pass --base-url")
    if not model:
        raise ModelError("no model: set OPENAI_MODEL or pass --model")
    payload = {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
        "stream_options": {"include_usage": True},
        "messages": messages,
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    body = json.dumps(payload).encode("utf-8")
    last = ""
    for attempt in range(attempts):
        request = urllib.request.Request(
            f"{url}/chat/completions", data=body, headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                content, usage, finish = _read_stream(response)
        except urllib.error.HTTPError as exc:
            if exc.code in RETRYABLE:
                last = f"HTTP {exc.code}"
                time.sleep(min(30, 3 * (attempt + 1)))
                continue
            detail = exc.read().decode("utf-8", errors="ignore")[:400]
            raise ModelError(f"HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = str(exc)
            time.sleep(min(30, 3 * (attempt + 1)))
            continue
        if finish not in {"stop", "length"}:
            # A stream that dies early leaves half a JSON array behind, which
            # the parser would silently reject as malformed claims.
            last = f"stream ended with finish={finish!r}"
            time.sleep(min(30, 3 * (attempt + 1)))
            continue
        return content, usage, finish
    raise ModelError(f"model call failed after {attempts} attempts: {last}")
