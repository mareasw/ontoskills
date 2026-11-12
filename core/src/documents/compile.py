"""Compile a segmented document into evidence-backed claims.

This is the product copy of the pipeline accepted in ADR 0002 Phase 1. The
benchmark script stays frozen so its measurements remain reproducible; the
parity test in ``core/tests/test_documents_segment.py`` keeps the segmenter from
drifting.

The compiler never writes a quote. It copies it from the span the model
selected, so the verbatim guarantee is structural, not a post-hoc repair.
"""

from __future__ import annotations

import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from compiler.documents.llm import ModelError, chat
from compiler.documents.model import Document
from compiler.documents.prompt import (
    CONFLICT_SYSTEM,
    MODALITIES,
    PROMPT_HASH,
    SYSTEM,
    make_prompt,
)
from compiler.documents.segment import chunk, lead_ins
from compiler.documents.text import modal_classes, norm, statement_tokens


@dataclass
class CompileOptions:
    model: str = ""
    base_url: str = ""
    api_key: str = ""
    chunk_size: int = 15
    overlap: int = 2
    max_tokens: int = 10000
    conflicts: bool = True
    concurrency: int = 1
    resume: bool = False
    price_in: float = 0.15
    price_out: float = 0.60
    cache_dir: Path | None = None
    dry_run: bool = False


@dataclass
class CompileStats:
    calls: int = 0
    cached: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    rejected: int = 0
    merged: int = 0
    truncated: int = 0
    failed: int = 0
    conflict_calls: int = 0

    def cost(self, options: CompileOptions) -> float:
        return (
            self.input_tokens / 1_000_000 * options.price_in
            + self.output_tokens / 1_000_000 * options.price_out
        )


@dataclass
class CompiledDocument:
    claims: list[dict]
    stats: CompileStats
    spans: list[dict] = field(default_factory=list)


def repair_json_array(text: str) -> list[dict]:
    """Recover the JSON objects from a malformed or truncated reply."""
    text = (text or "").strip()
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

    # Salvage complete top-level objects from a truncated reply.
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
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                last_complete = index
    if last_complete == -1:
        return []
    try:
        data = json.loads("[" + body[1 : last_complete + 1] + "]")
    except json.JSONDecodeError:
        return []
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


