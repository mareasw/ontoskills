"""The floor: chunk the corpus, rank the chunks, return the best ten.

This is the row that decides whether a semantic layer is worth its cost. It uses
no model to build and no model to answer: the corpus is cut into fixed windows,
BM25 ranks them, and the top `--k` are returned as the system's evidence. If a
system that spends dollars and hours cannot beat this, the honest conclusion is
that it bought nothing.

Two parameters are declared rather than tuned:

* **The window.** 4,800 characters with 400 of overlap, which is roughly the
  1,200-token window GraphRAG and LightRAG use at about four characters per
  token. The floor is meant to be the same shape of retrieval, not a strawman in
  postage stamps.
* **The cost.** Zero tokens. There is no build model, so the build column says
  zero and that is not a measurement of quality: it is the whole point of the
  row.

    python3 -m benchmark.layer.run_floor --corpus /tmp/layer/corpus \\
        --selection /tmp/layer/corpus/selection.json --out /tmp/layer/runs/floor.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.retrieval.baselines import BM25  # noqa: E402

SYSTEM = "vector-rag-floor"
WINDOW = 4_800
OVERLAP = 400
# BM25 returns a score for every chunk, so this row can never decline to answer.
# It is reported as it is: `abstention_rate` 0 % by construction, not by choice.


def windows(text: str, window: int = WINDOW, overlap: int = OVERLAP) -> list[str]:
    """Fixed windows with overlap, covering the text end to end.

    The step is window minus overlap, and a tail shorter than a quarter window is
    merged into the last one instead of becoming a fragment that matches nothing.
    """
    if len(text) <= window:
        return [text]
    step = window - overlap
    pieces = []
    start = 0
    while start < len(text):
        piece = text[start : start + window]
        if len(piece) < window // 4 and pieces:
            pieces[-1] += text[start:]
            break
        pieces.append(piece)
        if start + window >= len(text):
            break
        start += step
    return pieces


def build_index(corpus: Path) -> tuple[BM25, dict[str, str]]:
    chunks: dict[str, str] = {}
    for path in sorted(corpus.glob("*.txt")):
        text = path.read_text(encoding="utf-8")
        for number, piece in enumerate(windows(text)):
            chunks[f"{path.stem}::{number:03d}"] = piece
    return BM25(chunks, cache=None), chunks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument(
        "--build",
        type=Path,
        default=None,
        help="Where to write the build record the report table reads",
    )
    args = parser.parse_args(argv)

    started = time.time()
    index, chunks = build_index(args.corpus)
    build_seconds = time.time() - started

    selection = json.loads(args.selection.read_text(encoding="utf-8"))
    rows = []
    for item in selection["items"]:
        began = time.time()
        ranked = index.search(item["text"], top_k=args.k)
        rows.append(
            {
                "qid": item["qid"],
                "system": SYSTEM,
                "evidence": [chunks[chunk_id] for chunk_id in ranked],
                "chunk_ids": list(ranked),
                "documents": list(dict.fromkeys(chunk_id.split("::")[0] for chunk_id in ranked)),
                "refused": False,
                "seconds": round(time.time() - began, 4),
            }
        )

    if args.build is not None:
        # Zero calls and zero tokens is the point of this row: the floor is what
        # a corpus answers without a model. The artifact is the chunk store
        # itself, held in memory, so its size is the text it keeps.
        args.build.parent.mkdir(parents=True, exist_ok=True)
        args.build.write_text(
            json.dumps(
                {
                    "label": SYSTEM,
                    "calls": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "usd": 0.0,
                    "wall_clock_s": round(build_seconds, 2),
                    "artifact_bytes": sum(
                        len(chunk.encode("utf-8")) for chunk in chunks.values()
                    ),
                    "artifact_note": "in memory: the chunk store, no index on disk",
                    "chunks": len(chunks),
                },
                indent=1,
            )
            + "\n",
            encoding="utf-8",
        )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "system": SYSTEM,
                "corpus_documents": len({chunk_id.split("::")[0] for chunk_id in chunks}),
                "chunks": len(chunks),
                "build_seconds": round(build_seconds, 2),
                "build_tokens": 0,
                "questions": len(rows),
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
