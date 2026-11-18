"""RAPTOR, reimplemented faithfully, so the compression claim has a rival.

RAPTOR (Sarthi et al., ICLR 2024) is the only competitor in reach that shares
this layer's premise: spend a model at build time to produce compressed,
question-independent units, then answer at query time with no model at all. The
comparison is therefore about the *method*, not the category.

The configuration is fixed in `E6-PROTOCOL.md` §E16, committed before this file
ran. Every number below is a declared setting, not a tuned one:

* 400-character chunks with 80 of overlap — the paper's 100 tokens / 20 overlap
  at four characters per token;
* `intfloat/e5-large-v2` at revision `f169b11e`, fp32, with the `passage: ` and
  `query: ` prefixes E5 is trained with — the same encoder this layer uses, so
  the embedding is not a variable;
* UMAP to 10 components with `metric="cosine"`, then a spherical Gaussian
  mixture whose component count is chosen by BIC over `2..min(60, n//10)`;
* each cluster summarised by the pilot's own model at `temperature=0`,
  `max_tokens=512`, four in flight — the same model that writes our claims, so
  the comparison isolates the method;
* at most three levels, stopping when fewer than eight nodes remain;
* retrieval by collapsed tree: cosine over every node, chunks and summaries
  together, which is the paper's default and the only mode that calls no model
  at query time.

Three phases, because the build is the only part that costs money and a run that
dies in the second phase must not repeat the first:

    python3 -m benchmark.layer.run_raptor --phase build --layer .../pilot-work/layer
    python3 -m benchmark.layer.run_raptor --phase ask   --layer .../pilot-work/layer
    python3 -m benchmark.layer.run_raptor --phase score --layer .../pilot-work/layer

The build writes one JSON line per summary as soon as it is paid for, so
`--resume` continues a killed build without buying the same cluster twice. The
per-cluster summaries are derivate of the cluster members, which are read from
the tree the previous levels wrote, so a resumed build reconstructs the same
clusters it would have built.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.layer.budget import prefix_cut  # noqa: E402
from benchmark.retrieval.dense import E5_LARGE_V2, SentenceEncoder  # noqa: E402
from benchmark.retrieval.metrics import (  # noqa: E402
    answer_fact_coverage,
    answer_fact_support,
    tokens,
)

SYSTEM = "raptor"
CHUNK_CHARS = 400
CHUNK_OVERLAP = 80
MAX_LEVELS = 3
MIN_NODES = 8
MAX_COMPONENTS = 60
SUMMARY_MAX_TOKENS = 512
# Two hundred nodes fill sixteen thousand characters of four-hundred-character
# chunks; asking for more than the budgets can hold is work that cannot move a
# number.
TOP_K = 400
BUDGETS = (2000, 5000, 10000, 14830)
SEED = 20261118
# No input ceiling. The first build capped a cluster at 24 000 characters and
# 37 of the 60 level-one clusters hit the cap, which is a different algorithm:
# the paper summarises the cluster, not its head. The cap is kept as a knob so
# the truncated build can be reproduced, but the published run sets it high
# enough to never bind.
SUMMARY_INPUT_CHARS = 10**9
CONCURRENCY = 4

PROMPT = """You are summarising a cluster of related passages taken from a technical
documentation corpus. Write a dense, self-contained summary of the factual content
of these passages.

Rules:
- Keep every concrete detail: product and parameter names, default values, limits,
  numbers, units, error messages, version numbers.
- Do not add a single fact that is not in the passages.
- Do not use bullet points, headings or lists. Write continuous prose.
- Write between 150 and 250 words.

Passages:
{passages}

Summary:"""


# --- phase 1: the build ----------------------------------------------------


def chunk(text: str) -> list[str]:
    """Fixed windows with overlap, the paper's chunking in characters."""
    cleaned = " ".join(text.replace("\r", " ").split())
    if not cleaned:
        return []
    step = CHUNK_CHARS - CHUNK_OVERLAP
    out = [cleaned[start : start + CHUNK_CHARS] for start in range(0, len(cleaned), step)]
    return [piece for piece in out if len(piece.strip()) >= 120]


def load_chunks(layer: Path) -> list[dict]:
    nodes: list[dict] = []
    for path in sorted((layer / "corpus").glob("*.txt")):
        for piece in chunk(path.read_text(encoding="utf-8")):
            nodes.append(
                {
                    "node_id": f"c{len(nodes):05d}",
                    "level": 0,
                    "parent": None,
                    "doc": path.stem,
                    "text": piece,
                }
            )
    return nodes


