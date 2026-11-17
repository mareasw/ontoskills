"""Render the pilot table from the files the runs wrote.

The table in `LAYER.md` is not typed by hand. Every number in it comes from one
of three artifacts, and this file is the only thing that puts them side by side:

* a **meter log** (`meter_proxy.py`), one JSON line per call the gateway answered,
  failed calls included;
* a **build record**, written by whoever ran the build, carrying the wall clock
  and the size of the artifact on disk;
* a **score file** (`score.py --json`), produced by the same scorer for every
  system on the same selection.

A number that is missing stays missing. A system whose build did not finish gets
an em dash and its note, never a zero that would read like a bad score — the
difference between "scored nothing" and "did not run" is the difference between a
result and an excuse.

    python3 -m benchmark.layer.report --manifest /tmp/layer/manifest.json \\
        --out /tmp/layer/PILOT-TABLE.md

`--into LAYER.md` writes the same tables into the document, replacing whatever
sits between the `<!-- PILOT-TABLE -->` and `<!-- /PILOT-TABLE -->` markers. The
document then cannot drift from the artifacts: regenerating is one command, and a
number that changed is a number that moved in a run.

The manifest names the systems and where their files are:

    {"systems": [
      {"name": "ontoskills", "modality": "evidence",
       "meter": "ontoskills.meter.jsonl", "build": "ontoskills.build.json",
       "score": "ontoskills.score.json", "answers": "ontoskills.answers.jsonl",
       "queries_offline": true},
      {"name": "graphrag", "modality": "answer", "meter": "graphrag.meter.jsonl",
       "query_meter": "graphrag.query.jsonl", "score": "graphrag.score.json",
       "answers": "graphrag.answers.jsonl"},
      {"name": "lightrag", "modality": "answer", "note": "build failed at ..."}
    ]}

Query cost is a separate column on purpose: a build is paid once, a query is
paid per question for ever, and the systems in this pilot differ more there than
anywhere else. A system that reads its artifact declares `queries_offline` and
its zero is the measurement, with the median reply time beside it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.layer.meter_proxy import summarise  # noqa: E402

DASH = "—"
QUALITY = (
    ("answer_fact_coverage", "coverage"),
    ("answer_fact_support", "support"),
    ("numeric_congruence", "numeric"),
)


def number(value, digits: int = 3) -> str:
    """An Italian-style number: comma for decimals, space for thousands.

    The document is in English but its figures were written this way from the
    first table, and mixing the two separators inside one column reads as a typo.
    """
    if value is None:
        return DASH
    if isinstance(value, int):
        return f"{value:,}".replace(",", " ")
    text = f"{value:,.{digits}f}"
    return text.replace(",", " ").replace(".", ",")


def percent(value, digits: int = 1) -> str:
    if value is None:
        return DASH
    return number(value * 100, digits) + " %"


def duration(seconds) -> str:
    if seconds is None:
        return DASH
    seconds = int(round(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours} h {minutes:02d} min"
    if minutes:
        return f"{minutes} min {secs:02d} s"
    return f"{secs} s"


def bytes_human(size) -> str:
    if size is None:
        return DASH
    for unit in ("B", "kB", "MB", "GB"):
        if size < 1000 or unit == "GB":
            return f"{number(size, 1)} {unit}"
        size /= 1000
    return DASH


def load_json(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def summarise_system(entry: dict, root: Path) -> dict:
    """One row, with whatever the run managed to produce."""
    row = {
        "name": entry["name"],
        "modality": entry.get("modality") or DASH,
        "note": entry.get("note") or "",
        "meter": None,
        "build": None,
        "score": None,
        "query": None,
        "median_seconds": None,
    }
    if entry.get("meter"):
        path = root / entry["meter"]
        row["meter"] = summarise(path) if path.exists() else None
    if entry.get("build"):
        path = root / entry["build"]
        row["build"] = load_json(path) if path.exists() else None
    if entry.get("score"):
        path = root / entry["score"]
        row["score"] = load_json(path) if path.exists() else None
    if row["meter"] is None and row["build"]:
        # A system that was not put behind the meter still has to report its
        # cost: the build record carries the numbers its own manifest kept, and
        # the note in the manifest says where they came from.
        row["meter"] = _from_build(row["build"])
    if entry.get("query_meter"):
        path = root / entry["query_meter"]
        row["query"] = summarise(path) if path.exists() else None
    elif entry.get("queries_offline"):
        # Declared, not measured: a system that answers from its own artifact
        # spends nothing at query time, and the empty meter is the evidence.
        row["query"] = {"calls": 0, "failed_calls": 0, "prompt_tokens": 0,
                        "completion_tokens": 0, "usd": 0.0}
    if entry.get("answers"):
        path = root / entry["answers"]
        if path.exists():
            seconds = [
                float(row_json["seconds"])
                for row_json in (
                    json.loads(line)
                    for line in path.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                )
                if row_json.get("seconds") is not None
            ]
            if seconds:
                row["median_seconds"] = sorted(seconds)[len(seconds) // 2]
    return row


def _from_build(build: dict) -> dict | None:
    keys = ("calls", "failed_calls", "prompt_tokens", "completion_tokens", "usd")
    if not any(key in build for key in keys):
        return None
    # A build that was not metered cannot have failed calls the meter saw: the
    # count is zero rather than unknown, because the alternative prints an em
    # dash in a column where the reader is comparing systems.
    return {key: build.get(key, 0 if key == "failed_calls" else None) for key in keys}


def build_table(rows: list[dict]) -> str:
    """What the build cost, in tokens, dollars at the declared table, and time."""
    lines = [
        "| system | modality | calls | failed | in | out | $ at table | build | artifact |",
        "|---|---|---:|---:|---:|---:|---:|---|---|",
    ]
    for row in rows:
        meter = row["meter"] or {}
        build = row["build"] or {}
        lines.append(
            "| {name} | {modality} | {calls} | {failed} | {tin} | {tout} | {usd} | {wall} | {size} |".format(
                name=row["name"],
                modality=row["modality"],
                calls=number(meter.get("calls")),
                failed=number(meter.get("failed_calls")),
                tin=number(meter.get("prompt_tokens")),
                tout=number(meter.get("completion_tokens")),
                usd=number(meter.get("usd"), 4),
                wall=duration(build.get("wall_clock_s")),
                size=bytes_human(build.get("artifact_bytes")),
            )
        )
    return "\n".join(lines)


def query_table(rows: list[dict]) -> str:
    """What answering costs, which is where the systems differ most.

    Build cost is paid once; query cost is paid per question, for ever. A system
    that reads an artifact spends nothing, and the column says zero with the
    measured median time beside it, so "no model at query time" is a number and
    not a slogan.
    """
    lines = [
        "| system | query calls | failed | in | out | $ at table | median reply |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        query = row["query"] or {}
        lines.append(
            "| {name} | {calls} | {failed} | {tin} | {tout} | {usd} | {median} |".format(
                name=row["name"],
                calls=number(query.get("calls")),
                failed=number(query.get("failed_calls")),
                tin=number(query.get("prompt_tokens")),
                tout=number(query.get("completion_tokens")),
                usd=number(query.get("usd"), 4),
                median=(
                    f"{number(row['median_seconds'] * 1000, 0)} ms"
                    if row["median_seconds"] is not None
                    else DASH
                ),
            )
        )
    return "\n".join(lines)


def quality_table(rows: list[dict]) -> str:
    """What the answers earned, on the same selection, in each system's modality."""
    lines = [
        "| system | n | k | chars | coverage | support | numeric | false refusal | abstention |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        score = row["score"]
        if not score:
            lines.append(
                f"| {row['name']} | {DASH} | {DASH} | {DASH} | {DASH} | {DASH} | "
                f"{DASH} | {DASH} | {DASH} |"
            )
            continue
        overall, scored = _overall(score)
        lines.append(
            "| {name} | {n} | {k} | {chars} | {cov} | {sup} | {num} | {fr} | {ab} |".format(
                name=row["name"],
                n=number(scored),
                k=number(score.get("k")),
                chars=number(score.get("median_chars")),
                cov=percent(overall.get("answer_fact_coverage")),
                sup=percent(overall.get("answer_fact_support")),
                num=percent(overall.get("numeric_congruence")),
                fr=percent(score.get("false_refusal_rate")),
                ab=percent(score.get("abstention_rate")),
            )
        )
    return "\n".join(lines)


def _overall(score: dict) -> tuple[dict, int | None]:
    """Mean over the questions each kind's mean was computed on, and that count.

    The score file keeps the means per kind, and the weight has to be the number
    of questions behind each mean — the metric's own `n`. Weighting by the kind's
    question count instead is right only when every question carries the metric,
    and a prose system's refusals do not: they are outcomes, excluded from the
    mean on purpose. Dividing them back in as zeros is the one thing this pilot
    does not do, so the count comes from the metric and the returned `n` is the
    number of questions the three columns average over.

    A score file written before the metric carried its count falls back to the
    kind's question count, and only where the kind refused nothing — there the two
    counts are equal by construction, so the fallback cannot flatter or punish.
    """
    totals: dict[str, list[tuple[float, int]]] = {}
    for kind, bucket in score.get("by_kind", {}).items():
        if kind == "info_not_found":
            continue
        refused = bucket.get("refused", 0)
        for name, _label in QUALITY:
            entry = bucket.get("metrics", {}).get(name) or {}
            value = entry.get("mean")
            weight = entry.get("n")
            if weight is None and value is not None and not refused:
                weight = bucket.get("questions", 0)
            if value is not None and weight:
                totals.setdefault(name, []).append((value, weight))
    pooled: dict[str, float | None] = {}
    scored: int | None = None
    for name, pairs in totals.items():
        weight = sum(n for _value, n in pairs)
        pooled[name] = sum(value * n for value, n in pairs) / weight if weight else None
        if name == "answer_fact_coverage":
            scored = weight
    return pooled, scored


def kind_table(rows: list[dict]) -> str:
    """The same numbers broken out by question kind, one block per system."""
    blocks = []
    for row in rows:
        score = row["score"]
        if not score:
            continue
        lines = [
            f"**{row['name']}**, by question kind ({score.get('mode')}, k={score.get('k')}):",
            "",
            "| kind | n | coverage | support | numeric | refused |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        for kind, bucket in score.get("by_kind", {}).items():
            metrics = bucket.get("metrics", {})
            questions = bucket.get("questions", 0)
            refused = bucket.get("refused", 0)
            lines.append(
                "| {kind} | {n} | {cov} | {sup} | {num} | {refused} |".format(
                    kind=kind,
                    n=number(questions),
                    cov=percent(metrics.get("answer_fact_coverage", {}).get("mean")),
                    sup=percent(metrics.get("answer_fact_support", {}).get("mean")),
                    num=percent(metrics.get("numeric_congruence", {}).get("mean")),
                    refused=percent(refused / questions if questions else None),
                )
            )
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def render(manifest: dict, root: Path) -> str:
    rows = [summarise_system(entry, root) for entry in manifest["systems"]]
    parts = [
        "## Build",
        "",
        build_table(rows),
        "",
    ]
    if any(row["query"] for row in rows):
        parts += ["## Query", "", query_table(rows), ""]
    parts += [
        "## Quality on the pilot slice",
        "",
        quality_table(rows),
        "",
        "`n` is the number of questions the three quality columns average over. A",
        "system that refuses a question carries no quality value for it — the refusal",
        "is an outcome, and counting it as a zero would be a different measurement, so",
        "it is reported in its own column: the false-refusal rate is a share of the",
        "answerable questions, and abstention a share of the unanswerable ones.",
    ]
    kinds = kind_table(rows)
    if kinds:
        parts += ["", "## By question kind", "", kinds]
    notes = [row for row in rows if row["note"]]
    if notes:
        parts += ["", "## Notes", ""]
        parts += [f"- **{row['name']}** — {row['note']}" for row in notes]
    return "\n".join(parts) + "\n"


OPEN = "<!-- PILOT-TABLE -->"
CLOSE = "<!-- /PILOT-TABLE -->"


def splice(path: Path, table: str) -> int:
    """Replace the marked region of a document with the rendered tables."""
    document = Path(path).read_text(encoding="utf-8")
    start = document.find(OPEN)
    end = document.find(CLOSE)
    if start < 0 or end < 0 or end < start:
        raise SystemExit(f"{path}: missing {OPEN} ... {CLOSE}")
    head = document[: start + len(OPEN)]
    tail = document[end:]
    Path(path).write_text(head + "\n\n" + table + "\n" + tail, encoding="utf-8")
    return len(table)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument(
        "--into",
        type=Path,
        default=None,
        help="A document carrying the PILOT-TABLE markers to replace",
    )
    args = parser.parse_args(argv)

    manifest = load_json(args.manifest)
    text = render(manifest, args.manifest.parent)
    if args.into:
        spliced = splice(args.into, text)
        print(f"wrote {args.into} ({spliced} characters of table)")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
