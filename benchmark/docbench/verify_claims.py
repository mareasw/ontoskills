#!/usr/bin/env python3
"""Stage 2 of the document compiler: verify a claim against its own evidence.

`compile_claims.py` makes evidence verbatim by construction — the extractor may
only cite span ids, so the quote is always the segmenter's text. That guarantees
the quote *exists*, not that it *says what the statement says*. The Gate 2
census measured exactly that gap: 88.8% of claims were fully supported by their
own quote, below the 90% bar.

This stage closes the gap as a pipeline step, not as a per-document patch:

  1. **audit**  — a model sees ``(statement, quotes, section path)`` and returns
     ``ok | weak | no | fabricated`` on the same scale the census used. It never
     sees the rest of the document, so it cannot reward a claim for being true
     in the source but unsupported by its own evidence.
  2. **repair** — for every non-ok claim, a second call sees the claim, its
     current spans and the spans immediately around them, and chooses one of
     ``rewrite`` (restate within the current evidence), ``reevidence`` (cite a
     neighbouring span that does support it) or ``drop`` (no support anywhere
     in the neighbourhood). It may not invent a span or a sentence.
  3. **re-audit** — repaired claims are audited again. Whatever still fails
     after the last round is dropped: an unsupported claim is not shipped.

Only the claim and a bounded neighbourhood of its own spans are ever shown, so
the stage measures internal consistency, never agreement with the gold set.

Usage::

    # calibrate the instrument against the recorded census (no repair, cheap)
    python benchmark/docbench/verify_claims.py --calibrate /tmp/opencode/audit_full3

    # audit and repair a compiled artifact
    python benchmark/docbench/verify_claims.py \
        --claims gold/claims.compiled.jsonl \
        --spans gold/claims.compiled.jsonl.spans.jsonl \
        --out gold/claims.verified.jsonl --resume
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from claims_model import evidence_items, load_claims  # noqa: E402
from compile_claims import dedupe_claims, parse_claims  # noqa: E402
from env import load_dotenv  # noqa: E402

VERDICTS = ("ok", "weak", "no", "fabricated")
ACTIONS = ("rewrite", "reevidence", "drop")

# Spans considered as alternative evidence, on each side of a cited span. Three
# covers a lead-in followed by its list: ``The Commission may terminate ...:``
# then ``(a)``, ``(b)``, ``(c)``. It cannot reach into another section.
NEIGHBOURHOOD = 3
# A claim may cite at most this many candidate spans after repair.
MAX_CANDIDATES = 10

AUDIT_SYSTEM = """\
You are the evidence auditor for a document compiler. You are given claims that
were extracted from one document. For each claim you see the statement and the
verbatim evidence the compiler cited for it, with the section path the evidence
came from. You do not see the rest of the document.

Decide whether the evidence states the claim, as written. Use exactly this
scale:

  ok          every material element of the statement is in the quotes: the
              actor, the action, the object, any number or deadline, any
              condition or exception, and the strength of the modality ("may"
              is not "must").
  weak        the statement is plausibly true, but at least one material element
              is absent from the quotes (it came from a heading, a list
              lead-in, the adjacent line, or background knowledge), or the
              statement omits a condition that the quote attaches to the rule.
  no          the quotes do not state the claim, the modality is stronger than
              the quote's, or the claim contradicts the quotes.
  fabricated  the statement asserts a specific fact for which the quotes give
              no basis at all.

Check every claim the same way:

1. Break the statement into material elements: who, does what, to what or whom,
   when or how much, under which condition, with which strength.
2. Find each element in the quotes. An element is present only if the quote
   names it. A pronoun ("we", "it", "this section", "such", "they") does not
   name its referent, and a bare list item does not name its lead-in. An
   imperative ("Stop data flow"), a passive ("it should be removed") and a
   timetable entry ("Hour 1: Initial notification") do not name an actor: if
   the statement names one, that name is absent. The section path is context,
   not evidence: an element that appears only there is absent from the quotes.
3. A lead-in is not its list. "The Commission may terminate ... when:" does not
   contain grounds (a)-(c) unless they are quoted; "This Regulation lays down:"
   does not contain what follows it.
