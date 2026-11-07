#!/usr/bin/env python3
"""Build a minimal Turtle graph from DocBench claims.

The graph is intentionally small: documents, contexts, claims, evidence.
It is a proof that the annotation model is expressible in RDF, not the
final OntoSkills document profile.

Usage:
    python benchmark/docbench/build_ttl.py \
        --claims benchmark/docbench/gold/claims.jsonl \
        --out benchmark/docbench/runs/docbench.ttl
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent

PREFIXES = """\
@prefix oc: <https://ontoskills.sh/ontology#> .
@prefix ex: <https://ontoskills.sh/docbench/> .
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

DOC_TITLES = {
    "D1": "Commission Implementing Regulation (EU) 2026/1755",
    "D2": "Loyola University Artificial Intelligence Policy & Guidance (AY 26-27)",
    "D3": "OWASP Agentic Skills Top 10 Incident Response Playbook",
    "D4": "County of Greene RFP #2026-001 — Professional Engineering Services",
}


def lit(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def iri(value: str) -> str:
    return value.replace(" ", "_")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--claims", default=str(ROOT / "gold" / "claims.jsonl"))
    ap.add_argument("--out", default=str(ROOT / "runs" / "docbench.ttl"))
    args = ap.parse_args()

    claims = [json.loads(line) for line in Path(args.claims).read_text(encoding="utf-8").splitlines() if line.strip()]
    by_doc: dict[str, list[dict]] = defaultdict(list)
    for c in claims:
        by_doc[c["doc_id"]].append(c)

    out = [PREFIXES, TBOX]
    for doc, items in sorted(by_doc.items()):
        ctx = f"ex:ctx_{doc}"
        doc_iri = f"ex:doc_{doc}"
        first = items[0]["context"]
        out.append(f"{doc_iri} a oc:Document ;")
        out.append(f"    oc:hasTitle {lit(DOC_TITLES.get(doc, doc))} ;")
        out.append(f"    oc:hasVersion {lit(first.get('version', ''))} ;")
        out.append(f"    oc:hasDocType {lit(first.get('doc_type', ''))} ;")
        out.append(f"    oc:inContext {ctx} .")
        out.append("")
        out.append(f"{ctx} a oc:Context ;")
        out.append(f"    oc:hasSourceUrl {lit(items[0]['locator'].get('url', ''))} ;")
        if first.get("jurisdiction"):
            out.append(f"    oc:hasJurisdiction {lit(first['jurisdiction'])} ;")
        out.append(f"    oc:hasVersion {lit(first.get('version', ''))} .")
        out.append("")
        for c in items:
            cid = iri(c["claim_id"])
            ev = f"ex:ev_{cid}"
            out.append(f"ex:claim_{cid} a oc:Claim ;")
            out.append(f"    oc:inContext {ctx} ;")
            out.append(f"    oc:hasStatement {lit(c['statement'])} ;")
            out.append(f"    oc:hasModality {MODALITY[c['modality']]} ;")
            if c.get("actor"):
                out.append(f"    oc:hasActor {lit(c['actor'])} ;")
            if c.get("deadline"):
                out.append(f"    oc:hasDeadline {lit(c['deadline'])} ;")
            for cond in c.get("conditions", []) or []:
                out.append(f"    oc:hasCondition {lit(cond)} ;")
            out.append(f"    oc:hasLocator {lit(' > '.join(c['locator'].get('section_path', [])))} ;")
            if c["locator"].get("url"):
                out.append(f"    oc:hasSourceUrl {lit(c['locator']['url'])} ;")
            if c["locator"].get("page"):
                out.append(f"    oc:hasPage {c['locator']['page']} ;")
            out.append(f"    oc:hasConfidence {lit(str(c.get('confidence', 0.95)))} ;")
            out.append(f"    oc:hasEvidence {ev} ;")
            out.append(f"    prov:wasDerivedFrom {doc_iri} .")
            out.append("")
            out.append(f"{ev} a oc:Evidence ;")
            out.append(f"    oc:hasQuote {lit(c['quote'])} ;")
            out.append(f"    oc:hasLocator {lit(' > '.join(c['locator'].get('section_path', [])))} ;")
            if c["locator"].get("url"):
                out.append(f"    oc:hasSourceUrl {lit(c['locator']['url'])} ;")
            if c["locator"].get("page"):
                out.append(f"    oc:hasPage {c['locator']['page']} ;")
            out.append(f"    prov:wasDerivedFrom {doc_iri} .")
            out.append("")
            for other in c.get("conflicts_with", []) or []:
                out.append(f"ex:claim_{cid} oc:conflictsWith ex:claim_{iri(other)} .")
        out.append("")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
    print(f"wrote {len(claims)} claims to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
