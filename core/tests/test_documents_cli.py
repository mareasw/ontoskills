"""Tests for the ingest/ask/view CLI surface."""

from __future__ import annotations

from click.testing import CliRunner

from compiler.cli import cli
from compiler.cli.documents import _print_estimate
from compiler.documents.llm import ModelError
from compiler.documents.store import KnowledgeBase


def test_ingest_dry_run_segments_without_calling_a_model(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "contract.txt").write_text(
        "1. Notification\n\n1.1 The Supplier shall notify the Buyer within 48 hours of a breach.\n",
        encoding="utf-8",
    )
    result = CliRunner().invoke(
        cli, ["ingest", str(corpus), "-o", str(tmp_path / "kb"), "--dry-run"]
    )
    assert result.exit_code == 0, result.output
    assert "Estimate" in result.output
    assert "Dry run" in result.output
    assert not (tmp_path / "kb" / "claims.jsonl").exists()


def test_ingest_refuses_a_manifest_hash_mismatch(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "doc.txt").write_text("text", encoding="utf-8")
    (corpus / "manifest.json").write_text(
        '{"documents": [{"doc_id": "DOC", "path": "doc.txt", "sha256": "0"}]}',
        encoding="utf-8",
    )
    result = CliRunner().invoke(cli, ["ingest", str(corpus), "-o", str(tmp_path / "kb"), "--dry-run"])
    assert result.exit_code != 0
    assert "SHA-256 mismatch" in result.output


def _kb(tmp_path) -> KnowledgeBase:
    kb = KnowledgeBase(tmp_path / "kb")
    kb.write(
        manifest={"name": "demo"},
        documents=[
            {"doc_id": "MT_SCH20", "title": "Mid-Tier Schedule 20", "url": "https://example.org/a"},
            {"doc_id": "GDPR", "title": "GDPR", "url": "https://example.org/b"},
        ],
        spans=[],
        claims=[
            {
                "claim_id": "MT_SCH20-0001",
                "doc_id": "MT_SCH20",
                "statement": "The Supplier shall notify the Buyer within 48 hours of a personal data breach.",
                "modality": "obligation",
                "evidence": [
                    {
                        "quote": "The Supplier shall notify the Buyer within 48 hours of a personal data breach.",
                        "locator": {"kind": "pdf", "page": 4, "section_path": ["Notification"], "url": "https://example.org/a"},
                    }
                ],
            },
            {
                "claim_id": "GDPR-0001",
                "doc_id": "GDPR",
                "statement": "The controller shall notify the supervisory authority within 72 hours of a personal data breach.",
                "modality": "obligation",
                "evidence": [
                    {
                        "quote": "The controller shall notify the supervisory authority within 72 hours of a personal data breach.",
                        "locator": {"kind": "pdf", "page": 46, "section_path": ["Article 33"], "url": "https://example.org/b"},
                    }
                ],
            },
        ],
        verifier_rows=[],
    )
    return kb


def test_ask_prints_citations_and_tensions(tmp_path):
    kb = _kb(tmp_path)
    result = CliRunner().invoke(
        cli, ["ask", "How quickly must a breach be notified?", "-k", str(kb.root)]
    )
    assert result.exit_code == 0, result.output
    assert "MT_SCH20-0001" in result.output
    assert "48 hours" in result.output
    assert "Tensions" in result.output


def test_ask_json_shape(tmp_path):
    kb = _kb(tmp_path)
    result = CliRunner().invoke(
        cli, ["ask", "breach notification deadline", "-k", str(kb.root), "--json"]
    )
    assert result.exit_code == 0, result.output
    assert '"citations"' in result.output
    assert '"documents"' in result.output
    assert "MT_SCH20" in result.output


def test_view_writes_html(tmp_path):
    kb = _kb(tmp_path)
    out = tmp_path / "out.html"
    result = CliRunner().invoke(
        cli, ["view", "-k", str(kb.root), "-q", "How quickly must a breach be notified?", "-o", str(out)]
    )
    assert result.exit_code == 0, result.output
    html = out.read_text(encoding="utf-8")
    assert "MT_SCH20-0001" in html
    assert "copy citation" in html


def test_ask_without_a_knowledge_base_fails_cleanly(tmp_path):
    result = CliRunner().invoke(cli, ["ask", "anything", "-k", str(tmp_path)])
    assert result.exit_code != 0
    assert "no claims.jsonl" in result.output


