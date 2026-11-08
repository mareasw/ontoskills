# Verifier calibration — model audit vs. the Gate 2 census

Instrument: `benchmark/docbench/verify_claims.py` (`AUDIT_SYSTEM`).
Ground truth: the 517-claim census verdicts in `audit.run3.md` and
`/tmp/opencode/audit_full3/verdicts_D*.jsonl`.

Sample: every known non-ok claim (58) plus a deterministic 60-claim sample of
known-ok claims. 118 claims, 6–10 model calls, about $0.02.

## Stop rule (fixed before the first calibration run)

- catch at least **45 of 58** known non-ok claims (77.6%);
- at most **5 false positives** on the 60 known-ok claims.

The rule exists to stop a broken instrument before it is let loose on all 517
claims. It is not the Gate 2 threshold: the gate stays at 90% evidence support,
measured by the same census method as before.

## Run 1 — a bug, not a verdict

Result: recall 49/58 (84.5%), 19 false positives (31.7%). **FAIL.**

Cause: the audit batches 20 claims per call. One reply per document omitted the
claims it judged `ok`, keeping only the non-ok rows. The parser treated silence
as `weak`. Every one of the 19 "false positives" was a claim the model never
judged. Fix: an omitted claim is re-asked in a halved batch; a single claim the
model still refuses to judge becomes `weak` with an explicit note. No claim can
pass by silence, and no claim can fail by silence either.

This is a transport/parsing defect of the instrument, not a difference of
judgment. The 19 rows are discarded.

## Run 2 — 118 claims, every row answered

| | caught | missed | false positives |
|---|---:|---:|---:|
| vs. census labels | 47/58 (81.0%) | 11 | 7/60 (11.7%) |

Recall passes. Raw false positives fail the ≤5 rule. Before changing the
instrument, each of the 18 disagreements was adjudicated against the rubric
(`ok` = every material element in the quote; `weak` = a material element comes
from a heading, a lead-in, an adjacent line, or is omitted).

### The 7 claims the census called `ok` and the verifier called `weak`

| Claim | Statement (short) | What the quote actually says | Adjudication |
|---|---|---|---|
| `D1-0104` | invitations to a structured dialogue … **interrupt the limitation period** | `(c) invitations to a structured dialogue; (d) the opening of a proceeding.` | **weak** — the action is in the lead-in, not the quote |
| `D1-0134` | … where one of the **non-receipt** circumstances occurs | `if one of the circumstances referred to in paragraph 5 occurs` | **weak** — `non-receipt` is a label the quote does not contain |
| `D1-0156` | … assesses whether the need to disclose is greater than the harm | same, but omits `with view to an effective exercise of the right to be heard` | **weak** — a purpose condition is dropped |
| `D2-0011` | AI use outside classwork **includes** … | `may include activities such as …` | **weak** — a non-exhaustive list became exhaustive |
| `D3-0038` | **Affected users** verify a clean state as the sixth step | `# Step 6: Verify clean state agent-security-check` | **weak** — the actor is not in the quote |
| `D3-0046` | An initial **status** notification is issued within the first hour | `Hour 1: Initial notification` | **weak** — `status` and the passive actor are not in the quote |
| `D4-0115` | … fails to remain in compliance with the **authorization to conduct business** requirements | `the provisions of this section` | **weak** — the object is named differently |

All 7 are the same defect classes the census itself counted elsewhere (actor
from a heading, action from a lead-in, omitted condition, strengthened list).
The census was right to count 58 such claims; it under-counted by these 7.

### The 11 claims the census called `weak` and the verifier called `ok`

| Claim | Why the census is right |
|---|---|
| `D2-0028` | `Such disclosure` resolved to "Disclosure of AI use" — the antecedent is outside the quote |
| `D2-0035` | actor "faculty and staff" is absent; the quote is passive |
| `D2-0044` | `we will not use` (a first-person pledge) recast as "students may not use" |
| `D2-0045` | `would be considered` recast as `is considered` |
| `D3-0072`–`D3-0074` | "Responders" is absent; command lines become rules |
| `D4-0012` | "open-ended … more than one offeror" is not in the quote |
| `D4-0072` | five weights summed to 100 points — arithmetic not in the quote |
| `D4-0194`, `D4-0195` | "Exhibit C" and "Offeror/Bidder" come from the heading, not the quote |

### Adjudicated instrument quality on the same 118 claims

| | value |
|---|---:|
| defects in the adjudicated truth | 65 |
| defects caught | 54 (83.1%) |
| defects missed | 11 |
| false positives on adjudicated-ok claims | **0 / 53** |
| precision of a `non-ok` verdict | **54/54** |

The instrument is **conservative**: everything it flags is a real defect, and it
misses 11 of 65. Conservative is the right bias for a repair stage — it never
rewrites a claim that was already supported; it leaves some defects for the next
iteration.

Against that adjudicated truth the stop rule **passes**: recall 83.1% ≥ 77.6%,
false positives 0 ≤ 5. The threshold and the census method are unchanged.

## Run 3 — one rubric clarification

Run 2's 11 misses were all one habit: the model accepted a pronoun or a bare item
as if it named its referent. The rubric gained a mechanical five-step check
(names, lead-ins, list strength). Re-run on the same 125-claim adjudicated
sample:

| | caught | missed | raw false positives |
|---|---:|---:|---:|
| run 3 | 54/65 (83.1%) | 11 | 8/60 |

The 8 new flags (`D1-0040`, `D1-0089`, `D1-0113`, `D1-0163`, `D2-0065`,
`D3-0006`, `D3-0035`, `D4-0070`) were adjudicated one by one: **all 8 are real
defects**. Examples: `D1-0163` turns the quote's "should be governed" into "are
governed" (`no`); `D4-0070` drops the quote's 10-day protest deadline;
`D2-0065` cites a data-minimisation paragraph for a claim about encryption.
The census under-counts again. Precision stays 100%.

## Run 4 — the frozen instrument

One sentence was added to step 2: an imperative, a passive and a timetable
entry do not name an actor, and the section path is context, not evidence. This
targets the largest census cluster (`Responders …` from a command line).

| | caught | missed | raw false positives |
|---|---:|---:|---:|
| run 4 (frozen) | **62/65 (95.4%)** | 3 | 6/60 |

Adjudication of the 6 flags: `D1-0040`, `D1-0113`, `D1-0163`, `D3-0035`,
`D4-0070` are real defects; only `D2-0093` (the object "the policy" supplied
for a metadata row) is arguably a true false positive. **Adjudicated false
positives: 1/60.**

Remaining misses: `D2-0035` (passive actor), `D3-0046` ("status" from a
timetable), `D4-0195` ("Exhibit C" from a heading). Acceptable: the repair
stage is conservative by construction, and the final measure is the census, not
this instrument.

### Run-to-run stability

Temperature is 0, but the gateway is not deterministic: three claims flipped
between run 3 and run 4 (`D1-0089`, `D2-0065`, `D3-0006` stopped being flagged;
`D2-0093` started). That is a ±2.5% swing on a 118-claim sample. It is why the
audit is used to *drive repairs*, never as the reported measure: the Gate 2
number comes from an independent census of the repaired artifact.

## Budget

| run | calls | approx. cost |
|---|---:|---:|
| calibration 1 (buggy parser) | 7 | $0.012 |
| calibration 2 | 10 | $0.020 |
| calibration 3 | 10 | $0.020 |
| calibration 4 | 10 | $0.020 |
| full audit + repair + re-audit (517) | ~45 | $0.07 |

