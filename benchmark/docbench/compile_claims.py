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
from env import load_dotenv  # noqa: E402

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

Keep the JSON compact: one object per line, no extra keys, no explanation.

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
# A table block opened by an ALL-CAPS label is closed and reopened past this
# length, so one label can never swallow a whole document.
TABLE_BLOCK_CHARS = 700


# An ALL-CAPS label with a trailing qualifier, e.g. "CRITICAL (Red)". This is
# the shape a flattened HTML table gives to a column/band header, and it is
# what distinguishes it from an ordinary section title such as "PURPOSE".
TABLE_LABEL = re.compile(r"^[A-Z][A-Z0-9 &/\-.,']{1,40}\s*\([^)]{1,40}\)$")


def is_table_label(line: str) -> bool:
    """True for an ALL-CAPS label with a qualifier that heads a table block.

    Severity bands arrive from HTML as ``CRITICAL (Red)`` followed by their
    rows. The label is the only thing that says what the rows mean, so it has
    to travel with them instead of becoming a heading that the next row
    immediately replaces.
    """
    return bool(TABLE_LABEL.match(line.strip()))


def looks_like_heading(line: str) -> bool:
    stripped = line.strip()
    if not stripped or len(stripped) > 90:
        return False
    if stripped.endswith((".", ";", ":", ",")):
        return False
    words = stripped.split()
    if len(words) > 7:
        return False
    if is_table_label(stripped):
        return True
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
    # Lines of the table block opened by an ALL-CAPS label, or None.
    table_block: list[str] | None = None

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

    def flush_table(reopen: bool = False) -> None:
        """Emit the open table block: the label plus the rows it governs.

        The rows of a flattened HTML table are meaningless on their own —
        "Response time : 1 hour" says nothing about which band it belongs to.
        The label is the row's meaning, so it stays in the same span.
        """
        nonlocal table_block
        if not table_block:
            table_block = None
            return
        block = norm(" ".join(table_block))
        label = table_block[0]
        table_block = [label] if reopen else None
        emit(block)

    # splitlines() also splits on form feed, which is how pages are encoded
    # here, so split on newlines only and handle \f explicitly.
    for raw_line in text.split("\n"):
        if "\f" in raw_line:
            flush()
            flush_short()
            flush_table()
            page += raw_line.count("\f")
            continue
        stripped = raw_line.strip()
        if not stripped:
            # A blank line separates rows in flattened HTML, not blocks: do not
            # close the table here.
            flush()
            continue
        # Inside an open table block every short line is a row — including the
        # ones that look like headings, because a flattened HTML table ships its
        # cells as separate <div>s. The block is closed by its next label or by
        # a "key : value" terminator row, never by the shape of a cell.
        in_block = table_block is not None and not is_table_label(stripped)
        if looks_like_heading(stripped) and not in_block:
            flush()
            flush_short()
            flush_table()
            # Keep a shallow stack: a numbered heading pops to its own depth.
            match = re.match(r"^\s*(?:ARTICLE\s+|Article\s+)?((?:\d+|[IVXLC]+|[A-Z]))(?:\.\d+)*\.?\s", stripped)
            depth = 1
            if match:
                raw = stripped.split()[0].rstrip(".")
                depth = raw.count(".") + 1
            while section_stack and section_stack[-1][0] >= depth:
                section_stack.pop()
            section_stack.append((depth, stripped[:90]))
            if is_table_label(stripped):
                table_block = [stripped]
            continue
        if table_block is not None:
            table_block.append(stripped)
            # A "key : value" row is the terminator of a table record: the
            # severity band ends with its "Response time : ..." line, and the
            # next thing in the document is either the next band or a real
            # section heading.
            if re.search(r"\s:\s", stripped):
                flush_table()
                continue
            if len(norm(" ".join(table_block))) > TABLE_BLOCK_CHARS:
                # Never let a label swallow a whole document: close the block
                # and reopen it with the label repeated.
                flush_table(reopen=True)
            continue
        pending.append(stripped)
    flush()
    flush_short()
    flush_table()

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


