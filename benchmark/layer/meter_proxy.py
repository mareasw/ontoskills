"""A metering proxy in front of the chat endpoint.

The pilot's cost column is read from `usage`, never estimated (LAYER.md §4), and
a framework that reports its own spend is being believed rather than measured.
This proxy sits between a system and the gateway, forwards every request
unchanged, and appends one JSON line per call carrying the tokens the gateway
charged. It is the same proxy for every system, so nobody is measured by a
different instrument — including OntoSkills.

The gateway is ours and reports `cost: 0`: what is recorded here is tokens, and
they are priced afterwards at the declared table (0,15 $/M in, 0,60 $/M out).
Nothing in this file decides what anything is worth.

    python3 -m benchmark.layer.meter_proxy --port 8092 \\
        --upstream http://127.0.0.1:8080 --label graphrag \\
        --log /tmp/opencode/layer/meter.jsonl

``--upstream`` is an origin, not a base URL: the incoming path is forwarded
verbatim, and a trailing ``/v1`` is stripped so that a client pointing at
``http://127.0.0.1:8092/v1`` cannot produce ``/v1/v1/chat/completions``.

Streaming is passed through, not refused: some frameworks only stream, and a
proxy that changes the shape of the response would be measuring a different
system. The usage of a streamed reply is read from the last chunk that carries
it, which is where OpenAI-compatible servers put the totals.

``--stream-upstream`` is the one place where the proxy does change the shape of a
request, and it changes nothing the system can see. Our gateway answers
`503 omniroute unavailable, retry later` to *every* completion still running at
60,1 s, and streaming the identical request returns 200 after 111 s with 9 000
output tokens — the keepalive frames the gateway itself sends are the proof that
streaming is the path it supports for long generations. A framework with no
streaming option for extraction would therefore be scored as failing on a
transport limit, not on its quality. With this flag the proxy asks upstream for a
stream, reassembles the chunks into the non-streamed body the client expects, and
meters the assembled usage; the client is answered in exactly the shape it asked
for. The rewrite is recorded on every line (`upstream_streamed`), so no reader has
to take it on trust.

Each line also records *when* the call happened and *what it asked for* — the
model name the client used, `max_tokens`, whether the reply was requested as
JSON, and the prompt's length in characters, never its text. The timestamp exists
because a build that is restarted after a failed attempt is still one bill, and
without a clock the two halves cannot be told apart; the request shape exists
because a call that asks for 32k output holds gateway capacity a 4k call does
not, and the 503s this proxy recorded are not explained by the tokens alone.
``--append`` is how a restarted run says its earlier attempts belong to it.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

TIMEOUT = 900


def usage_from_body(payload: dict) -> dict:
    """Tokens from a non-streamed completion body."""
    usage = payload.get("usage") or {}
    return {
        "prompt_tokens": int(usage.get("prompt_tokens") or 0),
        "completion_tokens": int(usage.get("completion_tokens") or 0),
    }


def usage_from_stream(text: str) -> dict:
    """Tokens from a server-sent-event body: the last usage block wins.

    OpenAI-compatible servers put the totals in the final chunk before
    ``[DONE]``, and a few repeat a running total in every chunk. Both are read
    correctly by keeping the last block. A stream that reports nothing is
    recorded as zero rather than guessed: the zero is the finding, and the run
    report says the system did not report its usage.
    """
    last: dict | None = None
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data or data == "[DONE]":
            continue
        try:
            chunk = json.loads(data)
        except json.JSONDecodeError:
            continue
        usage = chunk.get("usage") or {}
        if usage:
            last = usage
    if last is None:
        return {"prompt_tokens": 0, "completion_tokens": 0}
    return {
        "prompt_tokens": int(last.get("prompt_tokens") or 0),
        "completion_tokens": int(last.get("completion_tokens") or 0),
    }


def assemble_stream(text: str) -> dict | None:
    """A non-streamed completion body rebuilt from a server-sent-event stream.

    The gateway sends frames with an empty ``choices`` list while it waits
    (`id: chatcmpl-keepalive`), then the deltas, then one final frame carrying
    ``finish_reason`` and the totals. All three are handled: empty frames are
    skipped, ``reasoning_content`` and ``content`` are joined separately so a
    reasoning model's answer keeps the shape the client expects, and the last
    usage block wins. ``None`` means the stream carried no answer at all — the
    caller turns that into a failure rather than into an empty success.
    """
    content: list[str] = []
    reasoning: list[str] = []
    usage: dict | None = None
    finish: str | None = None
    head: dict = {}
    seen = False
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data or data == "[DONE]":
            continue
        try:
            chunk = json.loads(data)
        except json.JSONDecodeError:
            continue
        if not head.get("model") and chunk.get("model"):
            head = chunk
        if chunk.get("usage"):
            usage = chunk["usage"]
        for choice in chunk.get("choices") or []:
            delta = choice.get("delta") or {}
            piece = delta.get("content")
            if piece:
                content.append(piece)
                seen = True
            thought = delta.get("reasoning_content")
            if thought:
                reasoning.append(thought)
            if choice.get("finish_reason"):
                finish = choice["finish_reason"]
                seen = True
    if not seen:
        return None
    message: dict = {"role": "assistant", "content": "".join(content)}
    if reasoning:
        message["reasoning_content"] = "".join(reasoning)
    body = {
        "id": head.get("id") or "assembled",
        "object": "chat.completion",
        "created": head.get("created") or 0,
        "model": head.get("model") or "",
        "choices": [{"index": 0, "message": message, "finish_reason": finish or "stop"}],
    }
    if usage:
        body["usage"] = usage
    return body


def ask_for_a_stream(body: bytes) -> tuple[bytes, bool]:
    """The same request, with ``stream: true`` — or unchanged, if it already asks.

    Returns the bytes to send and whether the proxy rewrote anything. A body that
    is not JSON is forwarded untouched: a proxy that mangles what it cannot parse
    is worse than one that fails.
    """
    try:
        request = json.loads(body.decode("utf-8", errors="replace") or "{}")
    except json.JSONDecodeError:
        return body, False
    if not isinstance(request, dict) or request.get("stream"):
        return body, False
    request["stream"] = True
    return json.dumps(request, ensure_ascii=False).encode(), True


def request_shape(body: bytes) -> dict:
    """What the client asked for, without what it asked *about*.

    ``max_tokens`` is here because it turned out to matter: a framework that asks
    for 32k output holds gateway capacity a framework that asks for 4k does not,
    and a log that records only the answer cannot tell the two apart. The prompt
    is recorded as a length, never as text — a cost log is not a transcript.
    """
    try:
        request = json.loads(body.decode("utf-8", errors="replace") or "{}")
    except json.JSONDecodeError:
        return {}
    messages = request.get("messages") or []
    chars = 0
    for message in messages:
        content = message.get("content")
        if isinstance(content, str):
            chars += len(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict):
                    chars += len(str(part.get("text") or ""))
    return {
        "asked_model": str(request.get("model") or ""),
        "max_tokens": request.get("max_tokens"),
        "stream": bool(request.get("stream")),
        "json_mode": bool(request.get("response_format")),
        "prompt_chars": chars,
    }


def record_line(
    label: str,
    model: str,
    usage: dict,
    streamed: bool,
    status: int = 200,
    shape: dict | None = None,
) -> str:
    """One JSON line, in the shape the run report sums.

    ``status`` is recorded because a failed call is not free of consequences: the
    gateway answered 503 for a few extraction calls during the smoke run, and a
    log that counted only tokens would have shown a cheaper build than the one
    that happened, with no trace of why the system failed.
    """
    row = {
        "ts": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "label": label,
        "model": model,
        "status": status,
        "prompt_tokens": usage["prompt_tokens"],
        "completion_tokens": usage["completion_tokens"],
        "streamed": streamed,
    }
    row.update(shape or {})
    return json.dumps(row, ensure_ascii=False)


class MeterServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address,
        upstream: str,
        log_path: Path,
        label: str,
        api_key: str | None = None,
        append: bool = False,
        capture_failures: Path | None = None,
        stream_upstream: bool = False,
    ):
        super().__init__(address, _Handler)
        # The path is forwarded verbatim, so the upstream is an *origin*: a
        # client whose api_base is ``http://proxy:8092/v1`` sends
        # ``/v1/chat/completions``, and joining that to an origin that already
        # ends in ``/v1`` produced ``/v1/v1/chat/completions`` — a 404 that read
        # like a bad model name. The trailing version is stripped here so the
        # mistake cannot reach a run.
        self.upstream = upstream.rstrip("/")
        if self.upstream.endswith("/v1"):
            self.upstream = self.upstream[: -len("/v1")]
        self.log_path = Path(log_path)
        self.label = label
        self.api_key = api_key
        # A refused call is a question about the gateway, and the only way to
        # answer it is to keep the request that was refused. Off by default: a
        # cost log is not a transcript, and this one is.
        self.capture_failures = Path(capture_failures) if capture_failures else None
        # The gateway closes a non-streamed completion at 60 s; a stream of the
        # same request runs to completion. The client still gets a single body.
        self.stream_upstream = stream_upstream
        self.lock = Lock()
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        # Truncated on purpose: a meter log is one run's cost column, and
        # appending would quietly merge two systems' calls into one total. A
        # system that is restarted mid-build says so with ``append`` — its
        # aborted attempts were paid for and belong to the same column.
        if not append:
            self.log_path.write_text("", encoding="utf-8")


class _Handler(BaseHTTPRequestHandler):
    server: MeterServer

    def log_message(self, format: str, *args) -> None:  # noqa: A002 - stdlib signature
        return

    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        self._forward(body=None)

    def do_POST(self) -> None:  # noqa: N802 - stdlib naming
        length = int(self.headers.get("Content-Length") or 0)
        self._forward(body=self.rfile.read(length) if length else b"")

    def _headers(self) -> dict[str, str]:
        """The client's key if it sent one, ours otherwise, and nothing else."""
        headers = {"Content-Type": "application/json"}
        key = self.headers.get("Authorization") or (
            f"Bearer {self.server.api_key}" if self.server.api_key else ""
        )
        if key:
            headers["Authorization"] = key
        return headers

    def _to_stream(self, body: bytes, headers: dict[str, str]) -> tuple[bytes, bool]:
        """Rewrite a completion request to ask for a stream, when configured.

        Only completions are touched: an embeddings call has no long generation
        to protect, and rewriting it would be a change with no reason behind it.
        """
        if not self.server.stream_upstream:
            return body, False
        if not self.path.rstrip("/").endswith("/chat/completions"):
            return body, False
        rewritten_body, rewritten = ask_for_a_stream(body)
        if rewritten:
            headers["Accept"] = "text/event-stream"
        return rewritten_body, rewritten

    def _call_upstream(
        self, url: str, body: bytes | None, headers: dict[str, str]
    ) -> tuple[bytes, int, str] | None:
        """Forward once. ``None`` means the gateway could not be reached at all.

        A connection failure is not an HTTP answer and must not be dressed as
        one: the caller turns it into a 502 with the reason, so a broken proxy
        cannot be read as a model that answered badly.
        """
        request = urllib.request.Request(
            url,
            data=body,
            headers=headers,
            method="POST" if body is not None else "GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                return (
                    response.read(),
                    response.status,
                    response.headers.get("Content-Type", "application/json"),
                )
        except urllib.error.HTTPError as exc:
            return exc.read(), exc.code, exc.headers.get("Content-Type", "application/json")
        except Exception as exc:  # noqa: BLE001 - reported, not swallowed
            self._json({"error": {"message": f"upstream unreachable: {exc}"}}, 502)
            return None

    def _forward(self, body: bytes | None) -> None:
        url = self.server.upstream + self.path
        headers = self._headers()
        upstream_body, rewritten = (
            self._to_stream(body, headers) if body is not None else (body, False)
        )

        answered = self._call_upstream(url, upstream_body, headers)
        if answered is None:
            return
        raw, status, content_type = answered

        if rewritten and status < 400:
            raw, status = self._reassemble(raw, status)
            content_type = "application/json"

        if body is not None and self.path.rstrip("/").endswith("/chat/completions"):
            self._meter(
                body,
                raw.decode("utf-8", errors="replace"),
                content_type,
                status,
                upstream_streamed=rewritten,
            )
            if status >= 400:
                self._capture(body, status)

        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        try:
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            # The client gave up while the answer was in flight — a killed run,
            # or a framework that timed out its own read. The call was still made
            # and the meter line above still counts it, which is the point: a
            # request that nobody received is not a request that cost nothing.
            return

    def _reassemble(self, raw: bytes, status: int) -> tuple[bytes, int]:
        """A streamed answer, turned back into the body the client asked for.

        A stream that ends without an answer becomes a 502 rather than an empty
        200: the client must not pay attention to a reply that does not exist,
        and the meter must not record a zero-token success.
        """
        assembled = assemble_stream(raw.decode("utf-8", errors="replace"))
        if assembled is None:
            return (
                json.dumps(
                    {"error": {"message": "the gateway's stream ended without an answer"}}
                ).encode(),
                502,
            )
        return json.dumps(assembled, ensure_ascii=False).encode(), status

    def _meter(
        self,
        body: bytes,
        text: str,
        content_type: str,
        status: int = 200,
        upstream_streamed: bool = False,
    ) -> None:
        try:
            request = json.loads(body.decode("utf-8", errors="replace") or "{}")
        except json.JSONDecodeError:
            request = {}
        streamed = "text/event-stream" in content_type or bool(request.get("stream"))
        usage = usage_from_stream(text) if streamed else _json_usage(text)
        shape = request_shape(body)
        shape["upstream_streamed"] = upstream_streamed
        line = record_line(
            self.server.label,
            str(request.get("model") or ""),
            usage,
            streamed,
            status,
            shape,
        )
        with self.server.lock:
            with self.server.log_path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")

    def _capture(self, body: bytes, status: int) -> None:
        path = self.server.capture_failures
        if path is None:
            return
        row = {
            "ts": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "status": status,
            "body": body.decode("utf-8", errors="replace"),
        }
        with self.server.lock:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _json(self, body: dict, status: int) -> None:
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def _json_usage(text: str) -> dict:
    try:
        return usage_from_body(json.loads(text))
    except json.JSONDecodeError:
        return {"prompt_tokens": 0, "completion_tokens": 0}


