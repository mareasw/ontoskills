"""Corpus model: one document, one manifest, one stable claim-id namespace.

A document is described by a manifest, not by the model. The manifest records
where the bytes came from, which licence allows the demo to redistribute them,
and the SHA-256 that was ingested. Without it a knowledge base cannot say what
it is a knowledge base *of*.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

SUPPORTED = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".odt": "docx",
    ".html": "html",
    ".htm": "html",
    ".txt": "text",
    ".md": "markdown",
    ".markdown": "markdown",
}

# A doc id is a stable slug, not a position in a folder listing. The schema's
# claim id is ``<doc_id>-NNNN``; underscores keep the numeric suffix the last
# dash-separated component.
DOC_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


@dataclass
class Document:
    doc_id: str
    path: Path
    title: str
    kind: str
    url: str = ""
    licence: str = "unknown"
    version: str = ""
    jurisdiction: str = ""
    doc_type: str = "document"
    page_range: list[int] | None = None
    sha256: str = ""
    text_path: Path | None = None
    notes: str = ""
    context: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not DOC_ID.match(self.doc_id):
            raise ValueError(
                f"doc_id {self.doc_id!r}: use a letter followed by letters, digits or underscores"
            )
        if not self.context:
            self.context = {
                "source": self.title,
                "version": self.version,
                "jurisdiction": self.jurisdiction,
                "doc_type": self.doc_type,
            }
        self.context = {k: v for k, v in self.context.items() if v}

    def segment_meta(self) -> dict[str, Any]:
        """The fields the segmenter needs; no path, no licence."""
        return {"doc_id": self.doc_id, "kind": self.kind, "url": self.url}

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "path": self.path.name,
            "title": self.title,
            "kind": self.kind,
            "url": self.url,
            "licence": self.licence,
            "version": self.version,
            "jurisdiction": self.jurisdiction,
            "doc_type": self.doc_type,
            "page_range": self.page_range,
            "sha256": self.sha256,
            "notes": self.notes,
            "context": self.context,
        }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _slug(text: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")
    if not slug:
        slug = "doc"
    if not slug[0].isalpha():
        slug = f"D_{slug}"
    return slug


def _unique(doc_id: str, seen: set[str]) -> str:
    candidate = doc_id
    index = 2
    while candidate in seen:
        candidate = f"{doc_id}_{index}"
        index += 1
    seen.add(candidate)
    return candidate


def load_corpus(folder: Path, manifest_path: Path | None = None) -> list[Document]:
    """Load a corpus from a manifest, or discover supported files in ``folder``.

    A manifest is optional for a quick local run, but it is the only way to
    record licence and provenance, so ``ingest`` warns when it is absent.
    """
    folder = Path(folder)
    if manifest_path is not None:
        data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        entries = data.get("documents", data) if isinstance(data, dict) else data
        docs: list[Document] = []
        seen: set[str] = set()
        for entry in entries:
            relative = entry.get("path")
            if not relative:
                raise ValueError("manifest entry without a path")
            path = (folder / relative).resolve()
            if not path.exists():
                raise FileNotFoundError(f"{relative}: not found under {folder}")
            doc_id = entry.get("doc_id") or _slug(path.stem)
            doc_id = _unique(doc_id, seen)
            kind = entry.get("kind") or SUPPORTED.get(path.suffix.lower(), "text")
            doc = Document(
                doc_id=doc_id,
                path=path,
                title=entry.get("title") or path.stem,
                kind=kind,
                url=entry.get("url", ""),
                licence=entry.get("licence", "unknown"),
                version=entry.get("version", ""),
                jurisdiction=entry.get("jurisdiction", ""),
                doc_type=entry.get("doc_type", "document"),
                page_range=entry.get("page_range"),
                sha256=entry.get("sha256", ""),
                notes=entry.get("notes", ""),
            )
            if doc.sha256:
                actual = sha256_file(path)
                if actual != doc.sha256:
                    raise ValueError(
                        f"{relative}: SHA-256 mismatch (expected {doc.sha256}, got {actual})"
                    )
            docs.append(doc)
        if not docs:
            raise ValueError("manifest contains no documents")
        return docs

    seen = set()
    docs = []
    for path in sorted(folder.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        kind = SUPPORTED.get(path.suffix.lower())
        if kind is None:
            continue
        doc_id = _unique(_slug(path.stem), seen)
        docs.append(
            Document(
                doc_id=doc_id,
                path=path.resolve(),
                title=path.stem.replace("_", " ").replace("-", " ").strip(),
                kind=kind,
                sha256=sha256_file(path),
            )
        )
    if not docs:
        raise ValueError(f"no supported documents under {folder}")
    return docs


def document_index(docs: Iterable[Document]) -> dict[str, Document]:
    return {doc.doc_id: doc for doc in docs}
