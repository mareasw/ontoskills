"""Turn a build's own manifest into the row the report table reads.

Our build does not sit behind the meter proxy — it calls the gateway through the
compiler's own client — so its cost comes from the knowledge base manifest, which
splits the work into two numbers that must not be confused:

* ``tokens`` / ``cost_usd`` — the calls this run actually made;
* ``replayed_tokens`` / ``replayed_cost_usd`` — calls whose answer was replayed
  from the on-disk cache and therefore was not paid twice.

A build finished with ``--resume`` reports the second group alone, and a table
that printed only the first would show a two-hour build as costing three cents.
The record published here sums the two, and keeps both halves next to the total
so anyone can see how much of it was replayed.

    python3 -m benchmark.layer.build_record --manifest /tmp/layer/kb/manifest.json \\
        --root /tmp/layer/kb --exclude cache --out /tmp/layer/ontoskills.build.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.layer.artifacts import describe  # noqa: E402


def _tokens(block: dict | None) -> tuple[int, int]:
    block = block or {}
    return int(block.get("input") or 0), int(block.get("output") or 0)


def record(manifest: dict, root: Path, exclude: tuple[str, ...] = ("cache",)) -> dict:
    """The published numbers, with the two halves they were added from."""
    fresh_in, fresh_out = _tokens(manifest.get("tokens"))
    replayed_in, replayed_out = _tokens(manifest.get("replayed_tokens"))
    fresh_usd = float(manifest.get("cost_usd") or 0.0)
    replayed_usd = float(manifest.get("replayed_cost_usd") or 0.0)
    artifact = describe(root, exclude)
    return {
        "label": manifest.get("name") or root.name,
        "model": manifest.get("model"),
        "prompt_hash": manifest.get("prompt_hash"),
        "documents": manifest.get("documents"),
        "claims": manifest.get("claims"),
        "verifier": manifest.get("verifier"),
        "truncated_calls": manifest.get("truncated_calls"),
        "truncated_enrichment": manifest.get("truncated_enrichment"),
        "wall_clock_s": manifest.get("elapsed_s"),
        "calls": manifest.get("calls"),
        "prompt_tokens": fresh_in + replayed_in,
        "completion_tokens": fresh_out + replayed_out,
        "usd": round(fresh_usd + replayed_usd, 6),
        # Kept apart on purpose: a reader who wants the fresh bill, or wants to
        # know that two thirds of the tokens came from a cache, has both.
        "fresh": {
            "prompt_tokens": fresh_in,
            "completion_tokens": fresh_out,
            "usd": round(fresh_usd, 6),
        },
        "replayed": {
            "prompt_tokens": replayed_in,
            "completion_tokens": replayed_out,
            "usd": round(replayed_usd, 6),
        },
        "artifact_bytes": artifact["artifact_bytes"],
        "artifact_files": artifact["files"],
        "excluded": artifact["excluded"],
        "excluded_not_found": artifact["excluded_not_found"],
    }


_TIMESTAMP = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")


def log_wall_clock(path: Path) -> float | None:
    """Seconds between the first and last timestamp a framework's log carries.

    A framework that keeps no build manifest still writes a log with a timestamp
    per line, and the span between its first and last line is the wall clock of
    the run that produced the artifact. Parsing it is the difference between a
    published number and an empty cell.
    """
    first = last = None
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        match = _TIMESTAMP.match(line)
        if not match:
            continue
        stamp = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
        first = first or stamp
        last = stamp
    if first is None or last is None:
        return None
    return (last - first).total_seconds()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="The knowledge base manifest, when the system writes one",
    )
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--exclude", nargs="*", default=["cache"])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--name", default=None, help="Label, when there is no manifest")
    parser.add_argument(
        "--log",
        type=Path,
        default=None,
        help="The run's log: its first and last timestamps are the wall clock "
        "when the build has no manifest of its own",
    )
    parser.add_argument(
        "--calls",
        type=int,
        default=None,
        help="Model calls, when the manifest does not count them (one cache "
        "record per call is the same number)",
    )
    parser.add_argument(
        "--wall-clock",
        type=float,
        default=None,
        help="Seconds, when the build ran in more than one attempt: the manifest "
        "times only the attempt that finished",
    )
    args = parser.parse_args(argv)

    manifest = {}
    if args.manifest is not None:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    row = record(manifest, args.root, tuple(args.exclude))
    if args.name is not None:
        row["label"] = args.name
    if args.log is not None:
        seconds = log_wall_clock(args.log)
        if seconds is not None:
            row["wall_clock_s"] = seconds
            row["wall_clock_note"] = "first to last timestamp in the run's own log"
    if args.calls is not None:
        row["calls"] = args.calls
    if args.wall_clock is not None:
        row["wall_clock_s"] = args.wall_clock
        row["wall_clock_note"] = "supplied on the command line, all attempts included"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(row, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(row, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