# The declared price table. The gateway reports `cost: 0`, so a dollar figure is
# a price at this table, never an invoice.
PRICE_INPUT_PER_MILLION = 0.15
PRICE_OUTPUT_PER_MILLION = 0.60


def summarise(path: Path) -> dict:
    """Sum a meter log the way the run report reads it.

    ``failed_calls`` is reported next to the totals because a framework that
    retried six times after a 503 spent the same tokens as one that did not, but
    its run says something different about the gateway.
    """
    rows = [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    prompt = sum(row["prompt_tokens"] for row in rows)
    completion = sum(row["completion_tokens"] for row in rows)
    failed = [row for row in rows if int(row.get("status", 200)) >= 400]
    return {
        "calls": len(rows),
        "failed_calls": len(failed),
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "streamed": sum(1 for row in rows if row["streamed"]),
        "usd": round(
            prompt / 1_000_000 * PRICE_INPUT_PER_MILLION
            + completion / 1_000_000 * PRICE_OUTPUT_PER_MILLION,
            6,
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8092)
    parser.add_argument("--upstream", required=True)
    parser.add_argument(
        "--append",
        action="store_true",
        help="Keep the existing log: a build that was restarted after a failed "
        "attempt was still paid for in full",
    )
    parser.add_argument("--label", required=True, help="Which system's calls these are")
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--api-key", default=None)
    parser.add_argument(
        "--stream-upstream",
        action="store_true",
        help="Ask upstream for a stream and reassemble it: the gateway closes a "
        "non-streamed completion at 60 s and runs the same request streamed to "
        "the end. The client sees the single body it asked for",
    )
    parser.add_argument(
        "--capture-failures",
        type=Path,
        default=None,
        help="Write the request body of every refused call here: the only way "
        "to compare what the gateway refused with what it accepted",
    )
    args = parser.parse_args(argv)

    server = MeterServer(
        (args.host, args.port),
        args.upstream,
        args.log,
        args.label,
        args.api_key,
        append=args.append,
        capture_failures=args.capture_failures,
        stream_upstream=args.stream_upstream,
    )
    print(
        f"metering {args.label} at {args.host}:{args.port} -> {args.upstream} "
        f"(log {args.log})",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
