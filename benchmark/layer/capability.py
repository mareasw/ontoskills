"""The capability table, measured instead of claimed.

`LAYER.md` §4 says capability is mechanical: every row can be answered by running
the artifact, with no judge and no model. This file is that claim, executed. It
reads a compiled knowledge base and reports six things that either hold or do
not:

* **typed predicates** — a claim carries a modality and an actor, not only a
  sentence;
* **schema** — every claim declares a schema version this reader understands;
* **contradiction** — some claims are linked to the claim that disagrees, and
  whether the disagreement crosses documents;
* **verbatim quote** — the quote occurs in the source document, checked against
  the text on disk rather than against the compiler's own verdict;
* **locator** — the offsets reproduce the quote, so a reader can be shown the
  sentence it came from;
* **graph** — the RDF artifact agrees with its own vocabulary and with the text:
  every `doc:` term it uses is declared, every property holds the kind of object
  it was declared to hold, and every locator read back out of the graph
  reproduces its quote. A lint, not a rate: it passes or it does not.

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

The other two rows of the §4 table are outcomes of a run, not properties of the
artifact: **offline query** is the absence of a meter log during `answers.py`, and
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


GRAPH = "graph.ttl"


def probe_graph(kb_dir: Path, texts: dict[str, str]) -> dict:
    """The RDF artifact, checked against its own vocabulary and against the text.

    Five things, all mechanical and all able to fail:

    * every `doc:` term the graph uses is declared in the spec — the check whose
      absence let `evidenceRole` be emitted without a declaration;
    * a property declared as a datatype carries literals and an object property
      carries resources, with the declared range respected — the check that
      catches a URL written where a datatype was declared, or the reverse;
    * every claim carries a statement, a modality and at least one evidence;
    * every evidence carries a quote and a locator;
    * every locator with offsets reproduces its quote in the normalised source,
      read back from the graph rather than from `claims.jsonl`, so the artifact
      is proved self-consistent and not merely consistent with the file it was
      built from.

    A knowledge base without a graph is not failed for it: the probe reports
    "not built" and the rest of the table stands, because an absent measurement
    is not a zero.

    The triples are copied into plain dictionaries after parsing: rdflib's own
    lookups cost about ninety seconds over this graph, a dictionary costs one,
    and the parse dominates either way.
    """
    path = kb_dir / GRAPH
    if not path.exists():
        return {"name": "graph", "value": None, "of": 0, "detail": "no graph.ttl; not built"}

    from collections import defaultdict

    from rdflib import RDF, RDFS, XSD, Graph as RDFGraph, Literal, Namespace, URIRef
    from rdflib.namespace import OWL, PROV

    from compiler.documents.store import ONTOLOGY_PATH, _iri

    doc = Namespace("https://ontoskills.sh/ontology/documents#")
    graph = RDFGraph()
    graph.parse(path, format="turtle")
    tbox = RDFGraph()
    tbox.parse(ONTOLOGY_PATH, format="turtle")

    index: dict = defaultdict(lambda: defaultdict(list))
    types: dict = defaultdict(set)
    for subject, predicate, obj in graph:
        index[subject][predicate].append(obj)
        if predicate == RDF.type:
            types[subject].add(obj)

    def first(subject, predicate):
        values = index.get(subject, {}).get(predicate)
        return values[0] if values else None

    declared: dict = {}
    for kind, role in (
        (OWL.Class, "class"),
        (OWL.ObjectProperty, "object"),
        (OWL.DatatypeProperty, "datatype"),
        (OWL.NamedIndividual, "individual"),
    ):
        for term in tbox.subjects(RDF.type, kind):
            declared[term] = role

    undeclared = sorted(
        str(term).split("#")[-1]
        for term in {
            *(
                predicate
                for subject in index
                for predicate in index[subject]
                if str(predicate).startswith(str(doc))
            ),
            *(
                obj
                for subject in types
                for obj in types[subject]
                if str(obj).startswith(str(doc))
            ),
        }
        if term not in declared
    )

    wrong_kind: list[str] = []
    wrong_range: list[str] = []
    for term, role in declared.items():
        objects = [obj for subject in index for obj in index[subject].get(term, ())]
        if not objects:
            continue
        if role == "object":
            if any(isinstance(obj, Literal) for obj in objects):
                wrong_kind.append(str(term).split("#")[-1] + " (object property, literal object)")
        elif role == "datatype":
            if any(isinstance(obj, URIRef) for obj in objects):
                wrong_kind.append(str(term).split("#")[-1] + " (datatype property, resource object)")
                continue
            expected = tbox.value(term, RDFS.range)
            if expected == XSD.integer and any(
                not isinstance(obj, Literal) or not isinstance(obj.toPython(), int)
                for obj in objects
            ):
                wrong_range.append(str(term).split("#")[-1] + " (not an integer)")

    by_iri = {f"https://ontoskills.sh/kb/doc_{_iri(doc_id)}": doc_id for doc_id in texts}
    # Normalise each document once: 12k locators against a 2 MB text is 24 GB of
    # work if the fold is recomputed per quote.
    folded = {doc_id: norm(text) for doc_id, text in texts.items()}

    claims = [subject for subject in types if doc.Claim in types[subject]]
    incomplete: set[str] = set()
    unresolved: set[str] = set()
    without_offsets = 0
    checked = 0
    for claim in claims:
        name = str(claim).split("/")[-1]
        evidence = index.get(claim, {}).get(doc.hasEvidence, [])
        if not first(claim, doc.hasStatement) or not first(claim, doc.hasModality) or not evidence:
            incomplete.add(name)
            continue
        for item in evidence:
            quote = first(item, doc.hasQuote)
            locator = first(item, doc.hasLocator)
            if quote is None or locator is None:
                incomplete.add(name)
                continue
            start = first(locator, doc.hasCharStart)
            end = first(locator, doc.hasCharEnd)
            if start is None or end is None:
                without_offsets += 1
                continue
            source = folded.get(by_iri.get(str(first(item, PROV.wasDerivedFrom)), ""))
            if source is None:
                unresolved.add(f"{name}: document not on disk")
                continue
            checked += 1
            if source[int(start) : int(end)] != norm(str(quote)):
                unresolved.add(name)

    sections = [subject for subject in types if doc.Section in types[subject]]
    titles = sum(1 for section in sections if first(section, doc.hasSectionTitle))
    problems = []
    if undeclared:
        problems.append(f"undeclared terms: {', '.join(undeclared)}")
    if wrong_kind:
        problems.append(f"wrong kind: {', '.join(wrong_kind)}")
    if wrong_range:
        problems.append(f"wrong range: {', '.join(wrong_range)}")
    if incomplete:
        problems.append(f"claims without statement, modality or evidence: {len(incomplete)}")
    if unresolved:
        problems.append(f"locators that do not reproduce their quote: {len(unresolved)}")

    ok = len(claims) - len(incomplete) - len(unresolved)
    detail = (
        "; ".join(problems)
        if problems
        else (
            f"every doc: term declared; {titles} of {len(sections)} sections titled; "
            f"{checked} locators reproduce their quote in the source "
            f"({without_offsets} quotes have no offsets)"
        )
    )
    return {
        "name": "graph",
        # A lint, not a rate: the artifact either agrees with its own vocabulary
        # and its own text, or it does not. The claim counts are in `detail` and
        # in the keys below, where a reader can see how much is affected.
        "value": None if not claims else (0.0 if problems else 1.0),
        "of": len(claims),
        "detail": detail,
        "complete_claims": ok,
        "triples": len(graph),
        "sections": len(sections),
        "titled_sections": titles,
    }


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
    # Folded once per document: recomputing it per claim costs ninety seconds on
    # the pilot's 279 documents and measures nothing extra.
    folded_texts = {doc_id: norm(text) for doc_id, text in texts.items()}
    for claim in claims:
        text = texts.get(claim.get("doc_id", ""))
        folded = folded_texts.get(claim.get("doc_id", ""))
        if text is None or folded is None:
            continue
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
    folded_texts = {doc_id: norm(text) for doc_id, text in texts.items()}
    for claim in claims:
        folded = folded_texts.get(claim.get("doc_id", ""))
        if folded is None:
            continue
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
            probe_graph(kb_dir, texts),
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
