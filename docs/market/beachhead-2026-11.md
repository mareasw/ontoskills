# Beachhead investigation — where the first five buyers come from

Status: internal working memo, pre-decision.
Date: 2026-11-10. Author: tech lead.
Question it answers: with no warm introductions and no sales team, which market
do we attack first, and how do we get from zero contacts to five qualified
conversations in 30 days?

Every figure below is public and dated; sources are listed at the end. Numbers
about our own product come from `benchmark/docbench/` and are cited there.
Where this memo makes an assumption, it says so.

## 1. The short version

**Do not enter "AI contract review".** That door is owned by Spellbook at
$99–199 per user per month, LegalOn at roughly $8k per user per year, Luminance
and Ironclad in the five to six figures, and Harvey at the top. A better
citation engine does not beat a Word add-in with distribution.

**Enter compliance evidence, sold through the consultants who already sell it.**
The buyer is not the general counsel; it is the DPO, the privacy consultancy and
the compliance firm that must produce documented evidence for GDPR
accountability, NIS2 supervision and AI-vendor contracts — with NIS2 deadlines
running now and AI Act documentation on a 2027 clock. They bill hours to
assemble evidence packs from contracts and policies. Our product turns that
assembly into a verified, citable claim set in minutes.

The beachhead, in one line:

> **Supplier-contract evidence packs for Italian mid-market companies, sold
> through DPO and compliance consultancies, starting with NIS2 supply-chain
> clauses, GDPR Article 28 agreements and AI-vendor contracts.**

This is still "contracts with obligations and evidence" — the thing the bench
actually measures — but with a buyer who has a legal deadline, a budget line and
a channel that reaches hundreds of companies without a sales team.

**This is the GTM entry point, not the definition of the product.** The product
is the enterprise knowledge base of ADR 0002: every document compiled into
claims with verbatim evidence and queried with a citation for every answer. The
evidence pack is the first **view** sold on top of it, chosen because it has a
buyer with a clock, a budget and a distribution channel. The document type is
narrow on purpose for the first five pilots; the pipeline, the schema and the
graph are the same ones that later ingest policies, board minutes, tenders and
internal procedures. Selling the view first is how the knowledge base gets its
first real corpus; it is not a retreat from the knowledge base.

## 2. What the data says

| Evidence | Number | What it means for us | Source, date |
|---|---|---|---|
| In-house teams using or evaluating AI for contract review | 52% | The category is mainstream; we do not need to educate the market on "AI for contracts" | LegalOn / In-House Connect, n=452, 2026 |
| Teams saying AI would help contract review | 87% | Demand is broad, and therefore undifferentiated | same |
| Time to review one contract | 3.1 hours average | The unit of pain is the contract, not the seat | same |
| Teams where the cost of human verification outweighs the benefit | 67% | The pain we actually solve: verification, not generation | Morae / Coleman Parkes, n=850, 2026 |
| Senior legal professionals who fully or mostly trust AI output | 33% | Trust is the binding constraint, not capability | same |
| Professionals citing hallucination / poor accuracy as a top constraint | 48% | Citation accuracy is the buying criterion | same |
| Confidence in legal AI output (any tool, own users) | 4–18% "very confident" | No incumbent has solved trust; the field is open on this axis | Law Insider, n=534, 2026 |
| Top factors that build trust | clear citations, confidentiality, trusted sources | Exactly the artifact we produce | Thomson Reuters Legal Tech Pulse, n>250, 2026 |
| Respondents "completely confident" in vendor security | 3% | Security is a gate, and a differentiator for a local/on-prem option | same |
| AI contract review price, mid-market | $6k–30k/yr | Willingness to pay exists at the consultancy and mid-market level | Spellbook pricing page, Oct 2026 |
| AI contract review price, enterprise | $30k–250k+/yr | Not our first market | same |

The strategic reading: the market has spent three years buying generation and is
now stuck paying for verification. That is the wedge. "Every claim has a quote,
a page and a section, and a machine checks it" is not a feature in this market;
it is the purchase criterion.

## 3. Why compliance evidence and not contract review

