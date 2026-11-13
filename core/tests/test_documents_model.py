"""Tests for the corpus model: ids, manifests, hashes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from compiler.documents.model import Document, load_corpus, sha256_file


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_doc_id_must_be_a_stable_slug():
    Document(doc_id="GDPR", path=Path("g.pdf"), title="GDPR", kind="pdf")
    Document(doc_id="TNA_CONTRACTS", path=Path("t.pdf"), title="TNA", kind="pdf")
    with pytest.raises(ValueError):
        Document(doc_id="D-1", path=Path("x"), title="x", kind="text")
    with pytest.raises(ValueError):
        Document(doc_id="1GDPR", path=Path("x"), title="x", kind="text")


def test_context_is_derived_from_metadata():
    doc = Document(
        doc_id="T1",
        path=Path("t.txt"),
        title="A title",
        kind="text",
        version="v1",
        jurisdiction="UK",
        doc_type="policy",
    )
    assert doc.context == {
        "source": "A title",
        "version": "v1",
        "jurisdiction": "UK",
        "doc_type": "policy",
    }


def test_load_corpus_discovers_supported_files(tmp_path):
    _write(tmp_path / "a.txt", "alpha")
    _write(tmp_path / "b.md", "beta")
    _write(tmp_path / "ignored.bin", "nope")
    docs = load_corpus(tmp_path)
    assert [doc.doc_id for doc in docs] == ["a", "b"]
    assert docs[0].sha256 == sha256_file(tmp_path / "a.txt")


def test_manifest_records_hash_and_licence(tmp_path):
    source = _write(tmp_path / "doc.txt", "the rule")
    manifest = {
        "documents": [
            {
                "doc_id": "DOC",
                "path": "doc.txt",
                "title": "Doc",
                "kind": "text",
                "licence": "CC0",
                "sha256": sha256_file(source),
            }
        ]
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    docs = load_corpus(tmp_path, path)
    assert len(docs) == 1
    assert docs[0].licence == "CC0"
    assert docs[0].context["source"] == "Doc"


def test_manifest_hash_mismatch_is_refused(tmp_path):
    _write(tmp_path / "doc.txt", "the rule")
    manifest = {
        "documents": [
            {"doc_id": "DOC", "path": "doc.txt", "sha256": "0" * 64}
        ]
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        load_corpus(tmp_path, path)


def test_manifest_missing_file_is_an_error(tmp_path):
    manifest = {"documents": [{"doc_id": "DOC", "path": "absent.txt"}]}
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        load_corpus(tmp_path, path)


def test_duplicate_doc_ids_are_disambiguated(tmp_path):
    _write(tmp_path / "same.txt", "alpha")
    (tmp_path / "sub").mkdir()
    _write(tmp_path / "sub" / "same.txt", "beta")
    docs = load_corpus(tmp_path)
    assert len({doc.doc_id for doc in docs}) == 2
