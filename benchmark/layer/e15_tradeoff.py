"""E15: the two readings a buyer asks for, computed from E14's rows.

E14 gives each system a set of (tokens returned, coverage) points. This script
turns that into the two sentences the whole pilot exists to be able to say:

* **at equal tokens** — interpolate each system's coverage at a fixed token
  volume and compare;
* **at equal coverage** — the smallest token volume at which each system reaches
  a target, interpolated the same way.

Interpolation is linear between a system's own measured points and is declared
here rather than chosen per comparison. A system with a single point (GraphRAG
writes one answer of its own length) has no curve: it is reported at its own
volume, and the comparison is made where the other curves cross it.

    python3 -m benchmark.layer.e15_tradeoff --layer .../pilot-work/layer
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

TARGETS = (400, 500, 1000, 2500, 4000)


def curve(rows: list[dict], system: str, metric: str) -> list[tuple[float, float]]:
    """The system's own points, sorted by token volume, deduplicated."""
    points = [
        (float(row["tokens_median"]), float(row[metric]))
        for row in rows
        if row["system"].startswith(system)
    ]
    seen: dict[float, float] = {}
    for tokens, value in points:
        seen[tokens] = max(seen.get(tokens, 0.0), value)
    return sorted(seen.items())


def at_tokens(points: list[tuple[float, float]], tokens: float) -> float | None:
    if not points:
        return None
    if tokens <= points[0][0]:
        return None if tokens < points[0][0] else points[0][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x0 <= tokens <= x1:
            return y0 + (y1 - y0) * (tokens - x0) / (x1 - x0)
    return None


def tokens_for(points: list[tuple[float, float]], target: float) -> float | None:
    if not points:
        return None
    if points[0][1] >= target:
        return points[0][0]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if y0 <= target <= y1 and y1 > y0:
            return x0 + (x1 - x0) * (target - y0) / (y1 - y0)
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--layer", type=Path, required=True)
    parser.add_argument("--half", default="dev", choices=("dev", "test", "all"))
    parser.add_argument("--metric", default="recall_strict",
                        choices=("recall_strict", "recall_answered", "f1_strict",
                                 "precision_strict"))
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)

    payload = json.loads((args.layer / f"runs/e14-pareto-{args.half}.json").read_text())
    rows = payload["rows"]

    systems = {
        "ours-statement": curve(rows, "ours-statement", args.metric),
        "ours-quote": curve(rows, "ours-quote", args.metric),
        "sentences": curve(rows, "sentences", args.metric),
        "floor": curve(rows, "floor", args.metric),
        "graphrag": curve(rows, "graphrag", args.metric),
    }

    payload_out = {
        "half": args.half,
        "metric": args.metric,
        "curves": {name: points for name, points in systems.items()},
        "at_tokens": {
            str(target): {
                name: at_tokens(points, target) for name, points in systems.items()
            }
            for target in TARGETS
        },
        "at_coverage": {
            str(target): {
                name: tokens_for(points, target) for name, points in systems.items()
            }
            for target in (60.0, 70.0, 75.0, 80.0)
        },
    }
    if args.json:
        args.json.write_text(json.dumps(payload_out, indent=1), encoding="utf-8")

    print(f"metric: {args.metric}  (percent of gold facts)")
    print("\nAt equal tokens returned:")
    header = f"{'tokens':>7} " + " ".join(f"{name:>15}" for name in systems)
    print(header)
    for target in TARGETS:
        cells = []
        for name, points in systems.items():
            value = at_tokens(points, target)
            cells.append(f"{value:15.2f}" if value is not None else f"{'-':>15}")
        print(f"{target:7d} " + " ".join(cells))

    print("\nAt equal coverage — tokens needed, and the ratio to ours:")
    for target in (60.0, 70.0, 75.0, 80.0):
        ours = tokens_for(systems["ours-statement"], target)
        cells = []
        for name, points in systems.items():
            value = tokens_for(points, target)
            if value is None:
                cells.append(f"{name} not reached")
                continue
            ratio = f" ({value / ours:.2f}x)" if ours else ""
            cells.append(f"{name} {value:.0f}{ratio}")
        print(f"  recall {target:.0f}%: " + "; ".join(cells))
    return 0


if __name__ == "__main__":
    sys.exit(main())
