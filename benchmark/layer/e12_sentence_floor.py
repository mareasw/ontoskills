"""E12: the sentence floor — the control that decides what the claim layer is worth.

The statement row in E9 is a *replication* of a published finding: retrieving
propositions instead of passages wins at a fixed word budget (Dense X Retrieval,
EMNLP 2024). A reviewer will therefore ask the question the pilot has not
answered: is the gain the claim layer, or is it just the granularity?

This row answers it without a model. Every document is cut into sentences, BM25
ranks the sentences, and the best ones are returned up to the same character
budget. Nothing semantic, nothing verified, no claim, no provenance — the same
kind of text at the same size. If the claim layer cannot beat this, the layer is
buying granularity and nothing else, and that is what will be published.

Everything runs on the CPU: no model, no key, no spend.

    python3 -m benchmark.layer.e12_sentence_floor --layer .../pilot-work/layer --half dev
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.layer.budget import prefix_cut  # noqa: E402
from benchmark.retrieval.baselines import BM25  # noqa: E402
from benchmark.retrieval.metrics import answer_fact_coverage, answer_fact_support  # noqa: E402

BUDGETS = (2000, 5000, 10000, 14830)
SEED = 20261118
TOP_K = 400
MIN_CHARS = 50
SPLIT = re.compile(r"(?<=[.!?])\s+")


def sentences(text: str) -> list[str]:
    """Sentences, with fragments merged forward so no unit is a label or a heading.

    The split is punctuation-only and deliberately dumb: it is the control, and a
    control that needed a model to segment would not isolate the variable.
    """
    out: list[str] = []
    buffer = ""
    for piece in SPLIT.split(text.replace("\r", " ")):
        piece = " ".join(piece.split())
        if not piece:
            continue
        buffer = f"{buffer} {piece}".strip() if buffer else piece
        if len(buffer) >= MIN_CHARS:
            out.append(buffer)
            buffer = ""
    if buffer:
        out.append(buffer)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--layer", type=Path, required=True)
    parser.add_argument("--half", default="dev", choices=("dev", "test", "all"))
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)

    layer = args.layer
    selection = json.loads((layer / "corpus/selection.json").read_text(encoding="utf-8"))
    split = json.loads((layer / "runs/split.json").read_text(encoding="utf-8"))
    wanted = None if args.half == "all" else set(split[args.half])
    items = [
        i for i in selection["items"]
        if (wanted is None or i["qid"] in wanted) and i.get("gold_facts")
    ]

    started = time.time()
    units: dict[str, str] = {}
    lengths: list[int] = []
    for path in sorted((layer / "corpus").glob("*.txt")):
        for number, sentence in enumerate(sentences(path.read_text(encoding="utf-8"))):
            units[f"{path.stem}::{number:04d}"] = sentence
            lengths.append(len(sentence))
    index = BM25(units, cache=None)
    build_seconds = time.time() - started

    started = time.time()
    raw: dict[str, dict[str, dict[str, float]]] = {}
    table = []
    for budget in BUDGETS:
        values, supports, chars, counts = {}, {}, [], []
        for item in items:
            ranked = index.search(item["text"], top_k=TOP_K)
            kept = prefix_cut([units[unit_id] for unit_id in ranked], budget)
            values[item["qid"]] = answer_fact_coverage(item["gold_facts"], kept)
            supports[item["qid"]] = answer_fact_support(item["gold_facts"], kept)
            chars.append(sum(len(k) for k in kept))
            counts.append(len(kept))
        raw[str(budget)] = {"coverage": values, "support": supports}
        row = {
            "budget": budget,
            "coverage": round(statistics.mean(values.values()) * 100, 2),
            "support": round(statistics.mean(supports.values()) * 100, 2),
            "characters_median": int(statistics.median(chars)),
            "units_median": int(statistics.median(counts)),
        }
        table.append(row)
        print(
            f"budget {budget:6d}  sentences {row['coverage']:6.2f}% "
            f"(support {row['support']:5.2f}%)  chars {row['characters_median']:5d}  "
            f"units {row['units_median']:3d}",
            flush=True,
        )

    out = args.json or layer / f"runs/e12-sentence-floor-{args.half}.json"
    payload = {
        "half": args.half,
        "questions": len(items),
        "seed": SEED,
        "units": len(units),
        "min_chars": MIN_CHARS,
        "top_k": TOP_K,
        "seconds": round(time.time() - started, 1),
        "build_seconds": round(build_seconds, 1),
        "median_unit_chars": int(statistics.median(lengths)),
        "rows": table,
    }
    out.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    out.with_suffix(".values.json").write_text(
        json.dumps({"half": args.half, "seed": SEED, "questions": len(items), "values": raw},
                   indent=1),
        encoding="utf-8",
    )
    print(f"written {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
