"""Slice a knowledge base into a small, committed fixture with golden answers.

The MCP reads the artifact in Rust; the core writes it in Python. Two
implementations of one ranking is a risk, and the way this repository pays for
it is a test that compares them on real data. That test needs a knowledge base
small enough to commit and rich enough to exercise the parts that can diverge:
a stopword-only question, a word long enough to be stemmed, an accented word, a
quote with curly punctuation, and a claim the verifier rejected.

This script produces exactly that, deterministically:

    python3 -m benchmark.layer.make_documents_fixture \
        --kb /path/to/kb --selection /path/to/selection.json \
        --out mcp/tests/fixtures/documents

What it writes:

    kb/manifest.json       counts recomputed, provenance added
    kb/documents.jsonl     the selected documents
    kb/claims.jsonl        their claims, unchanged
    kb/verifier.jsonl      their verdicts
    kb/text/<doc_id>.txt   the source text, byte for byte
    kb/graph.ttl           rebuilt from the subset, same writer as a real build
    golden.json            tokens, normalised hashes, and the ranking for a
                           fixed question list, computed by the Python core

`graph.ttl` is rebuilt rather than sliced: a graph that references a document
the fixture does not carry would make `documents_query` lie about what is here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from compiler.documents.ask import Corpus, ask
from compiler.documents.store import (
    KnowledgeBase,
    read_json,
    write_json,
)
from compiler.documents.text import STOPWORDS, norm, tokens

# Questions the fixture adds to the ones taken from the selection: each one aims
# at a rule a port can get wrong, not at a document.
PROBES = [
    "what is it?",
    "certificazioni fornitori",
    "qualità dell'aria nell'ufficio",
    "What are the default size limits for file uploads?",
    "the",
]


STOPWORDS_RS = Path(__file__).resolve().parents[2] / "mcp/src/documents/stopwords.rs"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_stopwords() -> int:
    """Regenerate the Rust copy of `STOPWORDS`, sorted, from the Python one.

    The list cannot be imported across the language boundary, so it is written
    as a Rust `static` and compared by `benchmark/tests/test_layer_documents_fixture.py`.
    A test that reads the file and the Python set is the only thing that keeps a
    fix applied on one side from silently diverging.
    """
    words = sorted(STOPWORDS)
    lines = [
        "//! Generated from `core/src/documents/text.py` (`STOPWORDS`), not typed by hand:",
        "//! a list copied twice is a list that drifts. Regenerate with",
        "//! `python3 -m benchmark.layer.make_documents_fixture --stopwords-only`.",
        "",
        "pub static STOPWORDS: &[&str] = &[",
    ]
    lines.extend(f'    "{word}",' for word in words)
    lines.append("];")
    STOPWORDS_RS.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(words)


def choose_documents(rows: list[dict], claims: list[dict], count: int) -> list[str]:
    """The first documents by id that have claims and text on disk."""
    with_claims = {claim["doc_id"] for claim in claims}
    eligible = [
        row["doc_id"]
        for row in rows
        if row.get("doc_id") in with_claims and row.get("path")
    ]
    return sorted(eligible)[:count]


def choose_questions(items: list[dict], doc_ids: set[str], count: int) -> list[dict]:
    """Questions whose gold documents are in the fixture, then the rest by qid.

    The second group keeps the list stable when a fixture is small: a question
    with no gold document in the slice still exercises ranking (it usually
    returns nothing or a weak match), and its answer is just as comparable.
    """
    inside = [item for item in items if doc_ids & set(item.get("gold_docs") or [])]
    outside = [item for item in items if item not in inside]
    order = sorted(inside, key=lambda item: item["qid"]) + sorted(
        outside, key=lambda item: item["qid"]
    )
    return order[:count]


def build(
    kb_dir: Path, selection: Path, out: Path, documents: int, questions: int
) -> dict:
    """Write the fixture under ``out/kb`` and its golden answers as ``out/golden.json``."""
    kb = KnowledgeBase(kb_dir)
    documents_in = kb.documents()
    claims_in = kb.claims()
    verdicts_in = kb.verifier()

    selected = choose_documents(documents_in, claims_in, documents)
    if not selected:
        raise SystemExit(f"{kb_dir}: no document with claims to slice")
    keep = set(selected)
    documents_out = [row for row in documents_in if row["doc_id"] in keep]
    claims_out = [claim for claim in claims_in if claim["doc_id"] in keep]
    verdicts_out = [
        row for row in verdicts_in if row.get("claim_id") in {c["claim_id"] for c in claims_out}
    ]

    # The manifest of a committed fixture describes the slice, not the machine
    # that built it and not the 279-document build it was cut from: no endpoint,
    # no absolute path, no totals that would contradict the three documents it
    # carries. What stays is what makes the claims reproducible — which model
    # wrote them, under which prompt hash, at which chunk size, under which
    # licence.
    manifest_in = read_json(kb.path("manifest.json"))
    manifest_out = {
        "name": "documents-fixture",
        "description": (
            "A deterministic slice of a compiled knowledge base, committed so the "
            "Rust read path can be compared with the Python one question by question."
        ),
        "model": manifest_in.get("model", ""),
        "prompt_hash": manifest_in.get("prompt_hash", ""),
        "chunk_size": manifest_in.get("chunk_size", 0),
        "overlap": manifest_in.get("overlap", 0),
        "licences": manifest_in.get("licences", []),
        "documents": len(documents_out),
        "claims": len(claims_out),
        "verifier": _counts(verdicts_out),
        "fixture": {
            "documents": selected,
            "note": (
                "Regenerate with benchmark/layer/make_documents_fixture.py; "
                "the source documents are public and MIT-licensed, and the "
                "verbatim text under kb/text/ is theirs, not this repository's."
            ),
        },
    }

    target = KnowledgeBase(out / "kb")
    target.write(
        manifest=manifest_out,
        documents=documents_out,
        spans=[],
        claims=claims_out,
        verifier_rows=verdicts_out,
    )
    for doc_id in selected:
        target.text_path(doc_id).parent.mkdir(parents=True, exist_ok=True)
        target.text_path(doc_id).write_bytes(kb.text_path(doc_id).read_bytes())
    # `write` always emits `spans.jsonl`, and the reader never opens it: the
    # slice has no segmenter, so the file would be empty. An empty file that a
    # reader is promised never to need is noise in a fixture, so it goes.
    (target.path("spans.jsonl")).unlink(missing_ok=True)

    items = json.loads(Path(selection).read_text(encoding="utf-8"))["items"]
    asked = choose_questions(items, keep, questions)
    corpus = Corpus(
        target.claims(),
        target.documents(),
        target.verifier(),
        include_unverified=False,
    )
    golden_answers = []
    for item in asked:
        answer = ask(item["text"], corpus, limit=10)
        golden_answers.append(
            {
                "qid": item["qid"],
                "question": item["text"],
                "kind": item["kind"],
                "citations": [
                    {
                        "claim_id": citation.claim_id,
                        "doc_id": citation.doc_id,
                        "score": citation.score,
                        "verdict": citation.verdict,
                        "quote": citation.quote,
                    }
                    for citation in answer.citations
                ],
                "documents": answer.documents,
                "tensions": [
                    {"topic": tension.topic, "values": tension.values, "reason": tension.reason}
                    for tension in answer.tensions
                ],
            }
        )
    for question in PROBES:
        answer = ask(question, corpus, limit=10)
        golden_answers.append(
            {
                "qid": "probe",
                "question": question,
                "kind": "probe",
                "citations": [
                    {
                        "claim_id": citation.claim_id,
                        "doc_id": citation.doc_id,
                        "score": citation.score,
                        "verdict": citation.verdict,
                        "quote": citation.quote,
                    }
                    for citation in answer.citations
                ],
                "documents": answer.documents,
                "tensions": [],
            }
        )

    texts = {}
    for doc_id in selected:
        text = kb.text_path(doc_id).read_text(encoding="utf-8")
        texts[doc_id] = {
            "sha256": sha256_text(text),
            "norm_sha256": sha256_text(norm(text)),
            "tokens": " ".join(tokens(text)),
        }

    golden = {
        "note": (
            "Computed by the Python core (compiler.documents.ask/text) on the sibling "
            "kb/. The Rust reader must reproduce every citation id, in order, and every "
            "token stream. Regenerate with benchmark/layer/make_documents_fixture.py."
        ),
        "documents": selected,
        "tokenizer": texts,
        "answers": golden_answers,
    }
    write_json(out / "golden.json", golden)
    return {
        "documents": len(documents_out),
        "claims": len(claims_out),
        "verdicts": _counts(verdicts_out),
        "questions": len(golden_answers),
        "bytes": sum(
            path.stat().st_size for path in out.rglob("*") if path.is_file()
        ),
    }


def _counts(rows: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for row in rows:
        verdict = row.get("verdict", "ok")
        counts[verdict] = counts.get(verdict, 0) + 1
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--stopwords-only",
        action="store_true",
        help="regenerate the Rust copy of STOPWORDS and exit",
    )
    parser.add_argument("--kb", type=Path)
    parser.add_argument("--selection", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--documents", type=int, default=3)
    parser.add_argument("--questions", type=int, default=20)
    parser.add_argument(
        "--force", action="store_true", help="overwrite an existing fixture directory"
    )
    args = parser.parse_args(argv)

    if args.stopwords_only:
        print(json.dumps({"stopwords": write_stopwords(), "path": str(STOPWORDS_RS)}, indent=1))
        return 0
    if not (args.kb and args.selection and args.out):
        parser.error("--kb, --selection and --out are required unless --stopwords-only is given")

    target = args.out / "kb"
    if target.exists() and not args.force:
        raise SystemExit(f"{target} exists; pass --force to replace it")
    for stale in sorted(args.out.rglob("*"), reverse=True) if args.out.exists() else []:
        if stale.is_file():
            stale.unlink()
        elif stale.is_dir():
            stale.rmdir()
    args.out.mkdir(parents=True, exist_ok=True)

    report = build(args.kb, args.selection, args.out, args.documents, args.questions)
    print(json.dumps(report, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
