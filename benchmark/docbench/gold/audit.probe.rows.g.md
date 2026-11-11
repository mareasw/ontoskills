# Evidence-support audit — §10.7(g) drop/rewrite guard and its paid run

Artifact: `benchmark/docbench/gold/probe.rows.g.compiled.verified.jsonl` (gitignored).
Produced by: `benchmark/docbench/compile_claims.py --verify` over D5 and D6 on
2026-11-11, with the row-claim rule of §10.7(f) and the drop/rewrite guard of
§10.7(g) as amended by §10.7(g)(ii). The earlier runs and their censuses stay
untouched in `gold/probe.compiled.verified.jsonl` / `gold/audit.probe.md`,
`gold/probe.fixed.compiled.verified.jsonl` / `gold/audit.probe.fixed.md`,
`gold/probe.kv.compiled.verified.jsonl` / `gold/audit.probe.kv.md` and
`gold/probe.rows.compiled.verified.jsonl` / `gold/audit.probe.rows.md`; the
replay artifact stays in `gold/probe.rows.compiled.jsonl.replay-10.7g/`.
Date: 2026-11-11. Model: `deepseek-v4.1-flash`.

This is the independent census required by §10.4 and promised by §10.7(g), not
the verifier's own audit. The worksheet (one block per claim, with every quote,
page and section path) was read end to end: **316 new rows, no sample**, plus
the **81 rows whose claim is byte-identical to a claim already censused in the
§10.7(f) run** (document, statement and quote set all equal), which keep their
recorded verdicts. Verdicts are in `gold/probe.rows.g.verdicts.jsonl` (397 rows,
gitignored with the corpus).

## Result in one line

**Accepted by §10.7(g).** D5 support is 97.7% (333/341) with **0 facts absent**
and **10/10 recall**, including all three named claims: `D5-0002` is recalled by
the name and address rows, `D5-0003` by the primary-place claim **and** the
governing-law claim, `D5-0004` by the two status rows. D6 is 56/56 with 10/10
recall and 0 misattributed authorities. The guard fired where it was built to:
the verifier tried to drop `D5-0006` (the primary-place claim) and was refused.

| Document | Structural | Support (census) | Facts absent from source | Recall | Verdict |
|---|---|---|---|---|---|
| D5 — contract | pass | 333/341 = **97.7%** | **0** | 10/10 = **100%** | **pass** |
| D6 — table-as-content | pass | 56/56 = **100%** | 0 | 10/10 = 100% | **pass** |

Support split as §10.7(f) requires:

| | Claims | `ok` | Support |
|---|---:|---:|---:|
| D5, model | 339 | 331 | 97.6% |
| D5, rule | 2 | 2 | 100% |
| D6, model | 56 | 56 | 100% |
| D6, rule | 0 | — | — |
| **Pooled** | **397** | **389** | **98.0%** |

The rule contributed two claims, both in D5: `D5-0362` (main address row) and
`D5-0363` (transferred-data row), recognised by shape — the statement is the
normalised row cell `label: value` and the single evidence quote is the whole
span paragraph. The other five row cells were extracted by the model.

## Artifact and pipeline

| Stage | Result |
|---|---|
| Spans | 359 (D5 324, D6 35); 28 extraction chunks, 15 spans each, overlap 2 |
| Raw compile | 402 claims (D5 345, D6 57); 18 near-duplicates merged, 5 rejected, 9 truncated retries, 7 conflict pairs, 2 rule claims |
| Verify | 402 rows: 290 `ok` / 111 `weak` / 1 `no` / 0 `fabricated` initially; two repair rounds; 0 dropped, 5 near-duplicates merged, 1 `reevidence` rejected by the section guard (`D5-0340`) |
| Guard | 4 `drop` attempts refused (`D5-0006`, `D5-0039`, `D5-0339` in round 1; `D5-0288` in round 2), 5 `rewrite` attempts refused for deleting a defined headword (`D5-0009`, `D5-0343`, `D5-0344`, `D5-0346`, `D5-0347`) |
| Final | **397 claims** (D5 341, D6 56), **534 evidence spans**, schema v2, `check_claims.py` **0 failures** |
| Verify residual | 378 `ok` / 19 `weak` / 0 `no` / 0 `fabricated` (95.21% pooled) |

Structural validity is 100% by the gate's definition: `check_claims.py` validates
every claim against the v2 schema, requires each quote to exist verbatim in the
whitespace-normalised source, and re-derives each declared PDF page. It reports
397 claims, 534 spans, 0 failures. D1–D4 and D6 segment byte-identically to the
baseline (154/50/115/101 and 35 spans); D5 segments to 324 spans.

## The eight `weak` rows

They are kept and listed, not hidden.