Three candidate markets, scored on what we can win with the artifact we have:

| Market | Urgency | Budget | Reach without a sales team | Fit with our artifact | Competition | Total |
|---|---|---|---|---|---|---|
| AI contract review (law firms, in-house) | 3 | 5 | 2 | 3 | 1 | **14** |
| Compliance evidence via consultancies | 5 | 4 | 4 | 5 | 3 | **21** |
| Legal research / case law | 2 | 4 | 2 | 2 | 1 | **11** |

Scores 1–5, higher is better; "competition" is scored inversely (5 = open).
This is a judgement, not a measurement; the falsification test is in §9.

Compliance evidence wins for four reasons:

1. **The output is the product.** A consultant sells a document that must
   survive an inspection. "Here is the clause, here is the page, here is the
   article it satisfies" is the deliverable, not a chat answer.
2. **The buyer has a clock.** NIS2 subjects first listed in 2025 close their
   18-month window for the base security measures between late 2026 and early
   2027; subjects first listed in 2026 have until 31 July 2027, with the CSIRT
   contact due by the end of 2026. The AI Act has applied since 2 August 2026
   for transparency and general-purpose models; the Digital Omnibus
   (Regulation (EU) 2026/1744) moved the high-risk obligations to 2 December
   2027 (Annex III) and 2 August 2028 (Annex I), and added two prohibitions from
   2 December 2026, with documentation retained for ten years. GDPR
   accountability has no deadline because it is continuous. NIS2 is the near
   clock; the AI Act is the 2027 pipeline that makes the evidence design
   reusable.
3. **The channel is ready-made.** Federprivacy reports more than 10,000
   participants across eleven editions of its Privacy Day Forum, and ASSO DPO is
   the other Italian reference association for privacy professionals. The
   consultancies already sell "audit readiness" and "evidence" projects. We sell
   them a faster way to produce the thing they already invoice.
4. **Our measured strength is exactly the need.** The bench's claim set is
   obligations, permissions, definitions and conditions with verbatim quotes —
   which is what a supplier contract clause inventory is.

Why not law firms first: they are the hardest buyers to reach without a
reputation, they are trained to distrust black boxes, and the incumbents already
own their Word workflow. A consultancy that bills by the hour for evidence
assembly has the opposite incentive: it wants the assembly to take less time.

## 4. The offer

**"Evidence pack in 48 hours."** Input: a folder of supplier contracts, DPAs and
AI-vendor agreements. Output:

- a clause inventory (data protection, security, audit rights, sub-processors,
  breach notification, AI use, liability) with quote, page and section for each
  clause;
- a gap report mapped to the relevant article (GDPR 28, NIS2 supply-chain
  measures, AI Act documentation where applicable);
- an exportable pack (CSV/JSON + PDF) that the consultant can attach to the
  client's file.

Pricing hypothesis to validate, not a decision:

| Model | Price | Basis |
|---|---|---|
| Pilot | €3,000–5,000 for up to 30 contracts | One engagement, one client, 2 weeks |
| Consultancy subscription | €800–1,500/month | Unlimited documents for one consultancy, fair use |
| Per-contract | €5–15 per contract above the fair-use cap | Scales with the consultancy's book |

The economic argument to the consultant: 30 contracts at 30 minutes each is
15 hours; at €80–150/hour that is €1,200–2,250 of billable time, and it is the
work nobody wants. If the pack costs €3–5k and takes a day, the consultant
either resells it at margin or keeps the hours for advisory work. That argument
must be tested with real numbers in the first five calls, not assumed.

Unit economics target (from the ADR): ≤ $0.05 of model cost per 60-page
document. At €5–15 per contract the gross margin is not the constraint; trust
and distribution are.

## 5. The five names, without a network

The funnel to run in 30 days: **30 contacted → 10 replies → 5 calls → 3 pilot
proposals → 1 paid pilot.** Thirty is reachable by hand; the other numbers are
the test.

### Channel 1 — the associations (highest density)

Federprivacy and ASSO DPO are the two Italian reference associations for privacy
professionals. Both publish events and training calendars that are effectively a
list of active consultancies:

- Federprivacy webinars, November–December 2026: "Audit, monitoraggio e
  accountability del DPO nei sistemi di IA" (27 Nov), "Il DPO come consulente
  strategico per la governance dell'IA" (11 Dec). Registration is online and
  open; attendees are exactly the ICP.
- ASSO DPO: 12th international congress, 28–29 September 2026 (already past;
  the 2027 edition is the next one). The association's member base and
  scientific committee are the target list.
- The Privacy Day Forum has moved to 31 March 2027, Arezzo. Book it now as the
  one event where five conversations can happen in a day.

Action: attend two online events in the next 30 days, ask one substantive
question each time in the Q&A, and follow up with the speaker and the three most
active participants. No pitching in the room; the follow-up is a 20-minute
conversation about their evidence workflow.

### Channel 2 — LinkedIn, with exact strings

Search people, not companies; filter Italy, company size 2–50:

```
("DPO esterno" OR "Data Protection Officer" OR "consulente privacy"
 OR "privacy officer") AND (NIS2 OR "AI Act" OR GDPR OR accountability)
```

```
("consulenza privacy" OR "compliance privacy") AND (NIS2 OR "regolamento")
```

Then the firm's page: look for "audit", "accountability", "NIS2", "DPO esterno"
in the services. A firm that already sells evidence projects is a buyer, not a
prospect to educate.

### Channel 3 — public procurement

Whoever won a public tender for privacy or NIS2 support is a consultancy with a
public-sector client base and a delivery deadline. Search TED
(`ted.europa.eu`) and the Italian public marketplace for:

```
"servizi di consulenza" "protezione dei dati" Italia
"supporto DPO" OR "adeguamento NIS2" OR "gap analysis privacy"
```

The winners are listed. Their names go into the same 30-contact list. This also
produces a warm opener: "ho visto che avete vinto il supporto NIS2 per X; come
state producendo l'evidenza documentale sui contratti fornitori?"

### Channel 4 — the adjacent vendors

System integrators and ISO 27001 auditors sell the same client the same
compliance project. They do not want to build extraction; they want a component.
Two conversations here can produce referrals faster than thirty cold emails.
Look for "consulenza ISO 27001", "audit di seconda parte", "NIS2" in the same
LinkedIn search.

### The outreach message (Italian, short)

> Buongiorno [nome], sto costruendo uno strumento che estrae da contratti e
> policy le clausole rilevanti per la compliance (GDPR art. 28, NIS2 catena di
> fornitura, AI Act) e produce un pacchetto di evidenze con citazione, pagina e
> sezione verificabili. Non è un chatbot: ogni affermazione ha la sua fonte
> controllabile. Sto cercando 5 consulenti privacy/NIS2 per una prova su 20–30
> contratti reali, senza costo, in cambio di un parere onesto sul flusso di
> lavoro. Ha 20 minuti questa settimana o la prossima?

The ask is a conversation plus a free pilot on their documents (with a data
processing agreement). The free pilot is the price of market access; the paid
pilot comes after the value is visible.

## 6. Questions for the call

Do not demo first. Ask, in this order:

1. How do you assemble the evidence pack today, and how many hours does it take
   per client?
2. Which documents are the bottleneck: supplier contracts, DPAs, policies,
   AI-vendor agreements?
3. What does the auditor or the client actually ask to see?
4. What would make you refuse to use an extraction tool on client documents?
5. Who signs off on a €3–5k engagement, and what is the budget cycle?
6. Can we run the pilot on 20–30 redacted contracts next month?

The answers either confirm the wedge or falsify it. Record them verbatim; five
calls are enough to see the pattern.

## 7. 30/60/90

| Window | Goal | Measure | Kill criterion |
|---|---|---|---|
| 30 days | 30 contacts, 5 calls, 3 pilot proposals | Calls booked and held | Fewer than 3 calls: the message or the list is wrong, not the product |
| 60 days | 1 paid pilot or 2 free pilots with a signed DPA | Signed pilot, real documents processed | No pilot: change channel (integrators, auditors) before changing product |
| 90 days | Pilot produces a pack a consultant would attach to a client file | Consultant uses the output in a real engagement | Output not used: the product is a demo, not a tool |