def parse_claims(text: str) -> list[dict]:
    """Parse a model reply into claim dicts, repairing common damage."""
    stripped = (text or "").strip()
    if not stripped:
        return []
    start = stripped.find("[")
    data: Any = None
    if start != -1:
        end = stripped.rfind("]")
        if start == -1 or end == -1:
            data = None
        else:
            try:
                data = json.loads(stripped[start : end + 1])
            except json.JSONDecodeError:
                data = None
    if data is None:
        return repair_json_array(stripped)
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def statement_key(statement: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", statement.lower()).strip()


def dedupe_claims(claims: list[dict], threshold: float = 0.85) -> tuple[list[dict], int]:
    """Merge near-identical statements within one document, keeping evidence.

    Claims are grouped by document: the same sentence in two documents is two
    claims with two citations, not one. A pair whose modality classes differ is
    never merged, even when the wording is otherwise identical: "must notify"
    and "may notify" are the same bag of words and opposite rules.
    """
    kept: list[dict] = []
    merged = 0
    by_doc: dict[str, list[dict]] = {}
    for claim in claims:
        by_doc.setdefault(claim["doc_id"], []).append(claim)

    for doc_claims in by_doc.values():
        token_sets = [set(statement_tokens(c["statement"])) for c in doc_claims]
        modal_sets = [modal_classes(c.get("statement", "")) for c in doc_claims]
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
                if modal_sets[i] and modal_sets[j] and modal_sets[i] != modal_sets[j]:
                    continue
                if len(left & right) / len(left | right) < threshold:
                    continue
                other = doc_claims[j]
                quotes = {e["quote"] for e in claim.get("evidence", [])}
                for evidence in other.get("evidence", []):
                    if evidence["quote"] not in quotes:
                        claim.setdefault("evidence", []).append(evidence)
                        quotes.add(evidence["quote"])
                for name in ("actor", "deadline", "subject", "predicate", "object"):
                    if not claim.get(name) and other.get(name):
                        claim[name] = other[name]
                conditions = claim.setdefault("conditions", [])
                for condition in other.get("conditions", []) or []:
                    if condition not in conditions:
                        conditions.append(condition)
                if not conditions:
                    claim.pop("conditions", None)
                absorbed.add(j)
                merged += 1
        kept.extend(c for index, c in enumerate(doc_claims) if index not in absorbed)
    return kept, merged


def build_claim(
    raw: dict[str, Any],
    span_by_id: dict[str, dict],
    doc: Document,
    number: int,
    lead_map: dict[str, dict] | None = None,
) -> dict | None:
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
        evidence.append(
            {"quote": span["paragraph"], "locator": dict(span["locator"]), "role": "supports"}
        )
    if not evidence:
        return None
    if lead_map:
        # A list item or a continuation carries no subject of its own: the model
        # read the lead-in in the chunk and its statement relies on it, so the
        # claim declares that reliance instead of leaving the verifier to find a
        # subject that is not in the quote. The quote is a verbatim span, never
        # an inference. Context comes after the supports items because the
        # statement is answered from ``evidence[0]``.
        cited = {item["quote"] for item in evidence}
        for span in spans:
            lead = lead_map.get(span["span_id"])
            if lead is None or lead["paragraph"] in cited:
                continue
            cited.add(lead["paragraph"])
            evidence.append(
                {"quote": lead["paragraph"], "locator": dict(lead["locator"]), "role": "context"}
            )
    claim: dict[str, Any] = {
        "claim_id": f"{doc.doc_id}-{number:04d}",
        "doc_id": doc.doc_id,
        "schema_version": 2,
        "statement": statement,
        "modality": modality,
    }
    for name in ("actor", "deadline", "subject", "predicate", "object"):
        value = raw.get(name)
        if isinstance(value, str) and value.strip():
            claim[name] = norm(value)
    conditions = raw.get("conditions")
    if isinstance(conditions, list):
        cleaned = [norm(str(c)) for c in conditions if str(c).strip()]
        if cleaned:
            claim["conditions"] = cleaned
    claim["evidence"] = evidence
    claim["context"] = dict(doc.context)
    return claim


def row_claims(spans: list[dict], doc: Document, start: int) -> list[dict]:
    """One deterministic claim per key/value row span the model did not cite.

    The statement is the printed label and value, with nothing paraphrased, so a
    row the model skipped still reaches the artifact.
    """
    out: list[dict] = []
    number = start
    for span in spans:
        row = span.get("row")
        if not row:
            continue
        label = norm(str(row.get("label", "")))
        value = norm(str(row.get("value", "")))
        if not label or not value:
            continue
        statement = f"{label}: {value}"
        if not statement.endswith((".", ";", "?", "!")):
            statement += "."
        out.append(
            {
                "claim_id": f"{doc.doc_id}-{number:04d}",
                "doc_id": doc.doc_id,
                "schema_version": 2,
                "statement": norm(statement),
                "modality": "definition",
                "evidence": [
                    {
                        "quote": span["paragraph"],
                        "locator": dict(span["locator"]),
                        "role": "supports",
                    }
                ],
                "context": dict(doc.context),
            }
        )
        number += 1
    return out


def _fingerprint(text: str, spans: list[dict], model: str) -> str:
    digest = hashlib.sha256()
    digest.update(PROMPT_HASH.encode())
    digest.update(model.encode())
    digest.update(text.encode("utf-8", errors="ignore"))
    for span in spans:
        digest.update(span["span_id"].encode())
    return digest.hexdigest()


def _cache_path(cache_dir: Path, doc_id: str, index: int) -> Path:
    return cache_dir / doc_id / f"{index:05d}.json"


def _read_cache(path: Path, fingerprint: str) -> dict | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if data.get("fingerprint") != fingerprint:
        return None
    return data


def _write_cache(path: Path, fingerprint: str, reply: str, usage: dict, finish: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"fingerprint": fingerprint, "reply": reply, "usage": usage, "finish": finish}
        ),
        encoding="utf-8",
    )


