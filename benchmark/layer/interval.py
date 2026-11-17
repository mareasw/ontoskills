"""How sure one run's number is.

The pilot reports means over 200 questions, and a mean without an interval is a
point pretending to be a measurement. The unit of observation is the *question*,
not the fact: the facts of one question come from the same documents and are
covered or missed together, so resampling facts would produce an interval that is
narrower than the evidence deserves. Everything here therefore resamples
questions with replacement, and the comparison of two systems resamples the same
questions for both, which is what a paired design asks for.

What this cannot tell you is how much the number would move if the *build* ran
again: one build exists per system, and a bootstrap over questions cannot invent
the variance of a build that was never run. That gap is stated in LAYER.md rather
than papered over, and it is the reason a `--repeats` column is future work
instead of a number here.

    python3 -m benchmark.layer.interval --score runs/ontoskills.score.json \\
        --score runs/floor.score.json --metric answer_fact_coverage

The seed is fixed so the interval is a property of the data, not of the run: two
invocations print the same bounds.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from pathlib import Path

SEED = 20261116
REPS = 5_000
QUALITY = (
    ("answer_fact_coverage", "coverage"),
    ("answer_fact_support", "support"),
    ("numeric_congruence", "numeric"),
)


def percentile(sorted_values: list[float], fraction: float) -> float:
    """Nearest-rank percentile on a sorted list, without a numpy dependency."""
    if not sorted_values:
        raise ValueError("no values")
    index = int(round(fraction * (len(sorted_values) - 1)))
    return sorted_values[index]


def mean_ci(values: list[float], reps: int = REPS, seed: int = SEED) -> dict:
    """The mean of ``values`` and a 95 % interval from resampling them."""
    if not values:
        return {"n": 0, "mean": None, "low": None, "high": None}
    draw = random.Random(seed)
    means = sorted(
        statistics.mean(draw.choices(values, k=len(values))) for _ in range(reps)
    )
    return {
        "n": len(values),
        "mean": statistics.mean(values),
        "low": percentile(means, 0.025),
        "high": percentile(means, 0.975),
    }


def paired_difference(
    left: list[float], right: list[float], reps: int = REPS, seed: int = SEED
) -> dict:
    """Mean difference ``left - right`` with an interval, questions kept in pairs.

    Both lists must be the same questions in the same order: that is the whole
    point of a paired comparison, and a length mismatch is an error rather than
    something to paper over with a pooled estimate.
    """
    if len(left) != len(right):
        raise ValueError("a paired difference needs the same questions on both sides")
    if not left:
        return {"n": 0, "mean": None, "low": None, "high": None}
    differences = [a - b for a, b in zip(left, right)]
    return mean_ci(differences, reps=reps, seed=seed)


def scores_by_question(path: Path) -> dict[str, dict]:
    """Per-question rows keyed by qid, from a score file."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {row["qid"]: row for row in payload.get("per_question") or []}


def paired_metric(
    left: dict[str, dict], right: dict[str, dict], metric: str
) -> dict:
    """The metric over the questions both sides answered, in a stable order."""
    qids = sorted(
        qid
        for qid in left
        if qid in right
        and left[qid].get(metric) is not None
        and right[qid].get(metric) is not None
    )
    return paired_difference(
        [left[qid][metric] for qid in qids], [right[qid][metric] for qid in qids]
    )


def _percent(value) -> str:
    return "—" if value is None else f"{value * 100:+.1f}"


def _percent_plain(value) -> str:
    return "—" if value is None else f"{value * 100:.1f}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--score",
        type=Path,
        action="append",
        required=True,
        help="A score file; two of them turn the report into a paired comparison",
    )
    parser.add_argument("--metric", default=None, help="One metric, or every one")
    parser.add_argument(
        "--label",
        default=None,
        help="The system's name, when the file's stem is not it (`graphrag.score` "
        "would otherwise be published as the system); a single --score only",
    )
    parser.add_argument("--json", type=Path, default=None, help="Write the numbers")
    args = parser.parse_args(argv)
    if args.label and len(args.score) != 1:
        parser.error("--label names the one system of a single --score; two scores keep both stems")
    names = [args.label or path.stem for path in args.score]

    metrics = [(args.metric, args.metric)] if args.metric else QUALITY
    tables = [scores_by_question(path) for path in args.score]
    out: list[dict] = []

    for metric, metric_label in metrics:
        for path, name, table in zip(args.score, names, tables):
            values = [row[metric] for row in table.values() if row.get(metric) is not None]
            row = {"kind": "mean", "system": name, "metric": metric_label, **mean_ci(values)}
            out.append(row)
            print(
                f"{name:28s} {metric_label:9s} {_percent_plain(row['mean']):>6s} % "
                f"[{_percent_plain(row['low'])}, {_percent_plain(row['high'])}] "
                f"n={row['n']}"
            )
        if len(tables) == 2:
            row = {
                "kind": "paired",
                "system": f"{names[0]} - {names[1]}",
                "metric": metric_label,
                **paired_metric(tables[0], tables[1], metric),
            }
            out.append(row)
            print(
                f"{'  difference':28s} {metric_label:9s} {_percent(row['mean']):>6s} pp "
                f"[{_percent(row['low'])}, {_percent(row['high'])}] n={row['n']}"
            )

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
