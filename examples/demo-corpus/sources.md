# Demo corpus — sources, licences, and why these documents

Fourteen public documents, five types, one purpose: prove that a compiled
knowledge base answers the same question from **more than one document**, with a
verbatim quote and a locator for every part of the answer.

The binaries are not committed. `./fetch.sh` downloads them and verifies every
SHA-256 against `manifest.json`.

| ID | Document | Type | Licence | Why it is here |
|---|---|---|---|---|
| **MSC_CORE** | Model Services Contract — Core Terms (E&W), v2.2A 2025 | contract | OGL v3.0 | Gold-tier government template; the contract the schedules attach to. |
| **MT_CORE** | The Mid-Tier Contract — Core Terms, v1.3A 2025 | contract | OGL v3.0 | Second contract family; same kinds of obligation, different wording. |
| **MT_SCH20** | The Mid-Tier Contract — Schedule 20 (Processing Data), v1.3 | schedule | OGL v3.0 | Breach notification in **48 hours**, sub-processing, retention. |
| **EU_SCC** | Commission Implementing Decision (EU) 2021/914 — SCCs | regulation | EU reuse | The clauses the UK schedules incorporate; transfer and deletion duties. |
| **GDPR** | Regulation (EU) 2016/679 | regulation | EU reuse | Breach notification in **72 hours** (Art. 33); storage limitation (Art. 5). |
| **EU_AI_ACT** | Regulation (EU) 2024/1689 — AI Act | regulation | EU reuse | Risk classification and timelines; a second regulatory voice. |
| **UK_AIPB** | AI Playbook for the UK Government | guidance | OGL v3.0 | Ten principles, lifecycle, assurance language. |
| **NIST_CSF** | NIST Cybersecurity Framework 2.0 | framework | public domain (US) | Govern/Identify/Protect/Detect/Respond/Recover. |
| **NIST_AIRMF** | NIST AI Risk Management Framework 1.0 | framework | public domain (US) | Risk functions and trustworthiness characteristics. |
| **TNA_CONTRACTS** | TNA retention scheduling 5 — Contractual records | guidance | OGL v3.0 | Six years after the end of the contract. |
| **TNA_ACCOUNTING** | TNA retention scheduling 3 — Accounting records | guidance | OGL v3.0 | Retention of financial records, including contract records. |
| **EU_TENDER_A5** | Annex A5 — draft framework contract for services | tender | EU reuse | Tender obligations: performance, payments, data protection, breach. |
| **UK_CYBER** | The Cyber Security Standard | standard | OGL v3.0 | Outcomes and the assurance process organisations must follow. |
| **NCSC_CLOUD** | Summary of the Cloud Security Principles (2014) | framework | OGL v3.0 | The fourteen principles as a table: principle, description, why it matters. |

## The demo questions

The exit criterion is structural, not a score: each question must return claims
from **at least two documents**, and the citations must name the document, the
page (where the format has pages), the section, and the source URL.

1. **How quickly must a personal-data breach be notified, and to whom?**
   MT_SCH20 (48 hours) vs GDPR (72 hours) vs EU_SCC / EU_TENDER_A5.
2. **How long may contractual records be kept?**
   TNA_CONTRACTS (six years after the end of the contract) vs TNA_ACCOUNTING vs
   GDPR storage limitation vs MT_SCH20 retention.
3. **What must a supplier do when it uses a sub-processor for personal data?**
   MT_SCH20 vs EU_SCC vs GDPR vs MSC_CORE.

The first two also exercise the deterministic tension report: two documents
state different numbers for the same topic, and the answer says so instead of
silently picking one.

## What is deliberately not in the corpus

- **The IDTA** (International Data Transfer Agreement) lives inside the
  consolidated Model Services Contract schedules. It is not redistributable
  without additional terms, so the schedules are excluded entirely rather than
  trimmed.
- **The consolidated MSC schedules** are also excluded because the only
  published format is DOCX and a page range would depend on a local
  LibreOffice conversion. A locator whose page number changes per machine is
  not a locator. DOCX documents that are ingested whole (MSC_CORE, MT_CORE,
  MT_SCH20) carry section paths and character offsets instead.
- **Private or client documents.** Nothing here is confidential; every entry has
  a public URL and a licence that permits reuse.
