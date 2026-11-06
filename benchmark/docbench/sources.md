# DocBench sources

Three documents selected for the pre-flight. They are all published in 2026 and cover three different claim types.

**Do not commit the source files.** Local copies live in `private/` (gitignored). This file records URLs, hashes and licences only.

| ID | Document | Published | Type | Working copy | SHA-256 |
|---|---|---|---|---|---|
| **D1** | Commission Implementing Regulation (EU) 2026/1755 — evaluations and proceedings under the AI Act | 2026-07-20 (in force 2026-08-10) | Regulation | `private/D1_ai_act_reader.html` (reader; official text on EUR-Lex) | `0b0202040e7cc238044e365a7ecb5a218c9fce2aa43dcecfe11b5fda71d580f1` |
| **D2** | Loyola University New Orleans — *University Artificial Intelligence Policy & Guidance*, AY 26-27 | 2026 | Institutional policy | `private/D2_loyola_ai_policy.pdf` (10 pages) | `af19d67315961f8d49cda2bd84267e46f803ae71dd4443fe31e1261fdacbdcf1` |
| **D3** | OWASP Agentic Skills Top 10 — *Incident Response Playbook* | 2026-03 (updated) | Operational procedure | `private/D3_owasp_ir.html` | `18b361fe60105594b582c36d39c0902b4955eebe32a0d69bb55ed3da55760616` |

## Links

- D1 official text: https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=OJ:L_202601755
- D1 reader used for the working copy: https://artificialintelligenceact.eu/ai-act-explorer/proceedings/
- D2: https://academicaffairs.loyno.edu/sites/default/files/university_ai_policy_ay_26-27_0.pdf
- D3: https://owasp.github.io/www-project-agentic-skills-top-10/incident-response

## Licences and reuse

- **D1**: EU reuse policy, Commission Decision 2011/833/EU. Attribution to the European Union required; do not imply endorsement.
- **D2**: Copyright Loyola University New Orleans. Research use only; do not redistribute the full text. Short quotes are used for evaluation.
- **D3**: CC BY-SA 4.0. Attribution and share-alike apply to redistributed derivatives. Short quotes are used for evaluation.

## Why these documents

- D1 exercises obligations, deadlines, roles, conditions, prohibitions and procedural safeguards.
- D2 exercises permissions, prohibitions, exceptions, review cadence and institutional roles.
- D3 exercises procedure steps, severity levels, response times, escalation and notification duties.
- All three are recent enough to be a fair test against memorisation, and short enough to annotate by hand.

## Missing

One real internal document from the target domain, anonymised and kept local. Public documents test the pipeline; a private document tests real-world fit and is not in any training set.
