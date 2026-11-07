#!/usr/bin/env python3
"""Run the DocBench baselines: full document, RAG top-k, compiled claims.

The three conditions use the same model, prompt shape and output contract.
Only the context changes:

  B0  full document text
  B1  top-k paragraphs retrieved with BM25
  B2  compiled claims with evidence and locators

Usage:
    # Inspect prompts and token estimates without calling a model
    python benchmark/docbench/run_baselines.py --dry-run

    # Run with Anthropic (requires: pip install anthropic)
    ANTHROPIC_API_KEY=... python benchmark/docbench/run_baselines.py \
        --model claude-sonnet-4-6 --backend anthropic

    # Run with an OpenAI-compatible endpoint (requires: pip install openai)
    OPENAI_API_KEY=... python benchmark/docbench/run_baselines.py \
        --model gpt-5.1 --backend openai

No key is read from disk. The runner reads the standard environment variables
of the chosen SDK and never prints them.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GOLD = ROOT / "gold"
PRIVATE = ROOT / "private"
RUNS = ROOT / "runs" / "baselines"

SOURCES = {
    "D1": PRIVATE / "D1.txt",
    "D2": PRIVATE / "D2.txt",
    "D3": PRIVATE / "D3.txt",
    "D4": PRIVATE / "D4.txt",
}

SYSTEM = (
    "You answer questions about one document. Use only the CONTEXT. "
    "Do not use outside knowledge. If the context does not support an answer, "
    'answer exactly "UNKNOWN". Return a JSON object with keys: '
    '"answer" (string), "citation" (a verbatim quote from CONTEXT, or ""), '
    '"claim_ids" (array of claim ids present in CONTEXT, or []).'
)

MAX_CLAIMS_IN_CONTEXT = 12
RAG_TOP_K = 5


def norm(text: str) -> str:
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    return re.sub(r"\s+", " ", text).strip()


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


class BM25:
    def __init__(self, docs: list[str], k1: float = 1.5, b: float = 0.75) -> None:
        self.docs = docs
        self.toks = [tokens(d) for d in docs]
        self.k1 = k1
        self.b = b
        self.avgdl = sum(len(t) for t in self.toks) / max(len(self.toks), 1)
        self.df = Counter()
        for t in self.toks:
            for term in set(t):
                self.df[term] += 1
        self.n = len(docs)

    def score(self, query: str, idx: int) -> float:
        q = tokens(query)
        dl = len(self.toks[idx])
        tf = Counter(self.toks[idx])
        s = 0.0
        for term in q:
            if term not in tf:
                continue
            df = self.df.get(term, 0)
            idf = math.log(1 + (self.n - df + 0.5) / (df + 0.5))
            s += idf * (tf[term] * (self.k1 + 1)) / (
                tf[term] + self.k1 * (1 - self.b + self.b * dl / max(self.avgdl, 1))
            )
        return s

    def top(self, query: str, k: int) -> list[int]:
        scored = [(self.score(query, i), i) for i in range(self.n)]
        scored.sort(reverse=True)
        return [i for _, i in scored[:k]]


def paragraphs(text: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"\n\s*\n|\f", text)]
    return [p for p in parts if len(p) >= 80]


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def build_context(condition: str, doc_id: str, question: str, claims: list[dict], source: str) -> tuple[str, dict]:
    if condition == "B0":
        return source, {"kind": "full_document", "chars": len(source)}

    if condition == "B1":
        paras = paragraphs(source)
        bm = BM25(paras)
        picked = bm.top(question, RAG_TOP_K)
        context = "\n\n".join(f"[paragraph {i + 1}]\n{paras[i]}" for i in picked)
        return context, {"kind": "bm25_paragraphs", "top_k": RAG_TOP_K, "paragraphs": len(paras), "picked": picked}

    doc_claims = [c for c in claims if c["doc_id"] == doc_id]
    if len(doc_claims) <= MAX_CLAIMS_IN_CONTEXT:
        picked = doc_claims
        mode = "all_claims"
    else:
        names = [c["statement"] + " " + c.get("actor", "") + " " + " ".join(c.get("conditions", []) or []) for c in doc_claims]
        bm = BM25(names)
        chosen = bm.top(question, MAX_CLAIMS_IN_CONTEXT)
        picked = [doc_claims[i] for i in chosen]
        mode = "bm25_claims"
    lines = []
    for c in picked:
        lines.append(f"[{c['claim_id']}] {c['statement']}")
        lines.append(f"MODALITY: {c['modality']}")
        if c.get("actor"):
            lines.append(f"ACTOR: {c['actor']}")
        if c.get("deadline"):
            lines.append(f"DEADLINE: {c['deadline']}")
        if c.get("conditions"):
            lines.append("CONDITIONS: " + "; ".join(c["conditions"]))
        lines.append(f"QUOTE: {c['quote']}")
        loc = " > ".join(c["locator"].get("section_path", []))
        if loc:
            lines.append(f"LOCATOR: {loc}")
        lines.append("")
    return "\n".join(lines).strip(), {"kind": "claims", "mode": mode, "claims": len(picked)}


def make_prompt(context: str, question: str) -> str:
    return f"CONTEXT:\n{context}\n\nQUESTION: {question}"


def call_model(backend: str, model: str, prompt: str, base_url: str = "") -> tuple[str, int, int]:
    started = time.monotonic()
    if backend == "mock":
        # Plumbing test only: never use mock answers for a real evaluation.
        return '{"answer":"UNKNOWN","citation":"","claim_ids":[]}', 0, 0
    if backend == "http":
        # OpenAI-compatible HTTP endpoint without the openai SDK. Works with
        # Ollama, vLLM, LM Studio, LocalAI and any compatible server.
        try:
            import requests
        except ImportError as exc:
            raise SystemExit("requests is not installed: pip install requests") from exc
        url = (base_url or os.environ.get("OPENAI_BASE_URL") or "http://localhost:8000/v1").rstrip("/")
        headers = {"Content-Type": "application/json"}
        key = os.environ.get("OPENAI_API_KEY")
        if key:
            headers["Authorization"] = f"Bearer {key}"
        payload = {
            "model": model,
            "temperature": 0,
            "max_tokens": 1024,
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": prompt},
            ],
        }
        resp = requests.post(f"{url}/chat/completions", headers=headers, json=payload, timeout=180)
        if resp.status_code >= 400:
            raise SystemExit(f"HTTP {resp.status_code} from {url}: {resp.text[:400]}")
        data = resp.json()
        text = data["choices"][0]["message"].get("content") or ""
        usage = data.get("usage") or {}
        return text, int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0))
    if backend == "anthropic":
        try:
            import anthropic
        except ImportError as exc:
            raise SystemExit("anthropic is not installed: pip install anthropic") from exc
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=model,
            max_tokens=1024,
            temperature=0,
            system=SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(block.text for block in resp.content if getattr(block, "type", "") == "text")
        usage = resp.usage
        return text, usage.input_tokens, usage.output_tokens

    if backend == "openai":
        try:
            import openai
        except ImportError as exc:
            raise SystemExit("openai is not installed: pip install openai") from exc
        client = openai.OpenAI(base_url=base_url or os.environ.get("OPENAI_BASE_URL") or None)
        resp = client.chat.completions.create(
            model=model,
            max_tokens=1024,
            temperature=0,
            messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
        )
        text = resp.choices[0].message.content or ""
        usage = resp.usage
        return text, usage.prompt_tokens, usage.completion_tokens

    raise SystemExit(f"unknown backend: {backend}")


def parse_answer(text: str) -> tuple[str, str, list[str]]:
    raw = text.strip()
    candidate = raw
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*", "", candidate)
        candidate = re.sub(r"\s*```$", "", candidate)
    try:
        obj = json.loads(candidate)
        return (
            str(obj.get("answer", "")).strip(),
            str(obj.get("citation", "")).strip(),
            [str(x) for x in obj.get("claim_ids", [])],
        )
    except Exception:  # noqa: BLE001 - fall back to the raw text
        return raw, "", []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="Build prompts only; do not call a model")
    ap.add_argument("--backend", choices=["anthropic", "openai", "http", "mock"], default="anthropic")
    ap.add_argument("--model", default=os.environ.get("DOCBENCH_MODEL", ""))
    ap.add_argument("--base-url", default=os.environ.get("OPENAI_BASE_URL", ""),
                    help="OpenAI-compatible base URL, e.g. http://localhost:11434/v1")
    ap.add_argument("--conditions", default="B0,B1,B2")
    ap.add_argument("--only-docs", default="", help="Comma-separated doc ids, e.g. D1,D4")
    args = ap.parse_args()

    questions = load_jsonl(GOLD / "questions.jsonl")
    claims = load_jsonl(GOLD / "claims.jsonl")

    if args.only_docs:
        keep = {x.strip() for x in args.only_docs.split(",") if x.strip()}
        questions = [q for q in questions if q["doc_id"] in keep]

    conditions = [c.strip() for c in args.conditions.split(",") if c.strip()]

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    outdir = RUNS / stamp
    outdir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "stamp": stamp,
        "backend": args.backend,
        "base_url": args.base_url or os.environ.get("OPENAI_BASE_URL", ""),
        "model": args.model or "(dry-run)",
        "conditions": conditions,
        "rag_top_k": RAG_TOP_K,
        "max_claims_in_context": MAX_CLAIMS_IN_CONTEXT,
        "questions": len(questions),
        "dry_run": args.dry_run,
    }
    (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    prompts = []
    answers = []
    for condition in conditions:
        for q in questions:
            source = SOURCES[q["doc_id"]].read_text(encoding="utf-8", errors="ignore")
            context, meta = build_context(condition, q["doc_id"], q["question"], claims, source)
            prompt = make_prompt(context, q["question"])
            prompts.append({
                "condition": condition,
                "question_id": q["question_id"],
                "doc_id": q["doc_id"],
                "chars": len(prompt),
                "estimated_tokens": len(prompt) // 4,
                "context": meta,
                "prompt": prompt,
            })
            if args.dry_run:
                continue
            if not args.model:
                raise SystemExit("--model is required unless --dry-run")
            started = time.monotonic()
            raw, in_tok, out_tok = call_model(args.backend, args.model, prompt, args.base_url)
            answer, citation, claim_ids = parse_answer(raw)
            answers.append({
                "condition": condition,
                "question_id": q["question_id"],
                "doc_id": q["doc_id"],
                "answer": answer,
                "citation": citation,
                "claim_ids": claim_ids,
                "input_tokens": in_tok,
                "output_tokens": out_tok,
                "latency_ms": round((time.monotonic() - started) * 1000, 1),
                "raw": raw,
            })
            print(f"{condition} {q['question_id']}: {answer[:80]!r}")

    if args.dry_run:
        (outdir / "prompts.jsonl").write_text(
            "".join(json.dumps(p, ensure_ascii=False) + "\n" for p in prompts), encoding="utf-8"
        )
        total = sum(p["estimated_tokens"] for p in prompts)
        print(f"dry-run: {len(prompts)} prompts, ~{total:,} estimated input tokens")
        for condition in conditions:
            subset = [p for p in prompts if p["condition"] == condition]
            print(f"  {condition}: {len(subset)} prompts, ~{sum(p['estimated_tokens'] for p in subset):,} tokens")
        print(f"wrote {outdir / 'prompts.jsonl'}")
        return 0

    (outdir / "answers.jsonl").write_text(
        "".join(json.dumps(a, ensure_ascii=False) + "\n" for a in answers), encoding="utf-8"
    )
    print(f"wrote {len(answers)} answers to {outdir / 'answers.jsonl'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
