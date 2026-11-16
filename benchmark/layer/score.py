"""Score one system's answers on the pilot slice, per question kind.

The scorer is deliberately the only place that knows what "better" means, and it
is a function of three things that were fixed before any system ran: the slice
(`selection.json`), the metric implementations in `benchmark.retrieval.metrics`,
and the answers themselves.

Two modalities are allowed, because systems differ in what they produce, and
neither is a score of the other:

* **answer** — the system returns one text per question. Coverage and support
  are the same measurement on that text.
* **evidence** — the system returns a ranked list of passages. Support is the
  best single passage, coverage is the union; the list is cut at `--k` so a
  system cannot buy coverage by returning its whole corpus.

Refusing is an answer, and it is scored as one: a refusal on `info_not_found` is
correct, a refusal on an answerable question is a false refusal. Neither is
counted as a zero-quality reply, because those are two different failures and
merging them would hide which one a system has.

    python3 -m benchmark.layer.score --selection corpus/selection.json \\
        --answers runs/ontoskills.jsonl --mode evidence --json runs/ontoskills.score.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.retrieval import metrics  # noqa: E402

QUALITY = ("answer_fact_coverage", "answer_fact_support", "numeric_congruence")


def read_answers(path: Path) -> dict[str, dict]:
    """One JSON object per line: qid, and an answer or evidence, or a refusal."""
    answers: dict[str, dict] = {}
    for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise SystemExit(f"{path}:{number}: not JSON ({error.msg})") from error
        qid = str(row.get("qid", ""))
        if not qid:
            raise SystemExit(f"{path}:{number}: no qid")
        if qid in answers:
            raise SystemExit(f"{path}:{number}: {qid} answered twice")
        answers[qid] = row
    return answers


def returned_text(
    row: dict, mode: str, k: int, max_chars: int | None = None
) -> tuple[str, list[str]]:
    """What the system says, as a single text and as scoreable items.

    ``max_chars`` holds the *volume* constant as well as ``k``: a lexical
    coverage metric rises with the characters returned, so two systems at the
    same k are not at the same volume, and a floor that returns whole documents
    would win on volume alone. Items are taken in rank order while the budget
    lasts, and the first one is always kept whole — truncating it mid-sentence
    would decide the score of a system for it.
    """
    if mode == "answer":
        text = str(row.get("answer") or "").strip()
        return text, ([text] if text else [])
    items = [str(item) for item in (row.get("evidence") or [])][:k]
    if max_chars is not None:
        kept: list[str] = []
        used = 0
        for item in items:
            if kept and used + len(item) > max_chars:
                break
            kept.append(item)
            used += len(item)
        items = kept
    return "\n".join(items), items


def score_question(
    item: dict, row: dict | None, mode: str, k: int, max_chars: int | None = None
) -> dict:
    """Every metric this question supports, and the refusal as its own outcome."""
    outcome: dict = {"kind": item["kind"], "ans": row is not None}
    if row is None:
        outcome["missing"] = True
        return outcome
    refused = bool(row.get("refused"))
    outcome["refused"] = refused
    if refused:
        return outcome
    text, items = returned_text(row, mode, k, max_chars)
    outcome["empty"] = not items
    outcome["chars"] = len(text)
    facts: Sequence[str] = item.get("gold_facts") or ()
    if not facts or not items:
        return outcome
    outcome["answer_fact_coverage"] = metrics.answer_fact_coverage(facts, text)
    outcome["answer_fact_support"] = metrics.answer_fact_support(facts, items)
    outcome["numeric_congruence"] = sum(metrics.numeric_congruence(fact, text) for fact in facts) / len(facts)
    return outcome


def _mean(values: Sequence[float], resamples: int = 10_000, seed: int = 0) -> dict:
    interval = metrics.bootstrap_ci(values, resamples=resamples, seed=seed)
    return {"mean": interval.mean, "ci_low": interval.low, "ci_high": interval.high, "n": interval.n}


def summarise(
    selection: dict,
    answers: dict[str, dict],
    mode: str,
    k: int,
    resamples: int = 10_000,
    max_chars: int | None = None,
) -> dict:
    items = selection["items"]
    per_question = [
        {
            "qid": item["qid"],
            **score_question(item, answers.get(item["qid"]), mode, k, max_chars),
        }
        for item in items
    ]

    kinds: dict[str, dict] = {}
    for outcome in per_question:
        bucket = kinds.setdefault(outcome["kind"], {"questions": 0, "refused": 0, "missing": 0, "empty": 0, "metrics": {}})
        bucket["questions"] += 1
        bucket["refused"] += 1 if outcome.get("refused") else 0
        bucket["missing"] += 1 if outcome.get("missing") else 0
        bucket["empty"] += 1 if outcome.get("empty") else 0
        for name in QUALITY:
            if name in outcome:
                bucket["metrics"].setdefault(name, []).append(outcome[name])

    for bucket in kinds.values():
        bucket["metrics"] = {name: _mean(values, resamples=resamples) for name, values in bucket["metrics"].items()}

    answerable = [o for o in per_question if o["kind"] != "info_not_found"]
    abstention = [o for o in per_question if o["kind"] == "info_not_found"]
    chars = sorted(o["chars"] for o in answerable if o.get("chars") is not None)
    return {
        "selection_digest": selection.get("corpus_digest", ""),
        "mode": mode,
        "k": k,
        "max_chars": max_chars,
        "median_chars": chars[len(chars) // 2] if chars else None,
        "questions": len(items),
        "answered": sum(1 for o in per_question if not o.get("missing")),
        "missing": [o["qid"] for o in per_question if o.get("missing")],
        "false_refusal_rate": (
            sum(1 for o in answerable if o.get("refused")) / len(answerable) if answerable else None
        ),
        "abstention_rate": (
            sum(1 for o in abstention if o.get("refused")) / len(abstention) if abstention else None
        ),
        "by_kind": kinds,
        "per_question": per_question,
    }


def format_score(result: dict) -> str:
    lines = [
        f"{result['mode']} k={result['k']}  questions {result['questions']}  "
        f"answered {result['answered']}  missing {len(result['missing'])}"
        + (
            f"  max_chars {result['max_chars']}"
            if result.get("max_chars") is not None
            else ""
        )
        + (
            f"  median chars {result['median_chars']}"
            if result.get("median_chars") is not None
            else ""
        ),
        f"  false refusal {result['false_refusal_rate']:.1%}"
        if result["false_refusal_rate"] is not None
        else "  false refusal n/a",
        f"  abstention on unanswerable {result['abstention_rate']:.1%}"
        if result["abstention_rate"] is not None
        else "  abstention n/a",
    ]
    header = f"  {'kind':26s} {'n':>3}  " + "  ".join(f"{name:>12s}" for name in QUALITY)
    lines.append(header)
    for kind in sorted(result["by_kind"]):
        bucket = result["by_kind"][kind]
        cells = []
        for name in QUALITY:
            value = bucket["metrics"].get(name)
            cells.append(f"{value['mean']:12.4f}" if value else f"{'-':>12s}")
        lines.append(f"  {kind:26s} {bucket['questions']:3d}  " + "  ".join(cells))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--answers", type=Path, required=True)
    parser.add_argument("--mode", choices=("answer", "evidence"), default="evidence")
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--resamples", type=int, default=10_000)
    parser.add_argument(
        "--max-chars",
        type=int,
        default=None,
        help="Cut the returned passages to this many characters, in rank order, "
        "so two systems are compared at the same volume as well as the same k",
    )
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)

    selection = json.loads(args.selection.read_text(encoding="utf-8"))
    answers = read_answers(args.answers)
    result = summarise(
        selection,
        answers,
        args.mode,
        args.k,
        resamples=args.resamples,
        max_chars=args.max_chars,
    )
    print(format_score(result))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
