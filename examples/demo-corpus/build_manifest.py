#!/usr/bin/env python3
"""Build ``manifest.json`` for the demo corpus from the documents on disk.

The manifest is the corpus's provenance, not a convenience index: every entry
records where the bytes came from, the licence that allows the demo to ship the
*compiled claims*, the SHA-256 of the exact file that was ingested, and the page
range when only part of a document is used. A downloaded file whose hash differs
from the manifest is a different document and ``ingest`` refuses it.

Usage:
    python examples/demo-corpus/build_manifest.py
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DOCUMENTS = HERE / "documents"

OGL = "OGL v3.0 (Crown copyright)"
EU_REUSE = "European Union reuse (Decision 2011/833/EU)"
PUBLIC_DOMAIN = "US Government work, public domain"

# doc_id, file, title, url, licence, version, jurisdiction, doc_type, notes
ROWS = [
    (
        "MSC_CORE",
        "msc-core-terms.docx",
        "Model Services Contract — Core Terms (England & Wales)",
        "https://www.gov.uk/government/publications/the-model-services-contract-core-terms-england-wales",
        OGL,
        "v2.2A (2025)",
        "UK-E&W",
        "contract",
        "Gold-tier government template. DOCX is the published format; no PDF is offered.",
    ),
    (
        "MT_CORE",
        "midtier-core-terms.docx",
        "The Mid-Tier Contract — Core Terms",
        "https://www.gov.uk/government/publications/the-mid-tier-contract-core-terms",
        OGL,
        "v1.3A (2025)",
        "UK",
        "contract",
        "Template for medium-value, non-complex services.",
    ),
    (
        "MT_SCH20",
        "midtier-schedule20.docx",
        "The Mid-Tier Contract — Schedule 20 (Processing Data)",
        "https://www.gov.uk/government/publications/the-mid-tier-contract-schedule-20-processing-data",
        OGL,
        "v1.3 (2025)",
        "UK",
        "schedule",
        "The data-protection schedule: breach notification, sub-processing, retention.",
    ),
    (
        "EU_SCC",
        "eu-scc-2021-914.pdf",
        "Commission Implementing Decision (EU) 2021/914 — standard contractual clauses",
        "https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:32021D0914",
        EU_REUSE,
        "2021",
        "EU",
        "regulation",
        "The SCCs the UK schedules incorporate by reference.",
    ),
    (
        "GDPR",
        "eu-gdpr-2016-679.pdf",
        "Regulation (EU) 2016/679 — General Data Protection Regulation",
        "https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:32016R0679",
        EU_REUSE,
        "2016",
        "EU",
        "regulation",
        "Art. 33: notification within 72 hours; Art. 5 storage limitation.",
    ),
    (
        "EU_AI_ACT",
        "eu-ai-act-2024-1689.pdf",
        "Regulation (EU) 2024/1689 — Artificial Intelligence Act",
        "https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:32024R1689",
        EU_REUSE,
        "2024",
        "EU",
        "regulation",
        "Risk classes, obligations, timelines.",
    ),
    (
        "UK_AIPB",
        "uk-ai-playbook.pdf",
        "Artificial Intelligence Playbook for the UK Government",
        "https://www.gov.uk/government/publications/ai-playbook-for-the-uk-government",
        OGL,
        "2025",
        "UK",
        "guidance",
        "Ten principles and a lifecycle for government AI use.",
    ),
    (
        "NIST_CSF",
        "nist-csf-2.0.pdf",
        "The NIST Cybersecurity Framework (CSF) 2.0",
        "https://nvlpubs.nist.gov/nistpubs/CSWP/NIST.CSWP.29.pdf",
        PUBLIC_DOMAIN,
        "2.0 (2024)",
        "US",
        "framework",
        "Govern, Identify, Protect, Detect, Respond, Recover.",
    ),
    (
        "NIST_AIRMF",
        "nist-ai-rmf-1.0.pdf",
        "Artificial Intelligence Risk Management Framework (AI RMF 1.0)",
        "https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf",
        PUBLIC_DOMAIN,
        "1.0 (2023)",
        "US",
        "framework",
        "Risk management functions and trustworthiness characteristics.",
    ),
    (
        "TNA_CONTRACTS",
        "tna-contractual-records.pdf",
        "Records Management retention scheduling 5 — Contractual records",
        "https://cdn.nationalarchives.gov.uk/documents/information-management/sched_contractual.pdf",
        OGL,
        "2012",
        "UK",
        "guidance",
        "Six years after the end of the contract; the Limitation Act 1980.",
    ),
    (
        "TNA_ACCOUNTING",
        "tna-accounting-records.pdf",
        "Records Management retention scheduling 3 — Accounting records",
        "https://cdn.nationalarchives.gov.uk/documents/information-management/sched_accounting.pdf",
        OGL,
        "2012",
        "UK",
        "guidance",
        "Financial records retention, including records of contracts.",
    ),
    (
        "EU_TENDER_A5",
        "eu-tender-annex-a5.pdf",
        "Annex A5 to the invitation to tender — draft framework contract for services",
        "https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/tender-details/docs/5a2ed580-8348-4114-8e72-ca458ac08eb0-CN/EC-HOME-2025-OP-0009_Annex%20A5_Draft%20FWC%20services_V1.pdf",
        EU_REUSE,
        "2025",
        "EU",
        "tender",
        "Tender annex: performance, payments, data protection, breach.",
    ),
    (
        "UK_CYBER",
        "uk-cyber-security-standard.html",
        "The Cyber Security Standard",
        "https://www.security.gov.uk/policy-and-guidance/the-cyber-security-standard/",
        OGL,
        "2025",
        "UK",
        "standard",
        "Outcomes and assurance process for government organisations.",
    ),
    (
        "NCSC_CLOUD",
        "ncsc-cloud-security-principles-summary.pdf",
        "Summary of the Cloud Security Principles",
        "https://www.gov.uk/government/publications/cloud-security-principles-summary",
        OGL,
        "2014",
        "UK",
        "framework",
        "The fourteen principles as a table: principle, description, why it matters.",
    ),
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    import sys

    verify_only = "--verify" in sys.argv[1:]
    if verify_only:
        manifest = json.loads((HERE / "manifest.json").read_text(encoding="utf-8"))
        bad, missing = [], []
        for entry in manifest.get("documents", []):
            path = HERE / entry["path"]
            if not path.exists():
                missing.append(entry["path"])
            elif sha256(path) != entry["sha256"]:
                bad.append(entry["path"])
        if missing:
            print("missing:", ", ".join(missing))
        if bad:
            print("hash mismatch:", ", ".join(bad))
        if missing or bad:
            return 1
        print(f"verified {len(manifest.get('documents', []))} documents")
        return 0

    entries = []
    missing = []
    for doc_id, name, title, url, licence, version, jurisdiction, doc_type, notes in ROWS:
        path = DOCUMENTS / name
        if not path.exists():
            missing.append(name)
            continue
        kind = {
            ".pdf": "pdf",
            ".docx": "docx",
            ".html": "html",
        }[path.suffix.lower()]
        entries.append(
            {
                "doc_id": doc_id,
                "path": f"documents/{name}",
                "title": title,
                "kind": kind,
                "url": url,
                "licence": licence,
                "version": version,
                "jurisdiction": jurisdiction,
                "doc_type": doc_type,
                "sha256": sha256(path),
                "notes": notes,
            }
        )
    if missing:
        print("missing documents:", ", ".join(missing))
        print("run ./fetch.sh first")
        return 1
    manifest = {
        "name": "OntoSkills demo corpus",
        "description": (
            "Fourteen public documents across contracts, schedules, regulation, "
            "guidance and a tender, chosen so the same question is answered by "
            "more than one of them."
        ),
        "documents": entries,
    }
    (HERE / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"wrote manifest.json with {len(entries)} documents")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