def repair_json_array(text: str) -> list[dict]:
    """Recover the JSON objects from a malformed or truncated reply.

    Two failure modes are common with reasoning models behind a gateway:

    * the separating comma between two objects is dropped (``}{``);
    * the reply is cut in the middle of an object, while the objects before
      it are complete.

    Both are recoverable without inventing anything: the objects that survive
    are still model output, and every one of them is validated afterwards
    against real span ids.
    """
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    start = text.find("[")
    if start == -1:
        return []
    body = text[start:]
    end = body.rfind("]")
    if end != -1:
        body = body[: end + 1]

    def close_objects(piece: str) -> str:
        return re.sub(r"\}\s*(?=\{)", "},", piece)

    for candidate in (body, close_objects(body), re.sub(r",\s*\]", "]", close_objects(body))):
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]

    # Salvage: keep the complete top-level objects of a truncated reply.
    depth = 0
    last_complete = -1
    in_string = False
    escaped = False
    for index, char in enumerate(body):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "[{":
            depth += 1
        elif char in "]}":
            depth -= 1
            if char == "}" and depth == 1:
                last_complete = index
    if last_complete > 0:
        try:
            data = json.loads(close_objects(body[: last_complete + 1]) + "]")
        except json.JSONDecodeError:
            return []
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
    return []