def test_ingest_end_to_end_with_a_stub_model(tmp_path, monkeypatch):
    """The whole command, with the model replaced by a fixed reply."""
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "contract.txt").write_text(
        "1. Notification\n\n"
        "1.1 The Supplier shall notify the Buyer within 48 hours of a breach.\n",
        encoding="utf-8",
    )
    reply = (
        '[{"span_ids": ["S0001"], '
        '"statement": "The Supplier shall notify the Buyer within 48 hours of a breach.", '
        '"modality": "obligation", "actor": "Supplier", "deadline": "48 hours", '
        '"conditions": []}]'
    )
    calls = []

    def fake_chat(*args, **kwargs):
        calls.append(args)
        return reply, {"input_tokens": 100, "output_tokens": 50}, "stop"

    monkeypatch.setattr("compiler.documents.compile.chat", fake_chat)
    monkeypatch.setenv("OPENAI_MODEL", "stub")

    result = CliRunner().invoke(
        cli, ["ingest", str(corpus), "-o", str(tmp_path / "kb"), "--no-conflicts"]
    )
    assert result.exit_code == 0, result.output
    assert calls

    kb = KnowledgeBase(tmp_path / "kb")
    claims = kb.claims()
    assert len(claims) == 1
    assert claims[0]["claim_id"] == "contract-0001"
    assert "The Supplier shall notify" in claims[0]["evidence"][0]["quote"]
    assert kb.verifier()[0]["verdict"] == "ok"
    assert kb.manifest()["claims"] == 1
    assert (tmp_path / "kb" / "view.html").exists()
    assert (tmp_path / "kb" / "graph.ttl").exists()
    assert (tmp_path / "kb" / "evidence.csv").exists()
    # Replies are cached even on the first run, so a failure mid-corpus is
    # resumable without paying for the completed chunks twice.
    assert list((tmp_path / "kb" / "cache").rglob("*.json"))


def test_ingest_keeps_going_when_one_document_fails(tmp_path, monkeypatch):
    """A chunk the gateway will not serve must not block the other documents."""
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "a_bad.txt").write_text(
        "1. Failure\n\n1.1 The Broken Party shall raise the error.\n", encoding="utf-8"
    )
    (corpus / "b_good.txt").write_text(
        "1. Notification\n\n"
        "1.1 The Supplier shall notify the Buyer within 48 hours of a breach.\n",
        encoding="utf-8",
    )
    reply = (
        '[{"span_ids": ["S0001"], '
        '"statement": "The Supplier shall notify the Buyer within 48 hours of a breach.", '
        '"modality": "obligation", "actor": "Supplier", "deadline": "48 hours", '
        '"conditions": []}]'
    )

    def fake_chat(base_url, api_key, model, messages, max_tokens, **kwargs):
        if "Broken Party" in messages[-1]["content"]:
            raise ModelError("HTTP 503: queued too long")
        return reply, {"input_tokens": 100, "output_tokens": 50}, "stop"

    monkeypatch.setattr("compiler.documents.compile.chat", fake_chat)
    monkeypatch.setenv("OPENAI_MODEL", "stub")

    result = CliRunner().invoke(
        cli, ["ingest", str(corpus), "-o", str(tmp_path / "kb"), "--no-conflicts"]
    )
    assert result.exit_code != 0, result.output
    assert "rerun with --resume" in result.output

    kb = KnowledgeBase(tmp_path / "kb")
    claims = kb.claims()
    assert [claim["doc_id"] for claim in claims] == ["b_good"]
    assert "The Supplier shall notify" in claims[0]["evidence"][0]["quote"]


def test_ingest_reports_a_truncated_reply_and_fails_the_run(tmp_path, monkeypatch):
    """A reply cut at the ceiling used to be reported as a successful run."""
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "contract.txt").write_text(
        "1. Notification\n\n1.1 The Supplier shall notify the Buyer within 48 hours.\n",
        encoding="utf-8",
    )

    def fake_chat(*args, **kwargs):
        return "", {"input_tokens": 100, "output_tokens": 10000}, "length"

    monkeypatch.setattr("compiler.documents.compile.chat", fake_chat)
    monkeypatch.setenv("OPENAI_MODEL", "stub")

    result = CliRunner().invoke(
        cli, ["ingest", str(corpus), "-o", str(tmp_path / "kb"), "--no-conflicts"]
    )
    assert result.exit_code != 0
    assert "truncated" in result.output
    assert KnowledgeBase(tmp_path / "kb").manifest()["truncated_calls"] == 1


def test_estimate_prints_the_page_count():
    rows = [
        {"doc_id": "A", "spans": 3, "chunks": 1, "chars": 300, "tokens": 100, "pages": 12},
        {"doc_id": "B", "spans": 2, "chunks": 1, "chars": 200, "tokens": 60, "pages": None},
    ]
    assert _print_estimate(rows, 0.15, 0.60)["pages"] == 12
