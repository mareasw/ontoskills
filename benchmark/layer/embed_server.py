"""An OpenAI-compatible embeddings endpoint, so the competitors can be built.

GraphRAG and LightRAG both refuse to index a corpus without an embedding model,
and the gateway this pilot uses exposes chat models only. Dropping two systems
from the comparison over a missing sidecar would be a worse result than serving
one: the pilot therefore runs the same pinned local model the retrieval benchmark
already uses — ``intfloat/e5-large-v2`` at revision ``f169b11e``, 1024
dimensions, CPU — behind the standard ``POST /v1/embeddings`` shape.

Two decisions are made explicit here because they are part of the measurement:

* **The prefix.** E5 is trained with ``query: `` and ``passage: `` prefixes and
  loses accuracy without them, but neither competitor distinguishes the two
  kinds of call. Every input therefore gets ``passage: ``, identically for both
  systems, so the choice cannot favour either one. It is recorded, not hidden.
* **The ceiling.** Inputs longer than the model's 512 tokens are truncated by
  the tokenizer, which is the same head-512 treatment the dense retrieval
  benchmark applies. A competitor that sends a 4,000-token chunk is therefore
  embedded on its first 512 tokens; that is a property of the model, not of the
  comparison, and it applies to every system equally.

Nothing here runs at query time for OntoSkills: our knowledge base is built
without vectors, and this server exists only to give the other two systems the
sidecar they require.

    python3 -m benchmark.layer.embed_server --port 8091
"""

from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from typing import Callable, Iterable, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.retrieval.dense import E5_LARGE_V2  # noqa: E402

EMBEDDING_MODEL = "e5-large-v2"
PREFIX = E5_LARGE_V2.passage_prefix


def normalise_input(payload: dict) -> list[str]:
    """The texts to embed, refusing the shapes that would silently mislead.

    ``input`` is a string or a list of strings in the OpenAI schema. Anything
    else — a nested token array, an empty list — is refused with a reason rather
    than coerced: a system that gets embeddings for the wrong text still gets a
    working index, and the difference would never surface again.
    """
    if "input" not in payload:
        raise ValueError("missing 'input'")
    value = payload["input"]
    if isinstance(value, str):
        texts = [value]
    elif isinstance(value, list) and all(isinstance(item, str) for item in value):
        texts = list(value)
    elif isinstance(value, list):
        raise ValueError("'input' must be a string or a list of strings, not token ids")
    else:
        raise ValueError("'input' must be a string or a list of strings")
    if not texts or any(not text.strip() for text in texts):
        raise ValueError("'input' contains no text to embed")
    return texts


def embedding_response(
    inputs: Sequence[str],
    vectors: Iterable[Sequence[float]],
    model: str = EMBEDDING_MODEL,
    count_tokens: Callable[[str], int] | None = None,
) -> dict:
    """The response body, in the shape the OpenAI clients expect."""
    data = [
        {"object": "embedding", "index": index, "embedding": [float(value) for value in vector]}
        for index, vector in enumerate(vectors)
    ]
    body: dict = {"object": "list", "data": data, "model": model}
    if count_tokens is not None:
        total = sum(int(count_tokens(text)) for text in inputs)
        body["usage"] = {"prompt_tokens": total, "total_tokens": total}
    return body


class EmbeddingServer(ThreadingHTTPServer):
    """A threaded server that owns the encoder and the lock around it.

    ``sentence_transformers`` is not documented as thread-safe, and GraphRAG
    calls the endpoint from several workers at once, so the lock is not
    defensive politeness: without it two concurrent encodes can interleave in
    the tokenizer and produce a vector for the wrong text.
    """

    daemon_threads = True

    def __init__(self, address, encode: Callable[[list[str]], Iterable[Sequence[float]]]):
        super().__init__(address, _Handler)
        self.encode = encode
        self.lock = Lock()


class _Handler(BaseHTTPRequestHandler):
    server: EmbeddingServer

    def log_message(self, format: str, *args) -> None:  # noqa: A002 - stdlib signature
        # One line per call would bury the run's own output; the server is a
        # sidecar and its traffic is counted by the system that makes it.
        return

    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        if self.path.rstrip("/").endswith("/models"):
            self._json(
                {
                    "object": "list",
                    "data": [
                        {"id": EMBEDDING_MODEL, "object": "model", "owned_by": "local"}
                    ],
                }
            )
            return
        self._error(404, f"no route {self.path}")

    def do_POST(self) -> None:  # noqa: N802 - stdlib naming
        if not self.path.rstrip("/").endswith("/embeddings"):
            self._error(404, f"no route {self.path}")
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(length) or b"{}")
            inputs = normalise_input(payload)
        except (ValueError, json.JSONDecodeError) as exc:
            self._error(400, str(exc))
            return
        try:
            with self.server.lock:
                vectors = list(self.server.encode([PREFIX + text for text in inputs]))
        except Exception as exc:  # noqa: BLE001 - reported to the caller, not swallowed
            self._error(500, f"encoding failed: {exc}")
            return
        self._json(embedding_response(inputs, vectors, count_tokens=_word_count))

    def _json(self, body: dict, status: int = 200) -> None:
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _error(self, status: int, message: str) -> None:
        self._json({"error": {"message": message, "type": "invalid_request_error"}}, status)


def _word_count(text: str) -> int:
    """A usage number that is honest about being an approximation.

    The real token count needs the model's tokenizer; nothing in the comparison
    bills on it, and reporting characters as tokens would be a worse lie.
    """
    return max(1, len(text.split()))


def load_encoder(device: str) -> Callable[[list[str]], list[list[float]]]:
    """The pinned model, loaded once. Kept apart so tests need no torch."""
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(
        E5_LARGE_V2.model_id, revision=E5_LARGE_V2.revision, device=device
    )
    model.max_seq_length = E5_LARGE_V2.max_length

    def encode(texts: list[str]) -> list[list[float]]:
        matrix = model.encode(
            texts, batch_size=8, normalize_embeddings=True, show_progress_bar=False
        )
        return [row.tolist() for row in matrix]

    return encode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8091)
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args(argv)

    server = EmbeddingServer((args.host, args.port), load_encoder(args.device))
    print(
        f"{EMBEDDING_MODEL} ({E5_LARGE_V2.describe()}) on {args.host}:{args.port}",
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
