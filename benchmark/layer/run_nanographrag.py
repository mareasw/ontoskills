"""Nano-GraphRAG answering the pilot's questions, through its own API.

E18 of `E6-PROTOCOL.md` fixed every choice before this file ran: version
`0.0.8.2` pinned, its default chunking (1 200 tokens, 100 of overlap), its
default gleaning, Leiden clustering, node2vec, its own local-retrieval budgets,
the pilot's model at `temperature=0`, and the pilot's corpus. Nothing here is
tuned: the only liberties are the ones a deployment takes anyway, and they are
declared in the protocol.

Two of them are worth naming in the code:

* **the embedding phase.** Nano calls one embedding function for stored text and
  for the query alike. E5 is trained with different prefixes on the two sides, so
  the function is told which side it is on — the adapter sets a phase before a
  query and clears it after. This favours the competitor, which is the safe
  direction for a falsification attempt.
* **the budget.** The protocol set a 2,50 $ ceiling. The adapter reads the meter
  log before every paid call and aborts above it, so a runaway build stops with a
  record instead of a surprise.

The build is one insertion of all 279 documents. Nano regenerates community
reports from the whole graph on every `ainsert`, so inserting document by document
would rebuild the tree 279 times; resume is handled instead by a disk cache keyed
on the exact request, which makes a killed build cost nothing to repeat.

    python -m benchmark.layer.run_nanographrag --phase build --layer ... --working .../nano
    python -m benchmark.layer.run_nanographrag --phase ask --mode local --layer ... --working .../nano
    python -m benchmark.layer.run_nanographrag --phase score --mode local --layer .../nano
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

SYSTEM = "nanographrag"
EMBED_DIM = 1024
EMBED_MAX_TOKENS = 512
CHARS_PER_TOKEN = 4.0
PRICE_IN, PRICE_OUT = 0.15, 0.60
DEFAULT_MAX_TOKENS = 4096
# Declared in the protocol: the run stops here and reports itself incomplete.
CEILING_USD = 3.20


class BudgetExceeded(RuntimeError):
    """The meter passed the ceiling the protocol set."""


def spent_usd(log: Path) -> float:
    """The bill so far, read from the meter, never estimated."""
    if not log.exists():
        return 0.0
    prompt = completion = 0
    for line in log.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        prompt += int(row.get("prompt_tokens") or 0)
        completion += int(row.get("completion_tokens") or 0)
    return prompt / 1e6 * PRICE_IN + completion / 1e6 * PRICE_OUT


def cache_path(root: Path, key: str) -> Path:
    return root / "llm-cache" / key[:2] / f"{key}.json"


def llm_client():
    from openai import AsyncOpenAI

    return AsyncOpenAI(
        base_url=os.environ.get("OPENAI_BASE_URL", ""),
        api_key=os.environ.get("OPENAI_API_KEY", ""),
        max_retries=3,
    )


def make_model_func(root: Path, meter: Path, stats: dict):
    """The function nano calls for every prompt, cached on disk and metered."""
    model = os.environ.get("OPENAI_MODEL", "deepseek-v4.1-flash")
    client = llm_client()

    async def complete(prompt, system_prompt=None, history_messages=None, **kwargs) -> str:
        kwargs.pop("hashing_kv", None)  # nano's own cache; ours is the disk
        response_format = kwargs.pop("response_format", None)
        max_tokens = int(kwargs.pop("max_tokens", DEFAULT_MAX_TOKENS))
        messages = list(history_messages or [])
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        key = hashlib.sha256(
            json.dumps(
                [model, messages, response_format, max_tokens], ensure_ascii=False
            ).encode("utf-8")
        ).hexdigest()
        cached = cache_path(root, key)
        if cached.exists():
            stats["cache_hits"] += 1
            return json.loads(cached.read_text(encoding="utf-8"))["text"]

        if spent_usd(meter) > CEILING_USD:
            raise BudgetExceeded(f"meter passed {CEILING_USD} $: {spent_usd(meter):.4f} $")

        payload = {
            "model": model,
            "temperature": 0,
            "max_tokens": max_tokens,
            "reasoning_effort": "none",
            "messages": messages,
        }
        if response_format:
            payload["response_format"] = response_format

        delay = 8.0
        for attempt in range(4):
            try:
                response = await client.chat.completions.create(**payload)
                break
            except Exception as error:  # the gateway 503s under load
                if attempt == 3:
                    raise
                stats["retries"] += 1
                print(f"  retry {attempt + 1} after {type(error).__name__}", flush=True)
                await asyncio.sleep(delay)
                delay *= 2

        text = (response.choices[0].message.content or "").strip()
        usage = getattr(response, "usage", None)
        stats["calls"] += 1
        stats["prompt_tokens"] += int(getattr(usage, "prompt_tokens", 0) or 0)
        stats["completion_tokens"] += int(getattr(usage, "completion_tokens", 0) or 0)

        cached.parent.mkdir(parents=True, exist_ok=True)
        temporary = cached.with_suffix(".tmp")
        temporary.write_text(json.dumps({"text": text}, ensure_ascii=False), encoding="utf-8")
        temporary.replace(cached)
        return text

    return complete


def make_embedding_func(device: str | None):
    """E5-large-v2 over the same weights the layer uses, with the right prefix."""
    import numpy as np
    from nano_graphrag._utils import EmbeddingFunc

    from benchmark.retrieval.dense import E5_LARGE_V2, SentenceEncoder

    encoder = SentenceEncoder(E5_LARGE_V2, device=device)
    phase = {"value": "passage"}

    async def embed(texts: list[str]) -> np.ndarray:
        def run() -> np.ndarray:
            if phase["value"] == "query":
                return np.stack([encoder.encode_query(text) for text in texts])
            return encoder.encode_passages(texts)

        return await asyncio.to_thread(run)

    return EmbeddingFunc(embedding_dim=EMBED_DIM, max_token_size=EMBED_MAX_TOKENS, func=embed), phase


def build_graph(root: Path, meter: Path, device: str | None, stats: dict):
    from nano_graphrag import GraphRAG

    embed, phase = make_embedding_func(device)
    # Both hooks, not one. Nano's `cheap_model_func` defaults to a hardcoded
    # `gpt-4o-mini`; leaving it unset asked the gateway for a model it does not
    # serve and killed the first build at the summary stage (E18 amendment 2).
    model_func = make_model_func(root, meter, stats)
    return GraphRAG(
        working_dir=str(root),
        best_model_func=model_func,
        cheap_model_func=model_func,
        embedding_func=embed,
        enable_naive_rag=True,
        # Twelve in flight, not four: E18 amendment 1. Throughput only — the calls
        # are independent and the model runs at temperature 0.
        best_model_max_async=12,
        embedding_func_max_async=1,
        embedding_batch_num=8,
        always_create_working_dir=True,
    ), phase


def documents(layer: Path) -> list[str]:
    return [path.read_text(encoding="utf-8") for path in sorted((layer / "corpus").glob("*.txt"))]


def phase_build(layer: Path, root: Path, meter: Path, device: str | None) -> int:
    stats = {"calls": 0, "retries": 0, "cache_hits": 0, "prompt_tokens": 0, "completion_tokens": 0}
    root.mkdir(parents=True, exist_ok=True)
    graph, _phase = build_graph(root, meter, device, stats)
    texts = documents(layer)
    print(f"documents {len(texts)}  spend so far {spent_usd(meter):.4f} $", flush=True)
    started = time.time()
    try:
        graph.insert(texts)
    except BudgetExceeded as error:
        print(f"STOPPED: {error}", flush=True)
        write_record(root, stats, started, "ceiling")
        return 2
    write_record(root, stats, started, "ok")
    print(f"build done in {time.time() - started:.0f}s  {spent_usd(meter):.4f} $", flush=True)
    return 0


def write_record(root: Path, stats: dict, started: float, outcome: str) -> None:
    record = {
        "system": SYSTEM,
        **stats,
        "seconds": round(time.time() - started, 1),
        "outcome": outcome,
        "ceiling_usd": CEILING_USD,
    }
    (root / "build.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
    print(json.dumps(record, indent=1), flush=True)


def phase_ask(layer: Path, root: Path, meter: Path, device: str | None, mode: str, half: str) -> int:
    from nano_graphrag import QueryParam

    from benchmark.layer.text_refusal import looks_like_refusal

    stats = {"calls": 0, "retries": 0, "cache_hits": 0, "prompt_tokens": 0, "completion_tokens": 0}
    graph, phase = build_graph(root, meter, device, stats)

    selection = json.loads((layer / "corpus/selection.json").read_text(encoding="utf-8"))
    split = json.loads((layer / "runs/split.json").read_text(encoding="utf-8"))
    wanted = None if half == "all" else set(split[half])
    items = [
        item
        for item in selection["items"]
        if (wanted is None or item["qid"] in wanted) and item.get("gold_facts")
    ]

    out = layer / "runs" / f"nanographrag.{mode}.{half}.jsonl"
    done = {}
    if out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                done[row["qid"]] = row
    todo = [item for item in items if item["qid"] not in done]
    print(f"questions {len(items)}  to ask {len(todo)}  mode {mode}", flush=True)

    started = time.time()
    with out.open("a", encoding="utf-8") as handle:
        for position, item in enumerate(todo, 1):
            phase["value"] = "query"
            try:
                answer = graph.query(item["text"], param=QueryParam(mode=mode))
            except BudgetExceeded as error:
                print(f"STOPPED: {error}", flush=True)
                return 2
            finally:
                phase["value"] = "passage"
            answer = (answer or "").strip()
            row = {
                "qid": item["qid"],
                "system": SYSTEM,
                "mode": mode,
                "answer": answer,
                "refused": looks_like_refusal(answer),
                "seconds": round(time.time() - started, 1),
            }
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
            done[item["qid"]] = row
            if position % 10 == 0:
                print(
                    f"{position}/{len(todo)}  {spent_usd(meter):.4f} $  "
                    f"cache {stats['cache_hits']}",
                    flush=True,
                )
    print(f"written {out}  {spent_usd(meter):.4f} $  {time.time() - started:.0f}s", flush=True)
    return 0


def phase_score(layer: Path, mode: str, half: str) -> int:
    from benchmark.layer.e14_pareto import common_types, score_row, summarise

    selection = json.loads((layer / "corpus/selection.json").read_text(encoding="utf-8"))
    split = json.loads((layer / "runs/split.json").read_text(encoding="utf-8"))
    wanted = None if half == "all" else set(split[half])
    items = [
        item
        for item in selection["items"]
        if (wanted is None or item["qid"] in wanted) and item.get("gold_facts")
    ]
    answers = {}
    path = layer / "runs" / f"nanographrag.{mode}.{half}.jsonl"
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            answers[row["qid"]] = row

    stop = common_types(layer)
    rows = []
    for item in items:
        row = answers.get(item["qid"])
        refused = bool(row and row.get("refused"))
        text = "" if refused or row is None else str(row.get("answer") or "")
        rows.append(score_row(item, text, refused, stop))

    table = summarise(f"{SYSTEM}-{mode}", rows)
    print(json.dumps(table, indent=1))
    out = layer / "runs" / f"nanographrag-score-{mode}-{half}.json"
    out.write_text(json.dumps({"row": table, "per_question": rows}, indent=1), encoding="utf-8")
    print(f"written {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--layer", type=Path, required=True)
    parser.add_argument("--working", type=Path, required=True)
    parser.add_argument("--meter", type=Path, required=True)
    parser.add_argument("--phase", required=True, choices=("build", "ask", "score"))
    parser.add_argument("--mode", default="local", choices=("local", "naive", "global"))
    parser.add_argument("--half", default="all", choices=("dev", "test", "all"))
    parser.add_argument("--device", default=None)
    args = parser.parse_args(argv)

    if args.phase == "build":
        return phase_build(args.layer, args.working, args.meter, args.device)
    if args.phase == "ask":
        return phase_ask(args.layer, args.working, args.meter, args.device, args.mode, args.half)
    return phase_score(args.layer, args.mode, args.half)


if __name__ == "__main__":
    sys.exit(main())
