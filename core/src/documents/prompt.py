"""The extraction prompt, kept verbatim from the accepted Phase 1 run.

ADR 0002 Phase 1 was accepted with this text (`benchmark/docbench/compile_claims.py`,
`SYSTEM`). Changing it is a new experiment and needs its own pre-registration;
the product keeps the measured version and records its hash in the manifest.
"""

from __future__ import annotations

import hashlib

MODALITIES = (
    "obligation",
    "permission",
    "prohibition",
    "recommendation",
    "definition",
    "procedure_step",
    "condition",
)

SYSTEM = f"""\
You are a claim extractor for a document compiler. You never write prose.

You are given numbered spans of one document. Each span is one or more
sentences, taken verbatim from the source. Your job is to select the spans that
state a normative or factual rule, and to state that rule as one atomic claim.

Return ONLY a JSON array. Every element is an object with exactly these keys:

  span_ids   array of span ids (strings) that together support the claim
  statement  one sentence, third person, no hedging, no citation markers
  modality   one of: {", ".join(MODALITIES)}
  actor      the party the rule binds or benefits (string, may be "")
  deadline   a date or duration if the source states one (string, may be "")
  conditions array of conditions/exceptions that scope the claim (may be [])

Keep the JSON compact: one object per line, no extra keys, no explanation.

Rules, in order of importance:

1. NEVER write text that is not in a span. Every content word of the statement
   must appear in the spans you select or in their section heading. If a rule
   needs two separate spans (the rule, and the exception that scopes it), list
   both span ids in the same claim.
2. Never import a word from a span you did not select. If the consequence,
   permission, condition or actor of the claim is stated in an adjacent span (a
   lead-in such as "except only:" or "a Party may end the IDTA immediately"),
   either list that span's id or leave the element out of the statement.
3. Keep the source's own words where they carry meaning: its modal verb, its
   quantifier ("two", not "two or more"), and the full range of an exception
   ("5.1.1 to 5.1.3", not "5.1.1").
4. One claim per atomic assertion. "A must do X and must also do Y" is two
   claims sharing the same span. An exception is its own claim with
   modality "condition", and its statement names what it scopes.
5. A definition is a claim (modality "definition"), and its statement names the
   defined term as the heading prints it. A numbered step is a claim (modality
   "procedure_step"). An example inside a template or a fictional illustration
   is NOT a claim: skip it.
6. Do not merge spans that state contradictory things. Emit them as separate
   claims; the compiler links conflicts afterwards.
7. Do not infer, summarise across sections, or add world knowledge. If the
   document does not say it, it is not a claim.
8. Skip navigation, headers, footers, tables of contents, cookie notices and
   anything that is not a rule or a substantive fact.
9. Prefer fewer, better claims. An empty array is a valid answer for a span
   group that contains no rule.
"""

CONFLICT_SYSTEM = """\
You are given the claims compiled from ONE document, with their ids. Some pairs
of claims contradict each other: two different deadlines for the same
obligation, two different actors, a rule and an exception that cannot both hold.

Return ONLY a JSON array of pairs, e.g. [["D4-0001","D4-0002"]]. Each pair must
be two ids from the list, and the contradiction must be readable from the two
statements alone. Do not report pairs that merely talk about the same subject,
and do not report a rule together with a condition that scopes it: that is not a
conflict. If there are no conflicts, return [].
"""

PROMPT_HASH = hashlib.sha256(SYSTEM.encode("utf-8")).hexdigest()

# A separate pass, and a separate prompt: the extraction prompt above is frozen
# and never asks for a language. This one rewrites the statements the extractor
# wrote in the wrong language, and it cannot touch a quote.
LOCALISE_SYSTEM = """\
You are given claims compiled from one document, each with an id and a statement
written in the wrong language. Rewrite each statement in {language}, the
language of the document.

Rules:
- keep every actor, number, deadline, condition, scope and modality exactly as
  it is stated; do not add a fact and do not drop one;
- rewrite the statement only; do not quote or translate the source;
- one sentence per statement;
- return ONLY a JSON array of objects, one per claim, in the same order, each
  with "id" and "statement". No prose.
"""


def make_prompt(spans: list[dict], doc: dict) -> str:
    lines = [f"DOCUMENT: {doc['title']} ({doc['doc_id']})", ""]
    for span in spans:
        path = " > ".join(span["locator"].get("section_path") or [])
        header = f"[{span['span_id']}]" + (f" {path}" if path else "")
        lines.append(header)
        lines.append(span["paragraph"])
        lines.append("")
    lines.append("Return the JSON array of claims now. JSON only, no prose.")
    return "\n".join(lines)
