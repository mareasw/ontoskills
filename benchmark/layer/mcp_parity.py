"""Gate G1: the MCP and the Python core answer the same questions the same way.

The port in `mcp/src/documents/` is a second implementation of the ranking, and
a second implementation is only allowed if something proves it is not a
different system. This is that something: it asks the pilot's questions through
both, compares the claim ids position by position, and fails on the first
difference that is not a tie.

A tie is the one place two BM25 implementations may legitimately disagree: the
scores are IEEE-754 doubles accumulated in query order and rounded to four
decimals, and a difference in the last bit reorders claims the reader cannot
tell apart. Ties are therefore compared as sets *inside a group of equal rounded
score*, and nothing else is. A missing claim, an extra claim, or a different
order outside a tie group is a defect, not a tolerance.

The harness also checks, on the same answers:

* **G2** — every quote occurs in its document at the reported offsets. It uses
  the rule `compiler.documents.verify` uses: the offsets index the normalised
  text, so `norm(text)[start:end] == norm(quote)`.
* **G5** — the p50/p95 latency of `documents_ask` over the MCP, which is the
  number LAYER.md publishes.
* **G6** — no file of the knowledge base is modified by the run.

Usage::

    python3 -m benchmark.layer.mcp_parity \\
        --kb /tmp/opencode/layer/kb \\
        --selection /tmp/opencode/layer/corpus/selection.json

Exit code 0 means every question matched; 1 means at least one did not, and the
first ten mismatches are printed with their question id.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import queue
import statistics
import subprocess
import tempfile
import sys
import threading
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from compiler.documents.ask import Corpus, ask
from compiler.documents.store import KnowledgeBase
from compiler.documents.text import norm

REPO = Path(__file__).resolve().parents[2]
DEFAULT_BINARY = REPO / "mcp/target/debug/ontomcp"
DEFAULT_LIMIT = 10
STARTUP_TIMEOUT = 30.0
CALL_TIMEOUT = 120.0


class McpClient:
    """A minimal MCP client over stdio, line-delimited JSON.

    The server speaks both framings; line-delimited is the one a person can
    debug with `tail -f`, and it is enough for a harness that owns both ends.
    """

    def __init__(self, binary: Path) -> None:
        self.process = subprocess.Popen(
            [str(binary)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            # The knowledge base is passed with every call, never through
            # `ONTOSKILLS_KB_ROOT`: if the environment could stand in for the
            # argument, a broken `kb` argument would still pass this harness.
            # Nothing else is needed — no proxy, no model, no network.
            env={"PATH": "/usr/bin:/bin", "HOME": str(Path.home())},
        )
        self._next_id = 0
        self._lines: queue.Queue[dict] = queue.Queue()
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()
        self._request(
            "initialize",
            {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "mcp-parity", "version": "1"},
            },
            timeout=STARTUP_TIMEOUT,
        )
        self._notify("notifications/initialized", {})

    def call(self, name: str, arguments: dict[str, Any], timeout: float = CALL_TIMEOUT) -> dict:
        response = self._request(
            "tools/call", {"name": name, "arguments": arguments}, timeout=timeout
        )
        if "error" in response:
            raise RuntimeError(f"{name}: {response['error']}")
        return response["result"]

    def close(self) -> None:
        if self.process.stdin:
            self.process.stdin.close()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()

    def _read(self) -> None:
        """Collect parsed messages until stdout closes.

        A thread rather than `select` on the pipe: a text-mode pipe can hold a
        complete line in Python's buffer while its file descriptor is empty, and
        `select` would then block forever on a message the process already sent.
        """
        assert self.process.stdout is not None
        for line in self.process.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                self._lines.put(json.loads(line))
            except json.JSONDecodeError:
                continue
        self._lines.put({"__closed__": True})

    def _notify(self, method: str, params: dict) -> None:
        assert self.process.stdin is not None
        self.process.stdin.write(
            json.dumps({"jsonrpc": "2.0", "method": method, "params": params}) + "\n"
        )
        self.process.stdin.flush()

    def _request(self, method: str, params: dict, timeout: float) -> dict:
        self._next_id += 1
        request_id = self._next_id
        assert self.process.stdin is not None
        self.process.stdin.write(
            json.dumps(
                {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
            )
            + "\n"
        )
        self.process.stdin.flush()

        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"{method}: no response within {timeout:.0f} s")
            try:
                message = self._lines.get(timeout=remaining)
            except queue.Empty:
                continue
            if message.get("__closed__"):
                raise RuntimeError(f"{method}: the server closed stdout")
            if message.get("id") == request_id:
                return message


def compare_rankings(expected: list[dict], got: list[dict]) -> str | None:
    """The first difference outside a tie group, or `None` when they agree.

    `expected` and `got` are citation dicts carrying `claim_id` and `score`; the
    expected side is the Python core, the got side is the MCP. A tie group is a
    maximal run of citations with the same rounded score on the *expected* side,
    which is where a last-ULP difference can legitimately land.
    """
    if len(expected) != len(got):
        return f"length {len(got)} != {len(expected)}"
    index = 0
    while index < len(expected):
        score = expected[index]["score"]
        end = index
        while end < len(expected) and expected[end]["score"] == score:
            end += 1
        expected_ids = [citation["claim_id"] for citation in expected[index:end]]
        got_ids = [citation["claim_id"] for citation in got[index:end]]
        if set(expected_ids) != set(got_ids):
            return (
                f"positions {index}..{end - 1} (score {score}) differ: "
                f"expected {expected_ids}, got {got_ids}"
            )
        index = end
    return None


def _quote_at_offsets(citation: dict, texts: dict[str, str]) -> bool:
    locator = citation.get("locator") or {}
    start, end = locator.get("char_start"), locator.get("char_end")
    if start is None or end is None:
        return False
    source = texts.get(citation["doc_id"], "")
    return source[start:end] == norm(citation.get("quote", ""))


def _file_state(root: Path) -> dict[str, tuple[int, int]]:
    return {
        str(path.relative_to(root)): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def run(kb_dir: Path, questions: list[dict], binary: Path, limit: int) -> dict:
    kb = KnowledgeBase(kb_dir)
    claims = kb.claims()
    if not claims:
        raise SystemExit(f"{kb_dir}: no claims.jsonl")
    corpus = Corpus(claims, kb.documents(), kb.verifier(), include_unverified=False)
    texts = {doc_id: norm(kb.text(doc_id)) for doc_id in {claim["doc_id"] for claim in claims}}

    before = _file_state(kb_dir)
    client = McpClient(binary)
    mismatches: list[dict] = []
    bad_quotes: list[dict] = []
    citations_checked = 0
    durations: list[float] = []
    warmup_ms: float | None = None
    try:
        # The first call pays the artifact load and the lexical index build:
        # once per process, not per question. Timing it inside the sample would
        # publish a latency no second question ever sees, so it is measured on
        # its own and reported as `warmup_ms`.
        started = time.perf_counter()
        client.call(
            "documents_ask",
            {"q": questions[0]["text"], "kb": str(kb_dir), "k": limit},
        )
        warmup_ms = round((time.perf_counter() - started) * 1000.0, 1)
        for item in questions:
            question = item["text"]
            expected = ask(question, corpus, limit=limit)
            started = time.perf_counter()
            result = client.call(
                "documents_ask",
                {"q": question, "kb": str(kb_dir), "k": limit},
            )
            durations.append((time.perf_counter() - started) * 1000.0)
            structured = result.get("structuredContent") or {}
            got = structured.get("citations") or []
            difference = compare_rankings(
                [
                    {"claim_id": citation.claim_id, "score": citation.score}
                    for citation in expected.citations
                ],
                got,
            )
            if difference:
                mismatches.append(
                    {"qid": item["qid"], "question": question, "difference": difference}
                )
            for citation in got:
                citations_checked += 1
                if not _quote_at_offsets(citation, texts):
                    bad_quotes.append(
                        {"qid": item["qid"], "claim_id": citation.get("claim_id")}
                    )
    finally:
        client.close()
    after = _file_state(kb_dir)

    return {
        "questions": len(questions),
        "limit": limit,
        "binary": str(binary),
        "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "mismatches": mismatches,
        "quotes_not_at_offsets": bad_quotes,
        "citations_checked": citations_checked,
        "read_only": before == after,
        "warmup_ms": warmup_ms,
        "latency_ms": {
            "p50": round(statistics.median(durations), 1) if durations else None,
            "p95": round(
                sorted(durations)[max(0, int(round(0.95 * len(durations))) - 1)], 1
            )
            if durations
            else None,
            "max": round(max(durations), 1) if durations else None,
        },
    }


def tokenizer_gate(kb_dir: Path, snapshot: Path) -> int:
    """G7 over a whole corpus: write the Python stream, let the Rust test compare.

    The tokenizer is the one piece of the port that can differ by a single
    Unicode category and reorder a ranking nobody can explain, so the gate is
    token-level on every document, not on a sample. The comparison lives in
    Rust (`documents::text::tests::g7_token_stream_matches_python`) because the
    Rust side is the side that must be checked; this writes the answer key from
    the Python module, which is the reference, and runs the test against it.
    """
    from compiler.documents.text import tokens

    rows = []
    for path in sorted((kb_dir / "text").glob("*.txt")):
        rows.append(
            json.dumps(
                {"doc_id": path.stem, "tokens": " ".join(tokens(path.read_text(encoding="utf-8")))},
                ensure_ascii=False,
            )
        )
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_text("\n".join(rows) + "\n", encoding="utf-8")
    completed = subprocess.run(
        [
            "cargo",
            "test",
            "--offline",
            "--bin",
            "ontomcp",
            "documents::text::tests::g7_token_stream_matches_python",
            "--",
            "--ignored",
            "--nocapture",
        ],
        cwd=REPO / "mcp",
        env=dict(
            os.environ,
            ONTOSKILLS_ROOT=str(kb_dir),
            ONTOSKILLS_TOKEN_SNAPSHOT=str(snapshot),
        ),
        capture_output=True,
        text=True,
    )
    print(f"documents compared: {len(rows)}")
    print("G7 tokenizer parity:", "PASS" if completed.returncode == 0 else "FAIL")
    if completed.returncode != 0:
        print(completed.stdout[-2000:])
        print(completed.stderr[-2000:])
    return 0 if completed.returncode == 0 else 1


def format_report(report: dict) -> str:
    lines = [
        f"questions: {report['questions']} (k={report['limit']})",
        f"mismatches: {len(report['mismatches'])}",
        f"quotes checked at their offsets: {report['citations_checked']} "
        f"({len(report['quotes_not_at_offsets'])} wrong)",
        f"read-only: {'yes' if report['read_only'] else 'NO'}",
        f"first call (artifact load + index build): {report['warmup_ms']} ms",
        f"latency: p50 {report['latency_ms']['p50']} ms, "
        f"p95 {report['latency_ms']['p95']} ms, max {report['latency_ms']['max']} ms",
    ]
    for mismatch in report["mismatches"][:10]:
        lines.append(f"  {mismatch['qid']}: {mismatch['difference']}")
        lines.append(f"    {mismatch['question'][:140]}")
    for bad in report["quotes_not_at_offsets"][:10]:
        lines.append(f"  {bad['qid']}: quote of {bad['claim_id']} is not at its offsets")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--kb", required=True, type=Path)
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--binary", type=Path, default=DEFAULT_BINARY)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--questions", type=int, default=0, help="first N questions only")
    parser.add_argument("--out", type=Path, default=None, help="write the JSON report here")
    parser.add_argument(
        "--tokenizer",
        action="store_true",
        help="run gate G7 over every text in the corpus instead of the questions",
    )
    parser.add_argument(
        "--tokenizer-snapshot",
        type=Path,
        default=Path(tempfile.gettempdir()) / "ontoskills-tokenizer-snapshot.jsonl",
        help="where the Python token streams are written for the Rust test",
    )
    args = parser.parse_args(argv)

    if args.tokenizer:
        return tokenizer_gate(args.kb, args.tokenizer_snapshot)

    if not args.binary.is_file():
        raise SystemExit(f"{args.binary}: not built; run `cargo build` in mcp/ first")
    items = json.loads(args.selection.read_text(encoding="utf-8"))["items"]
    if args.questions:
        items = items[: args.questions]
    if not items:
        raise SystemExit(f"{args.selection}: no questions to ask")

    report = run(args.kb, items, args.binary, args.limit)
    print(format_report(report))
    if args.out:
        args.out.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    clean = (
        not report["mismatches"]
        and not report["quotes_not_at_offsets"]
        and report["read_only"]
    )
    return 0 if clean else 1


if __name__ == "__main__":
    raise SystemExit(main())
