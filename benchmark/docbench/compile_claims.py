#!/usr/bin/env python3
"""Compile a source document into claims with evidence (v0, span-first).

The pipeline is the one in ``docs/adr/0001-document-first-kernel.md``:

    source -> segmenter -> extractor -> validator -> emitter

What makes this version falsifiable rather than hopeful:

* **Span-first.** The segmenter assigns every span an id and a locator *before*
  the model runs. The extractor may only reference existing span ids; it never
  writes the quote. The emitted quote is copied from the segmenter, so it is
  verbatim by construction, and the locator (page, section path, char offsets,
  url) comes from the span, not from the model.
* **Schema-constrained.** The model answers with a JSON array of
  ``{span_ids, statement, modality, ...}``; anything else is rejected.
* **Deduplicated.** Consecutive chunks of a long document overlap, so the same
  claim can be extracted twice. Statements are normalised and deduplicated.

Usage:
    # 1. See what would be sent, and the token estimate (no API calls)
    python benchmark/docbench/compile_claims.py --dry-run

    # 2. Compile (this costs API calls; see --estimate first)
    python benchmark/docbench/compile_claims.py --out gold/claims.compiled.jsonl

    # 3. Validate the result against the sources
    python benchmark/docbench/check_claims.py gold/claims.compiled.jsonl

    # 4. Use it as the B2 context
    python benchmark/docbench/run_baselines.py --conditions B2 --claims gold/claims.compiled.jsonl

The extractor only sees a span list, so the cost is bounded by the source size
once, not once per question.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from claims_model import to_v2  # noqa: E402

PRIVATE = ROOT / "private"
GOLD = ROOT / "gold"

# Document metadata. This is context about the document, not a claim about it:
# it comes from the source page itself and is already recorded in sources.md.
DOCS = {
    "D1": {
        "file": "D1.txt",
        "kind": "html",
        "url": "https://artificialintelligenceact.eu/implementing-regulation-evaluations/",
        "context": {
            "source": "Commission Implementing Regulation (EU) 2026/1755",
            "version": "2026-07-20",
            "jurisdiction": "EU",
            "doc_type": "regulation",
            "valid_from": "2026-08-10",
        },
    },
    "D2": {
        "file": "D2.txt",
        "kind": "pdf",
        "url": "https://www.luc.edu/media/lucedu/ai/pdfs/AI-Policy-Guidance.pdf",
        "context": {
            "source": "Loyola University Chicago AI Policy & Guidance",
            "version": "2025",
            "jurisdiction": "US-IL",
            "doc_type": "policy",
        },
    },
    "D3": {
        "file": "D3.txt",
        "kind": "html",
        "url": "https://owasp.org/www-project-ai-security-and-privacy-guide/",
        "context": {
            "source": "OWASP AI Security and Privacy Guide — Incident Response Playbook",
            "version": "2025",
            "jurisdiction": "global",
            "doc_type": "playbook",
        },
    },
    "D4": {
        "file": "D4.txt",
        "kind": "pdf",
        "url": "https://greenecountyva.gov/DocumentCenter/View/1577",
        "context": {
            "source": "Greene County RFP 2026-001",
            "version": "2026-01",
            "jurisdiction": "US-VA-Greene",
            "doc_type": "rfp",
            "valid_from": "2026-01-01",
        },
    },
}

# HTML extractions keep the site chrome: cookies, JavaScript notices, navigation
# and print artefacts. They are not part of the document, and a span made of
# them can only produce a junk claim. This is a conservative blocklist of
# boilerplate phrases, not a topic filter.
BOILERPLATE = re.compile(
    r"enable javascript|cookies? to analyze|uses cookies|privacy policy|terms of (use|service)"
    r"|all rights reserved|skip to (main )?content|sign in|log in|subscribe to|newsletter"
    r"|share this|follow us|©|\bcopyright\b|download (the )?(pdf|app)|back to top",
    re.IGNORECASE,
)

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
  subject    short noun phrase the claim is about (may be "")
  predicate  the relation, e.g. "must submit", "may not use" (may be "")
  object     the thing the relation points at (may be "")

Rules, in order of importance:

1. NEVER write text that is not in a span. If a rule needs two separate spans
   (the rule, and the exception that scopes it), list both span ids in the same
   claim and use role-free supporting evidence.
2. One claim per atomic assertion. "A must do X and must also do Y" is two
   claims sharing the same span. An exception is its own claim with
   modality "condition", and its statement names what it scopes.
3. A definition is a claim (modality "definition"). A numbered step is a claim
   (modality "procedure_step"). An example inside a template or a fictional
   illustration is NOT a claim: skip it.
4. Do not merge spans that state contradictory things. Emit them as separate
   claims; the compiler links conflicts afterwards.
5. Do not infer, summarise across sections, or add world knowledge. If the
   document does not say it, it is not a claim.
6. Skip navigation, headers, footers, tables of contents, cookie notices and
   anything that is not a rule or a substantive fact.
7. Prefer fewer, better claims. An empty array is a valid answer for a span
   group that contains no rule.
"""


