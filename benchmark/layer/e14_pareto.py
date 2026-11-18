"""E14: the comparison that costs money to dispute — tokens in, tokens out.

Every other table in this pilot holds characters constant. An agent does not pay
characters, it pays context tokens, so this one converts and then asks the two
questions a buyer asks:

* at the same tokens returned, which system covers more of the gold answer facts?
* at the same coverage, which system returns fewer tokens?

Coverage alone rewards dumping: a system that returns the whole corpus covers
every fact and is useless. So precision is measured here for the first time —
the fraction of returned *types* that belong to the gold facts — and F1 with it.
Precision is type-level (a repeated word counts once), which is the choice that
does not let a system farm a score by repeating itself.

The conversion is declared, not tuned: **four characters per token**, the usual
English estimate. Word counts are reported beside it so a reader can check the
conversion against their own tokenizer.

Every system runs on the same slice, the same questions and the same gold facts:

* ``ours`` — the frozen order, rendered as quote or statement, cut by budget;
* ``floor`` — the 4 800-character BM25 passages, cut by budget;
* ``sentences`` — BM25 over single sentences at the same budget;
* ``graphrag`` — its own written answer, at whatever length it chose, with its
  refusals kept as a separate outcome and counted as failures in the strict view.

    python3 -m benchmark.layer.e14_pareto --layer .../pilot-work/layer --half dev
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.layer import claim_vectors, select  # noqa: E402
from benchmark.layer.budget import prefix_cut  # noqa: E402
from benchmark.layer.e12_sentence_floor import sentences  # noqa: E402
from benchmark.retrieval.baselines import BM25  # noqa: E402
from benchmark.retrieval.dense import E5_LARGE_V2, SentenceEncoder  # noqa: E402
from benchmark.retrieval.metrics import answer_fact_coverage, answer_fact_support, tokens  # noqa: E402

BUDGETS = (2000, 5000, 10000, 14830)
SEED = 20261118
CHARS_PER_TOKEN = 4.0
UNITS = ("quote", "statement")


def render(claim, unit: str) -> str:
    statement = (claim.get("statement") or "").strip()
    quotes = [q for q in ((e.get("quote") or "").strip() for e in claim.get("evidence") or []) if q]
    if unit == "quote":
        return quotes[0] if quotes else statement
    if unit == "statement":
        return statement
    raise ValueError(unit)


def type_precision(gold_types: set[str], returned: str) -> float:
    """Of the distinct words returned, the share that the gold facts also use."""
    seen = set(tokens(returned))
    if not seen:
        return 0.0
    return len(seen & gold_types) / len(seen)


def f1(recall: float, precision: float) -> float:
    if recall + precision <= 0:
        return 0.0
    return 2 * recall * precision / (recall + precision)


def ours_rows(
    layer: Path, items: list[dict], device: str | None, depth: int = select.DEPTH
) -> dict[str, dict[str, list[str]]]:
    """The frozen order rendered both ways, one row per question, cached on disk."""
    cache = layer / f"runs/e14-ours-d{depth}.jsonl"
    done = {}
    if cache.exists():
        for line in cache.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                done[row["qid"]] = row
    todo = [item for item in items if item["qid"] not in done]
    if todo:
        corpus = select._corpus(layer / "kb", False)
        by_id = {claim["claim_id"]: claim for claim in corpus.claims}
        ids, matrix = claim_vectors.read(layer / "runs/claim-vectors.npz")
        row_of = {claim_id: index for index, claim_id in enumerate(ids)}
        encoder = SentenceEncoder(E5_LARGE_V2, device=device)
        for position, item in enumerate(todo, 1):
            query = encoder.encode_query(item["text"])
            pool = corpus.search(item["text"], limit=depth)
            dense = select.dense_order(pool, row_of, matrix, query)
            chosen = select.cover(dense, corpus, item["text"], min(200, len(dense)))
            row = {"qid": item["qid"], **{
                unit: [render(by_id.get(c.claim_id), unit)
                       for c in chosen if by_id.get(c.claim_id)]
                for unit in UNITS
            }}
            with cache.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                handle.flush()
            print(f"{position:3d}/{len(todo)} {item['qid']}", file=sys.stderr, flush=True)
            done[item["qid"]] = row
    return done


def sentence_rows(layer: Path, items: list[dict]) -> dict[str, list[str]]:
    units: dict[str, str] = {}
    for path in sorted((layer / "corpus").glob("*.txt")):
        for number, sentence in enumerate(sentences(path.read_text(encoding="utf-8"))):
            units[f"{path.stem}::{number:04d}"] = sentence
    index = BM25(units, cache=None)
    return {
        item["qid"]: [units[unit_id] for unit_id in index.search(item["text"], top_k=400)]
        for item in items
    }


def score_row(item: dict, text: str, refused: bool) -> dict:
    gold_types: set[str] = set()
    for fact in item["gold_facts"]:
        gold_types |= set(tokens(fact))
    recall = answer_fact_coverage(item["gold_facts"], text) if text else 0.0
    precision = type_precision(gold_types, text) if text else 0.0
    return {
        "qid": item["qid"],
        "chars": len(text),
        "tokens": int(math.ceil(len(text) / CHARS_PER_TOKEN)),
        "words": len(tokens(text)),
        "recall": recall,
        "precision": precision,
        "f1": f1(recall, precision),
        "support": answer_fact_support(item["gold_facts"], [text]) if text else 0.0,
        "refused": refused,
    }


def summarise(name: str, rows: list[dict]) -> dict:
    answered = [row for row in rows if not row["refused"]]
    strict = rows

    def mean(rows_, key):
        return statistics.mean(row[key] for row in rows_) * 100 if rows_ else 0.0

    return {
        "system": name,
        "questions": len(rows),
        "answered": len(answered),
        "refusal_rate": round((len(rows) - len(answered)) / len(rows) * 100, 2) if rows else 0.0,
        "tokens_median": int(statistics.median(row["tokens"] for row in rows)) if rows else 0,
        "words_median": int(statistics.median(row["words"] for row in rows)) if rows else 0,
        "recall_answered": round(mean(answered, "recall"), 2),
        "recall_strict": round(mean(strict, "recall"), 2),
        "precision_answered": round(mean(answered, "precision"), 2),
        "precision_strict": round(mean(strict, "precision"), 2),
        "f1_answered": round(mean(answered, "f1"), 2),
        "f1_strict": round(mean(strict, "f1"), 2),
        "support_answered": round(mean(answered, "support"), 2),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--layer", type=Path, required=True)
    parser.add_argument("--half", default="dev", choices=("dev", "test", "all"))
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--device", default=None)
    parser.add_argument("--depth", type=int, default=select.DEPTH, help="claim pool depth")
    args = parser.parse_args(argv)

    layer = args.layer
    selection = json.loads((layer / "corpus/selection.json").read_text(encoding="utf-8"))
    split = json.loads((layer / "runs/split.json").read_text(encoding="utf-8"))
    wanted = None if args.half == "all" else set(split[args.half])
    items = [
        i for i in selection["items"]
        if (wanted is None or i["qid"] in wanted) and i.get("gold_facts")
    ]

    ours = ours_rows(layer, items, args.device, args.depth)
    sentence = sentence_rows(layer, items)

    floor = {}
    for line in (layer / "runs/floor.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            floor[row["qid"]] = row.get("evidence") or []

    graphrag = {}
    for line in (layer / "runs/graphrag.answers.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            graphrag[row["qid"]] = row

    table = []
    detail: dict[str, list[dict]] = {}
    for unit in UNITS:
        for budget in BUDGETS:
            rows = [
                score_row(
                    item,
                    "\n".join(prefix_cut(ours[item["qid"]][unit], budget)),
                    False,
                )
                for item in items
            ]
            name = f"ours-{unit}@{budget}"
            table.append(summarise(name, rows))
            detail[name] = rows

    for budget in BUDGETS:
        rows = [
            score_row(item, "\n".join(prefix_cut(floor[item["qid"]], budget)), False)
            for item in items
        ]
        name = f"floor@{budget}"
        table.append(summarise(name, rows))
        detail[name] = rows

    for budget in BUDGETS:
        rows = [
            score_row(item, "\n".join(prefix_cut(sentence[item["qid"]], budget)), False)
            for item in items
        ]
        name = f"sentences@{budget}"
        table.append(summarise(name, rows))
        detail[name] = rows

    rows = []
    for item in items:
        row = graphrag.get(item["qid"])
        refused = bool(row and row.get("refused"))
        text = "" if refused or row is None else str(row.get("answer") or "")
        rows.append(score_row(item, text, refused))
    table.append(summarise("graphrag", rows))
    detail["graphrag"] = rows

    header = (
        f"{'system':22s} {'tok':>6} {'ref%':>6} {'recall':>7} {'strict':>7} "
        f"{'prec':>7} {'F1':>7} {'strictF1':>8} {'sup':>6}"
    )
    print(header)
    for row in table:
        print(
            f"{row['system']:22s} {row['tokens_median']:6d} {row['refusal_rate']:6.2f} "
            f"{row['recall_answered']:7.2f} {row['recall_strict']:7.2f} "
            f"{row['precision_answered']:7.2f} {row['f1_answered']:7.2f} "
            f"{row['f1_strict']:8.2f} {row['support_answered']:6.2f}"
        )

    out = args.json or layer / f"runs/e14-pareto-{args.half}.json"
    out.write_text(
        json.dumps(
            {
                "half": args.half,
                "questions": len(items),
                "seed": SEED,
                "chars_per_token": CHARS_PER_TOKEN,
                "depth": args.depth,
                "rows": table,
                "per_question": detail,
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"written {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
