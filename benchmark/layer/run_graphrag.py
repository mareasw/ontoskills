"""Ask GraphRAG the pilot's questions, through its own query API.

GraphRAG is measured as it ships: its own indexing workflow, its own local
search, its own answer prompt. This file only loads the index once and asks the
questions — spawning the `graphrag query` CLI per question would reload the
parquet tables 200 times and measure disk, not retrieval.

Two things are declared rather than tuned:

* **The method.** `local` is the primary row: entity-anchored retrieval is the
  shape a user gets by default and the closest analogue to a compiled knowledge
  base answering one question. `global` is a different query shape and is run
  separately for the corpus-level question kinds, reported as its own row —
  never mixed into the primary number.
* **The modality.** GraphRAG returns prose, so its rows are `answer`. A refusal
  is read out of the text by `benchmark/layer/text_refusal.py`, the same
  function used for every prose system, and the raw text is kept.

    python3 -m benchmark.layer.run_graphrag --root /tmp/layer/graphrag \\
        --selection /tmp/layer/corpus/selection.json --out /tmp/layer/runs/graphrag.jsonl
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.layer.text_refusal import looks_like_refusal  # noqa: E402

SYSTEM = "graphrag"
COMMUNITY_LEVEL = 2
RESPONSE_TYPE = "Multiple Paragraphs"


def load_index(root: Path):
    """The config and the five tables local search needs, read once."""
    from graphrag.cli.query import _resolve_output_files
    from graphrag.config.load_config import load_config

    config = load_config(root_dir=root)
    tables = _resolve_output_files(
        config=config,
        output_list=[
            "communities",
            "community_reports",
            "text_units",
            "relationships",
            "entities",
        ],
        optional_list=["covariates"],
    )
    return config, tables


async def ask_local(config, tables, question: str) -> str:
    from graphrag.api.query import local_search

    response, _context = await local_search(
        config=config,
        entities=tables["entities"],
        communities=tables["communities"],
        community_reports=tables["community_reports"],
        text_units=tables["text_units"],
        relationships=tables["relationships"],
        covariates=tables["covariates"],
        community_level=COMMUNITY_LEVEL,
        response_type=RESPONSE_TYPE,
        query=question,
    )
    return response if isinstance(response, str) else json.dumps(response)


async def ask_global(config, tables, question: str) -> str:
    from graphrag.api.query import global_search

    community_reports = tables["community_reports"]
    response, _context = await global_search(
        config=config,
        entities=tables["entities"],
        communities=tables["communities"],
        community_reports=community_reports,
        community_level=COMMUNITY_LEVEL,
        dynamic_community_selection=False,
        response_type=RESPONSE_TYPE,
        query=question,
    )
    return response if isinstance(response, str) else json.dumps(response)


async def run(args) -> int:
    selection = json.loads(args.selection.read_text(encoding="utf-8"))
    items = selection["items"]
    if args.kinds:
        wanted = set(args.kinds.split(","))
        items = [item for item in items if item["kind"] in wanted]
    if args.limit:
        items = items[: args.limit]

    config, tables = load_index(args.root)
    ask = ask_global if args.method == "global" else ask_local

    rows = []
    for item in items:
        started = time.time()
        try:
            text = await ask(config, tables, item["text"])
        except Exception as exc:  # noqa: BLE001 - a failed question is data
            text = f"ERROR: {type(exc).__name__}: {exc}"
            print(text, flush=True)
        rows.append(
            {
                "qid": item["qid"],
                "system": SYSTEM,
                "method": args.method,
                "answer": text,
                "refused": looks_like_refusal(text),
                "seconds": round(time.time() - started, 3),
            }
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
                "method": args.method,
                "questions": len(rows),
                "refused": sum(1 for row in rows if row["refused"]),
                "errors": sum(1 for row in rows if row["answer"].startswith("ERROR:")),
                "median_seconds": sorted(row["seconds"] for row in rows)[len(rows) // 2],
                "out": str(args.out),
            },
            indent=1,
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, required=True, help="GraphRAG project root")
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--method", choices=("local", "global"), default="local")
    parser.add_argument("--kinds", default="", help="Comma-separated question kinds to ask")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
