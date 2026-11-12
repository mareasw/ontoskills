"""The knowledge base on disk.

A compiled corpus is a directory, not a database:

    manifest.json      what was ingested and how (SHA-256, licence, prompt hash)
    documents.jsonl    one row per document
    spans.jsonl        one row per span the segmenter emitted
    claims.jsonl       one row per claim, schema v2
    verifier.jsonl     one row per claim, deterministic verdict
    rejected.jsonl     one row per claim the compiler refused, and why
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
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from compiler.documents.prompt import PROMPT_HASH

MANIFEST = "manifest.json"
DOCUMENTS = "documents.jsonl"
SPANS = "spans.jsonl"
CLAIMS = "claims.jsonl"
VERIFIER = "verifier.jsonl"
REJECTED = "rejected.jsonl"
GRAPH = "graph.ttl"
EVIDENCE = "evidence.csv"
TEXT_DIR = "text"
VIEW = "view.html"

PREFIXES = """\
@prefix oc: <https://ontoskills.sh/ontology#> .
@prefix ex: <https://ontoskills.sh/kb/> .
@prefix prov: <http://www.w3.org/ns/prov#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
"""

TBOX = """\
oc:Document a owl:Class .
oc:Section a owl:Class .
oc:Claim a owl:Class .
oc:Evidence a owl:Class .
oc:Context a owl:Class .

oc:hasTitle a owl:DatatypeProperty .
oc:hasVersion a owl:DatatypeProperty .
oc:hasDocType a owl:DatatypeProperty .
oc:hasJurisdiction a owl:DatatypeProperty .
oc:hasLicence a owl:DatatypeProperty .
oc:hasSha256 a owl:DatatypeProperty .
oc:inContext a owl:ObjectProperty .
oc:hasClaim a owl:ObjectProperty .
oc:hasEvidence a owl:ObjectProperty .
oc:hasStatement a owl:DatatypeProperty .
oc:hasQuote a owl:DatatypeProperty .
oc:hasModality a owl:ObjectProperty .
oc:hasActor a owl:DatatypeProperty .
oc:hasDeadline a owl:DatatypeProperty .
oc:hasCondition a owl:DatatypeProperty .
oc:hasLocator a owl:DatatypeProperty .
oc:hasSourceUrl a owl:DatatypeProperty .
oc:hasPage a owl:DatatypeProperty .
oc:hasConfidence a owl:DatatypeProperty .
oc:conflictsWith a owl:ObjectProperty .

oc:Obligation a owl:Class .
oc:Permission a owl:Class .
oc:Prohibition a owl:Class .
oc:Recommendation a owl:Class .
oc:Definition a owl:Class .
oc:ProcedureStep a owl:Class .
oc:Condition a owl:Class .
"""

MODALITY = {
    "obligation": "oc:Obligation",
    "permission": "oc:Permission",
    "prohibition": "oc:Prohibition",
    "recommendation": "oc:Recommendation",
    "definition": "oc:Definition",
    "procedure_step": "oc:ProcedureStep",
    "condition": "oc:Condition",
}

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


def build_graph(documents: list[dict], claims: list[dict]) -> str:
    """Render documents and claims as Turtle, without inventing triples."""
    out = [PREFIXES, TBOX]
    by_doc: dict[str, list[dict]] = defaultdict(list)
    for claim in claims:
        by_doc[claim["doc_id"]].append(claim)
    doc_by_id = {doc["doc_id"]: doc for doc in documents}
    for doc_id, items in sorted(by_doc.items()):
        doc = doc_by_id.get(doc_id, {})
        ctx = f"ex:ctx_{_iri(doc_id)}"
        doc_iri = f"ex:doc_{_iri(doc_id)}"
        out.append(f"{doc_iri} a oc:Document ;")
        out.append(f"    oc:hasTitle {_lit(doc.get('title', doc_id))} ;")
        if doc.get("version"):
            out.append(f"    oc:hasVersion {_lit(doc['version'])} ;")
        if doc.get("doc_type"):
            out.append(f"    oc:hasDocType {_lit(doc['doc_type'])} ;")
        if doc.get("licence"):
            out.append(f"    oc:hasLicence {_lit(doc['licence'])} ;")
        if doc.get("sha256"):
            out.append(f"    oc:hasSha256 {_lit(doc['sha256'])} ;")
        out.append(f"    oc:hasClaim {', '.join('ex:claim_' + _iri(c['claim_id']) for c in items)} ;")
        out.append(f"    oc:inContext {ctx} .")
        out.append("")
        out.append(f"{ctx} a oc:Context ;")
        out.append(f"    oc:hasSourceUrl {_lit(doc.get('url', ''))} ;")
        if doc.get("jurisdiction"):
            out.append(f"    oc:hasJurisdiction {_lit(doc['jurisdiction'])} ;")
        if doc.get("version"):
            out.append(f"    oc:hasVersion {_lit(doc['version'])} ;")
        out.append(f"    oc:hasDocType {_lit(doc.get('doc_type', ''))} .")
        out.append("")
        for claim in items:
            cid = _iri(claim["claim_id"])
            out.append(f"ex:claim_{cid} a oc:Claim ;")
            out.append(f"    oc:inContext {ctx} ;")
            out.append(f"    oc:hasStatement {_lit(claim['statement'])} ;")
            out.append(f"    oc:hasModality {MODALITY.get(claim['modality'], 'oc:Definition')} ;")
            if claim.get("actor"):
                out.append(f"    oc:hasActor {_lit(claim['actor'])} ;")
            if claim.get("deadline"):
                out.append(f"    oc:hasDeadline {_lit(claim['deadline'])} ;")
            for condition in claim.get("conditions") or []:
                out.append(f"    oc:hasCondition {_lit(condition)} ;")
            evidence = claim.get("evidence") or []
            links = " ,\n        ".join(f"ex:ev_{cid}_{i}" for i in range(len(evidence)))
            if links:
                out.append(f"    oc:hasEvidence {links} ;")
            out.append(f"    prov:wasDerivedFrom {doc_iri} .")
            out.append("")
            for index, item in enumerate(evidence):
                locator = item.get("locator") or {}
                out.append(f"ex:ev_{cid}_{index} a oc:Evidence ;")
                out.append(f"    oc:hasQuote {_lit(item.get('quote', ''))} ;")
                out.append(f"    oc:evidenceRole {_lit(item.get('role', 'supports'))} ;")
                if locator.get("section_path"):
                    out.append(f"    oc:hasLocator {_lit(' > '.join(locator['section_path']))} ;")
                if locator.get("url"):
                    out.append(f"    oc:hasSourceUrl {_lit(locator['url'])} ;")
                if locator.get("page"):
                    out.append(f"    oc:hasPage {int(locator['page'])} ;")
                out.append(f"    prov:wasDerivedFrom {doc_iri} .")
                out.append("")
            for other in claim.get("conflicts_with") or []:
                out.append(f"ex:claim_{cid} oc:conflictsWith ex:claim_{_iri(other)} .")
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