4. Keep the quote's strength. "should" is not "must"; "may include", "such as"
   and "including" are not an exhaustive list; a proposal that "would be
   considered" a violation is not a rule that "is" one.
5. If any element is missing, the verdict is weak. If the quote says the
   opposite, or the modality is strengthened, it is no. If the statement
   invents a specific fact, it is fabricated.

Judge only the text in front of you. Do not use the document title, the subject
matter, or world knowledge to fill a gap.

Return ONLY a JSON array, one object per claim, in input order:

  {"claim_id": "...", "verdict": "ok|weak|no|fabricated", "note": "<= 20 words"}

Use "-" as the note for an ok claim. No prose outside the array.
"""

REPAIR_SYSTEM = """\
You are repairing claims from a document compiler. For each failing claim you
are given its statement, its structured fields, the evidence spans it currently
cites, and the spans immediately around them in the same document. Every span
is verbatim source text. You may use only the spans shown.

Choose exactly one action:

  reevidence  Keep the statement, or restate it, and cite a different set of
              spans from the candidates, when the current spans do not support
              it but the surrounding spans do. Use span ids only. Prefer this
              when a candidate span contains the missing element: it preserves
              the statement, and the quote stays verbatim.
  rewrite     Keep the claim but restate it so that every material element
              (actor, action, object, number, deadline, condition, modality) is
              present in its CURRENT evidence. Never strengthen the modality.
              Never add an element that is absent. If the evidence supports only
              a weaker or narrower rule, write that rule.
  drop        The evidence states no complete rule and no candidate span
              supports the statement. Prefer this over inventing support.

Rules:

1. A claim may not assert an actor, condition, number, exception or modality
   that the chosen evidence does not state.
2. A rewrite must preserve the meaning as far as the evidence allows. Do not
   replace a specific rule with a generic one.
3. Re-evidencing may use the current spans and any candidate span shown. Never
   cite a span id that is not shown, and never cite a span from another
   document.
4. Do not merge claims, split claims, or add claims.

Return ONLY a JSON array, one object per claim, in input order:

  {"claim_id": "...", "action": "rewrite|reevidence|drop",
   "statement": "...",            // required for rewrite, optional for reevidence
   "evidence_span_ids": ["S0001"], // required for reevidence
   "note": "<= 20 words"}