CONFLICT_SYSTEM = """\
You are given the claims compiled from ONE document, with their ids. Some pairs
of claims contradict each other: two different deadlines for the same
obligation, two different actors, a rule and an exception that cannot both hold.

Return ONLY a JSON array of pairs, e.g. [["D4-0001","D4-0002"]]. Each pair must
be two ids from the list, and the contradiction must be readable from the two
statements alone. Do not report pairs that merely talk about the same subject,
and do not report a rule together with a condition that scopes it: that is not
a conflict. If there are no conflicts, return [].
"""


def norm(text: str) -> str:
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    # Collapse *all* whitespace, newlines included: that is the same
    # convention check_claims.py verifies, so "verbatim" means one thing.
    text = re.sub(r"\s+", " ", text)
    return text.strip()


HEADING_NUMBERED = re.compile(
    r"^\s*(?:ARTICLE\s+|Article\s+)?(?:\d+(?:\.\d+)*\.?|[IVXLC]+\.|[A-Z]\.)\s+\S"
)
HEADING_SHORT = re.compile(r"^[A-Z][A-Za-z0-9 ,'&()\-/]{2,70}$")


def looks_like_heading(line: str) -> bool:
    stripped = line.strip()
    if not stripped or len(stripped) > 90:
        return False
    if stripped.endswith((".", ";", ":", ",")):
        return False
    words = stripped.split()
    if len(words) > 7:
        return False
    # A parenthetical line is usually a table row ("... (typically 72 hours)"),
    # not a title; keep it in the body so it can carry a claim.
    if stripped.endswith(")") and not HEADING_NUMBERED.match(stripped):
        return False
    if HEADING_NUMBERED.match(stripped):
        return True
    # ALL CAPS or Title Case with no terminal punctuation and few words.
    letters = [c for c in stripped if c.isalpha()]
    if letters and sum(1 for c in letters if c.isupper()) / len(letters) > 0.6:
        return True
    return bool(HEADING_SHORT.match(stripped)) and len(words) <= 8


def split_sentences(text: str, limit: int = 700) -> list[str]:
    """Split a block into sentence windows of at most roughly ``limit`` chars."""
    parts = re.split(r"(?<=[.;:])\s+", text)
    out: list[str] = []
    current = ""
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if current and len(current) + 1 + len(part) > limit:
            out.append(current)
            current = part
        else:
            current = f"{current} {part}".strip()
    if current:
        out.append(current)
    return out