| Claim | Where the statement goes beyond its quotes |
|---|---|
| `D5-0039` | Object of "provide" missing: the quotes stop at "able to provide institutional" and resume at "this, if requested". "Information Security policies (or equivalent) confirming that it meets the terms" is only in the section path. |
| `D5-0072` | Permission not in the quote: the quoted clause is the purpose "to update the IDTA … if the Parties want to". "May be updated" comes from the unquoted list lead-in "except only:". |
| `D5-0264` | Consequence not in the quote: "a Party may end the IDTA immediately" is the 30.1 lead-in, unquoted; the quote gives only the 30.1.1 limb. |
| `D5-0265` | Framing "immediate ending for a breach applies where" comes from 30.1, unquoted; the quote is only condition 30.1.1.1. |
| `D5-0266` | Same, for condition 30.1.1.2. |
| `D5-0267` | Same, for condition 30.1.2. |
| `D5-0288` | Operative entitlement ("Relevant Data Subjects are entitled to bring claims") is the 33.1 lead-in, quoted in the sibling `D5-0287` and not here; this claim's quotes are the section list alone. The verifier flags the same row. |
| `D5-0109` | Reused verdict from the §10.7(f) census: qualifier dropped. The source limits the Local Laws to those "which may prevent or limit the Importer complying", the statement generalises to "any Local Laws". |

The `D5-0264`–`D5-0267` family is one mechanism, not four: the model splits
clause 30.1 into its four grounds and quotes the ground without the parent
sentence that supplies "may end this IDTA immediately". It is the same defect
the §10.7(f) census recorded on the old `D5-0067`/`D5-0069` (permission taken
from an unquoted lead-in) and is reported as such.

## Named claims of §10.7(g)

| Named claim | Recalled by | Result |
|---|---|---|
| `D5-0002` — exporter name **and** Beacon House address | `D5-0004` (full legal name) + `D5-0362` (main address) | **pass** |
| `D5-0003` — governing law **and** primary place for legal claims | `D5-0097` (governing law) + `D5-0006` (primary place) | **pass** |
| `D5-0004` — both Exporter and Importer are Controllers | `D5-0007` + `D5-0010` | **pass** |

`D5-0006` is the claim the §10.7(g) guard exists for, and this time the guard
fired. In round 1 the verifier audited it `weak` and issued a `drop`; the guard
refused with "verdict weak, evidence verbatim in its own section"
(`report.json` → `rounds[0].guard_rejected_drops`). The census counts the row
`ok` under the pre-registered rule: the evidence is the value cell "England and
Wales" plus the locator whose section path is "Primary place for legal claims to
be made by the Parties", and the locator is part of the evidence (§10.4). That
is the mechanism §10.7(g) wrote down, not a threshold moved after the score: it
was pre-registered, replayed at zero cost, and the claim's fate in this run was
decided by the guard before the census began.

## D5 recall — 10/10 = 100%

| Gold claim | Recalled by | Note |
|---|---|---|
| `D5-0001` | `D5-0048` | four parts of the IDTA |
| `D5-0002` | `D5-0004` + `D5-0362` | name and address, as the pre-registration allows |
| `D5-0003` | `D5-0097` + `D5-0006` | governing law, and the primary place survived the drop |
| `D5-0004` | `D5-0007` + `D5-0010` | Exporter and Importer status |
| `D5-0005` | `D5-0008` | UK GDPR does not apply |
| `D5-0006` | `D5-0014` (+ `D5-0015`) | cannot end before the Term |
| `D5-0007` | `D5-0019` | forward only to co-applicants with a DAA |
| `D5-0008` | `D5-0067` (+ `D5-0069`) | Mandatory Clauses; the exception is narrowed to 5.1.1 — recorded as a defect, not a miss |
| `D5-0009` | `D5-0176` | Importer remains fully liable |
| `D5-0010` | `D5-0258` + `D5-0259` + `D5-0260` + `D5-0261` | four ways the IDTA ends |

## D6 — 10/10, 100% support, 0 misattributed authorities

| Gold claim | Recalled by |
|---|---|
| `D6-0001` | `D6-0011` |
| `D6-0002` | `D6-0012` |
| `D6-0003` | `D6-0014` |
| `D6-0004` | `D6-0028` |
| `D6-0005` | `D6-0029` |
| `D6-0006` | `D6-0034` |
| `D6-0007` | `D6-0042` |
| `D6-0008` | `D6-0048` |
| `D6-0009` | `D6-0038` |
| `D6-0010` | `D6-0054` |

Every disposition authority quoted by a D6 claim was checked against the item
that owns it in the source (the 14 item headers of `private/D6.txt`, full
strings because items 010 and 090 share the eight digits `00030001`): **30
attributions, 30 correct, 0 misattributed**.

## Verifier audit vs independent census

