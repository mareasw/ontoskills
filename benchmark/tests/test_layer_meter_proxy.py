"""The meter is the instrument the cost column comes from: pin it.

A proxy that miscounts silently would move every comparison number without
failing anything, so the two shapes it has to read — a plain completion body and
a server-sent-event stream — are tested against real payloads, and so is the
forwarding round trip.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from benchmark.layer import meter_proxy


def test_usage_comes_from_the_usage_block():
    body = {"usage": {"prompt_tokens": 1200, "completion_tokens": 340}}
    assert meter_proxy.usage_from_body(body) == {
        "prompt_tokens": 1200,
        "completion_tokens": 340,
        "cached_tokens": 0,
        "reasoning_tokens": 0,
    }


def test_a_body_without_usage_is_zero_and_not_an_estimate():
    assert meter_proxy.usage_from_body({"choices": []}) == {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "cached_tokens": 0,
        "reasoning_tokens": 0,
    }


def test_a_stream_carries_its_usage_in_the_last_chunk():
    stream = "\n".join(
        [
            'data: {"choices":[{"delta":{"content":"Hel"}}]}',
            "",
            'data: {"choices":[{"delta":{"content":"lo"}}]}',
            "",
            'data: {"choices":[],"usage":{"prompt_tokens":900,"completion_tokens":40}}',
            "",
            "data: [DONE]",
            "",
        ]
    )
    assert meter_proxy.usage_from_stream(stream) == {
        "prompt_tokens": 900,
        "completion_tokens": 40,
        "cached_tokens": 0,
        "reasoning_tokens": 0,
    }


def test_a_stream_that_repeats_a_running_total_is_taken_once():
    """Some providers repeat the cumulative count in every chunk."""
    stream = "\n".join(
        [
            'data: {"usage":{"prompt_tokens":10,"completion_tokens":5}}',
            'data: {"usage":{"prompt_tokens":10,"completion_tokens":9}}',
            "data: [DONE]",
        ]
    )
    # The deltas sum to more than the total, which is why the last total wins
    # when every chunk repeats one number.
    usage = meter_proxy.usage_from_stream(stream)
    assert usage == {
        "prompt_tokens": 10,
        "completion_tokens": 9,
        "cached_tokens": 0,
        "reasoning_tokens": 0,
    }


def test_the_recorded_line_names_the_system_and_the_model():
    line = meter_proxy.record_line(
        "graphrag", "deepseek-v4.1-flash", {"prompt_tokens": 3, "completion_tokens": 4}, False
    )
    row = json.loads(line)
    assert len(row.pop("ts")) == 19  # a timestamp, so restarts can be told apart
    assert row == {
        "label": "graphrag",
        "model": "deepseek-v4.1-flash",
        "status": 200,
        "prompt_tokens": 3,
        "completion_tokens": 4,
        "cached_tokens": 0,
        "reasoning_tokens": 0,
        "streamed": False,
    }


def test_the_request_shape_is_recorded_without_the_prompt_text():
    """`max_tokens` is capacity asked for, and it belongs in the cost column."""
    shape = meter_proxy.request_shape(
        json.dumps(
            {
                "model": "deepseek-v4.1-flash",
                "max_tokens": 32000,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "user", "content": "a" * 120}],
            }
        ).encode()
    )
    assert shape == {
        "asked_model": "deepseek-v4.1-flash",
        "max_tokens": 32000,
        "stream": False,
        "json_mode": True,
        "prompt_chars": 120,
    }


class _Upstream(BaseHTTPRequestHandler):
    def log_message(self, *args):
        return

    def do_POST(self):  # noqa: N802 - stdlib naming
        length = int(self.headers.get("Content-Length") or 0)
        request = json.loads(self.rfile.read(length))
        body = json.dumps(
            {
                "id": "x",
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 7},
                "echo_model": request.get("model"),
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def test_a_forwarded_call_is_passed_through_and_metered(tmp_path):
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), _Upstream)
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    log = tmp_path / "meter.jsonl"
    proxy = meter_proxy.MeterServer(
        ("127.0.0.1", 0),
        f"http://127.0.0.1:{upstream.server_address[1]}",
        log,
        "ontoskills",
    )
    threading.Thread(target=proxy.serve_forever, daemon=True).start()
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{proxy.server_address[1]}/v1/chat/completions",
            data=json.dumps({"model": "deepseek-v4.1-flash", "messages": []}).encode(),
            headers={"Content-Type": "application/json", "Authorization": "Bearer test"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            answer = json.load(response)
        # The reply is what the system asked for, unchanged.
        assert answer["echo_model"] == "deepseek-v4.1-flash"
        rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        assert len(rows) == 1
        row = rows[0]
        assert len(row.pop("ts")) == 19
        row.pop("asked_model")
        assert row == {
            "label": "ontoskills",
            "model": "deepseek-v4.1-flash",
            "status": 200,
            "prompt_tokens": 11,
            "completion_tokens": 7,
            "cached_tokens": 0,
            "reasoning_tokens": 0,
            "streamed": False,
            "max_tokens": None,
            "stream": False,
            "json_mode": False,
            "prompt_chars": 0,
            "upstream_streamed": False,
        }
    finally:
        proxy.shutdown()
        proxy.server_close()
        upstream.shutdown()
        upstream.server_close()


def test_a_trailing_version_in_the_upstream_cannot_double_the_path(tmp_path):
    """`--upstream .../v1` plus a client at `/v1/...` produced a 404 read as auth."""
    proxy = meter_proxy.MeterServer(
        ("127.0.0.1", 0), "http://127.0.0.1:9/v1/", tmp_path / "m.jsonl", "x"
    )
    try:
        assert proxy.upstream == "http://127.0.0.1:9"
    finally:
        proxy.server_close()


def test_a_failed_call_is_counted_and_priced_at_the_declared_table(tmp_path):
    """A 503 carries no usage, but it still has to appear in the run's log."""
    log = tmp_path / "meter.jsonl"
    log.write_text(
        "\n".join(
            [
                meter_proxy.record_line(
                    "graphrag",
                    "deepseek-v4.1-flash",
                    {"prompt_tokens": 1_000_000, "completion_tokens": 500_000},
                    False,
                ),
                meter_proxy.record_line(
                    "graphrag",
                    "deepseek-v4.1-flash",
                    {"prompt_tokens": 0, "completion_tokens": 0},
                    False,
                    status=503,
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    summary = meter_proxy.summarise(log)
    assert summary["calls"] == 2
    assert summary["failed_calls"] == 1
    assert summary["prompt_tokens"] == 1_000_000
    # 1M in at 0,15 $/M plus 0,5M out at 0,60 $/M.
    assert summary["usd"] == 0.45


def test_an_appended_log_keeps_the_attempt_that_was_paid_for(tmp_path):
    """A restarted build is one bill, not two: `--append` is how it says so."""
    log = tmp_path / "m.jsonl"
    log.write_text('{"label": "x", "status": 503}\n', encoding="utf-8")
    server = meter_proxy.MeterServer(
        ("127.0.0.1", 0), "http://127.0.0.1:9", log, "x", append=True
    )
    server.server_close()
    assert log.read_text(encoding="utf-8") == '{"label": "x", "status": 503}\n'


def test_without_append_the_log_is_this_run_alone(tmp_path):
    log = tmp_path / "m.jsonl"
    log.write_text('{"label": "y", "status": 503}\n', encoding="utf-8")
    server = meter_proxy.MeterServer(("127.0.0.1", 0), "http://127.0.0.1:9", log, "x")
    server.server_close()
    assert log.read_text(encoding="utf-8") == ""


class _Refusing(BaseHTTPRequestHandler):
    def log_message(self, *args):
        return

    def do_POST(self):  # noqa: N802 - stdlib naming
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        body = json.dumps({"error": {"message": "omniroute unavailable"}}).encode()
        self.send_response(503)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def test_a_refused_request_is_kept_so_it_can_be_compared(tmp_path):
    """The 503 could not be explained from tokens alone; the request had to be kept."""
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), _Refusing)
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    captured = tmp_path / "failures.jsonl"
    proxy = meter_proxy.MeterServer(
        ("127.0.0.1", 0),
        f"http://127.0.0.1:{upstream.server_address[1]}",
        tmp_path / "meter.jsonl",
        "probe",
        capture_failures=captured,
    )
    threading.Thread(target=proxy.serve_forever, daemon=True).start()
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{proxy.server_address[1]}/v1/chat/completions",
            data=json.dumps(
                {"model": "deepseek-v4.1-flash", "messages": [{"role": "user", "content": "hi"}]}
            ).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(request, timeout=10)
        rows = [json.loads(line) for line in captured.read_text(encoding="utf-8").splitlines()]
        assert len(rows) == 1
        assert rows[0]["status"] == 503
        assert json.loads(rows[0]["body"])["messages"][0]["content"] == "hi"
        # The cost log still records the call, with its status and no tokens.
        meter = [json.loads(line) for line in (tmp_path / "meter.jsonl").read_text().splitlines()]
        assert meter[0]["status"] == 503
        assert meter[0]["completion_tokens"] == 0
    finally:
        proxy.shutdown()
        proxy.server_close()
        upstream.shutdown()
        upstream.server_close()


STREAM = "\n".join(
    [
        'data: {"id": "chatcmpl-keepalive", "object": "chat.completion.chunk", "choices": []}',
        "",
        'data: {"id": "gw-1", "object": "chat.completion.chunk", "model": "deepseek-v4.1-flash", '
        '"choices": [{"index": 0, "delta": {"role": "assistant", "reasoning_content": "think"}, '
        '"finish_reason": null}]}',
        "",
        'data: {"id": "gw-1", "object": "chat.completion.chunk", '
        '"choices": [{"index": 0, "delta": {"content": "{\\"entities\\": "}, "finish_reason": null}]}',
        "",
        'data: {"id": "gw-1", "object": "chat.completion.chunk", '
        '"choices": [{"index": 0, "delta": {"content": "[]}"}, "finish_reason": "stop"}], '
        '"usage": {"prompt_tokens": 41, "completion_tokens": 28}}',
        "",
        "data: [DONE]",
    ]
)


def test_a_stream_is_rebuilt_into_the_body_the_client_asked_for():
    body = meter_proxy.assemble_stream(STREAM)
    assert body["choices"][0]["message"]["content"] == '{"entities": []}'
    assert body["choices"][0]["message"]["reasoning_content"] == "think"
    assert body["choices"][0]["finish_reason"] == "stop"
    assert body["usage"]["prompt_tokens"] == 41
    assert body["usage"]["completion_tokens"] == 28
    assert body["model"] == "deepseek-v4.1-flash"


def test_a_stream_without_an_answer_is_not_an_empty_success():
    keepalive_only = 'data: {"id": "chatcmpl-keepalive", "choices": []}\n\ndata: [DONE]\n'
    assert meter_proxy.assemble_stream(keepalive_only) is None


def test_a_request_is_asked_for_as_a_stream_once():
    once, rewritten = meter_proxy.ask_for_a_stream(
        json.dumps({"model": "m", "messages": []}).encode()
    )
    assert rewritten is True
    assert json.loads(once)["stream"] is True
    twice, rewritten_again = meter_proxy.ask_for_a_stream(once)
    assert rewritten_again is False
    assert twice == once


class _Streaming(BaseHTTPRequestHandler):
    def log_message(self, *args):
        return

    def do_POST(self):  # noqa: N802 - stdlib naming
        length = int(self.headers.get("Content-Length") or 0)
        request = json.loads(self.rfile.read(length))
        assert request["stream"] is True  # the proxy asked for a stream
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        self.wfile.write(STREAM.encode())


def test_the_proxy_streams_upstream_and_answers_with_one_body(tmp_path):
    """The 60 s ceiling is the gateway's, and this is how the pilot steps around it."""
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), _Streaming)
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    log = tmp_path / "meter.jsonl"
    proxy = meter_proxy.MeterServer(
        ("127.0.0.1", 0),
        f"http://127.0.0.1:{upstream.server_address[1]}",
        log,
        "graphrag",
        stream_upstream=True,
    )
    threading.Thread(target=proxy.serve_forever, daemon=True).start()
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{proxy.server_address[1]}/v1/chat/completions",
            data=json.dumps(
                {"model": "deepseek-v4.1-flash", "messages": [{"role": "user", "content": "hi"}]}
            ).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            answer = json.load(response)
        assert answer["choices"][0]["message"]["content"] == '{"entities": []}'
        rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        assert rows[0]["status"] == 200
        assert rows[0]["upstream_streamed"] is True
        assert rows[0]["completion_tokens"] == 28
    finally:
        proxy.shutdown()
        proxy.server_close()
        upstream.shutdown()
        upstream.server_close()


def test_reasoning_tokens_are_a_subset_of_the_completion_and_never_added():
    """The gateway reports this model's thinking twice: in the completion total
    and inside it. Recording both is a diagnostic; summing them would bill it
    twice, so the cost formula keeps reading `completion_tokens` alone."""
    body = {
        "usage": {
            "prompt_tokens": 79,
            "completion_tokens": 9000,
            "cached_tokens": 0,
            "reasoning_tokens": 6180,
            "prompt_tokens_details": {"cached_tokens": 0},
        }
    }
    usage = meter_proxy.usage_from_body(body)
    assert usage["reasoning_tokens"] == 6180
    assert usage["completion_tokens"] == 9000


def test_the_nested_openai_details_are_read_too():
    body = {
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "prompt_tokens_details": {"cached_tokens": 64},
            "completion_tokens_details": {"reasoning_tokens": 30},
        }
    }
    usage = meter_proxy.usage_from_body(body)
    assert usage["cached_tokens"] == 64
    assert usage["reasoning_tokens"] == 30