def segment(text: str, doc_id: str, min_chars: int = 60) -> list[dict]:
    """Turn a document into spans with ids and locators. No model involved.

    Short blocks are merged with their neighbours instead of dropped: tabular
    runbooks state their rules in lines like "Response time: 1 hour", and
    discarding those would remove the very content the benchmark is about.
    """
    spans: list[dict] = []
    page = 1
    section_stack: list[tuple[int, str]] = []
    pending: list[str] = []
    short_buffer: list[str] = []

    def emit(piece: str) -> None:
        # A span must carry words: table rules, arrows and page numbers are not
        # claims, and a span with no letters only wastes prompt space.
        if not re.search(r"[A-Za-z]{3,}", piece):
            return
        if BOILERPLATE.search(piece):
            return
        spans.append(
            {
                "span_id": f"S{len(spans) + 1:04d}",
                "doc_id": doc_id,
                "paragraph": piece,
                "locator": {
                    "kind": DOCS[doc_id]["kind"],
                    "page": page,
                    "section_path": [title for _, title in section_stack][-3:],
                    "url": DOCS[doc_id]["url"],
                },
            }
        )

    def flush_short() -> None:
        nonlocal short_buffer
        if short_buffer:
            merged = norm(" ".join(short_buffer))
            short_buffer = []
            if len(merged) >= 20:
                emit(merged)

    def flush() -> None:
        nonlocal pending, short_buffer
        if not pending:
            return
        block = norm(" ".join(pending))
        pending = []
        if len(block) < min_chars:
            short_buffer.append(block)
            if len(" ".join(short_buffer)) >= min_chars:
                flush_short()
            return
        flush_short()
        for piece in split_sentences(block):
            if len(piece) >= min_chars:
                emit(piece)

    # splitlines() also splits on form feed, which is how pages are encoded
    # here, so split on newlines only and handle \f explicitly.
    for raw_line in text.split("\n"):
        if "\f" in raw_line:
            flush()
            flush_short()
            page += raw_line.count("\f")
            continue
        stripped = raw_line.strip()
        if not stripped:
            flush()
            continue
        if looks_like_heading(stripped):
            flush()
            flush_short()
            # Keep a shallow stack: a numbered heading pops to its own depth.
            match = re.match(r"^\s*(?:ARTICLE\s+|Article\s+)?((?:\d+|[IVXLC]+|[A-Z]))(?:\.\d+)*\.?\s", stripped)
            depth = 1
            if match:
                raw = stripped.split()[0].rstrip(".")
                depth = raw.count(".") + 1
            while section_stack and section_stack[-1][0] >= depth:
                section_stack.pop()
            section_stack.append((depth, stripped[:90]))
            continue
        pending.append(stripped)
    flush()
    flush_short()

    # Char offsets index the whitespace-normalised source (the same string the
    # verbatim check uses). They are a convenience, not the identity of a span;
    # page + section path + url are the stable part.
    flat = norm(text)
    cursor = 0
    for span in spans:
        found = flat.find(span["paragraph"], cursor)
        if found == -1:
            found = flat.find(span["paragraph"])
        if found != -1:
            span["locator"]["char_start"] = found
            span["locator"]["char_end"] = found + len(span["paragraph"])
            cursor = found + len(span["paragraph"])
    return spans


def chunk(spans: list[dict], size: int, overlap: int = 1) -> list[list[dict]]:
    if size <= 0:
        return [spans]
    out = []
    step = max(1, size - overlap)
    for start in range(0, len(spans), step):
        block = spans[start : start + size]
        if block:
            out.append(block)
        if start + size >= len(spans):
            break
    return out


def make_prompt(spans: list[dict], doc_id: str) -> str:
    lines = [f"DOCUMENT: {DOCS[doc_id]['context']['source']} ({doc_id})", ""]
    for span in spans:
        path = " > ".join(span["locator"].get("section_path") or [])
        header = f"[{span['span_id']}]" + (f" {path}" if path else "")
        lines.append(header)
        lines.append(span["paragraph"])
        lines.append("")
    lines.append("Return the JSON array of claims now. JSON only, no prose.")
    return "\n".join(lines)