## 8. Risks and what would change the plan

- **Channel conflict.** A consultancy may see us as a competitor that disintermediates
  them. Mitigation: sell a tool that makes their hours more valuable, never a
  service to their clients; white-label the output.
- **Confidentiality.** Client contracts are sensitive. Mitigation: local or
  private deployment, no training on customer data, DPA ready before the first
  pilot, deletion SLA. This is also a selling point against US cloud tools.
- **Price sensitivity.** Italian mid-market pays less than US legal. The pilot
  price may need to be €1.5–3k. Validate in the first three calls, do not
  discount before hearing a number.
- **Generalisation.** The bench has two documents. A pilot on 30 real contracts
  is also the generalisation test; if support collapses, the product claim
  collapses with it, and we must know before selling.
- **Regulatory drift.** NIS2 and AI Act guidance is still moving. The product
  must cite the article, not interpret it; the consultant owns the legal
  judgement. Say this explicitly, in writing.

## 9. What would falsify this memo

- Fewer than 3 of 10 consultancies say evidence assembly is a recurring,
  time-consuming pain.
- They already have a tool they are happy with (unlikely, but ask).
- They refuse to put client documents into any external tool, even privately
  deployed (then the buyer is the enterprise itself, with a longer cycle).
- The pilot shows support below 90% on real contracts, or a fabrication rate
  above zero. Then the honest move is to stop selling and fix the pipeline.

## 10. What I need from you

1. **Approve the beachhead**: compliance evidence via DPO/NIS2 consultancies,
   starting in Italy, with contracts as the document type. If you prefer law
   firms or procurement, say so now; the list-building changes.
2. **Two hours a week** for events and calls. I can build the list and the
   messages; a founder-level conversation closes faster than an agent's email.
3. **Billing entity and a pilot contract template** before the first paid
   engagement. No legal entity, no pilot.

You do not need to produce five names. The list comes from the four channels
above; the founder time is what turns a list into conversations.

## Sources

All checked 2026-11-10.

| Claim | Source |
|---|---|
| Contract review price tiers, mid-market and enterprise | Spellbook, *AI Contract Review Software Pricing*, 2026-10-25; Gavel, *17 Tools Compared*, 2026-10-30 |
| Harvey / Spellbook / LegalOn / Luminance positioning and price | Deepak Gupta, *Top 5 AI Legal and Contract Tools 2026*, 2026-08-16 |
| 52% using/evaluating, 87% benefit, 3.1 hours per contract | LegalOn & In-House Connect, *2026 State of AI for In-House Legal*, n=452, 2026 |
| 67% verification cost, 33% trust, 48% hallucination | Morae / Coleman Parkes, *The Intelligence Gap*, n=850, 2026 |
| Citation as top trust factor, 3% completely confident in security | Thomson Reuters, *Legal Tech Pulse 2026*, n>250, 2026 |
| 86% weekly AI use, 4–18% very confident per tool | Law Insider, *2026 AI Adoption Study*, n=534, 2026-09-02 |
| NIS2 deadlines, registration, evidence categories | ACN, *La normativa* and FAQ *Misure di sicurezza*, 2025–2026; ACN Determina 379907/2025 and 127434/2026 |
| NIS2 supply-chain contract requirements | ACN FAQ MSB.12–MSB.13 |
| AI Act application dates, high-risk deferral and 10-year documentation retention | Regulation (EU) 2026/1744 (Digital Omnibus on AI), in force 2026-07-27; EU AI Act Service Desk, Article 18; European Commission, *AI Act* policy page, 2026 |
| GDPR accountability and Article 28 audit rights | GDPR Articles 5(2), 28(3)(h) |
| Federprivacy events and Privacy Day Forum date | Federprivacy, agenda and *Privacy Day Forum rinviato al 31 marzo 2027*, 2026-08-24 |
| ASSO DPO congress and association scope | assodpo.it, 2026 |
