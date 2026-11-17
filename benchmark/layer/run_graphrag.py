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

Questions are asked one at a time and every answer is flushed as soon as it is
paid for, so `--resume` can continue a killed run without buying the same answer
twice. The file is the state: a line that does not parse is the last write of a
killed run and is dropped, never trusted or left inside a published answers
file, and a question whose row says `ERROR:` is asked again — its cost stays in
the meter, but a failed call is not an answer.

    python3 -m benchmark.layer.run_graphrag --root /tmp/layer/graphrag \\
        --selection /tmp/layer/corpus/selection.json --out /tmp/layer/runs/graphrag.jsonl

    # after a reboot: keep what was paid for, ask only what is missing
    python3 -m benchmark.layer.run_graphrag --root /tmp/layer/graphrag \\
        --selection /tmp/layer/corpus/selection.json --out /tmp/layer/runs/graphrag.jsonl \\
        --resume
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


def read_answers(path: Path) -> tuple[list[dict], int]:
    """The rows already paid for, and how many lines could not be read.

    A run is killed between one question and the next — a reboot, a closed
    terminal — and the questions it answered were paid for. The file is
    therefore appended one row at a time and read back on `--resume`; a line
    that does not parse is the last write of a killed run, and it is dropped
    rather than trusted, because the question it belonged to cannot be read out
    of it. Whether that question is asked again depends on the readable rows
    alone: at most one answer is bought twice, never a truncated one published.
    """
    rows: list[dict] = []
    broken = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            broken += 1
            continue
        if isinstance(row, dict) and row.get("qid"):
            rows.append(row)
        else:
            broken += 1
    return rows, broken


def rewrite_in_selection_order(path: Path, rows: list[dict], items: list[dict]) -> list[dict]:
    """Write the finished file in the selection's order, whatever order it was asked.

    A resumed run answers the missing questions last, and the published file should
    not depend on whether the machine rebooted half-way. The write goes through a
    temporary file and a rename: a kill during the final write cannot leave a
    half-written file where a complete answers file was. Rows whose qid is not in
    the selection are kept, at the end, rather than dropped — `score.py` and the
    run's own check are what refuse them.
    """
    position = {item["qid"]: index for index, item in enumerate(items)}
    ordered = sorted(rows, key=lambda row: position.get(row["qid"], len(position)))
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in ordered),
        encoding="utf-8",
    )
    temporary.replace(path)
    return ordered


async def run(args) -> int:
    selection = json.loads(args.selection.read_text(encoding="utf-8"))
    ordered = selection["items"]
    if args.kinds:
        wanted = set(args.kinds.split(","))
        ordered = [item for item in ordered if item["kind"] in wanted]
    if args.limit:
        ordered = ordered[: args.limit]

    done: list[dict] = []
    broken = 0
    retried = 0
    if args.resume and args.out.exists():
        rows, broken = read_answers(args.out)
        # A failed question is not an answer: the call was paid for and the meter
        # keeps the spend, but the row says nothing about the system. It is asked
        # again, and its old row is dropped from the file so a question can only
        # appear once.
        for row in rows:
            if str(row.get("answer", "")).startswith("ERROR:"):
                retried += 1
            else:
                done.append(row)
        answered = {row["qid"] for row in done}
        items = [item for item in ordered if item["qid"] not in answered]
    else:
        items = list(ordered)

    config, tables = load_index(args.root)
    ask = ask_global if args.method == "global" else ask_local

    args.out.parent.mkdir(parents=True, exist_ok=True)
    if done:
        # Rewrite the readable rows before appending. A killed run can leave a
        # half-written last line, and appending behind it would keep a corrupt
        # record inside a published answers file.
        args.out.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in done),
            encoding="utf-8",
        )

    fresh: list[dict] = []
    # A resumed run continues its file; a fresh run replaces it, so a second
    # measurement can never be read as one long run of six answers to three
    # questions.
    with args.out.open("a" if done else "w", encoding="utf-8") as handle:
        for item in items:
            started = time.time()
            try:
                text = await ask(config, tables, item["text"])
            except Exception as exc:  # noqa: BLE001 - a failed question is data
                text = f"ERROR: {type(exc).__name__}: {exc}"
                print(text, flush=True)
            row = {
                "qid": item["qid"],
                "system": SYSTEM,
                "method": args.method,
                "answer": text,
                "refused": looks_like_refusal(text),
                "seconds": round(time.time() - started, 3),
            }
            # Written and flushed per question: a run killed after this line has
            # already paid for it, and `--resume` will not ask it again.
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()
            fresh.append(row)

    rows = rewrite_in_selection_order(args.out, done + fresh, ordered)
    print(
        json.dumps(
            {
                "system": SYSTEM,
                "method": args.method,
                "questions": len(rows),
                "asked": len(fresh),
                "resumed": len(done),
                "retried": retried,
                "unreadable_lines": broken,
                "refused": sum(1 for row in rows if row["refused"]),
                "errors": sum(1 for row in rows if row["answer"].startswith("ERROR:")),
                "median_seconds": (
                    sorted(row["seconds"] for row in rows)[len(rows) // 2] if rows else None
                ),
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
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Keep the answers already in --out and ask only the missing questions",
    )
    args = parser.parse_args(argv)
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
