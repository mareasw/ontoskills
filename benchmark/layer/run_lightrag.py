"""Ask LightRAG the pilot's questions, and write what `score.py` scores.

LightRAG is measured as it ships: its own chunker, its own entity extraction, its
own retrieval modes, its own prompt for a synthesised answer. The only things
pinned from outside are the ones fairness requires — the corpus bytes, the model
id, the endpoints — and the adapter refuses to hide the rest behind a nicer
default.

Two phases, because building costs money and asking costs time, and a run that
dies in the second phase should not repeat the first:

    python3 -m benchmark.layer.run_lightrag --phase ingest --corpus /tmp/layer/corpus \\
        --working-dir /tmp/layer/lightrag --limit 5
    python3 -m benchmark.layer.run_lightrag --phase ask --working-dir /tmp/layer/lightrag \\
        --selection /tmp/layer/corpus/selection.json --out /tmp/layer/runs/lightrag.jsonl

The answer modality is ``answer``: LightRAG returns prose, not ranked passages.
A refusal is read from the text with ``text_refusal.looks_like_refusal``, the
same function applied to every prose system, and the raw text is kept in the run
file so the classification can be audited.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.layer.text_refusal import looks_like_refusal  # noqa: E402

SYSTEM = "lightrag"
MODEL = os.environ.get("PILOT_MODEL", "deepseek-v4.1-flash")
BASE_URL = os.environ.get("PILOT_BASE_URL", "")
API_KEY = os.environ.get("PILOT_API_KEY", "")
EMBED_URL = os.environ.get("PILOT_EMBED_URL", "http://127.0.0.1:8091/v1")
EMBED_MODEL = os.environ.get("PILOT_EMBED_MODEL", "e5-large-v2")
EMBED_DIM = 1024
EMBED_MAX_TOKENS = 512
# The gateway answers 503 when several builds hit it at once, so the number of
# requests in flight is a declared setting, not an accident of the framework's
# default: it is the same ceiling the OntoSkills build uses (8), and the builds
# are run one at a time.
LLM_ASYNC = int(os.environ.get("PILOT_LLM_ASYNC", "8"))


def build_rag(working_dir: Path):
    """A LightRAG instance wired to the pilot's endpoints and nothing else."""
    from lightrag import LightRAG
    from lightrag.llm.openai import openai_complete_if_cache, openai_embed
    from lightrag.utils import EmbeddingFunc

    async def llm_model_func(prompt, system_prompt=None, history_messages=None, **kwargs):
        return await openai_complete_if_cache(
            MODEL,
            prompt,
            system_prompt=system_prompt,
            history_messages=history_messages or [],
            base_url=BASE_URL,
            api_key=API_KEY,
            **kwargs,
        )

    async def embedding_func(texts):
        # ``openai_embed`` is decorated with ``embedding_dim=1536`` — the OpenAI
        # default — and validates every batch against it, so calling it directly
        # killed the first smoke run at flush time with a dimension error, after
        # the extraction had already been paid for. ``.func`` is the undecorated
        # callable; the dimension is declared once, by the wrapper below.
        return await openai_embed.func(
            texts, model=EMBED_MODEL, base_url=EMBED_URL, api_key="local-sidecar"
        )

    return LightRAG(
        working_dir=str(working_dir),
        llm_model_func=llm_model_func,
        embedding_func=EmbeddingFunc(
            embedding_dim=EMBED_DIM,
            max_token_size=EMBED_MAX_TOKENS,
            func=embedding_func,
        ),
        # The corpus is 279 short documents: a handful in flight keeps the
        # gateway busy without turning a rate limit into a night of retries.
        llm_model_max_async=LLM_ASYNC,
        embedding_func_max_async=4,
    )


async def ingest(rag, corpus: Path, limit: int | None) -> int:
    documents = sorted(corpus.glob("*.txt"))
    if limit:
        documents = documents[:limit]
    for number, path in enumerate(documents, start=1):
        text = path.read_text(encoding="utf-8")
        started = time.time()
        await rag.ainsert(text, ids=path.stem, file_paths=str(path))
        print(
            f"{number}/{len(documents)} {path.stem} {len(text)} chars "
            f"{time.time() - started:.1f}s",
            flush=True,
        )
    return len(documents)


async def ask(rag, selection: dict, out: Path) -> int:
    from lightrag import QueryParam

    rows = []
    for item in selection["items"]:
        started = time.time()
        answer = await rag.aquery(item["text"], param=QueryParam(mode="mix"))
        text = answer if isinstance(answer, str) else str(answer)
        rows.append(
            {
                "qid": item["qid"],
                "system": SYSTEM,
                "answer": text,
                "refused": looks_like_refusal(text),
                "seconds": round(time.time() - started, 3),
            }
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "system": SYSTEM,
                "questions": len(rows),
                "refused": sum(1 for row in rows if row["refused"]),
                "median_seconds": sorted(row["seconds"] for row in rows)[len(rows) // 2],
                "out": str(out),
            },
            indent=1,
        )
    )
    return len(rows)


async def run(args) -> int:
    rag = build_rag(args.working_dir)
    await rag.initialize_storages()
    try:
        if args.phase in ("ingest", "all"):
            count = await ingest(rag, args.corpus, args.limit)
            print(f"ingested {count} documents", flush=True)
        if args.phase in ("ask", "all"):
            selection = json.loads(args.selection.read_text(encoding="utf-8"))
            await ask(rag, selection, args.out)
    finally:
        await rag.finalize_storages()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--phase", choices=("ingest", "ask", "all"), default="all")
    parser.add_argument("--corpus", type=Path, default=Path("corpus"))
    parser.add_argument("--working-dir", type=Path, required=True)
    parser.add_argument("--selection", type=Path, default=Path("corpus/selection.json"))
    parser.add_argument("--out", type=Path, default=Path("runs/lightrag.jsonl"))
    parser.add_argument("--limit", type=int, default=None, help="First N documents only")
    args = parser.parse_args(argv)

    if not BASE_URL or not API_KEY:
        raise SystemExit("set PILOT_BASE_URL and PILOT_API_KEY to the pilot's endpoints")
    args.working_dir.mkdir(parents=True, exist_ok=True)
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
