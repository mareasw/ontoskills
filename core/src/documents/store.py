"""The knowledge base on disk.

A compiled corpus is a directory, not a database:

    manifest.json      what was ingested and how (SHA-256, licence, prompt hash)
    documents.jsonl    one row per document
    spans.jsonl        one row per span the segmenter emitted
    claims.jsonl       one row per claim, schema v2
    verifier.jsonl     one row per claim, deterministic verdict
    rejected.jsonl     one row per claim the compiler refused, and why
    vectors.jsonl      one embedding per claim, plus the model that made them
    graph.ttl          the same claims as RDF
    evidence.csv       claims flattened for a spreadsheet
    text/<doc_id>.txt  the extracted, paginated plain text
    view.html          a static, read-only view

Everything is written atomically (write to ``.tmp`` then rename) so an
interrupted ingest never leaves a half-written claims file that looks valid.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import tempfile
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from compiler.documents.prompt import PROMPT_HASH

MANIFEST = "manifest.json"
DOCUMENTS = "documents.jsonl"
SPANS = "spans.jsonl"
CLAIMS = "claims.jsonl"
VERIFIER = "verifier.jsonl"
REJECTED = "rejected.jsonl"
VECTORS = "vectors.jsonl"
GRAPH = "graph.ttl"
EVIDENCE = "evidence.csv"
TEXT_DIR = "text"
VIEW = "view.html"

PREFIXES = """\
@prefix doc: <https://ontoskills.sh/ontology/documents#> .
@prefix ex: <https://ontoskills.sh/kb/> .
@prefix prov: <http://www.w3.org/ns/prov#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix dcterms: <http://purl.org/dc/terms/> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
"""

# The TBox is a file, not a string literal: `core/specs/documents.ttl` is the
# normative definition, versioned on its own and published at
# https://ontoskills.sh/ontology/documents. It is read once and inlined into
# every graph so the artifact parses offline, without a network fetch and
# without asking the reader to trust that two copies agree.
ONTOLOGY_PATH = Path(__file__).resolve().parent.parent.parent / "specs" / "documents.ttl"


@lru_cache(maxsize=1)
def documents_ontology() -> str:
    """The document layer's TBox, with its prefix declarations removed.

    The graph declares its prefixes in one block at the top; repeating them
    mid-file is legal Turtle that reads like an accident, so they are stripped
    here and the tests assert the inlined copy declares no prefix of its own.
    """
    if not ONTOLOGY_PATH.exists():
        raise FileNotFoundError(f"document ontology not found: {ONTOLOGY_PATH}")
    lines = [
        line
        for line in ONTOLOGY_PATH.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("@prefix")
    ]
    return "\n".join(lines).strip() + "\n"


MODALITY = {
    "obligation": "doc:Obligation",
    "permission": "doc:Permission",
    "prohibition": "doc:Prohibition",
    "recommendation": "doc:Recommendation",
    "definition": "doc:Definition",
    "procedure_step": "doc:ProcedureStep",
    "condition": "doc:Condition",
}

ROLE = {"supports": "doc:supportsRole", "context": "doc:contextRole"}
DEFAULT_ROLE = "doc:supportsRole"

# An IRIREF may not contain these. A source URL that does is not an address this
# writer can hand to a reader, so it is dropped rather than mangled: a broken
# link is worse than an absent one, and the locator still carries offsets and
# section.
_IRIREF_UNSAFE = re.compile(r'[\s<>"{}|^`\\]')


def _url_iri(value: Any) -> str | None:
    url = str(value or "").strip()
    if url.startswith(("http://", "https://")) and not _IRIREF_UNSAFE.search(url):
        return f"<{url}>"
    return None


CSV_FIELDS = [
    "claim_id",
    "doc_id",
    "statement",
    "modality",
    "actor",
    "deadline",
    "conditions",
    "verdict",
    "page",
    "section",
    "url",
    "quote",
]


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=str(path.parent), delete=False, prefix=".tmp-", suffix=path.suffix
    )
    try:
        with handle:
            handle.write(text)
        os.replace(handle.name, path)
    except BaseException:
        Path(handle.name).unlink(missing_ok=True)
        raise


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    lines = [json.dumps(row, ensure_ascii=False) for row in rows]
    _atomic_text(path, "\n".join(lines) + ("\n" if lines else ""))
    return len(lines)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_json(path: Path, data: Any) -> None:
    _atomic_text(path, json.dumps(data, ensure_ascii=False, indent=1) + "\n")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _lit(value: Any) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def _iri(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in str(value))
    return cleaned or "x"


def _sections(doc_id: str, claims: list[dict]) -> dict[tuple[str, ...], str]:
    """Every heading path a document's locators mention, and its IRI.

    Built from the locators the claims already carry, so nothing is invented and
    no model call is needed: the section tree was in the data and the old writer
    flattened it into a string. Every prefix of a path is registered too, so a
    section that holds no claim of its own still exists as a parent.
    """
    paths: set[tuple[str, ...]] = set()
    for claim in claims:
        for item in claim.get("evidence") or []:
            path = (item.get("locator") or {}).get("section_path") or []
            for depth in range(1, len(path) + 1):
                paths.add(tuple(path[:depth]))
    return {
        path: f"ex:sec_{_iri(doc_id)}_{index:03d}"
        for index, path in enumerate(sorted(paths))
    }


def _entity(subject: str, kind: str, pairs: list[tuple[str, str]]) -> str:
    """One subject, its type, and its predicate-object pairs, joined safely.

    Written as a list rather than as appended lines with trailing semicolons:
    almost every predicate is conditional, and the previous shape ended in a
    period only because the last line happened to be unconditional.
    """
    parts = [f"a {kind}", *(f"{predicate} {obj}" for predicate, obj in pairs)]
    return f"{subject} " + " ;\n    ".join(parts) + " ."


def build_graph(documents: list[dict], claims: list[dict]) -> str:
    """Render documents and claims as Turtle, without inventing triples."""
    out = [PREFIXES, documents_ontology()]
    by_doc: dict[str, list[dict]] = defaultdict(list)
    for claim in claims:
        by_doc[claim["doc_id"]].append(claim)
    doc_by_id = {doc["doc_id"]: doc for doc in documents}
    for doc_id, items in sorted(by_doc.items()):
        doc = doc_by_id.get(doc_id, {})
        doc_iri = f"ex:doc_{_iri(doc_id)}"
        ctx = f"ex:ctx_{_iri(doc_id)}"
        sections = _sections(doc_id, items)
        children: dict[tuple[str, ...], list[str]] = defaultdict(list)
        for path in sections:
            if len(path) > 1:
                children[path[:-1]].append(sections[path])

        pairs = [
            ("doc:hasTitle", _lit(doc.get("title", doc_id))),
            ("doc:inContext", ctx),
        ]
        if doc.get("version"):
            pairs.insert(1, ("doc:hasDocVersion", _lit(doc["version"])))
        if doc.get("doc_type"):
            pairs.append(("doc:hasDocType", _lit(doc["doc_type"])))
        if doc.get("licence"):
            pairs.append(("doc:hasLicence", _lit(doc["licence"])))
        if doc.get("sha256"):
            pairs.append(("doc:hasSha256", _lit(doc["sha256"])))
        top_level = [iri for path, iri in sorted(sections.items()) if len(path) == 1]
        if top_level:
            pairs.append(("doc:hasSection", ", ".join(top_level)))
        pairs.append(
            ("doc:hasClaim", ", ".join(f"ex:claim_{_iri(c['claim_id'])}" for c in items))
        )
        out.append(_entity(doc_iri, "doc:Document", pairs))
        out.append("")

        ctx_pairs: list[tuple[str, str]] = []
        ctx_url = _url_iri(doc.get("url"))
        if ctx_url:
            ctx_pairs.append(("doc:hasSourceUrl", ctx_url))
        if doc.get("jurisdiction"):
            ctx_pairs.append(("doc:hasJurisdiction", _lit(doc["jurisdiction"])))
        if doc.get("version"):
            ctx_pairs.append(("doc:hasDocVersion", _lit(doc["version"])))
        ctx_pairs.append(("doc:hasDocType", _lit(doc.get("doc_type", ""))))
        out.append(_entity(ctx, "doc:Context", ctx_pairs))
        out.append("")

        for path, iri in sorted(sections.items()):
            section_pairs = [
                ("doc:hasSectionTitle", _lit(path[-1])),
                ("doc:hasSectionPath", _lit(" > ".join(path))),
            ]
            if children.get(path):
                section_pairs.append(
                    ("doc:hasSubsection", ", ".join(sorted(children[path])))
                )
            out.append(_entity(iri, "doc:Section", section_pairs))
        if sections:
            out.append("")

        for claim in items:
            cid = _iri(claim["claim_id"])
            if claim["modality"] not in MODALITY:
                raise ValueError(
                    f"{claim['claim_id']}: modality {claim['modality']!r} is not one of "
                    f"{sorted(MODALITY)}; the document ontology has no bucket for it"
                )
            claim_pairs = [
                ("doc:inContext", ctx),
                ("doc:hasStatement", _lit(claim["statement"])),
                ("doc:hasModality", MODALITY[claim["modality"]]),
            ]
            if claim.get("actor"):
                claim_pairs.append(("doc:hasActor", _lit(claim["actor"])))
            if claim.get("deadline"):
                claim_pairs.append(("doc:hasDeadline", _lit(claim["deadline"])))
            for condition in claim.get("conditions") or []:
                claim_pairs.append(("doc:hasCondition", _lit(condition)))
            evidence = claim.get("evidence") or []
            if evidence:
                claim_pairs.append(
                    ("doc:hasEvidence", ", ".join(f"ex:ev_{cid}_{i}" for i in range(len(evidence))))
                )
            claim_pairs.append(("prov:wasDerivedFrom", doc_iri))
            out.append(_entity(f"ex:claim_{cid}", "doc:Claim", claim_pairs))
            out.append("")

            for index, item in enumerate(evidence):
                locator = item.get("locator") or {}
                loc_iri = f"ex:loc_{cid}_{index}"
                role = ROLE.get(str(item.get("role", "supports")), DEFAULT_ROLE)
                ev_pairs = [
                    ("doc:hasQuote", _lit(item.get("quote", ""))),
                    ("doc:evidenceRole", role),
                    ("doc:hasLocator", loc_iri),
                    ("prov:wasDerivedFrom", doc_iri),
                ]
                out.append(_entity(f"ex:ev_{cid}_{index}", "doc:Evidence", ev_pairs))

                loc_pairs: list[tuple[str, str]] = []
                for key, predicate in (
                    ("char_start", "doc:hasCharStart"),
                    ("char_end", "doc:hasCharEnd"),
                ):
                    if locator.get(key) is not None:
                        loc_pairs.append((predicate, str(int(locator[key]))))
                if locator.get("page") is not None:
                    loc_pairs.append(("doc:hasPage", str(int(locator["page"]))))
                loc_url = _url_iri(locator.get("url"))
                if loc_url:
                    loc_pairs.append(("doc:hasSourceUrl", loc_url))
                path = tuple(locator.get("section_path") or [])
                if path in sections:
                    loc_pairs.append(("doc:inSection", sections[path]))
                out.append(_entity(loc_iri, "doc:Locator", loc_pairs))
            out.append("")

            for other in claim.get("conflicts_with") or []:
                out.append(f"ex:claim_{cid} doc:conflictsWith ex:claim_{_iri(other)} .")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def write_evidence_csv(path: Path, claims: list[dict], verdicts: dict[str, str]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="", dir=str(path.parent), delete=False, prefix=".tmp-", suffix=".csv"
    )
    try:
        with handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
            writer.writeheader()
            for claim in claims:
                evidence = claim.get("evidence") or [{}]
                first = evidence[0]
                locator = first.get("locator") or {}
                writer.writerow(
                    {
                        "claim_id": claim["claim_id"],
                        "doc_id": claim["doc_id"],
                        "statement": claim["statement"],
                        "modality": claim["modality"],
                        "actor": claim.get("actor", ""),
                        "deadline": claim.get("deadline", ""),
                        "conditions": " | ".join(claim.get("conditions") or []),
                        "verdict": verdicts.get(claim["claim_id"], ""),
                        "page": locator.get("page", ""),
                        "section": " > ".join(locator.get("section_path") or []),
                        "url": locator.get("url", ""),
                        "quote": first.get("quote", ""),
                    }
                )
        os.replace(handle.name, path)
    except BaseException:
        Path(handle.name).unlink(missing_ok=True)
        raise
    return len(claims)


class KnowledgeBase:
    """Read and write one compiled corpus directory."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    # --- paths -------------------------------------------------------------

    def path(self, name: str) -> Path:
        return self.root / name

    @property
    def text_dir(self) -> Path:
        return self.root / TEXT_DIR

    def text_path(self, doc_id: str) -> Path:
        return self.text_dir / f"{doc_id}.txt"

    # --- read --------------------------------------------------------------

    def manifest(self) -> dict:
        path = self.path(MANIFEST)
        return read_json(path) if path.exists() else {}

    def documents(self) -> list[dict]:
        return read_jsonl(self.path(DOCUMENTS))

    def spans(self) -> list[dict]:
        return read_jsonl(self.path(SPANS))

    def claims(self) -> list[dict]:
        return read_jsonl(self.path(CLAIMS))

    def verifier(self) -> list[dict]:
        return read_jsonl(self.path(VERIFIER))

    def rejected(self) -> list[dict]:
        return read_jsonl(self.path(REJECTED))

    def vectors(self) -> dict[str, list[float]]:
        """Claim id to embedding, empty when the KB was built without them.

        Line one is a header describing the model; the rest are the rows. A
        caller that has no vectors must fall back to BM25 rather than fail.
        """
        path = self.path(VECTORS)
        if not path.exists():
            return {}
        out: dict[str, list[float]] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if "claim_id" in row:
                out[row["claim_id"]] = row["vector"]
        return out

    def vectors_header(self) -> dict:
        """The model that built the vectors, read from the header line alone.

        The file is one row per claim, so reading it whole to look at line one
        would cost a few megabytes for a string comparison.
        """
        path = self.path(VECTORS)
        if not path.exists():
            return {}
        with path.open(encoding="utf-8") as handle:
            return json.loads(handle.readline())

    def text(self, doc_id: str) -> str:
        path = self.text_path(doc_id)
        return path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""

    def texts(self) -> dict[str, str]:
        return {doc["doc_id"]: self.text(doc["doc_id"]) for doc in self.documents()}

    def exists(self) -> bool:
        return self.path(CLAIMS).exists()

    # --- write -------------------------------------------------------------

    def save_texts(self, texts: dict[str, str]) -> None:
        self.text_dir.mkdir(parents=True, exist_ok=True)
        for doc_id, text in texts.items():
            _atomic_text(self.text_path(doc_id), text)

    def write_view(self, html: str) -> None:
        _atomic_text(self.path(VIEW), html)

    def write(
        self,
        *,
        manifest: dict,
        documents: list[dict],
        spans: list[dict],
        claims: list[dict],
        verifier_rows: list[dict] | None = None,
        rejected_rows: list[dict] | None = None,
        view: str | None = None,
    ) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        if not manifest.get("prompt_hash"):
            manifest = {**manifest, "prompt_hash": PROMPT_HASH}
        write_json(self.path(MANIFEST), manifest)
        write_jsonl(self.path(DOCUMENTS), documents)
        write_jsonl(self.path(SPANS), spans)
        write_jsonl(self.path(CLAIMS), claims)
        rows = verifier_rows or []
        write_jsonl(self.path(VERIFIER), rows)
        # A rejected claim leaves no other trace, so the file has to be written
        # when there is one and removed when there is not: a stale file from an
        # earlier build would report rejections this build did not make.
        rejected = rejected_rows or []
        if rejected:
            write_jsonl(self.path(REJECTED), rejected)
        else:
            self.path(REJECTED).unlink(missing_ok=True)
        _atomic_text(self.path(GRAPH), build_graph(documents, claims))
        verdicts = {row["claim_id"]: row["verdict"] for row in rows}
        write_evidence_csv(self.path(EVIDENCE), claims, verdicts)
        if view is not None:
            _atomic_text(self.path(VIEW), view)


def write_vectors(kb: KnowledgeBase, claims: list[dict], embedder) -> int:
    """Embed every claim's searchable text; returns how many vectors were written.

    The header is written first and names the model and revision, so a KB built
    by one model can refuse another model's query vectors instead of silently
    comparing two different spaces.
    """
    from compiler.documents.ask import _claim_text
    from compiler.documents.vector import DIM, MODEL, REVISION

    rows = []
    texts = [" ".join(value for value in _claim_text(claim).values() if value) for claim in claims]
    for claim, vector in zip(claims, embedder.encode(texts)):
        rows.append({"claim_id": claim["claim_id"], "vector": vector})
    _atomic_text(
        kb.path(VECTORS),
        "\n".join(
            [json.dumps({"model": MODEL, "revision": REVISION, "dim": DIM})]
            + [json.dumps(row) for row in rows]
        )
        + "\n",
    )
    return len(rows)
