# DocBench sources

Four documents selected for the pre-flight. They are all published in 2026 and cover four different claim types.

**Do not commit the source files.** Local copies live in `private/` (gitignored). This file records URLs, hashes and licences only.

| ID | Document | Published | Type | Working copy | SHA-256 |
|---|---|---|---|---|---|
| **D1** | Commission Implementing Regulation (EU) 2026/1755 — evaluations and proceedings under the AI Act | 2026-07-20 (in force 2026-08-10) | Regulation | `private/D1_ai_act_reader.html` (reader; official text on EUR-Lex) | `0b0202040e7cc238044e365a7ecb5a218c9fce2aa43dcecfe11b5fda71d580f1` |
| **D2** | Loyola University New Orleans — *University Artificial Intelligence Policy & Guidance*, AY 26-27 | 2026 | Institutional policy | `private/D2_loyola_ai_policy.pdf` (10 pages) | `af19d67315961f8d49cda2bd84267e46f803ae71dd4443fe31e1261fdacbdcf1` |
| **D3** | OWASP Agentic Skills Top 10 — *Incident Response Playbook* | 2026-03 (updated) | Operational procedure | `private/D3_owasp_ir.html` | `18b361fe60105594b582c36d39c0902b4955eebe32a0d69bb55ed3da55760616` |
| **D4** | County of Greene, Virginia — *RFP #2026-001, Professional Engineering Services* | 2026-01-22 | Procurement solicitation | `private/D4_greene_rfp_2026_001.pdf` (10 pages) | `a29f3f3f48a4f255573177f47778340b96370f2ebbee18bb83fed52791e81042` |

## Links

- D1 official text: https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=OJ:L_202601755
- D1 reader used for the working copy: https://artificialintelligenceact.eu/ai-act-explorer/proceedings/
- D2: https://academicaffairs.loyno.edu/sites/default/files/university_ai_policy_ay_26-27_0.pdf
- D3: https://owasp.github.io/www-project-agentic-skills-top-10/incident-response
- D4: https://greenecountyva.gov/DocumentCenter/View/1577

## Licences and reuse

- **D1**: EU reuse policy, Commission Decision 2011/833/EU. Attribution to the European Union required; do not imply endorsement.
- **D2**: Copyright Loyola University New Orleans. Research use only; do not redistribute the full text. Short quotes are used for evaluation.
- **D3**: CC BY-SA 4.0. Attribution and share-alike apply to redistributed derivatives. Short quotes are used for evaluation.
- **D4**: Public procurement record of Greene County, Virginia. Research use only; verify local reuse policy before redistribution.

## Why these documents

- D1 exercises obligations, deadlines, roles, conditions, prohibitions and procedural safeguards.
- D2 exercises permissions, prohibitions, exceptions, review cadence and institutional roles.
- D3 exercises procedure steps, severity levels, response times, escalation and notification duties.
- D4 exercises mandatory submission requirements, hard deadlines, evaluation criteria and contract terms.
- All four are recent enough to be a fair test against memorisation, and short enough to annotate by hand.

## The D4 conflict

D4 contains an inconsistency worth preserving: the cover states a closing date of **February 12, 2026, at 2 p.m.**, while section 6 says electronic submissions must arrive **no later than 2 p.m. on Thursday, January 22, 2026** (the issue date). A correct claim layer must surface both statements with their locators and mark the conflict, not silently pick one.

## Known limitation

No private internal document is included. D4 is a niche public document, which gives some protection against memorisation, but it is not the same as an unseen internal policy. Fairness is approximate; the result is a pipeline test, not a market test.