def reduce_dimensions(vectors: np.ndarray, seed: int) -> np.ndarray:
    """UMAP to ten components, the paper's setting."""
    import umap

    if len(vectors) <= 12:
        return vectors
    reducer = umap.UMAP(
        n_components=min(10, len(vectors) - 2),
        metric="cosine",
        random_state=seed,
        n_neighbors=min(15, len(vectors) - 1),
    )
    return np.asarray(reducer.fit_transform(vectors), dtype=np.float32)


def fit_clusters(matrix: np.ndarray, seed: int) -> tuple[object, int, list[dict]]:
    """A spherical mixture whose component count wins on BIC, over the declared grid."""
    from sklearn.mixture import GaussianMixture

    top = max(2, min(MAX_COMPONENTS, len(matrix) // 10))
    tried: list[dict] = []
    best: tuple[float, int, object] | None = None
    for k in range(2, top + 1):
        candidate = GaussianMixture(
            n_components=k,
            covariance_type="spherical",
            random_state=seed,
            n_init=1,
        )
        candidate.fit(matrix)
        score = float(candidate.bic(matrix))
        tried.append({"k": k, "bic": round(score, 1)})
        if best is None or score < best[0]:
            best = (score, k, candidate)
    assert best is not None
    return best[2], best[1], tried


def summarise_one(client, model: str, text: str) -> tuple[str, dict]:
    """One cluster, one call, the usage handed back for the record."""
    started = time.time()
    response = client.chat.completions.create(
        model=model,
        temperature=0,
        max_tokens=SUMMARY_MAX_TOKENS,
        # The gateway's model emits hidden reasoning by default, and those tokens
        # are charged against `max_tokens`: with reasoning on, a 512-token budget
        # buys a truncated summary or none at all. Turning it off is a decoding
        # setting, not a quality knob, and it is the same setting the listwise
        # harness already uses. It is recorded in the build record.
        reasoning_effort="none",
        messages=[{"role": "user", "content": PROMPT.format(passages=text)}],
    )
    usage = getattr(response, "usage", None)
    return (response.choices[0].message.content or "").strip(), {
        "prompt_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
        "completion_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
        "seconds": round(time.time() - started, 1),
    }


def read_rows(path: Path) -> dict[str, dict]:
    done: dict[str, dict] = {}
    if not path.exists():
        return done
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue  # the last write of a killed run, dropped not trusted
        done[row["node_id"]] = row
    return done


def build(layer: Path, device: str | None) -> int:
    from openai import OpenAI

    root = layer / "raptor"
    root.mkdir(parents=True, exist_ok=True)
    rows_path = root / "nodes.jsonl"
    encoder = SentenceEncoder(E5_LARGE_V2, device=device)
    client = OpenAI(
        base_url=os.environ.get("OPENAI_BASE_URL", ""),
        api_key=os.environ.get("OPENAI_API_KEY", ""),
    )
    model = os.environ.get("OPENAI_MODEL", "deepseek-v4.1-flash")
    done = read_rows(rows_path)

    chunks = load_chunks(layer)
    print(f"chunks {len(chunks)}", flush=True)
    current: list[dict] = chunks
    vectors = encoder.encode_passages([node["text"] for node in current])
    levels_done: list[dict] = []

    for level in range(1, MAX_LEVELS + 1):
        if len(current) < MIN_NODES:
            print(f"level {level}: {len(current)} nodes, stop", flush=True)
            break

        reduced = reduce_dimensions(vectors, SEED)
        model_gmm, k, tried = fit_clusters(reduced, SEED)
        labels = model_gmm.predict(reduced)
        print(
            f"level {level}: {len(current)} nodes -> {k} clusters "
            f"(bic {tried[0]['bic']} .. {tried[-1]['bic']})",
            flush=True,
        )

        clusters: list[list[int]] = [[] for _ in range(k)]
        for index, label in enumerate(labels):
            clusters[int(label)].append(index)

        jobs: list[tuple[str, list[int], str, bool]] = []
        for number, members in enumerate(clusters):
            if not members:
                continue
            node_id = f"s{level}-{number:03d}"
            if node_id in done:
                continue
            body = "\n\n".join(current[index]["text"] for index in members)
            truncated = len(body) > SUMMARY_INPUT_CHARS
            jobs.append((node_id, members, body[:SUMMARY_INPUT_CHARS], truncated))

        def paid(job):
            node_id, members, body, _ = job
            text, usage = summarise_one(client, model, body)
            return node_id, members, text, usage

        written: list[dict] = []
        with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
            for node_id, members, text, usage in pool.map(paid, jobs):
                if not text:
                    print(f"  {node_id}: empty summary, skipped", flush=True)
                    continue
                row = {
                    "node_id": node_id,
                    "level": level,
                    "parent": None,
                    "doc": None,
                    "members": len(members),
                    "member_ids": [current[index]["node_id"] for index in members],
                    "text": text,
                    **usage,
                }
                written.append(row)
                done[node_id] = row
                with rows_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                    handle.flush()
                print(
                    f"  {node_id} {len(text):5d} ch  in {usage['prompt_tokens']:6d} "
                    f"out {usage['completion_tokens']:5d}  {usage['seconds']:5.1f}s",
                    flush=True,
                )

        hit = sum(1 for job in jobs if job[3])
        # A resumed build finds its clusters already paid for and writes nothing;
        # the level still exists, and the next level must read the whole of it.
        built = sorted(
            (row for row in done.values() if row["level"] == level),
            key=lambda row: row["node_id"],
        )
        if not built:
            print(f"level {level}: nothing on disk, stop", flush=True)
            break
        levels_done.append(
            {
                "level": level,
                "clusters": k,
                "summaries": len(built),
                "paid_this_run": len(written),
                "ceiling_hits": hit,
                "bic": tried,
            }
        )
        print(
            f"level {level}: {len(built)} summaries ({len(written)} paid this run), "
            f"{hit} clusters hit the input ceiling",
            flush=True,
        )
        current = built
        vectors = encoder.encode_passages([row["text"] for row in current])

    payload = {
        "system": SYSTEM,
        "chunks": len(chunks),
        "chunk_chars": CHUNK_CHARS,
        "chunk_overlap": CHUNK_OVERLAP,
        "max_levels": MAX_LEVELS,
        "summary_max_tokens": SUMMARY_MAX_TOKENS,
        "reasoning_effort": "none",
        "summary_input_chars": SUMMARY_INPUT_CHARS,
        "seed": SEED,
        "nodes_written": len(done),
        "levels": levels_done,
        "mechanism": {
            "reduction": "umap(n_components=10, metric=cosine)",
            "clustering": "GaussianMixture(covariance_type=spherical), BIC over 2..min(60,n//10)",
            "prompt_hash": _digest(PROMPT),
        },
    }
    (root / "build.json").write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(f"build record written, {len(done)} nodes", flush=True)
    return 0


def _digest(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# --- phase 2: the queries --------------------------------------------------


def all_nodes(layer: Path) -> list[dict]:
    nodes = load_chunks(layer)
    rows_path = layer / "raptor" / "nodes.jsonl"
    if rows_path.exists():
        nodes.extend(read_rows(rows_path).values())
    return nodes


def ask(layer: Path, half: str, device: str | None) -> int:
    selection = json.loads((layer / "corpus/selection.json").read_text(encoding="utf-8"))
    split = json.loads((layer / "runs/split.json").read_text(encoding="utf-8"))
    wanted = None if half == "all" else set(split[half])
    items = [
        item
        for item in selection["items"]
        if (wanted is None or item["qid"] in wanted) and item.get("gold_facts")
    ]

    nodes = all_nodes(layer)
    encoder = SentenceEncoder(E5_LARGE_V2, device=device)
    matrix = encoder.encode_passages([node["text"] for node in nodes])
    out = layer / "runs" / f"raptor.{half}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)

    started = time.time()
    with out.open("w", encoding="utf-8") as handle:
        for position, item in enumerate(items, 1):
            query = encoder.encode_query(item["text"])
            scores = matrix @ query
            order = np.argsort(-scores)[:TOP_K]
            handle.write(
                json.dumps(
                    {
                        "qid": item["qid"],
                        "system": SYSTEM,
                        "method": "collapsed-tree",
                        "evidence": [nodes[int(index)]["text"] for index in order],
                        "levels": [int(nodes[int(index)]["level"]) for index in order],
                        "seconds": round(time.time() - started, 1),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            handle.flush()
            if position % 25 == 0:
                print(f"{position}/{len(items)}", flush=True)
    print(f"written {out}  nodes {len(nodes)}  {time.time() - started:.0f}s", flush=True)
    return 0


# --- phase 3: the scoring --------------------------------------------------


def type_precision(gold: set[str], question: set[str], text: str) -> float:
    seen = set(tokens(text)) - question
    return len(seen & gold) / len(seen) if seen else 0.0


def background_types(layer: Path, share: float = 0.5) -> set[str]:
    paths = sorted((layer / "corpus").glob("*.txt"))
    counts: dict[str, int] = {}
    for path in paths:
        for token in set(tokens(path.read_text(encoding="utf-8"))):
            counts[token] = counts.get(token, 0) + 1
    limit = share * len(paths)
    return {token for token, count in counts.items() if count > limit}


def score(
    layer: Path, half: str, source: str | None = None, only_summaries: bool = False
) -> int:
    selection = json.loads((layer / "corpus/selection.json").read_text(encoding="utf-8"))
    split = json.loads((layer / "runs/split.json").read_text(encoding="utf-8"))
    wanted = None if half == "all" else set(split[half])
    items = [
        item
        for item in selection["items"]
        if (wanted is None or item["qid"] in wanted) and item.get("gold_facts")
    ]
    rows: dict[str, list[str]] = {}
    path = layer / "runs" / f"raptor.{source or half}.jsonl"
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if only_summaries:
                # The compressed artifact alone, in the order the tree ranked it.
                rows[row["qid"]] = [
                    text
                    for text, level in zip(row["evidence"], row["levels"])
                    if int(level) >= 1
                ]
            else:
                rows[row["qid"]] = row["evidence"]

    background = background_types(layer)
    table = []
    per_budget: dict[str, dict[str, dict[str, float]]] = {}
    for budget in BUDGETS:
        recall: dict[str, float] = {}
        support: dict[str, float] = {}
        precision: dict[str, float] = {}
        chars: list[int] = []
        units: list[int] = []
        for item in items:
            kept = prefix_cut(rows[item["qid"]], budget)
            gold: set[str] = set()
            for fact in item["gold_facts"]:
                gold |= set(tokens(fact))
            question = set(tokens(item["text"])) | background
            recall[item["qid"]] = answer_fact_coverage(item["gold_facts"], kept)
            support[item["qid"]] = answer_fact_support(item["gold_facts"], kept)
            precision[item["qid"]] = type_precision(gold, question, "\n".join(kept))
            chars.append(sum(len(piece) for piece in kept))
            units.append(len(kept))
        f1 = {
            qid: (2 * recall[qid] * precision[qid] / (recall[qid] + precision[qid]))
            if recall[qid] + precision[qid] > 0
            else 0.0
            for qid in recall
        }
        row = {
            "budget": budget,
            "coverage": round(statistics.mean(recall.values()) * 100, 2),
            "support": round(statistics.mean(support.values()) * 100, 2),
            "precision": round(statistics.mean(precision.values()) * 100, 2),
            "f1": round(statistics.mean(f1.values()) * 100, 2),
            "characters_median": int(statistics.median(chars)),
            "units_median": int(statistics.median(units)),
        }
        table.append(row)
        per_budget[str(budget)] = {
            "coverage": recall,
            "support": support,
            "precision": precision,
        }
        print(
            f"budget {budget:6d}  {row['coverage']:6.2f}% (support {row['support']:5.2f}% "
            f"prec {row['precision']:5.2f}% F1 {row['f1']:5.2f})  chars "
            f"{row['characters_median']:5d}  units {row['units_median']:3d}",
            flush=True,
        )

    suffix = "-summaries" if only_summaries else ""
    out = layer / "runs" / f"raptor-score-{half}{suffix}.json"
    out.write_text(
        json.dumps(
            {
                "system": SYSTEM + ("-summaries" if only_summaries else ""),
                "half": half,
                "questions": len(items),
                "seed": SEED,
                "rows": table,
                "per_question": per_budget,
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"written {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--layer", type=Path, required=True)
    parser.add_argument("--phase", required=True, choices=("build", "ask", "score"))
    parser.add_argument("--half", default="all", choices=("dev", "test", "all"))
    parser.add_argument("--device", default=None)
    parser.add_argument("--only-summaries", action="store_true",
                        help="score the compressed nodes alone, no leaf chunks")
    parser.add_argument(
        "--source", default=None,
        help="which evidence file to score; defaults to the half being scored",
    )
    args = parser.parse_args(argv)

    if args.phase == "build":
        return build(args.layer, args.device)
    if args.phase == "ask":
        return ask(args.layer, args.half, args.device)
    return score(args.layer, args.half, args.source, args.only_summaries)


if __name__ == "__main__":
    sys.exit(main())