| | Count |
|---|---:|
| Rows where both call `weak` | 2 (`D5-0039`, `D5-0288`) |
| Verifier `weak`, census `ok` | 17 |
| Census `weak`, verifier `ok` | 6 |
| Verifier `weak` total | 19 (95.21% pooled) |
| Census `weak` total | 8 (97.98% pooled) |

The 17 verifier-only weak rows are the known class: the verifier is quote-only,
so a statement whose subject is the row label or glossary headword is `weak` to
it even when the locator supplies the term. Eleven of them are glossary rows
(`D5-0009`, `D5-0343`, `D5-0344`, `D5-0346`, `D5-0347`, `D5-0348`, `D5-0359`,
`D5-0339`, `D5-0340`, `D5-0044`) or the primary-place row (`D5-0006`); six are
D6 retention clauses (`D6-0034`, `D6-0035`, `D6-0038`, `D6-0039`, `D6-0040`,
`D6-0042`) where the quote carries "Destroy N years after…" and the statement
names the record type.

The 6 census-only weak rows are the opposite: the verifier passes them because
the quote contains the statement's words, while the census flags that the
operative element sits in a neighbouring, unquoted line (`D5-0072`,
`D5-0264`–`D5-0267`) or a dropped qualifier (`D5-0109`). Both lists are kept;
neither is folded into the other.

## Residual defects the fix does not repair

1. **Bare definition fragments as statements**: `D5-0307`, `D5-0341`,
   `D5-0345` state a definition without naming the defined term (and `D5-0341`
   says only "The defined term"). Counted `ok` under the locator rule, as in the
   §10.7(f) census; the term is in the section path.
2. **Wrong locator**: `D5-0361` is the "Approved IDTA" glossary definition but
   its locator names `Without Undue Delay`. The quote and page are right; the
   section path is wrong.
3. **Narrowed exception**: `D5-0067` reduces "except only: 5.1.1–5.1.3" to
   clause 5.1.1. Support is present; the scope is narrower than the source.
4. **Generalised quantity**: `D5-0063` says "two or more identical copies" where
   the quoted rule is stated for two copies.
5. **Source duplication carried into a statement**: `D5-0148` lists "Sections
   14, 15 and 21" because the document's own list quotes Section 15 twice
   (and does not print 19/20). The claim follows the source, not the intended
   section numbers.
6. **D6 actor from the schedule regime**: the retention-permission claims say
   "Agencies may retain…" while the item quote says "longer retention is
   authorized". Counted `ok`: the GRS is addressed to agencies and the item is a
   schedule of agency records, so the actor is the document's addressee, not a
   neighbouring clause. Passive formulations ("longer retention is authorized")
   are the `weak`-free alternative the next run should prefer.

## Verdict

**Accepted by §10.7(g).** Every pre-registered criterion passes: D5 structural
100%, support 97.7% ≥ 90%, 0 facts absent, recall 10/10 with `D5-0002`,
`D5-0003` and `D5-0004` all recalled, and the primary-place half of `D5-0003`
present and `ok`; D6 100% support, 10/10 recall, 0 misattributed authorities;
0 `no`, 0 `fabricated`; `check_claims.py` 0 failures; guard activity recorded
(one refused `drop` on `D5-0006`, plus three more refused drops and five refused
rewrites).

The guard did what the replay predicted, on the claim it was written for. The
pipeline is accepted for the demo; §10.7(h) records the result. Phase 0 of ADR
0002 (deterministic verification vs this census) now has a measured census to
compare against.

## Cost

| Stage | Tokens | Cost |
|---|---|---:|
| Compile (402 claims) | 66,057 in / 140,768 out | **$0.094** |
| Verify (402 rows → 397) | 272,441 in / 391,131 out, 118 calls | **$0.2755** |
| **Total** | | **$0.3695** |

The quote was **≤ $0.55**; the run cost **$0.37**, 33% under. The compile was
resumed three times on HTTP 503 from the local provider; `--resume` skips every
cached chunk, so the retries cost nothing beyond the successful calls.

## Limits

- One reader. The census is a single careful pass over every row, as in the
  earlier audits; no second reviewer scored these 397 claims.
- Support is measured on D5 and D6 only. The Gate 2 corpus (D1–D4) was censused
  at 99.0% by a different run; this artifact does not re-score it.
- The verifier remains quote-only. Its 19 `weak` rows are not errors of this
  run; they are the representation disagreement documented in §10.4 and in every
  earlier audit.
- Model nondeterminism: this run emitted 402 claims where §10.7(f) emitted 394
  and D6 57 where it emitted 51. The comparison between runs is on criteria, not
  on claim counts.
- The rule layer is small here: only 2 of 397 claims come from the deterministic
  row reader, because the model extracted the other five clean rows itself.
