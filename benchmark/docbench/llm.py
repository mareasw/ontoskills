"""One OpenAI-compatible chat call, shared by the benchmark stages.

The gateway drops long runs with 503s, often several in a row. Six attempts
with a widening backoff is cheaper than losing a run that has already spent
twenty minutes of extraction. That policy lives here once so the compiler and
the verifier cannot drift apart.

Credentials are read by the caller from the environment; this module never
prints them.
"""

from __future__ import annotations

import time

RETRYABLE = {408, 409, 429, 500, 502, 503, 504}
ATTEMPTS = 6


def chat(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict],
    max_tokens: int,
    *,
    temperature: float = 0,
    timeout: int = 300,
    attempts: int = ATTEMPTS,
) -> tuple[str, dict, str]:
    """POST one chat completion. Returns (content, usage, finish_reason)."""
    import requests

    url = (base_url or "").rstrip("/")
    if not url:
        raise SystemExit("no base URL: set OPENAI_BASE_URL or pass --base-url")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": messages,
    }
    last = ""
    for attempt in range(attempts):
        try:
            resp = requests.post(f"{url}/chat/completions", headers=headers, json=payload, timeout=timeout)
        except requests.RequestException as exc:
            last = str(exc)
            time.sleep(min(30, 3 * (attempt + 1)))
            continue
        if resp.status_code in RETRYABLE:
            last = f"HTTP {resp.status_code}"
            time.sleep(min(30, 3 * (attempt + 1)))
            continue
        if resp.status_code >= 400:
            raise SystemExit(f"HTTP {resp.status_code}: {resp.text[:400]}")
        data = resp.json()
        choice = (data.get("choices") or [{}])[0]
        content = (choice.get("message") or {}).get("content") or ""
        usage = data.get("usage") or {}
        finish = str(choice.get("finish_reason") or "")
        return content, {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
        }, finish
    raise SystemExit(f"model call failed after retries: {last}")
