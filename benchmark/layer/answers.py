"""Ask our own system the pilot questions and write what `score.py` scores.

A comparison is only fair if each system is asked the way a user would ask it.
For OntoSkills that means: the compiled knowledge base, the verifier's filter,
and BM25 over the claims — no model at query time, no reply rewritten on the way
out, no citation picked by hand. Whatever the artifact returns is what is scored.

The output is one JSON object per question, which is the format `score.py`
reads. Two fields matter there:

* ``evidence`` — the verbatim quotes the knowledge base cited, in rank order.
  Scoring the quotes rather than the restated statements is the strict choice: a
  claim that paraphrases its source cannot earn credit for text it does not show.
* ``refused`` — true when the artifact cited nothing. A refusal is an outcome,
  not a missing answer: it is correct on `info_not_found` and a false refusal on
  an answerable question, and `score.py` counts them separately.

Document-level retrieval is recorded but not scored here. The slice is built from
the gold documents of the selected questions (LAYER.md §2), so retrieval against
it is inflated for every system by construction.

    python3 -m benchmark.layer.answers --kb /tmp/layer/kb \\
        --selection /tmp/layer/corpus/selection.json --out runs/ontoskills.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

SYSTEM = "ontoskills"


def _corpus(kb_dir: Path, include_unverified: bool):
    """The corpus the CLI's ``ask`` answers from: verified claims by default."""
    from compiler.documents.ask import Corpus
    from compiler.documents.store import KnowledgeBase

    kb = KnowledgeBase(kb_dir)
    claims = kb.claims()
    if not claims:
        raise SystemExit(f"{kb_dir}: no claims.jsonl; build the knowledge base first")
    return Corpus(
        claims,
        kb.documents(),
        verdicts=kb.verifier(),
        include_unverified=include_unverified,
    )


def answer_rows(kb_dir: Path, selection: dict, limit: int, include_unverified: bool = False):
    """One row per selected question, in the selection's own order."""
    from compiler.documents.ask import ask

    corpus = _corpus(kb_dir, include_unverified)
    for item in selection["items"]:
        started = time.time()
        result = ask(item["text"], corpus, limit=limit)
        row = {
            "qid": item["qid"],
            "system": SYSTEM,
            # The quotes, not the statements: see the module docstring.
            "evidence": [citation.quote for citation in result.citations if citation.quote],
            "answer": "\n".join(
                f"{citation.statement} — \"{citation.quote}\"" for citation in result.citations
            ),
            "documents": result.documents,
            "citations": [
                {
                    "claim_id": citation.claim_id,
                    "doc_id": citation.doc_id,
                    "verdict": citation.verdict,
                    "score": round(citation.score, 6),
                    "quote": citation.quote,
                    "locator": {
                        "page": citation.page,
                        "section_path": citation.section_path,
                        "url": citation.url,
                    },
                }
                for citation in result.citations
            ],
            "refused": not result.citations,
            "seconds": round(time.time() - started, 4),
        }
        yield row


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--kb", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=10, help="Citations scored per question")
    parser.add_argument("--include-unverified", action="store_true")
    args = parser.parse_args(argv)

    selection = json.loads(args.selection.read_text(encoding="utf-8"))
    rows = list(answer_rows(args.kb, selection, args.limit, args.include_unverified))
    if len(rows) != len(selection["items"]):
        raise SystemExit(f"wrote {len(rows)} rows for {len(selection['items'])} questions")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
    )

    cited = sum(1 for row in rows if not row["refused"])
    print(
        json.dumps(
            {
                "system": SYSTEM,
                "kb": str(args.kb),
                "questions": len(rows),
                "cited": cited,
                "refused": len(rows) - cited,
                "median_seconds": sorted(row["seconds"] for row in rows)[len(rows) // 2],
                "out": str(args.out),
                "corpus_digest": selection.get("corpus_digest", ""),
            },
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