def parse_claims(text: str) -> list[dict]:
    """Extract the JSON array from a model reply, tolerating fences and damage."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("["), text.rfind("]")
        if start == -1 or end == -1:
            return repair_json_array(text)
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return repair_json_array(text)
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def parse_pair_indices(reply: str, count: int) -> list[int]:
    """Parse a JSON array of pair numbers (1-based), validated against count."""
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
    out: list[int] = []
    for item in data:
        try:
            index = int(item)
        except (TypeError, ValueError):
            continue
        if 1 <= index <= count and index not in out:
            out.append(index)
    return out


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


STOP = set(
    "the a an and or of to in on for by with from as at is are was were be been being that this these those "
    "it its their his her shall must may can will would should not no any all such other which who whom whose".split()
)


def tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOP and len(t) > 2}


def conflict_candidates(claims: list[dict], k: int = 3, floor: float = 0.12) -> list[tuple[str, str]]:
    """Cheap local candidate generation: a contradiction is usually between two
    claims that talk about the same thing. The model then only confirms or
    rejects a numbered pair list, instead of comparing every claim to every
    other one (which made it exhaust its reasoning budget and return nothing).
    """
    sets = {c["claim_id"]: tokens(c["statement"] + " " + str(c.get("deadline") or "")) for c in claims}
    scored: dict[tuple[str, str], float] = {}
    ids = list(sets)
    for i, left in enumerate(ids):
        for right in ids[i + 1 :]:
            a, b = sets[left], sets[right]
            if not a or not b:
                continue
            score = len(a & b) / len(a | b)
            if score >= floor:
                scored[(left, right)] = score
    per_claim: dict[str, int] = {}
    picked: list[tuple[str, str, float]] = []
    for (left, right), score in sorted(scored.items(), key=lambda kv: -kv[1]):
        if per_claim.get(left, 0) >= k or per_claim.get(right, 0) >= k:
            continue
        per_claim[left] = per_claim.get(left, 0) + 1
        per_claim[right] = per_claim.get(right, 0) + 1
        picked.append((left, right, score))
    return [(left, right) for left, right, _ in picked]


def pairs_prompt(claims: list[dict], pairs: list[tuple[str, str]]) -> str:
    by_id = {c["claim_id"]: c for c in claims}
    lines = ["PAIRS:"]
    for index, (left, right) in enumerate(pairs, start=1):
        lines.append(f"{index}. [{left}] {by_id[left]['statement']}")
        lines.append(f"   [{right}] {by_id[right]['statement']}")
    lines.append("")
    lines.append("Return the JSON array of pair numbers that contradict each other, e.g. [3,7]. JSON only.")
    return "\n".join(lines)


def call_model(prompt: str, args, system: str = SYSTEM) -> tuple[str, dict, str]:
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
    # The gateway drops long runs with 503s, often several in a row. Six
    # attempts with widening backoff is cheaper than losing a 20-minute run.
    for attempt in range(6):
        try:
            resp = requests.post(f"{url}/chat/completions", headers=headers, json=payload, timeout=300)
        except requests.RequestException as exc:
            last = str(exc)
            time.sleep(min(30, 3 * (attempt + 1)))
            continue
        if resp.status_code in {408, 409, 429, 500, 502, 503, 504}:
            last = f"HTTP {resp.status_code}"
            time.sleep(min(30, 3 * (attempt + 1)))
            continue
        if resp.status_code >= 400:
            raise SystemExit(f"HTTP {resp.status_code}: {resp.text[:400]}")
        data = resp.json()
        choice = (data.get("choices") or [{}])[0]
        content = (choice.get("message") or {}).get("content") or ""
        usage = data.get("usage") or {}
        finish = str(choice.get("finish_reason") or "")
        return content, {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
        }, finish
    raise SystemExit(f"model call failed after retries: {last}")


def statement_key(statement: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", statement.lower()).strip()


def dedupe_claims(claims: list[dict], threshold: float = 0.85) -> tuple[list[dict], int]:
    """Merge claims that state the same rule twice.

    Consecutive chunks overlap by two spans, so the same rule is often
    extracted twice and paraphrased slightly ("must"/"shall"). Exact
    statement matching does not catch that, and a duplicated rule crowds a
    retrieval budget that should cover different rules.

    Only near-identical statements inside one document are merged, and the
    survivor keeps the union of the evidence: a merge never deletes support.
    """
    by_doc: dict[str, list[dict]] = {}
    for claim in claims:
        by_doc.setdefault(claim["doc_id"], []).append(claim)

    kept: list[dict] = []
    merged_count = 0
    for doc_claims in by_doc.values():
        token_sets = [tokens(c["statement"]) for c in doc_claims]
        absorbed: set[int] = set()
        for i, claim in enumerate(doc_claims):
            if i in absorbed:
                continue
            for j in range(i + 1, len(doc_claims)):
                if j in absorbed:
                    continue
                left, right = token_sets[i], token_sets[j]
                if not left or not right:
                    continue
                if len(left & right) / len(left | right) < threshold:
                    continue
                other = doc_claims[j]
                quotes = {e["quote"] for e in claim.get("evidence", [])}
                for evidence in other.get("evidence", []):
                    if evidence["quote"] not in quotes:
                        claim.setdefault("evidence", []).append(evidence)
                        quotes.add(evidence["quote"])
                for field in ("actor", "deadline", "subject", "predicate", "object"):
                    if not claim.get(field) and other.get(field):
                        claim[field] = other[field]
                conditions = claim.setdefault("conditions", [])
                for condition in other.get("conditions", []) or []:
                    if condition not in conditions:
                        conditions.append(condition)
                if not conditions:
                    claim.pop("conditions", None)
                conflicts = claim.setdefault("conflicts_with", [])
                for conflict in other.get("conflicts_with", []) or []:
                    if conflict not in conflicts:
                        conflicts.append(conflict)
                if not conflicts:
                    claim.pop("conflicts_with", None)
                absorbed.add(j)
                merged_count += 1
        kept.extend(c for index, c in enumerate(doc_claims) if index not in absorbed)
    kept.sort(key=lambda c: (c["doc_id"], int(c["claim_id"].split("-")[-1])))
    return kept, merged_count


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
    load_dotenv()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--docs", default="D1,D2,D3,D4")
    ap.add_argument("--out", default=str(GOLD / "claims.compiled.jsonl"))
    ap.add_argument("--spans-out", default="", help="Write the span list here (default: <out>.spans.jsonl)")
    ap.add_argument("--backend", choices=["http", "dry-run"], default="http")
    ap.add_argument("--model", default=os.environ.get("DOCBENCH_MODEL") or os.environ.get("OPENAI_MODEL", ""))
    ap.add_argument("--base-url", default=os.environ.get("OPENAI_BASE_URL", ""))
    ap.add_argument("--chunk-size", type=int, default=15, help="Spans per request")
    ap.add_argument("--overlap", type=int, default=2, help="Spans repeated between requests")
    ap.add_argument("--min-chars", type=int, default=60)
    ap.add_argument("--max-tokens", type=int, default=10000)
    ap.add_argument("--resume", action="store_true",
                    help="Continue a previous run, skipping completed chunks")
    ap.add_argument("--retry-failed", action="store_true",
                    help="With --resume: redo the chunks touched by recorded failures")
    ap.add_argument("--conflicts", dest="conflicts", action="store_true", default=True,
                    help="Second pass that links contradicting claims (default: on)")
    ap.add_argument("--no-conflicts", dest="conflicts", action="store_false")
    ap.add_argument("--pair-batch", type=int, default=20, help="Candidate pairs per conflict request")
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

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    state_path = Path(str(out) + ".state.json")
    failures_path = Path(str(out) + ".failures.jsonl")

    claims: list[dict] = []
    counters: dict[str, int] = {}
    done_chunks: dict[str, int] = {}
    if args.resume and out.exists() and state_path.exists():
        claims = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines() if line.strip()]
        for claim in claims:
            doc = claim["doc_id"]
            counters[doc] = max(counters.get(doc, 0), int(claim["claim_id"].split("-")[-1]))
        done_chunks = json.loads(state_path.read_text(encoding="utf-8")).get("done", {})
        print(f"resuming: {len(claims)} claims, {len(done_chunks)} chunk(s) already done")
        # Keep the accounting honest across invocations: tokens already spent
        # belong in the manifest of the finished artifact.
        prior_manifest = Path(str(out) + ".manifest.json")
        if prior_manifest.exists():
            prior = json.loads(prior_manifest.read_text(encoding="utf-8"))
            prior_totals = {
                "input_tokens": prior.get("input_tokens", 0),
                "output_tokens": prior.get("output_tokens", 0),
            }
            prior_rejected = prior.get("rejected", 0)
            prior_counts = {
                "truncated_retries": prior.get("truncated_retries", 0),
                "duplicates_merged": prior.get("duplicates_merged", 0),
                "conflict_pairs": prior.get("conflict_pairs", 0),
                "conflict_batch_failures": prior.get("conflict_batch_failures", 0),
            }
        else:
            prior_totals = {"input_tokens": 0, "output_tokens": 0}
            prior_rejected = 0
            prior_counts = {}
    else:
        counters = {}
        prior_totals = {"input_tokens": 0, "output_tokens": 0}
        prior_rejected = 0
        prior_counts = {}

    seen_statements: set[str] = {statement_key(c["statement"]) for c in claims}
    totals = dict(prior_totals)
    rejected = prior_rejected
    # These describe the whole artifact, not one invocation, so a resumed run
    # adds to what the previous invocation already recorded.
    truncated = prior_counts.get("truncated_retries", 0)
    duplicates_merged = prior_counts.get("duplicates_merged", 0)
    if not (args.resume and done_chunks):
        failures_path.write_text("", encoding="utf-8")

    if args.retry_failed and failures_path.exists():
        failed_spans: set[str] = set()
        for line in failures_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                failed_spans.update(json.loads(line).get("span_ids") or [])
        reset = 0
        for block in chunks:
            key = f"{block[0]['doc_id']}:{block[0]['span_id']}-{block[-1]['span_id']}"
            if key in done_chunks and any(span["span_id"] in failed_spans for span in block):
                del done_chunks[key]
                reset += 1
        print(f"retry: {reset} chunk(s) reset, touching {len(failed_spans)} recorded span(s)")

    def save() -> None:
        out.write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in claims), encoding="utf-8")
        state_path.write_text(json.dumps({"done": done_chunks}, indent=1), encoding="utf-8")

    def record_failure(doc_id: str, block: list[dict], reply: str, reason: str) -> None:
        with failures_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "doc_id": doc_id,
                "span_ids": [s["span_id"] for s in block],
                "reason": reason,
                "reply": reply[:4000],
            }, ensure_ascii=False) + "\n")

    def absorb_objects(doc_id: str, parsed: list[dict]) -> int:
        """Turn parsed reply objects into claims. Returns how many were kept."""
        nonlocal rejected
        kept = 0
        for raw in parsed:
            counters[doc_id] = counters.get(doc_id, 0) + 1
            claim = build_claim(raw, per_doc_by_id[doc_id], doc_id, counters[doc_id])
            if claim is None:
                counters[doc_id] -= 1
                rejected += 1
                continue
            key = statement_key(claim["statement"])
            if key in seen_statements:
                counters[doc_id] -= 1
                rejected += 1
                continue
            seen_statements.add(key)
            claims.append(claim)
            kept += 1
        return kept

    def absorb(doc_id: str, block: list[dict]) -> tuple[int, int]:
        """Extract from one block, salvaging what is complete and retrying the rest."""
        nonlocal truncated
        prompt = make_prompt(block, doc_id)
        reply, usage, finish = call_model(prompt, args)
        totals["input_tokens"] += usage["input_tokens"]
        totals["output_tokens"] += usage["output_tokens"]

        cut_off = finish == "length" or (bool(reply.strip()) and not reply.strip().endswith("]"))
        parsed = parse_claims(reply)
        kept = absorb_objects(doc_id, parsed)
        if not parsed and reply.strip() not in ("[]", ""):
            record_failure(doc_id, block, reply, "unparseable")

        # A reply cut in the middle is not "this block has no rules". Keep the
        # objects that arrived complete, and ask again only for the spans they
        # do not cover.
        if cut_off:
            truncated += 1
            record_failure(doc_id, block, reply, f"truncated (finish={finish or 'unknown'})")
            covered = {
                str(span_id).strip().strip("[]")
                for raw in parsed
                for span_id in (raw.get("span_ids") or raw.get("spans") or [])
            }
            remaining = [span for span in block if span["span_id"] not in covered]
            if remaining and len(block) > 1:
                middle = len(remaining) // 2
                first, _ = absorb(doc_id, remaining[:middle])
                second, _ = absorb(doc_id, remaining[middle:])
                return kept + first + second, len(parsed)
        return kept, len(parsed)

    for index, block in enumerate(chunks, start=1):
        doc_id = block[0]["doc_id"]
        chunk_key = f"{doc_id}:{block[0]['span_id']}-{block[-1]['span_id']}"
        if chunk_key in done_chunks:
            continue
        before = (totals["input_tokens"], totals["output_tokens"])
        kept, parsed = absorb(doc_id, block)
        done_chunks[chunk_key] = kept
        save()
        print(
            f"[{index}/{len(chunks)}] {doc_id} spans={len(block)} parsed={parsed} "
            f"kept={kept} tokens={totals['input_tokens'] - before[0]}+"
            f"{totals['output_tokens'] - before[1]}"
        )

    claims, newly_merged = dedupe_claims(claims)
    duplicates_merged += newly_merged
    if newly_merged:
        seen_statements = {statement_key(c["statement"]) for c in claims}
        print(f"dedupe: merged {newly_merged} near-duplicate claim(s) -> {len(claims)} claims")
    save()

    conflict_pairs = prior_counts.get("conflict_pairs", 0)
    conflict_failures = prior_counts.get("conflict_batch_failures", 0)
    if args.conflicts:
        by_doc_claims: dict[str, list[dict]] = {}
        for claim in claims:
            by_doc_claims.setdefault(claim["doc_id"], []).append(claim)
        for doc_id in doc_ids:
            doc_claims = by_doc_claims.get(doc_id, [])
            if len(doc_claims) < 2:
                continue
            pairs = conflict_candidates(doc_claims)
            linked = 0
            failed = 0
            for start in range(0, len(pairs), args.pair_batch):
                batch = pairs[start : start + args.pair_batch]
                try:
                    reply, usage, finish = call_model(pairs_prompt(doc_claims, batch), args, CONFLICT_SYSTEM)
                except SystemExit as exc:
                    # The gateway drops long runs with 503s. Losing one batch of
                    # 20 candidate pairs must not lose the other 100 claims.
                    failed += 1
                    record_failure(doc_id, [], str(exc), "conflict batch failed")
                    print(f"  conflicts {doc_id}: batch {start // args.pair_batch + 1} failed ({exc})")
                    continue
                totals["input_tokens"] += usage["input_tokens"]
                totals["output_tokens"] += usage["output_tokens"]
                chosen = parse_pair_indices(reply, len(batch))
                if finish == "length" and not chosen:
                    print(f"  conflicts {doc_id}: batch of {len(batch)} pairs hit the token limit, skipped")
                    continue
                selected = [batch[i - 1] for i in chosen]
                linked += link_conflicts(doc_claims, json.dumps([[a, b] for a, b in selected]))
            conflict_pairs += linked
            conflict_failures += failed
            print(
                f"conflicts {doc_id}: {linked} pair(s) confirmed from {len(pairs)} candidate(s), "
                f"{len(doc_claims)} claims" + (f", {failed} batch(es) failed" if failed else "")
            )

    save()

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
        "duplicates_merged": duplicates_merged,
        "truncated_retries": truncated,
        "conflict_pairs": conflict_pairs,
        "conflict_batch_failures": conflict_failures,
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
