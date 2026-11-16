"""The capability table, measured instead of claimed.

`LAYER.md` §4 says capability is mechanical: every row can be answered by running
the artifact, with no judge and no model. This file is that claim, executed. It
reads a compiled knowledge base and reports five things that either hold or do
not:

* **typed predicates** — a claim carries a modality and an actor, not only a
  sentence;
* **schema** — every claim declares a schema version this reader understands;
* **contradiction** — some claims are linked to the claim that disagrees, and
  whether the disagreement crosses documents;
* **verbatim quote** — the quote occurs in the source document, checked against
  the text on disk rather than against the compiler's own verdict;
* **locator** — the offsets reproduce the quote, so a reader can be shown the
  sentence it came from.

Two definitions are inherited from the product and named here, because a probe
that used a stricter definition would fail a system for a convention it
documents:

* **verbatim** is `compiler.documents.text.norm` — curly quotes and dashes
  folded to ASCII, whitespace collapsed. The byte-exact share is reported next
  to it, so the gap between "the same sentence" and "the same bytes" is visible
  rather than argued about.
* **offsets** index the normalised text, which `gaps.raw_offsets` maps back to
  the bytes on disk. The probe therefore slices the normalised text; slicing the
  raw file at these offsets is the mistake the mapper exists to prevent.

The other two probes in §4 are outcomes of a run, not properties of the artifact:
**offline query** is the absence of a meter log during `answers.py`, and
**abstention** is `abstention_rate` in `score.py`.

    python3 -m benchmark.layer.capability --kb /tmp/layer/kb
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from compiler.documents.text import norm  # noqa: E402

SCHEMA_VERSION = 2


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def documents(kb_dir: Path) -> dict[str, str]:
    """The source text of every document, keyed by doc id."""
    out = {}
    text_dir = kb_dir / "text"
    if not text_dir.is_dir():
        return out
    for path in sorted(text_dir.glob("*.txt")):
        out[path.stem] = path.read_text(encoding="utf-8")
    return out


def probe_typed(claims: list[dict]) -> dict:
    typed = [c for c in claims if c.get("modality") and c.get("actor")]
    return {
        "name": "typed predicates",
        "value": len(typed) / len(claims) if claims else None,
        "of": len(claims),
        "detail": "claims carrying both a modality and an actor",
    }


def probe_schema(claims: list[dict]) -> dict:
    good = [c for c in claims if c.get("schema_version") == SCHEMA_VERSION]
    return {
        "name": "schema",
        "value": len(good) / len(claims) if claims else None,
        "of": len(claims),
        "detail": f"claims declaring schema version {SCHEMA_VERSION}",
    }


def probe_contradiction(claims: list[dict]) -> dict:
    linked = [c for c in claims if c.get("conflicts_with")]
    by_id = {c.get("claim_id"): c for c in claims}
    across_documents = 0
    for claim in linked:
        for other in claim.get("conflicts_with") or []:
            target = by_id.get(other)
            if target and target.get("doc_id") != claim.get("doc_id"):
                across_documents += 1
                break
    return {
        "name": "contradiction",
        "value": len(linked),
        "of": len(claims),
        "detail": (
            f"claims linked to a conflicting claim; {across_documents} of them "
            "against a different document"
        ),
    }


def probe_verbatim(claims: list[dict], texts: dict[str, str]) -> dict:
    checked = found = byte_exact = 0
    for claim in claims:
        text = texts.get(claim.get("doc_id", ""))
        if text is None:
            continue
        folded = norm(text)
        for evidence in claim.get("evidence") or []:
            quote = evidence.get("quote", "")
            if not quote:
                continue
            checked += 1
            if norm(quote) in folded:
                found += 1
            if quote in text:
                byte_exact += 1
    return {
        "name": "verbatim quote",
        "value": found / checked if checked else None,
        "of": checked,
        "detail": (
            "quotes found in the source under the declared normalisation; "
            f"{byte_exact} of {checked} are byte-exact"
        ),
    }


def probe_locator(claims: list[dict], texts: dict[str, str]) -> dict:
    checked = exact = 0
    without = 0
    for claim in claims:
        text = texts.get(claim.get("doc_id", ""))
        if text is None:
            continue
        folded = norm(text)
        for evidence in claim.get("evidence") or []:
            locator = evidence.get("locator") or {}
            start, end = locator.get("char_start"), locator.get("char_end")
            quote = evidence.get("quote", "")
            if start is None or end is None:
                without += 1
                continue
            if not quote:
                continue
            checked += 1
            if folded[start:end] == norm(quote):
                exact += 1
    return {
        "name": "locator",
        "value": exact / checked if checked else None,
        "of": checked,
        "detail": (
            "offsets that reproduce the quote exactly in the normalised text "
            f"({without} quotes with no offsets)"
        ),
    }


def accepted_ids(kb_dir: Path) -> set[str]:
    """The claims the artifact's own verifier did not reject.

    A knowledge base keeps the claims it rejected, with the reason, because a
    rejection is information. That makes two honest numbers possible, and the
    probe reports both: what the artifact holds, and what its own audit vouches
    for. Publishing only the first would understate the result; only the second
    would hide the rejects.
    """
    rows = read_jsonl(kb_dir / "verifier.jsonl")
    return {
        str(row.get("claim_id"))
        for row in rows
        if str(row.get("verdict")) != "no"
    }


def measure(kb_dir: Path) -> dict:
    claims = read_jsonl(kb_dir / "claims.jsonl")
    if not claims:
        raise SystemExit(f"{kb_dir}: no claims.jsonl; build the knowledge base first")
    texts = documents(kb_dir)
    result = {
        "kb": str(kb_dir),
        "documents": len(texts),
        "claims": len(claims),
        "probes": [
            probe_typed(claims),
            probe_schema(claims),
            probe_contradiction(claims),
            probe_verbatim(claims, texts),
            probe_locator(claims, texts),
        ],
    }
    accepted = accepted_ids(kb_dir)
    if accepted:
        kept = [c for c in claims if str(c.get("claim_id")) in accepted]
        result["accepted"] = {
            "claims": len(kept),
            "probes": [probe_verbatim(kept, texts), probe_locator(kept, texts)],
        }
    return result


def percent(value) -> str:
    if value is None:
        return "—"
    return f"{value * 100:.1f} %".replace(".", ",")


def format_report(result: dict) -> str:
    lines = [
        f"{result['kb']}: {result['claims']} claims over {result['documents']} documents",
        "",
        "| probe | result | of | detail |",
        "|---|---:|---:|---|",
    ]
    for probe in result["probes"]:
        value = probe["value"]
        if isinstance(value, float):
            shown = percent(value)
        elif value is None:
            shown = "—"
        else:
            shown = str(value)
        lines.append(f"| {probe['name']} | {shown} | {probe['of']} | {probe['detail']} |")
    accepted = result.get("accepted")
    if accepted:
        lines += [
            "",
            f"On the {accepted['claims']} claims the artifact's own verifier accepted "
            "(verdict `ok` or `weak`):",
            "",
            "| probe | result | of | detail |",
            "|---|---:|---:|---|",
        ]
        for probe in accepted["probes"]:
            value = probe["value"]
            shown = percent(value) if isinstance(value, float) else (
                "—" if value is None else str(value)
            )
            lines.append(
                f"| {probe['name']} | {shown} | {probe['of']} | {probe['detail']} |"
            )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--kb", type=Path, required=True)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)

    result = measure(args.kb)
    print(format_report(result))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
