"""E7: does a text-only recogniser that sees the candidates find the answering claims?

The protocol is `E6-PROTOCOL.md`, committed before this file was run. The pool is
the dense order of the top 100; the candidates the model reads are the first 60
of that order, full quotes; it returns ten indices; the ten quotes are scored with
the same `answer_fact_coverage` every other number in the pilot uses.

The same sixty candidates are also read by three free baselines in this script —
the plain cut, `cover`, and an exact greedy oracle — so the paid number and the
free numbers share one pool, one order and one budget.

Every answered row is appended and flushed before the next call is made, and a
row already in the output file is never asked for twice. A run that dies has
spent the money it spent and keeps the answers it bought; the rest is resumed by
running the same command again.

    python3 -m benchmark.layer.e7_listwise --layer .../pilot-work/layer
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.layer import claim_vectors, select  # noqa: E402
from benchmark.retrieval.dense import E5_LARGE_V2, SentenceEncoder  # noqa: E402
from benchmark.retrieval.metrics import tokens  # noqa: E402

SYSTEM = (
    "You rank candidate evidence for a question. You reply with a JSON array of "
    "integers and nothing else."
)
USER = """Question: {question}

Candidates:
{candidates}

Return the indices of the {k} candidates most likely to contain the facts needed \
to answer the question, best first, as a JSON array of {k} integers."""

DEPTH = 100
CANDIDATES = 60
K = 10
PRICE_IN, PRICE_OUT = 0.15, 0.60
# This model spends tokens on `reasoning_content` before it answers: at 120 the
# content came back empty on every smoke question and the array was never
# produced. The budget has to cover the reasoning and the answer.
MAX_TOKENS = 1500


def build_user(question: str, quotes: list[str]) -> str:
    listing = "\n".join(f"{index}. {quote}" for index, quote in enumerate(quotes))
    return USER.format(question=question, candidates=listing, k=K)


def parse_indices(text: str, n: int) -> list[int]:
    match = re.search(r"\[[^\]]*\]", text or "")
    if not match:
        return []
    out: list[int] = []
    for raw in re.findall(r"-?\d+", match.group(0)):
        value = int(raw)
        if 0 <= value < n and value not in out:
            out.append(value)
    return out


def coverage_from_sets(fact_sets, chosen_sets):
    if not fact_sets:
        return 0.0
    union = set().union(*chosen_sets) if chosen_sets else set()
    return sum(len(union & fs) / len(fs) for fs in fact_sets) / len(fact_sets)


def greedy_oracle(fact_sets, token_sets, k=K):
    """The best ten of these candidates, by exact union recall."""
    if not fact_sets:
        return 0.0
    chosen, remaining, union = [], list(range(len(token_sets))), set()
    for _ in range(min(k, len(token_sets))):
        best, best_gain = None, -1.0
        for index in remaining:
            gain = sum(len((union | token_sets[index]) & fs) / len(fs) for fs in fact_sets)
            if gain > best_gain:
                best, best_gain = index, gain
        if best is None:
            break
        chosen.append(best)
        union |= token_sets[best]
        remaining.remove(best)
    return coverage_from_sets(fact_sets, [token_sets[i] for i in chosen])


def read_rows(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    rows: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        rows[row["qid"]] = row
    return rows


def append_row(path: Path, row: dict) -> None:
    """Written and flushed before the next call: a dead run keeps what it bought."""
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--layer", type=Path, default=Path("/tmp/opencode/layer"))
    parser.add_argument("--limit", type=int, default=0, help="questions to run; 0 is all")
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL", "deepseek-v4.1-flash"))
    parser.add_argument(
        "--reasoning-effort",
        default="none",
        help="Listwise ranking needs no chain of thought: at the default the model "
        "spends the whole token budget reasoning and returns empty content",
    )
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--no-call", action="store_true", help="baselines only, no request")
    parser.add_argument("--fresh", action="store_true", help="ignore rows already on disk")
    parser.add_argument("--device", default=None)
    args = parser.parse_args(argv)

    layer = args.layer
    tag = f"smoke{args.limit}" if args.limit else "full"
    out = args.out or layer / f"runs/e7-listwise.{tag}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    if args.fresh and out.exists():
        out.unlink()

    selection = json.loads((layer / "corpus/selection.json").read_text(encoding="utf-8"))
    split = json.loads((layer / "runs/split.json").read_text(encoding="utf-8"))
    dev = set(split["dev"])
    items = [i for i in selection["items"] if i["qid"] in dev and i.get("gold_facts")]
    if args.limit:
        items = items[: args.limit]

    done = read_rows(out)
    todo = [item for item in items if item["qid"] not in done]
    if done:
        print(f"{len(done)} rows already on disk, {len(todo)} to ask", file=sys.stderr)

    corpus = select._corpus(layer / "kb", False)
    ids, matrix = claim_vectors.read(layer / "runs/claim-vectors.npz")
    row_of = {claim_id: index for index, claim_id in enumerate(ids)}
    encoder = SentenceEncoder(E5_LARGE_V2, device=args.device)

    client = None
    if not args.no_call:
        from openai import OpenAI

        client = OpenAI(
            api_key=os.environ["OPENAI_API_KEY"],
            base_url=os.environ.get("OPENAI_BASE_URL") or None,
        )

    spent = 0.0
    for position, item in enumerate(todo, 1):
        query = encoder.encode_query(item["text"])
        pool = corpus.search(item["text"], limit=DEPTH)
        dense = select.dense_order(pool, row_of, matrix, query)
        candidates = dense[:CANDIDATES]
        quotes = [citation.quote or "" for citation in candidates]

        fact_sets = [set(tokens(fact)) for fact in item["gold_facts"]]
        fact_sets = [fs for fs in fact_sets if fs]
        token_sets = [set(tokens(quote)) for quote in quotes]

        row = {
            "qid": item["qid"],
            "baseline_plain60": coverage_from_sets(fact_sets, token_sets[:K]),
            "baseline_cover60": coverage_from_sets(
                fact_sets, [set(tokens(c.quote or "")) for c in select.cover(candidates, corpus, item["text"], K)]
            ),
            "oracle60": greedy_oracle(fact_sets, token_sets),
        }

        if client is None:
            append_row(out, row)
            print(
                f"{position:3d}/{len(todo)} {item['qid']} "
                f"plain60 {row['baseline_plain60'] * 100:5.1f}%  "
                f"cover60 {row['baseline_cover60'] * 100:5.1f}%  "
                f"oracle60 {row['oracle60'] * 100:5.1f}%",
                file=sys.stderr,
                flush=True,
            )
            continue

        user = build_user(item["text"], quotes)
        with (out.parent / f"e7-prompts.{tag}.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"qid": item["qid"], "system": SYSTEM, "user": user}) + "\n")
            handle.flush()

        started = time.time()
        try:
            reply = client.chat.completions.create(
                model=args.model,
                temperature=0,
                max_tokens=MAX_TOKENS,
                reasoning_effort=args.reasoning_effort,
                messages=[
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": user},
                ],
            )
            text = (reply.choices[0].message.content or "").strip()
            usage = getattr(reply, "usage", None)
            prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
            completion_tokens = getattr(usage, "completion_tokens", 0) or 0
            finish = reply.choices[0].finish_reason
            details = getattr(usage, "completion_tokens_details", None)
            reasoning_tokens = getattr(details, "reasoning_tokens", 0) or 0
            error = None if text else f"empty content (finish_reason={finish})"
        except Exception as exc:  # a failed call is a failure, not an answer
            text, prompt_tokens, completion_tokens = "", 0, 0
            finish, reasoning_tokens = None, 0
            error = f"{type(exc).__name__}: {exc}"
        seconds = time.time() - started
        spent += prompt_tokens / 1e6 * PRICE_IN + completion_tokens / 1e6 * PRICE_OUT

        picked = parse_indices(text, len(quotes))
        padding = 0
        for index in range(len(quotes)):
            if len(picked) >= K:
                break
            if index not in picked:
                picked.append(index)
                padding += 1
        row.update({
            "indices": picked[:K],
            "padding": padding,
            "coverage": coverage_from_sets(fact_sets, [token_sets[i] for i in picked[:K]]),
            "raw": text,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "reasoning_tokens": reasoning_tokens,
            "finish_reason": finish,
            "seconds": round(seconds, 3),
            "error": error,
        })
        append_row(out, row)
        print(
            f"{position:3d}/{len(todo)} {item['qid']} "
            f"cov {row['coverage'] * 100:5.1f}%  pad {padding}  "
            f"{prompt_tokens}+{completion_tokens} tok  {seconds:5.1f}s  "
            f"spent {spent:.4f}$"
            + (f"  ERROR {error}" if error else ""),
            file=sys.stderr,
            flush=True,
        )

    rows = list(read_rows(out).values())
    rows.sort(key=lambda r: r["qid"])

    def mean(key):
        values = [r[key] for r in rows if key in r]
        return sum(values) / len(values) * 100 if values else 0.0

    tin = sum(r.get("prompt_tokens", 0) for r in rows)
    tout = sum(r.get("completion_tokens", 0) for r in rows)
    summary = {
        "questions": len(rows),
        "model": args.model,
        "candidates": CANDIDATES,
        "k": K,
        "temperature": 0,
        "reasoning_effort": args.reasoning_effort,
        "max_tokens": MAX_TOKENS,
        "baseline_plain60": round(mean("baseline_plain60"), 2),
        "baseline_cover60": round(mean("baseline_cover60"), 2),
        "oracle60": round(mean("oracle60"), 2),
        "prompt_tokens": tin,
        "completion_tokens": tout,
        "cost_usd": round(tin / 1e6 * PRICE_IN + tout / 1e6 * PRICE_OUT, 5),
    }
    if not args.no_call:
        summary["coverage"] = round(mean("coverage"), 2)
        summary["errors"] = sum(1 for r in rows if r.get("error"))
        summary["padded"] = sum(1 for r in rows if r.get("padding"))
        seconds = [r["seconds"] for r in rows if "seconds" in r]
        summary["median_seconds"] = round(sorted(seconds)[len(seconds) // 2], 3)
    (out.parent / f"e7-summary.{tag}.json").write_text(
        json.dumps(summary, indent=1), encoding="utf-8"
    )
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
