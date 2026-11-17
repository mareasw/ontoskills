"""The pilot corpus: a deterministic slice of EnterpriseRAG-Bench.

A semantic-layer comparison does not need half a million documents. It needs the
documents the questions are about. EnterpriseRAG-Bench has 480 answerable
questions resting on 722 distinct gold documents, so a slice built that way is
the whole question set over six hundred times less material — and the same slice
can be fed, byte for byte, to every system in the comparison.

Two rules make the slice defensible:

* the questions are stratified by kind rather than taken as the first N, because
  the dataset is ordered by kind and "the first 100" is 100 questions of one
  type;
* the corpus is addressed by content. The selection is written down, digested,
  and refused if the bytes change, so "we scored well on our slice" cannot
  quietly become "we scored well on a slice we tuned".

The output is a folder of `.txt` files plus a manifest, which is exactly what
`ontocore ingest` reads and what a competitor's CLI can be pointed at.

    python3 -m benchmark.layer.corpus --questions 100 --out /tmp/layer/corpus
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Iterable, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.retrieval.adapters import Question, enterprise_rag  # noqa: E402

DATASET = "onyx-dot-app/EnterpriseRAG-Bench"
CITATION = "Sun et al. 2026, arXiv:2605.05253"
LICENCE = "MIT"


def slug(doc_id: str) -> str:
    """A stable, valid doc id for an arbitrary dataset id.

    Underscores are doubled and every other punctuation mark becomes an
    underscore, so the mapping is reversible: `a-b` and `a_b` are different
    documents, and a slice cannot merge two of them into one. The caller makes
    the result unique in case two ids still collide.
    """
    encoded = "".join(char if char.isalnum() else ("__" if char == "_" else "_") for char in doc_id)
    if not encoded or not encoded[0].isalpha():
        encoded = f"d_{encoded}"
    return encoded


def _unique(candidate: str, seen: set[str]) -> str:
    if candidate not in seen:
        return candidate
    suffix = 1
    while f"{candidate}_{suffix}" in seen:
        suffix += 1
    return f"{candidate}_{suffix}"


def stratify(questions: Sequence[Question], count: int) -> dict[str, int]:
    """How many questions each kind gets, proportional to how many it has.

    EnterpriseRAG-Bench is ordered by kind, so "the first 100" is 100 questions
    of one type — a slice that cannot say anything about the types that matter.
    Allocation is proportional with the largest remainder, and the remainder is
    broken by kind name so two runs never disagree about who got the last seat.
    """
    by_kind: dict[str, list[Question]] = {}
    for question in questions:
        by_kind.setdefault(question.kind, []).append(question)
    total = sum(len(v) for v in by_kind.values())
    if count > total:
        raise SystemExit(f"asked for {count} questions, the dataset has {total} scorable")

    quota = {kind: count * len(group) / total for kind, group in by_kind.items()}
    allocation = {kind: int(value) for kind, value in quota.items()}
    shortfall = count - sum(allocation.values())
    ranking = sorted(by_kind, key=lambda kind: (-(quota[kind] - allocation[kind]), kind))
    for kind in ranking[:shortfall]:
        allocation[kind] += 1

    # A kind cannot contribute more than it has; every seat it refuses goes to
    # the kind that was closest to one.
    for kind in allocation:
        allocation[kind] = min(allocation[kind], len(by_kind[kind]))
    while sum(allocation.values()) < count:
        room = [kind for kind in by_kind if allocation[kind] < len(by_kind[kind])]
        if not room:
            break
        kind = max(room, key=lambda k: (quota[k] - allocation[k], -len(by_kind[k]), k))
        allocation[kind] += 1
    return allocation


def select_questions(questions: Sequence[Question], count: int) -> list[Question]:
    """`count` questions, stratified by kind, in the dataset's order.

    Every kind is included, and two of them exist precisely because they cannot
    be scored the ordinary way: `high_level` names gold facts but no document,
    and `info_not_found` is the abstention row. Leaving them out because they
    have no gold document would silently drop the two tests a semantic layer is
    most likely to fail.

    Within a kind the questions are taken in the dataset's own order, so the
    choice never depends on what any system finds easy.
    """
    allocation = stratify(questions, count)
    taken: dict[str, int] = {}
    chosen: list[Question] = []
    for question in questions:
        used = taken.get(question.kind, 0)
        if used < allocation.get(question.kind, 0):
            taken[question.kind] = used + 1
            chosen.append(question)
    if len(chosen) != count:
        raise SystemExit(f"stratified selection produced {len(chosen)} questions, expected {count}")
    return chosen


def wanted_document_ids(questions: Iterable[Question]) -> set[str]:
    return {doc_id for question in questions for doc_id in question.gold_docs}


def collect_documents(
    rows: Iterable[tuple[str, str]], wanted: set[str]
) -> dict[str, tuple[str, str]]:
    """Stream the whole corpus once and keep only the documents the gold names.

    Streaming matters: materialising 512k documents costs gigabytes to answer a
    question about a hundred of them.
    """
    kept: dict[str, tuple[str, str]] = {}
    for doc_id, text in rows:
        if doc_id in wanted:
            kept[doc_id] = (doc_id, text)
    missing = wanted - set(kept)
    if missing:
        raise SystemExit(f"{len(missing)} gold documents are not in the corpus, e.g. {sorted(missing)[:3]}")
    return kept


def corpus_digest(documents: dict[str, str]) -> str:
    """The slice, addressed by its bytes: same digest, same comparison."""
    digest = hashlib.sha256()
    for name in sorted(documents):
        digest.update(name.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(documents[name].encode("utf-8"))
        digest.update(b"\x01")
    return digest.hexdigest()


def write_corpus(
    out: Path,
    questions: Sequence[Question],
    documents: dict[str, tuple[str, str]],
    force: bool = False,
) -> dict:
    """Write the documents, the manifest and the selection; refuse to overwrite."""
    out = Path(out)
    if out.exists() and any(out.iterdir()) and not force:
        raise SystemExit(f"{out} is not empty; pass --force to replace it")

    out.mkdir(parents=True, exist_ok=True)
    for stale in out.glob("*.txt"):
        stale.unlink()

    names: dict[str, str] = {}
    seen: set[str] = set()
    for doc_id in sorted(documents):
        name = _unique(slug(doc_id), seen)
        seen.add(name)
        names[doc_id] = name

    texts: dict[str, str] = {}
    entries: list[dict] = []
    for doc_id in sorted(documents):
        name = names[doc_id]
        text = documents[doc_id][1]
        texts[name] = text
        path = out / f"{name}.txt"
        path.write_text(text + "\n", encoding="utf-8")
        entries.append(
            {
                "doc_id": name,
                "path": path.name,
                "title": name,
                "kind": "text",
                "url": f"https://huggingface.co/datasets/{DATASET}",
                "licence": LICENCE,
                "sha256": hashlib.sha256((text + "\n").encode("utf-8")).hexdigest(),
                "notes": f"{DATASET} document {doc_id}",
            }
        )

    manifest = {
        "name": "enterpriserag-pilot",
        "description": (
            "A deterministic slice of EnterpriseRAG-Bench: the gold documents of "
            "the first N scorable questions, for comparing semantic layers on the "
            "same corpus, the same questions and the same cost accounting."
        ),
        "citation": CITATION,
        "licence": LICENCE,
        "documents": entries,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")

    selection = {
        "dataset": DATASET,
        "citation": CITATION,
        "licence": LICENCE,
        "questions": len(questions),
        "documents": len(documents),
        "corpus_digest": corpus_digest(texts),
        "question_ids": [question.qid for question in questions],
        "document_ids": names,
        "items": [
            {
                "qid": question.qid,
                "text": question.text,
                "kind": question.kind,
                "gold_docs": [names[doc_id] for doc_id in question.gold_docs],
                "gold_facts": list(question.gold_facts),
            }
            for question in questions
        ],
    }
    (out / "selection.json").write_text(json.dumps(selection, indent=1) + "\n", encoding="utf-8")
    return selection


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--questions", type=int, default=100)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--check", action="store_true", help="print the slice accounting and stop")
    args = parser.parse_args(argv)

    benchmark = enterprise_rag()
    questions = select_questions(benchmark.questions, args.questions)
    wanted = wanted_document_ids(questions)
    print(f"questions {len(questions)}  gold documents {len(wanted)}", flush=True)

    documents = collect_documents(benchmark.documents(), wanted)
    chars = sum(len(text) for _, text in documents.values())
    print(f"documents kept {len(documents)}  characters {chars:,}", flush=True)

    if args.check:
        print(json.dumps({"questions": len(questions), "documents": len(documents), "characters": chars}, indent=1))
        return 0

    selection = write_corpus(args.out, questions, documents, force=args.force)
    kinds: dict[str, int] = {}
    for question in questions:
        kinds[question.kind] = kinds.get(question.kind, 0) + 1
    print(
        json.dumps(
            {
                "out": str(args.out),
                "documents": selection["documents"],
                "questions": selection["questions"],
                "corpus_digest": selection["corpus_digest"][:16],
                "kinds": kinds,
            },
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
