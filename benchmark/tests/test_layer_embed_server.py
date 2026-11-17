"""The embeddings sidecar the competitors need: pin its shape, not its numbers.

Nothing here loads a model. What is tested is the contract a RAG framework
relies on — one vector per input, in input order, under the OpenAI keys — and
the refusals, because a silently coerced request produces a working index of the
wrong text.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

import pytest

from benchmark.layer.embed_server import (
    EmbeddingServer,
    embedding_response,
    normalise_input,
)


def test_a_single_string_is_one_embedding():
    assert normalise_input({"input": "hello"}) == ["hello"]


def test_a_list_keeps_its_order():
    assert normalise_input({"input": ["a", "b", "c"]}) == ["a", "b", "c"]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"input": []},
        {"input": ["  "]},
        {"input": [[1, 2, 3]]},
        {"input": 42},
    ],
)
def test_inputs_that_cannot_be_embedded_are_refused(payload):
    with pytest.raises(ValueError):
        normalise_input(payload)


def test_the_response_is_one_vector_per_input_in_order():
    body = embedding_response(["a", "b"], [[0.1, 0.2], [0.3, 0.4]])
    assert body["object"] == "list"
    assert [row["index"] for row in body["data"]] == [0, 1]
    assert body["data"][1]["embedding"] == [0.3, 0.4]
    assert body["data"][0]["object"] == "embedding"


def test_usage_is_omitted_rather_than_guessed():
    """A number the caller cannot trust is worse than no number."""
    assert "usage" not in embedding_response(["a"], [[0.1]])
    body = embedding_response(["two words"], [[0.1]], count_tokens=lambda text: len(text.split()))
    assert body["usage"] == {"prompt_tokens": 2, "total_tokens": 2}


def test_the_server_answers_a_real_request_and_refuses_a_bad_one():
    seen: list[list[str]] = []

    def encode(texts):
        seen.append(texts)
        return [[float(len(text)), 1.0] for text in texts]

    server = EmbeddingServer(("127.0.0.1", 0), encode)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        request = urllib.request.Request(
            base + "/v1/embeddings",
            data=json.dumps({"input": ["first", "second"]}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            body = json.load(response)
        assert len(body["data"]) == 2
        # The passage prefix is applied server-side, once, for every system.
        assert seen == [["passage: first", "passage: second"]]
        assert body["data"][0]["embedding"][0] > 0

        with urllib.request.urlopen(base + "/v1/models", timeout=10) as response:
            models = json.load(response)
        assert models["data"][0]["id"] == "e5-large-v2"

        bad = urllib.request.Request(
            base + "/v1/embeddings",
            data=json.dumps({"input": []}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(bad, timeout=10)
        assert exc.value.code == 400
    finally:
        server.shutdown()
        server.server_close()
