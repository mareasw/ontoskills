"""One OpenAI-compatible chat call, with the retry policy the gateway needs.

The gateway drops long runs with 503s. Six attempts with a widening backoff is
cheaper than losing a run that has already spent twenty minutes extracting.
Credentials are read by the caller; this module never prints them.

The timeout is per attempt and it is generous on purpose: the model returns the
whole reply at once (no streaming), so a legal chunk that emits 6,000 tokens
holds the connection for ~3 minutes. A 300-second ceiling turned those into
retries that could never succeed; 600 seconds is a measured 1.7x margin over a
real chunk (6,132 tokens in 175 s).
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

RETRYABLE = {408, 409, 429, 500, 502, 503, 504}
ATTEMPTS = 6


class ModelError(RuntimeError):
    pass


def chat(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict],
    max_tokens: int,
    *,
    temperature: float = 0,
    timeout: int = 600,
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
                data = json.loads(response.read().decode("utf-8"))
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
        choice = (data.get("choices") or [{}])[0]
        content = (choice.get("message") or {}).get("content") or ""
        usage = data.get("usage") or {}
        finish = str(choice.get("finish_reason") or "")
        return content, {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
        }, finish
    raise ModelError(f"model call failed after {attempts} attempts: {last}")