def parse_claims(text: str) -> list[dict]:
    """Extract the first JSON array from a model reply, tolerating fences."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("["), text.rfind("]")
        if start == -1 or end == -1:
            return []
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return []
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def parse_conflicts(reply: str, valid_ids: set[str]) -> list[tuple[str, str]]:
    """Parse and validate conflict pairs. Symmetry is enforced by the caller."""
    text = reply.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("["), text.rfind("]")
        if start == -1 or end == -1:
            return []
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return []
    if not isinstance(data, list):
        return []
    pairs: list[tuple[str, str]] = []
    for item in data:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            continue
        left, right = str(item[0]).strip(), str(item[1]).strip()
        if left == right or left not in valid_ids or right not in valid_ids:
            continue
        pair = tuple(sorted((left, right)))
        if pair not in pairs:
            pairs.append(pair)
    return pairs


def link_conflicts(claims: list[dict], reply: str) -> int:
    """Set conflicts_with in both directions. Returns the number of pairs linked."""
    by_id = {c["claim_id"]: c for c in claims}
    pairs = parse_conflicts(reply, set(by_id))
    for left, right in pairs:
        for a, b in ((left, right), (right, left)):
            existing = by_id[a].setdefault("conflicts_with", [])
            if b not in existing:
                existing.append(b)
    return len(pairs)


def conflict_prompt(claims: list[dict]) -> str:
    lines = ["CLAIMS:"]
    for claim in claims:
        extra = f" (deadline: {claim['deadline']})" if claim.get("deadline") else ""
        lines.append(f"[{claim['claim_id']}] {claim['statement']}{extra}")
    lines.append("")
    lines.append("Return the JSON array of conflicting id pairs now.")
    return "\n".join(lines)


def call_model(prompt: str, args, system: str = SYSTEM) -> tuple[str, dict]:
    import requests

    key = os.environ.get("OPENAI_API_KEY", "")
    url = (args.base_url or os.environ.get("OPENAI_BASE_URL", "")).rstrip("/")
    if not url:
        raise SystemExit("no base URL: set OPENAI_BASE_URL or pass --base-url")
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    payload = {
        "model": args.model,
        "temperature": 0,
        "max_tokens": args.max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    }
    last = ""
    for attempt in range(4):
        try:
            resp = requests.post(f"{url}/chat/completions", headers=headers, json=payload, timeout=300)
        except requests.RequestException as exc:
            last = str(exc)
            time.sleep(2 * (attempt + 1))
            continue
        if resp.status_code in {408, 409, 429, 500, 502, 503, 504}:
            last = f"HTTP {resp.status_code}"
            time.sleep(2 * (attempt + 1))
            continue
        if resp.status_code >= 400:
            raise SystemExit(f"HTTP {resp.status_code}: {resp.text[:400]}")
        data = resp.json()
        choice = (data.get("choices") or [{}])[0]
        content = (choice.get("message") or {}).get("content") or ""
        usage = data.get("usage") or {}
        return content, {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
        }
    raise SystemExit(f"model call failed after retries: {last}")


def statement_key(statement: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", statement.lower()).strip()


def build_claim(raw: dict, span_by_id: dict[str, dict], doc_id: str, number: int) -> dict | None:
    ids = raw.get("span_ids") or raw.get("spans") or []
    if isinstance(ids, str):
        ids = [ids]
    ids = [str(i).strip().strip("[]") for i in ids]
    spans = [span_by_id[i] for i in ids if i in span_by_id]
    if not spans:
        return None
    statement = norm(str(raw.get("statement", "")))
    if len(statement) < 15:
        return None
    modality = str(raw.get("modality", "")).strip().lower()
    if modality not in MODALITIES:
        modality = "definition" if modality in {"fact", "rule", "statement"} else "obligation"
    evidence = []
    seen: set[str] = set()
    for span in spans:
        if span["paragraph"] in seen:
            continue
        seen.add(span["paragraph"])
        evidence.append({"quote": span["paragraph"], "locator": dict(span["locator"]), "role": "supports"})
    if not evidence:
        return None
    claim = {
        "claim_id": f"{doc_id}-{number:04d}",
        "doc_id": doc_id,
        "statement": statement,
        "modality": modality,
    }
    for field in ("actor", "deadline", "subject", "predicate", "object"):
        value = raw.get(field)
        if isinstance(value, str) and value.strip():
            claim[field] = norm(value)
    conditions = raw.get("conditions")
    if isinstance(conditions, list):
        cleaned = [norm(str(c)) for c in conditions if str(c).strip()]
        if cleaned:
            claim["conditions"] = cleaned
    claim["evidence"] = evidence
    claim["context"] = dict(DOCS[doc_id]["context"])
    return to_v2(claim)


def estimate(spans: list[dict], chunks: list[list[dict]], args, conflicts: bool = True) -> dict:
    prompt_chars = sum(len(make_prompt(c, c[0]["doc_id"])) for c in chunks if c)
    # ~3.6 chars/token for English, plus the system prompt on every call.
    input_tokens = int(prompt_chars / 3.6 + 900 * len(chunks))
    output_tokens = int(len(spans) * 45)
    calls = len(chunks)

    # The conflict pass is one small call per document: claim id + statement,
    # and a short array of pairs.
    conflict_calls = 0
    if conflicts:
        docs = {c[0]["doc_id"] for c in chunks if c}
        claims_est = max(1, len(spans) // 3)
        conflict_calls = len(docs)
        calls += conflict_calls
        input_tokens += claims_est * 25 + 700 * len(docs)
        output_tokens += 40 * len(docs)

    return {
        "calls": calls,
        "extraction_calls": len(chunks),
        "conflict_calls": conflict_calls,
        "prompt_chars": prompt_chars,
        "input_tokens_est": input_tokens,
        "output_tokens_est": output_tokens,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--docs", default="D1,D2,D3,D4")
    ap.add_argument("--out", default=str(GOLD / "claims.compiled.jsonl"))
    ap.add_argument("--spans-out", default="", help="Write the span list here (default: <out>.spans.jsonl)")
    ap.add_argument("--backend", choices=["http", "dry-run"], default="http")
    ap.add_argument("--model", default=os.environ.get("DOCBENCH_MODEL") or os.environ.get("OPENAI_MODEL", ""))
    ap.add_argument("--base-url", default=os.environ.get("OPENAI_BASE_URL", ""))
    ap.add_argument("--chunk-size", type=int, default=40, help="Spans per request")
    ap.add_argument("--overlap", type=int, default=2, help="Spans repeated between requests")
    ap.add_argument("--min-chars", type=int, default=60)
    ap.add_argument("--max-tokens", type=int, default=4096)
    ap.add_argument("--conflicts", dest="conflicts", action="store_true", default=True,
                    help="Second pass that links contradicting claims (default: on)")
    ap.add_argument("--no-conflicts", dest="conflicts", action="store_false")
    ap.add_argument("--dry-run", action="store_true", help="Segment and estimate only")
    ap.add_argument("--estimate", action="store_true", help="Estimate tokens and stop (implies --dry-run)")
    args = ap.parse_args()

    if args.estimate:
        args.dry_run = True
    if not args.model and not args.dry_run:
        raise SystemExit("no model: pass --model or set OPENAI_MODEL")

    doc_ids = [d.strip() for d in args.docs.split(",") if d.strip()]
    all_spans: list[dict] = []
    per_doc_spans: dict[str, list[dict]] = {}
    for doc_id in doc_ids:
        path = PRIVATE / DOCS[doc_id]["file"]
        if not path.exists():
            raise SystemExit(f"missing source: {path}")
        spans = segment(path.read_text(encoding="utf-8", errors="ignore"), doc_id, args.min_chars)
        per_doc_spans[doc_id] = spans
        all_spans.extend(spans)
        print(f"{doc_id}: {len(spans)} spans, {sum(len(s['paragraph']) for s in spans)} chars")

    chunks: list[list[dict]] = []
    for doc_id in doc_ids:
        chunks.extend(chunk(per_doc_spans[doc_id], args.chunk_size, args.overlap))

    est = estimate(all_spans, chunks, args, conflicts=args.conflicts)
    print(
        f"\ncalls: {est['calls']} ({est['extraction_calls']} extraction"
        f" + {est['conflict_calls']} conflicts)  "
        f"input tokens (est): {est['input_tokens_est']:,}  "
        f"output tokens (est): {est['output_tokens_est']:,}"
    )
    usd_in = est["input_tokens_est"] / 1_000_000 * 0.15
    usd_out = est["output_tokens_est"] / 1_000_000 * 0.60
    print(f"cost at $0.15/M in, $0.60/M out: ${usd_in + usd_out:.4f}")

    spans_out = Path(args.spans_out) if args.spans_out else Path(str(args.out) + ".spans.jsonl")
    spans_out.parent.mkdir(parents=True, exist_ok=True)
    spans_out.write_text(
        "".join(json.dumps(s, ensure_ascii=False) + "\n" for s in all_spans), encoding="utf-8"
    )
    print(f"wrote spans: {spans_out}")

    if args.dry_run:
        if chunks:
            print(f"\n--- first prompt (chunk 1/{len(chunks)}) ---\n")
            print(make_prompt(chunks[0], chunks[0][0]["doc_id"])[:2500])
        return 0

    # Span ids are per document, so the lookup is per document.
    per_doc_by_id = {
        doc_id: {s["span_id"]: s for s in spans} for doc_id, spans in per_doc_spans.items()
    }

    claims: list[dict] = []
    seen_statements: set[str] = set()
    totals = {"input_tokens": 0, "output_tokens": 0}
    rejected = 0
    for index, block in enumerate(chunks, start=1):
        doc_id = block[0]["doc_id"]
        prompt = make_prompt(block, doc_id)
        reply, usage = call_model(prompt, args)
        totals["input_tokens"] += usage["input_tokens"]
        totals["output_tokens"] += usage["output_tokens"]
        parsed = parse_claims(reply)
        kept = 0
        for raw in parsed:
            claim = build_claim(raw, per_doc_by_id[doc_id], doc_id, len(claims) + 1)
            if claim is None:
                rejected += 1
                continue
            key = statement_key(claim["statement"])
            if key in seen_statements:
                rejected += 1
                continue
            seen_statements.add(key)
            claims.append(claim)
            kept += 1
        print(
            f"[{index}/{len(chunks)}] {doc_id} spans={len(block)} parsed={len(parsed)} "
            f"kept={kept} tokens={usage['input_tokens']}+{usage['output_tokens']}"
        )

    conflict_pairs = 0
    if args.conflicts:
        for doc_id in doc_ids:
            doc_claims = [c for c in claims if c["doc_id"] == doc_id]
            if len(doc_claims) < 2:
                continue
            reply, usage = call_model(conflict_prompt(doc_claims), args, CONFLICT_SYSTEM)
            totals["input_tokens"] += usage["input_tokens"]
            totals["output_tokens"] += usage["output_tokens"]
            linked = link_conflicts(doc_claims, reply)
            conflict_pairs += linked
            print(f"conflicts {doc_id}: {linked} pair(s) of {len(doc_claims)} claims")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in claims), encoding="utf-8")

    manifest = {
        "model": args.model,
        "base_url": args.base_url,
        "docs": doc_ids,
        "chunk_size": args.chunk_size,
        "overlap": args.overlap,
        "min_chars": args.min_chars,
        "chunks": len(chunks),
        "spans": len(all_spans),
        "claims": len(claims),
        "rejected": rejected,
        "conflict_pairs": conflict_pairs,
        "input_tokens": totals["input_tokens"],
        "output_tokens": totals["output_tokens"],
        "spans_sha256": hashlib.sha256(spans_out.read_bytes()).hexdigest(),
        "claims_sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
        "claims_by_doc": {d: sum(1 for c in claims if c["doc_id"] == d) for d in doc_ids},
    }
    Path(str(out) + ".manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"\nwrote {len(claims)} claims -> {out}")
    print(json.dumps(manifest, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