def _one_chunk(
    prompt: str,
    fingerprint: str,
    cache_path: Path | None,
    options: CompileOptions,
    system: str = SYSTEM,
) -> tuple[str, dict, str, bool]:
    if cache_path is not None and options.resume:
        cached = _read_cache(cache_path, fingerprint)
        if cached is not None:
            # A resumed build still cost what those chunks cost the first
            # time: report it, otherwise a cached run claims to be free.
            usage = cached.get("usage") or {}
            return (
                str(cached.get("reply") or ""),
                {
                    "input_tokens": int(usage.get("input_tokens", 0) or 0),
                    "output_tokens": int(usage.get("output_tokens", 0) or 0),
                },
                str(cached.get("finish") or ""),
                True,
            )
    reply, usage, finish = chat(
        options.base_url,
        options.api_key,
        options.model,
        [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        options.max_tokens,
    )
    if cache_path is not None:
        _write_cache(cache_path, fingerprint, reply, usage, finish)
    return reply, usage, finish, False


def _conflict_pairs(reply: str, valid_ids: set[str]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []

    def walk(value: Any) -> None:
        if isinstance(value, list):
            if len(value) == 2 and all(isinstance(item, str) for item in value):
                left, right = value
                if left in valid_ids and right in valid_ids and left != right:
                    pairs.append((left, right))
                return
            for item in value:
                walk(item)

    try:
        walk(json.loads(reply))
    except (json.JSONDecodeError, TypeError):
        for left, right in re.findall(r"\[\s*\"([^\"]+)\"\s*,\s*\"([^\"]+)\"\s*\]", reply or ""):
            if left in valid_ids and right in valid_ids and left != right:
                pairs.append((left, right))
    return pairs


def compile_document(
    doc: Document,
    text: str,
    spans: list[dict],
    options: CompileOptions,
    progress: Callable[[str], None] | None = None,
    lead_map: dict[str, dict] | None = None,
) -> CompiledDocument:
    if options.dry_run:
        return CompiledDocument(claims=[], stats=CompileStats(), spans=spans)

    span_by_id = {span["span_id"]: span for span in spans}
    # Only the model-backed claims get a context item: a row claim is built from
    # the span alone and states exactly what the row says. A caller that has
    # already repaired the section paths passes its own map, so context and
    # evidence agree on the section the verifier will see.
    if lead_map is None:
        lead_map = lead_ins(spans)
    chunks = chunk(spans, options.chunk_size, options.overlap)
    cache_dir = options.cache_dir
    jobs: list[tuple[int, str, str, Path | None]] = []
    for index, block in enumerate(chunks):
        prompt = make_prompt(block, {"doc_id": doc.doc_id, "title": doc.title})
        fingerprint = _fingerprint(text, block, options.model)
        path = _cache_path(cache_dir, doc.doc_id, index) if cache_dir else None
        jobs.append((index, prompt, fingerprint, path))

    replies: dict[int, tuple[str, dict, str, bool]] = {}
    stats = CompileStats()
    if options.concurrency > 1 and len(jobs) > 1:
        with ThreadPoolExecutor(max_workers=options.concurrency) as pool:
            futures = {
                pool.submit(_one_chunk, prompt, fingerprint, path, options): index
                for index, prompt, fingerprint, path in jobs
            }
            for future in as_completed(futures):
                index = futures[future]
                try:
                    replies[index] = future.result()
                except ModelError as exc:
                    stats.failed += 1
                    if progress:
                        progress(f"{doc.doc_id}: chunk {index} failed: {exc}")
    else:
        for index, prompt, fingerprint, path in jobs:
            try:
                replies[index] = _one_chunk(prompt, fingerprint, path, options)
            except ModelError as exc:
                stats.failed += 1
                if progress:
                    progress(f"{doc.doc_id}: chunk {index} failed: {exc}")

    raw_claims: list[dict] = []
    for index in sorted(replies):
        reply, usage, finish, cached = replies[index]
        stats.calls += 0 if cached else 1
        stats.cached += 1 if cached else 0
        stats.input_tokens += int(usage.get("input_tokens", 0) or 0)
        stats.output_tokens += int(usage.get("output_tokens", 0) or 0)
        if finish == "length":
            stats.truncated += 1
        raw_claims.extend(parse_claims(reply))

    claims: list[dict] = []
    number = 1
    for raw in raw_claims:
        claim = build_claim(raw, span_by_id, doc, number, lead_map)
        if claim is None:
            stats.rejected += 1
            continue
        claims.append(claim)
        number += 1

    claims, merged = dedupe_claims(claims)
    stats.merged = merged
    number = len(claims) + 1

    cited = {
        item["quote"] for claim in claims for item in claim.get("evidence", [])
    }
    for claim in row_claims(spans, doc, number):
        if claim["evidence"][0]["quote"] in cited:
            continue
        claims.append(claim)
        cited.add(claim["evidence"][0]["quote"])
        number += 1

    # Final ids are positional after dedupe and row insertion, so they stay
    # stable for a given reply set.
    for position, claim in enumerate(claims, start=1):
        claim["claim_id"] = f"{doc.doc_id}-{position:04d}"

    if options.conflicts and claims and not options.dry_run:
        _link_conflicts(doc, claims, options, stats, progress)

    return CompiledDocument(claims=claims, stats=stats, spans=spans)


def _link_conflicts(
    doc: Document,
    claims: list[dict],
    options: CompileOptions,
    stats: CompileStats,
    progress: Callable[[str], None] | None,
) -> None:
    listing = "\n".join(f"{c['claim_id']}: {c['statement']}" for c in claims)
    prompt = f"DOCUMENT: {doc.title} ({doc.doc_id})\n\n{listing}\n\nReturn the JSON array of pairs now."
    fingerprint = hashlib.sha256(
        (PROMPT_HASH + CONFLICT_SYSTEM + options.model + listing).encode()
    ).hexdigest()
    path = _cache_path(options.cache_dir, doc.doc_id, 99999) if options.cache_dir else None
    try:
        reply, usage, finish, cached = _one_chunk(
            prompt, fingerprint, path, options, system=CONFLICT_SYSTEM
        )
    except ModelError as exc:
        stats.failed += 1
        if progress:
            progress(f"{doc.doc_id}: conflict pass failed: {exc}")
        return
    stats.conflict_calls += 0 if cached else 1
    stats.cached += 1 if cached else 0
    stats.input_tokens += int(usage.get("input_tokens", 0) or 0)
    stats.output_tokens += int(usage.get("output_tokens", 0) or 0)
    if finish == "length":
        stats.truncated += 1
    by_id = {claim["claim_id"]: claim for claim in claims}
    for left, right in _conflict_pairs(reply, set(by_id)):
        by_id[left].setdefault("conflicts_with", [])
        by_id[right].setdefault("conflicts_with", [])
        if right not in by_id[left]["conflicts_with"]:
            by_id[left]["conflicts_with"].append(right)
        if left not in by_id[right]["conflicts_with"]:
            by_id[right]["conflicts_with"].append(left)