No prose outside the array.
"""


# --------------------------------------------------------------------------
# Loading and indexing


def load_jsonl(path: str | Path) -> list[dict]:
    text = Path(path).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def append_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


class SpanIndex:
    """Resolve a claim's evidence to spans, and each span to its neighbours.

    A span is identified by ``(doc_id, char_start, char_end)`` because that is
    what the evidence locator already carries. Falling back to the quote text
    keeps the stage usable with a claim file whose locators are coarser than
    the span list (v1 claims, for instance).
    """

    def __init__(self, spans: list[dict]) -> None:
        self.by_range: dict[tuple, dict] = {}
        self.by_text: dict[tuple, dict] = {}
        self.by_id: dict[tuple, dict] = {}
        self.order: dict[str, list[dict]] = {}
        for span in spans:
            locator = span.get("locator") or {}
            doc = span["doc_id"]
            self.by_range[(doc, locator.get("char_start"), locator.get("char_end"))] = span
            self.by_text.setdefault((doc, span.get("paragraph", "")), span)
            self.by_id[(doc, span["span_id"])] = span
            self.order.setdefault(doc, []).append(span)
        self.position: dict[tuple, int] = {}
        for doc, doc_spans in self.order.items():
            doc_spans.sort(key=lambda s: (s.get("locator") or {}).get("char_start") or 0)
            for index, span in enumerate(doc_spans):
                self.position[(doc, span["span_id"])] = index

    def resolve(self, claim: dict) -> list[dict]:
        """The spans a claim cites, in citation order, skipping unresolvable ones."""
        out: list[dict] = []
        doc = claim["doc_id"]
        for item in evidence_items(claim):
            locator = item.get("locator") or {}
            span = self.by_range.get((doc, locator.get("char_start"), locator.get("char_end")))
            if span is None:
                span = self.by_text.get((doc, item.get("quote", "")))
            if span is not None and span not in out:
                out.append(span)
        return out

    def neighbourhood(self, spans: list[dict], radius: int = NEIGHBOURHOOD) -> list[dict]:
        """Spans around the cited ones, nearest first, capped at MAX_CANDIDATES."""
        if not spans:
            return []
        doc = spans[0]["doc_id"]
        doc_spans = self.order.get(doc, [])
        cited = {(doc, s["span_id"]) for s in spans}
        picked: dict[tuple, tuple[int, int]] = {}
        for span in spans:
            index = self.position.get((doc, span["span_id"]))
            if index is None:
                continue
            for offset in range(-radius, radius + 1):
                other = index + offset
                if not (0 <= other < len(doc_spans)):
                    continue
                candidate = doc_spans[other]
                key = (doc, candidate["span_id"])
                if key in cited or key in picked:
                    continue
                picked[key] = (abs(offset), other)
        ordered = sorted(picked.items(), key=lambda item: (item[1][0], item[1][1]))
        return [self.by_id[key] for key, _ in ordered[:MAX_CANDIDATES]]


# --------------------------------------------------------------------------
# Prompt rendering


def _section_path(span: dict | None) -> str:
    if not span:
        return "-"
    path = (span.get("locator") or {}).get("section_path") or []
    return " > ".join(str(part) for part in path) if path else "-"


def audit_item(claim: dict, spans: list[dict]) -> str:
    lines = [f"### CLAIM {claim['claim_id']}", f"statement: {claim['statement']}"]
    items = evidence_items(claim)
    for index, item in enumerate(items, start=1):
        span = spans[index - 1] if index - 1 < len(spans) else None
        lines.append(f"section: {_section_path(span)}")
        lines.append(f'quote {index}: """{item.get("quote", "")}"""')
    return "\n".join(lines)


def audit_prompt(batch: list[tuple[dict, list[dict]]]) -> str:
    body = "\n\n".join(audit_item(claim, spans) for claim, spans in batch)
    return f"{body}\n\nReturn the JSON array now."


def repair_item(claim: dict, current: list[dict], candidates: list[dict]) -> str:
    lines = [
        f"### CLAIM {claim['claim_id']}",
        f"statement: {claim['statement']}",
        f"modality: {claim.get('modality', '')}",
    ]
    if claim.get("actor"):
        lines.append(f"actor: {claim['actor']}")
    if claim.get("deadline"):
        lines.append(f"deadline: {claim['deadline']}")
    conditions = claim.get("conditions") or []
    if conditions:
        lines.append("conditions: " + " | ".join(str(c) for c in conditions))
    lines.append(f"section: {_section_path(current[0] if current else None)}")
    lines.append("current evidence:")
    for span in current:
        lines.append(f'  [CURRENT {span["span_id"]}] """{span.get("paragraph", "")}"""')
    if candidates:
        lines.append("candidate spans (nearest first):")
        for span in candidates:
            lines.append(f'  [CANDIDATE {span["span_id"]}] """{span.get("paragraph", "")}"""')
    return "\n".join(lines)


def repair_prompt(batch: list[tuple[dict, list[dict], list[dict]]]) -> str:
    body = "\n\n".join(repair_item(claim, current, candidates) for claim, current, candidates in batch)
    return f"{body}\n\nReturn the JSON array now."


# --------------------------------------------------------------------------
# Model passes


def _batches(items: list, size: int) -> list[list]:
    size = max(1, size)
    return [items[start : start + size] for start in range(0, len(items), size)]


def audit_claims(
    claims: list[dict],
    spans: SpanIndex,
    call,
    *,
    cache_path: Path | None = None,
    resume: bool = False,
    batch_size: int = 10,
    max_tokens: int = 8000,
) -> dict[str, dict]:
    """Return ``{claim_id: {verdict, note}}`` for every claim.

    The cache is append-only JSONL, keyed by claim id, so an interrupted run
    re-audits only the claims it never reached.

    A reply that omits claims is not a verdict: re-asking for the missing ones
    is both cheaper and more honest than treating silence as ``weak``. Silence
    used to produce a false positive on every claim a batch skipped, so the
    omission is retried, halving the batch each time.
    """
    done: dict[str, dict] = {}
    aborted: list[str] = []
    if resume and cache_path and cache_path.exists():
        for row in load_jsonl(cache_path):
            if row.get("verdict") in VERDICTS and row.get("claim_id"):
                done[row["claim_id"]] = {"verdict": row["verdict"], "note": row.get("note", "")}
    if cache_path and not resume:
        cache_path.unlink(missing_ok=True)

    def ask(batch: list[dict]) -> None:
        pairs = [(claim, spans.resolve(claim)) for claim in batch]
        try:
            reply, _usage, finish = call(audit_prompt(pairs), AUDIT_SYSTEM, max_tokens)
        except SystemExit as exc:
            # One dead batch must not lose the 400 claims already audited. The
            # cache keeps them; --resume re-asks only this batch.
            aborted.extend(claim["claim_id"] for claim in batch)
            print(f"  audit: batch of {len(batch)} failed ({exc})", file=sys.stderr)
            return
        parsed = parse_claims(reply)
        by_id = {str(row.get("claim_id")): row for row in parsed if row.get("claim_id")}
        rows: list[dict] = []
        missing: list[dict] = []
        for claim in batch:
            row = by_id.get(claim["claim_id"])
            verdict = str((row or {}).get("verdict", "")).strip().lower()
            if verdict not in VERDICTS:
                missing.append(claim)
                continue
            record = {"verdict": verdict, "note": str((row or {}).get("note", ""))[:160]}
            done[claim["claim_id"]] = record
            rows.append({"claim_id": claim["claim_id"], **record})
        if cache_path and rows:
            append_jsonl(cache_path, rows)
        if missing and len(batch) > 1:
            middle = len(missing) // 2 or 1
            ask(missing[:middle])
            ask(missing[middle:])
        elif missing:
            # A single claim the model will not judge cannot pass the audit.
            claim = missing[0]
            record = {"verdict": "weak", "note": "audit reply omitted this claim"}
            done[claim["claim_id"]] = record
            if cache_path:
                append_jsonl(cache_path, [{"claim_id": claim["claim_id"], **record}])
        if finish == "length":
            print(f"  audit: batch of {len(batch)} hit the token limit", file=sys.stderr)

    pending = [c for c in claims if c["claim_id"] not in done]
    for batch in _batches(pending, batch_size):
        ask(batch)
    if aborted:
        raise SystemExit(
            f"audit incomplete: {len(aborted)} claim(s) never judged, e.g. {aborted[:5]}. "
            "Progress is cached; re-run with --resume."
        )
    return done


def repair_claims(
    claims: list[dict],
    spans: SpanIndex,
    call,
    *,
    cache_path: Path | None = None,
    resume: bool = False,
    batch_size: int = 6,
    max_tokens: int = 8000,
) -> dict[str, dict]:
    """Return ``{claim_id: action record}`` for the claims that need repair."""
    done: dict[str, dict] = {}
    aborted: list[str] = []
    if resume and cache_path and cache_path.exists():
        for row in load_jsonl(cache_path):
            if row.get("claim_id"):
                done[row["claim_id"]] = row
    if cache_path and not resume:
        cache_path.unlink(missing_ok=True)

    def ask(batch: list[dict]) -> None:
        triples = [
            (claim, spans.resolve(claim), spans.neighbourhood(spans.resolve(claim)))
            for claim in batch
        ]
        try:
            reply, _usage, finish = call(repair_prompt(triples), REPAIR_SYSTEM, max_tokens)
        except SystemExit as exc:
            aborted.extend(claim["claim_id"] for claim in batch)
            print(f"  repair: batch of {len(batch)} failed ({exc})", file=sys.stderr)
            return
        parsed = parse_claims(reply)
        by_id = {str(row.get("claim_id")): row for row in parsed if row.get("claim_id")}
        rows: list[dict] = []
        missing: list[dict] = []
        for claim in batch:
            row = by_id.get(claim["claim_id"])
            if row is None:
                missing.append(claim)
                continue
            action = str(row.get("action", "")).strip().lower()
            record = {
                "claim_id": claim["claim_id"],
                "action": action if action in ACTIONS else "",
                "statement": str(row.get("statement") or "").strip(),
                "evidence_span_ids": [str(s).strip() for s in (row.get("evidence_span_ids") or [])],
                "note": str(row.get("note") or "")[:160],
            }
            done[claim["claim_id"]] = record
            rows.append(record)
        if cache_path and rows:
            append_jsonl(cache_path, rows)
        if missing and len(batch) > 1:
            middle = len(missing) // 2 or 1
            ask(missing[:middle])
            ask(missing[middle:])
        elif missing:
            claim = missing[0]
            done[claim["claim_id"]] = {
                "claim_id": claim["claim_id"],
                "action": "",
                "statement": "",
                "evidence_span_ids": [],
                "note": "repair reply omitted this claim",
            }
        if finish == "length":
            print(f"  repair: batch of {len(batch)} hit the token limit", file=sys.stderr)

    pending = [c for c in claims if c["claim_id"] not in done]
    for batch in _batches(pending, batch_size):
        ask(batch)
    if aborted:
        raise SystemExit(
            f"repair incomplete: {len(aborted)} claim(s) never judged, e.g. {aborted[:5]}. "
            "Progress is cached; re-run with --resume."
        )
    return done


# --------------------------------------------------------------------------
# Applying repairs (pure: no model, no network)


def clean_statement(text: str) -> str:
    """One line, no citation markers, no surrounding quotes."""
    text = " ".join(str(text or "").split())
    return text.strip().strip('"').strip()


# The compiler rejects an extracted statement shorter than this (build_claim);
# a repair must not smuggle in a stub the extractor was not allowed to write.
MIN_STATEMENT = 15


def usable_statement(statement: str, old: str) -> bool:
    """True when a rewritten statement is a real, different sentence."""
    return len(statement) >= MIN_STATEMENT and statement != old


def make_evidence(span: dict, role: str = "supports") -> dict:
    return {"quote": span.get("paragraph", ""), "locator": dict(span.get("locator") or {}), "role": role}


def apply_repairs(
    claims: list[dict],
    repairs: dict[str, dict],
    spans: SpanIndex,
) -> tuple[list[dict], dict]:
    """Apply repair records to the claim list.

    A record is only honoured when it is usable: a rewrite needs a non-empty
    statement, at least ``MIN_STATEMENT`` characters and different from the old
    one; a re-evidence needs at least one span that is actually in the claim's
    neighbourhood; an unknown action leaves the claim untouched. Rejected
    records are counted, never silently accepted.
    """
    report = {
        "rewritten": 0,
        "reevidenced": 0,
        "dropped": 0,
        "unchanged": 0,
        "rejected": 0,
        "dropped_ids": [],
    }
    out: list[dict] = []
    for claim in claims:
        record = repairs.get(claim["claim_id"])
        action = (record or {}).get("action", "")
        if not record or action not in ACTIONS:
            report["unchanged"] += 1
            out.append(claim)
            continue

        if action == "drop":
            report["dropped"] += 1
            report["dropped_ids"].append(claim["claim_id"])
            continue

        allowed = {span["span_id"]: span for span in spans.neighbourhood(spans.resolve(claim))}
        allowed.update({span["span_id"]: span for span in spans.resolve(claim)})

        if action == "reevidence":
            chosen: list[dict] = []
            for span_id in record.get("evidence_span_ids") or []:
                span = allowed.get(span_id)
                if span is not None and span not in chosen:
                    chosen.append(span)
            if not chosen:
                report["rejected"] += 1
                out.append(claim)
                continue
            chosen.sort(key=lambda s: spans.position.get((s["doc_id"], s["span_id"]), 0))
            prior_roles = {
                (item.get("locator") or {}).get("char_start"): item.get("role", "supports")
                for item in evidence_items(claim)
            }
            updated = dict(claim)
            updated["evidence"] = [
                make_evidence(span, prior_roles.get((span.get("locator") or {}).get("char_start"), "supports"))
                for span in chosen
            ]
            statement = clean_statement(record.get("statement", ""))
            if usable_statement(statement, claim["statement"]):
                updated["statement"] = statement
                report["rewritten"] += 1
            report["reevidenced"] += 1
            out.append(updated)
            continue

        # rewrite
        statement = clean_statement(record.get("statement", ""))
        if not usable_statement(statement, claim["statement"]):
            report["rejected"] += 1
            out.append(claim)
            continue
        updated = dict(claim)
        updated["statement"] = statement
        report["rewritten"] += 1
        out.append(updated)
    return out, report


def prune_conflicts(claims: list[dict]) -> int:
    """Drop `conflicts_with` references to claims that no longer exist."""
    alive = {claim["claim_id"] for claim in claims}
    removed = 0
    for claim in claims:
        links = claim.get("conflicts_with")
        if not links:
            continue
        kept = [link for link in links if link in alive]
        if len(kept) != len(links):
            removed += len(links) - len(kept)
            if kept:
                claim["conflicts_with"] = kept
            else:
                del claim["conflicts_with"]
    return removed


# --------------------------------------------------------------------------
# Orchestration


def run_pipeline(
    claims: list[dict],
    spans: SpanIndex,
    call,
    *,
    work: Path,
    rounds: int = 2,
    audit_batch: int = 10,
    repair_batch: int = 6,
    max_tokens: int = 8000,
    resume: bool = False,
    keep_residual: bool = False,
    initial_audit: dict[str, dict] | None = None,
    verbose: bool = True,
) -> tuple[list[dict], dict]:
    """audit -> repair -> re-audit, repeated `rounds` times. Pure policy."""
    audit = initial_audit
    if audit is None:
        audit = audit_claims(
            claims,
            spans,
            call,
            cache_path=work / "audit.jsonl",
            resume=resume,
            batch_size=audit_batch,
            max_tokens=max_tokens,
        )
    report = {"initial": summarize(claims, audit), "rounds": []}

    for index in range(1, max(1, rounds) + 1):
        failing = [claim for claim in claims if audit.get(claim["claim_id"], {}).get("verdict") != "ok"]
        if not failing:
            break
        repairs = repair_claims(
            failing,
            spans,
            call,
            cache_path=work / f"repair.{index}.jsonl",
            resume=resume,
            batch_size=repair_batch,
            max_tokens=max_tokens,
        )
        claims, round_report = apply_repairs(claims, repairs, spans)
        touched = [claim for claim in claims if claim["claim_id"] in repairs]
        audit.update(
            audit_claims(
                touched,
                spans,
                call,
                cache_path=work / f"audit.{index + 1}.jsonl",
                resume=resume,
                batch_size=audit_batch,
                max_tokens=max_tokens,
            )
        )
        unresolved = [c for c in touched if audit.get(c["claim_id"], {}).get("verdict") != "ok"]
        round_report.update(
            {
                "round": index,
                "audited_before": len(failing),
                "repaired_claims": len(touched),
                "still_failing": len(unresolved),
                "still_failing_ids": [c["claim_id"] for c in unresolved],
            }
        )
        report["rounds"].append(round_report)
        if verbose:
            print(
                f"round {index}: {len(failing)} failing -> {round_report['rewritten']} rewritten, "
                f"{round_report['reevidenced']} re-evidenced, {round_report['dropped']} dropped, "
                f"{round_report['rejected']} rejected, {len(unresolved)} still failing"
            )

    # Merge near-duplicates that rewriting may have created, then clean links.
    claims, merged = dedupe_claims(claims)
    residual = [claim for claim in claims if audit.get(claim["claim_id"], {}).get("verdict") != "ok"]
    if residual and not keep_residual:
        residual_ids = {claim["claim_id"] for claim in residual}
        claims = [claim for claim in claims if claim["claim_id"] not in residual_ids]
    report["merged_duplicates"] = merged
    report["residual_dropped"] = 0 if keep_residual else len(residual)
    report["residual_ids"] = [claim["claim_id"] for claim in residual]
    report["conflict_links_removed"] = prune_conflicts(claims)
    report["final"] = summarize(claims, audit)
    return claims, report


def summarize(claims: list[dict], audit: dict[str, dict]) -> dict:
    counts = {verdict: 0 for verdict in VERDICTS}
    for claim in claims:
        verdict = audit.get(claim["claim_id"], {}).get("verdict", "weak")
        counts[verdict] = counts.get(verdict, 0) + 1
    total = len(claims)
    counts["claims"] = total
    counts["ok_share"] = round(counts.get("ok", 0) / total, 4) if total else 0.0
    return counts


# --------------------------------------------------------------------------
# Calibration against the recorded census


def calibration_sample(claims: list[dict], known: dict[str, str], ok_target: int) -> list[dict]:
    """Every known non-ok claim, plus a deterministic sample of known ok ones."""
    bad = [c for c in claims if known.get(c["claim_id"]) in ("weak", "no", "fabricated")]
    good = [c for c in claims if known.get(c["claim_id"]) == "ok"]
    if ok_target and good:
        step = max(1, len(good) // ok_target)
        good = good[::step][:ok_target]
    return sorted(bad + good, key=lambda c: c["claim_id"])


def calibration_report(
    sample: list[dict],
    audit: dict[str, dict],
    known: dict[str, str],
) -> dict:
    matrix = {(truth, pred): 0 for truth in ("ok", "bad") for pred in ("ok", "bad")}
    missed: list[str] = []
    false_positives: list[str] = []
    for claim in sample:
        cid = claim["claim_id"]
        truth = "bad" if known.get(cid) in ("weak", "no", "fabricated") else "ok"
        pred = "ok" if audit.get(cid, {}).get("verdict") == "ok" else "bad"
        matrix[(truth, pred)] += 1
        if truth == "bad" and pred == "ok":
            missed.append(cid)
        if truth == "ok" and pred == "bad":
            false_positives.append(cid)
    known_bad = sum(1 for c in sample if known.get(c["claim_id"]) in ("weak", "no", "fabricated"))
    known_ok = len(sample) - known_bad
    caught = matrix[("bad", "bad")]
    return {
        "sample": len(sample),
        "known_bad": known_bad,
        "known_ok": known_ok,
        "caught": caught,
        "missed": missed,
        "false_positives": false_positives,
        "recall": round(caught / known_bad, 3) if known_bad else 0.0,
        "false_positive_rate": round(len(false_positives) / known_ok, 3) if known_ok else 0.0,
        "matrix": {f"{truth}->{pred}": value for (truth, pred), value in matrix.items()},
        "agreement": round((caught + matrix[("ok", "ok")]) / len(sample), 3) if sample else 0.0,
    }


# --------------------------------------------------------------------------
# CLI


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--claims", default=str(ROOT / "gold" / "claims.compiled.jsonl"))
    parser.add_argument("--spans", default="", help="default: <claims>.spans.jsonl")
    parser.add_argument("--out", default="", help="repaired claims (default: <claims>.verified.jsonl)")
    parser.add_argument("--work", default="", help="cache/report directory (default: alongside --out)")
    parser.add_argument("--model", default=os.environ.get("DOCBENCH_MODEL") or os.environ.get("OPENAI_MODEL", ""))
    parser.add_argument("--base-url", default=os.environ.get("OPENAI_BASE_URL", ""))
    parser.add_argument("--audit-batch", type=int, default=10)
    parser.add_argument("--repair-batch", type=int, default=6)
    parser.add_argument("--max-tokens", type=int, default=8000)
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--audit-only", action="store_true", help="stop after the first audit")
    parser.add_argument("--keep-residual", action="store_true",
                        help="keep claims that still fail after the last round")
    parser.add_argument("--calibrate", default="", metavar="DIR",
                        help="directory with verdicts_D*.jsonl from the census")
    parser.add_argument("--adjudications", default="", metavar="FILE",
                        help="JSONL of {claim_id, verdict, reason} that overrides the census "
                             "where a second reviewer disagreed with it")
    parser.add_argument("--calibrate-ok", type=int, default=60,
                        help="known-ok claims to include in the calibration sample")
    parser.add_argument("--min-recall", type=float, default=round(45 / 58, 4),
                        help="calibration stop rule: share of known non-ok claims caught")
    parser.add_argument("--max-fp", type=int, default=5,
                        help="calibration stop rule: false positives on known-ok claims")
    parser.add_argument("--synthetic", action="store_true", help="skip the model, use an empty call (tests)")
    args = parser.parse_args(argv)

    claims_path = Path(args.claims)
    spans_path = Path(args.spans) if args.spans else Path(str(claims_path) + ".spans.jsonl")
    out_path = Path(args.out) if args.out else Path(str(claims_path).replace(".jsonl", "") + ".verified.jsonl")
    work = Path(args.work) if args.work else Path(str(out_path) + ".work")
    work.mkdir(parents=True, exist_ok=True)

    claims = load_claims(claims_path)
    spans = SpanIndex(load_jsonl(spans_path))
    print(f"claims: {len(claims)}  spans: {sum(len(v) for v in spans.order.values())}  work: {work}")

    def call(prompt: str, system: str, max_tokens: int):
        from llm import chat

        return chat(
            args.base_url or os.environ.get("OPENAI_BASE_URL", ""),
            os.environ.get("OPENAI_API_KEY", ""),
            args.model,
            [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            max_tokens,
        )

    if args.synthetic:
        def call(prompt, system, max_tokens):  # noqa: F811 - deliberate override
            return "[]", {"input_tokens": 0, "output_tokens": 0}, "stop"

    if args.calibrate:
        known: dict[str, str] = {}
        for path in sorted(Path(args.calibrate).glob("verdicts_D*.jsonl")):
            for row in load_jsonl(path):
                known[row["claim_id"]] = row["verdict"]
        if not known:
            raise SystemExit(f"no verdicts_D*.jsonl in {args.calibrate}")
        if args.adjudications:
            overrides = load_jsonl(args.adjudications)
            known.update({row["claim_id"]: row["verdict"] for row in overrides})
            print(f"adjudications applied: {len(overrides)}")
        sample = calibration_sample(claims, known, args.calibrate_ok)
        print(f"calibration sample: {len(sample)} claims ({sum(1 for c in sample if known[c['claim_id']] != 'ok')} known non-ok)")
        audit = audit_claims(
            sample,
            spans,
            call,
            cache_path=work / "calibration.audit.jsonl",
            resume=args.resume,
            batch_size=args.audit_batch,
            max_tokens=args.max_tokens,
        )
        report = calibration_report(sample, audit, known)
        (work / "calibration.report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
        print(json.dumps(report, indent=1))
        ok = report["caught"] >= args.min_recall * report["known_bad"] and len(report["false_positives"]) <= args.max_fp
        print(f"stop rule: {'PASS' if ok else 'FAIL'} "
              f"(need >= {args.min_recall:.3f} recall, <= {args.max_fp} false positives)")
        return 0 if ok else 2

    audit = audit_claims(
        claims,
        spans,
        call,
        cache_path=work / "audit.jsonl",
        resume=args.resume,
        batch_size=args.audit_batch,
        max_tokens=args.max_tokens,
    )
    initial = summarize(claims, audit)
    print(f"audit: {json.dumps(initial)}")
    if args.audit_only:
        (work / "report.json").write_text(json.dumps({"initial": initial}, indent=1), encoding="utf-8")
        return 0

    claims, report = run_pipeline(
        claims,
        spans,
        call,
        work=work,
        rounds=args.rounds,
        audit_batch=args.audit_batch,
        repair_batch=args.repair_batch,
        max_tokens=args.max_tokens,
        resume=args.resume,
        keep_residual=args.keep_residual,
        initial_audit=audit,
    )
    report["claims_in"] = len(load_claims(claims_path))

    write_jsonl(out_path, claims)
    (work / "report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"\nwrote {len(claims)} claims -> {out_path}")
    print(json.dumps(report["final"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
