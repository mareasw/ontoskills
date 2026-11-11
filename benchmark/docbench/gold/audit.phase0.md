# Phase 0 — the deterministic verifier against the accepted census

Artifact: `gold/probe.rows.g.compiled.verified.jsonl` (397 claims, D5 341 / D6 56)
and its spans `gold/probe.rows.g.compiled.jsonl.spans.jsonl`.
Census: `gold/probe.rows.g.verdicts.jsonl` (389 `ok` / 8 `weak`), produced by the
independent read recorded in `gold/audit.probe.rows.g.md`.
Tool: `benchmark/docbench/verify_deterministic.py` — six rules, no model, no
network. Cost: **$0**. Date: 2026-11-11.

`docs/adr/0002-evidence-first-extraction.md` blocks Phase 1 on one measurement:
the deterministic verifier must agree with the census on at least 95% of the
artifact. This is that measurement.

## Result in one line

**388/397 = 97.73% agreement**, above the 95% bar. The verifier emits 394 `ok`
and 3 `weak`, and **not one `no`** — so it rejects no claim the census accepts.
Its errors run the other way: it misses 7 of the 8 census `weak` rows and calls
2 census `ok` rows `weak`.

| Document | Claims | Agree | Agreement |
|---|---:|---:|---:|
| D5 — contract | 341 | 332 | 97.36% |
| D6 — table-as-content | 56 | 56 | 100% |
| **Pooled** | **397** | **388** | **97.73%** |

Confusion (deterministic → census):

| | census `ok` | census `weak` |
|---|---:|---:|
| verifier `ok` | 387 | 7 |
| verifier `weak` | 2 | 1 |
| verifier `no` | 0 | 0 |

The rate that matters for shipping is the last row: the verifier produced **0
`no`** on an artifact whose census contains 0 `no`. A deterministic gate that
rejects nothing correctly cannot lose a claim on its own.

## The rules, as run

| # | Check | Rule | Verdict |
|---|---|---|---|
| 1 | Verbatim | each quote is a substring of the normalised source | `no` |
| 2 | Locator | the locator resolves to a span and the quote is in that span | `no` |
| 3 | Page | the declared PDF page is a page the quote occurs on | `no` |
| 4 | Section | declared section path and the span's own path are prefix-compatible | `no` |
| 5 | Numbers | every number in the statement is in the evidence or section path | `no` |
| 6 | Attestation | more than 25% of the statement's content tokens are unattested by the evidence and the section path | `weak` |
| — | Modality | permission vs obligation mismatch | **note, not a verdict** |

Inflection is not counted as paraphrase: `date`/`dated`, `party`/`parties`,
`process`/`processed`, `override`/`overridden` match on a shared stem of four
characters. One-letter tokens are dropped (`Importer's` → `s`, `5.1(b)` → `b`):
they carry no claim.

## The one calibrated number, and why it is not a fudge

Attestation needs a tolerance because the census counts a restated predicate as
supported. A literal every-token rule scores **310/397 = 78.1%** (85 false
`weak`, 2 false `ok`): it calls `D5-0203` unsupported because the statement says
"apply" where the quote says "applies".

The 25% allowance is the point where both kinds of error stop moving: on the
artifact, statements the census accepts have at most **24%** unattested content
tokens, and the census `weak` rows it catches sit at **30%** and above. The bar
is deliberately placed in that empty band, not on a boundary.

It is still a number chosen on the artifact it is measured on. Two checks that
it is not fitted to a particular half:

| Subset | Agreement at 25% |
|---|---:|
| D5, even-indexed claims (171) | 167 = 97.66% |
| D5, odd-indexed claims (170) | 165 = 97.06% |
| D6 (56) | 56 = 100% |

## The nine disagreements, named

**Census `weak`, verifier `ok` (7).** One mechanism: the statement's operative
element sits in an unquoted lead-in or a sibling span, and the word itself is
attested elsewhere in the quote.

| Claim | Element outside the quotes |
|---|---|
| `D5-0039` | object of "provide": "Information Security policies (or equivalent)" |
| `D5-0072` | "may be updated" from the list lead-in "except only:" |
| `D5-0109` | qualifier dropped ("any Local Laws" vs "which may prevent or limit") |
| `D5-0264`, `D5-0265`, `D5-0267` | "a Party may end the IDTA immediately", the 30.1 lead-in |
| `D5-0288` | "are entitled to bring claims", the 33.1 lead-in quoted in `D5-0287` |

`D5-0266` is the only census `weak` the verifier catches: 3/10 content tokens
unattested (30%), over the 25% bar.

**Census `ok`, verifier `weak` (2).** `D5-0315` and `D5-0318` are glossary rows
("… has the meaning given in the UK GDPR") where the statement's copula and
"given" come from the entry format while the quote is only the definition body:
40% and 33% unattested. The census counts them `ok` under the locator rule, as
it does every glossary row of this shape.

## Modality was demoted by the measurement

The ADR listed "must/may in the statement is present in the evidence" as a
`weak` gate. Implemented literally it produced **16 false `weak`** on D6
dispositions, where the quote is imperative ("Destroy when 3 years old") or
passive ("longer retention is authorized"). Implemented as a class comparison
(permission vs obligation vs prohibition) it still produced 8 false `weak` and
caught **none** of the census's 8. It is kept as a `note` on 10 claims: visible
in the report, not a verdict. That is the same treatment ADR 0002 gives
contradictions until a precedence rule exists.

## What this does and does not license

- **It licenses the hard gate.** Verbatim, locator, page, section and numbers
  are exactly what `check_claims.py` already proves, and here they run per claim
  in milliseconds with a machine-readable reason. On this artifact they are
  clean: 0 `no`, 0 false rejections.
- **It does not license deleting the audit's judgement of `weak`.** The 7 misses
  are the class the LLM audit exists for: a lead-in one span away. Used alone,
  the verifier would report D5 support as 338/341 = 99.1% where the census says
  97.4%. Under-reporting a support defect ships the claim, so the damage is
  bounded — but it is a real blind spot, and it is the same blind spot that made
  `D5-0003` fail twice.
- **It sets the Phase 1 shape**: deterministic verifier as the hard gate for
  `no`, sampled LLM QA for `weak` (the ADR's 10% stratified sample), not the
  deterministic verifier alone deciding support.

## Limits

- One artifact, one census, one reader. The 95% bar is met on the artifact the
  ADR named; the demo corpus is the generalization test.
- The tolerance was calibrated on this artifact. The split halves and D6 are
  within-artifact controls, not an independent corpus.
- D6's 56/56 is a weak control: its census is 100% `ok`, so a verifier that
  never says `weak` also scores 100% there. It is reported because it is the
  holdout document, not because it proves the tolerance.
- The verifier reads the sources with `check_claims.SOURCES`; on a corpus where
  a source is missing it cannot check pages, and the run must say so.
