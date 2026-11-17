"""The capability probes must measure the product's own declared rules.

The trap this file guards against is a probe that silently invents a stricter
definition than the artifact promises: an em dash folded to a hyphen is by design,
and a probe that called it a missing quote would publish a 14 % that looks like a
failure. Both numbers are reported — the declared one and the byte-exact one —
so the gap is visible instead of argued.
"""

from __future__ import annotations

import json

from benchmark.layer import capability


def _kb(tmp_path, text: str, claims: list[dict]):
    (tmp_path / "text").mkdir(exist_ok=True)
    (tmp_path / "text" / "d1.txt").write_text(text, encoding="utf-8")
    (tmp_path / "claims.jsonl").write_text(
        "".join(json.dumps(claim) + "\n" for claim in claims), encoding="utf-8"
    )
    return tmp_path


def _claim(quote: str, start: int, end: int, **extra) -> dict:
    claim = {
        "claim_id": "d1-0001",
        "doc_id": "d1",
        "schema_version": 2,
        "modality": "fact",
        "actor": "someone",
        "statement": "a statement",
        "evidence": [{"quote": quote, "locator": {"char_start": start, "char_end": end}}],
    }
    claim.update(extra)
    return claim


def test_a_folded_dash_is_verbatim_but_not_byte_exact(tmp_path):
    text = "The limit \u2014 ten MiB \u2014 applies."
    folded = "The limit - ten MiB - applies."
    start = text.find("ten")
    kb = _kb(tmp_path, text, [_claim(folded, start, start + len(folded))])
    result = capability.measure(kb)
    probes = {probe["name"]: probe for probe in result["probes"]}
    assert probes["verbatim quote"]["value"] == 1.0
    assert "0 of 1 are byte-exact" in probes["verbatim quote"]["detail"]


def test_offsets_are_read_in_the_normalised_text(tmp_path):
    """The documented convention, not the raw bytes: spaces collapse first."""
    text = "Alpha   beta\n\ngamma delta"
    quote = "Alpha beta gamma delta"
    start = 0
    kb = _kb(tmp_path, text, [_claim(quote, start, len(quote))])
    probes = {probe["name"]: probe for probe in capability.measure(kb)["probes"]}
    assert probes["locator"]["value"] == 1.0
    assert probes["locator"]["of"] == 1


def test_a_quote_that_is_not_in_the_source_is_counted_against_it(tmp_path):
    text = "The limit is ten MiB."
    kb = _kb(tmp_path, text, [_claim("The limit is fifty MiB.", 0, 25)])
    probes = {probe["name"]: probe for probe in capability.measure(kb)["probes"]}
    assert probes["verbatim quote"]["value"] == 0.0
    assert probes["locator"]["value"] == 0.0


def test_typed_predicates_and_schema_are_counted_per_claim(tmp_path):
    text = "A sentence."
    claims = [
        _claim("A sentence.", 0, 11),
        _claim("A sentence.", 0, 11, modality="", actor=""),
        {**_claim("A sentence.", 0, 11), "schema_version": 1},
    ]
    kb = _kb(tmp_path, text, claims)
    probes = {probe["name"]: probe for probe in capability.measure(kb)["probes"]}
    assert probes["typed predicates"]["value"] == 2 / 3
    assert probes["schema"]["value"] == 2 / 3


def test_a_conflict_is_counted_and_says_whether_it_crosses_documents(tmp_path):
    text = "A sentence."
    first = _claim("A sentence.", 0, 11, conflicts_with=["d2-0001"])
    second = _claim("A sentence.", 0, 11, conflicts_with=["d2-0001"])
    second["claim_id"] = "d2-0001"
    second["doc_id"] = "d2"
    kb = _kb(tmp_path, text, [first, second])
    (kb / "text" / "d2.txt").write_text(text, encoding="utf-8")
    probes = {probe["name"]: probe for probe in capability.measure(kb)["probes"]}
    assert probes["contradiction"]["value"] == 2
    assert "against a different document" in probes["contradiction"]["detail"]


def test_an_empty_knowledge_base_is_refused_rather_than_scored_zero(tmp_path):
    (tmp_path).mkdir(exist_ok=True)
    try:
        capability.measure(tmp_path)
    except SystemExit as exc:
        assert "build the knowledge base first" in str(exc)
    else:  # pragma: no cover - the assertion above is the test
        raise AssertionError("an empty knowledge base was scored")


def test_the_rejected_claims_are_measured_separately(tmp_path):
    """A knowledge base keeps what it rejected; the probe says so in two rows."""
    text = "The limit is ten MiB."
    good = _claim("The limit is ten MiB.", 0, 21)
    bad = _claim("The limit is fifty MiB.", 0, 24)
    bad["claim_id"] = "d1-0002"
    kb = _kb(tmp_path, text, [good, bad])
    (kb / "verifier.jsonl").write_text(
        json.dumps({"claim_id": "d1-0001", "doc_id": "d1", "verdict": "ok"})
        + "\n"
        + json.dumps(
            {"claim_id": "d1-0002", "doc_id": "d1", "verdict": "no", "reasons": ["x"]}
        )
        + "\n",
        encoding="utf-8",
    )
    result = capability.measure(kb)
    probes = {probe["name"]: probe for probe in result["probes"]}
    assert probes["verbatim quote"]["value"] == 0.5
    assert result["accepted"]["claims"] == 1
    accepted = {probe["name"]: probe for probe in result["accepted"]["probes"]}
    assert accepted["verbatim quote"]["value"] == 1.0
    assert accepted["locator"]["value"] == 1.0
    assert "verifier accepted" in capability.format_report(result)


def test_a_knowledge_base_without_a_verifier_file_has_no_second_table(tmp_path):
    text = "The limit is ten MiB."
    kb = _kb(tmp_path, text, [_claim("The limit is ten MiB.", 0, 20)])
    result = capability.measure(kb)
    assert "accepted" not in result
    assert "verifier accepted" not in capability.format_report(result)


def _kb_with_graph(tmp_path, url_object: str):
    """A one-claim knowledge base plus the graph the store would write for it."""
    text = "Alpha beta gamma."
    claims = [json.loads(json.dumps(_claim("Alpha beta gamma.", 0, 17)))]
    claims[0]["evidence"][0]["locator"]["url"] = "https://example.org/d1"
    (tmp_path / "text").mkdir(exist_ok=True)
    (tmp_path / "text" / "d1.txt").write_text(text, encoding="utf-8")
    (tmp_path / "claims.jsonl").write_text(
        "".join(json.dumps(claim) + "\n" for claim in claims), encoding="utf-8"
    )
    (tmp_path / "graph.ttl").write_text(
        """@prefix doc: <https://ontoskills.sh/ontology/documents#> .
@prefix ex: <https://ontoskills.sh/kb/> .
@prefix prov: <http://www.w3.org/ns/prov#> .

ex:doc_d1 a doc:Document ;
    doc:hasTitle "d1" ;
    doc:hasClaim ex:claim_d1-0001 .
ex:claim_d1-0001 a doc:Claim ;
    doc:hasStatement "Alpha beta gamma." ;
    doc:hasModality doc:Obligation ;
    doc:hasEvidence ex:ev_1 .
ex:ev_1 a doc:Evidence ;
    doc:hasQuote "Alpha beta gamma." ;
    doc:evidenceRole doc:supportsRole ;
    doc:hasLocator ex:loc_1 ;
    prov:wasDerivedFrom ex:doc_d1 .
ex:loc_1 a doc:Locator ;
"""
        + url_object
        + """    doc:hasCharStart 0 ;
    doc:hasCharEnd 17 ;
    doc:inSection ex:sec_1 .
ex:sec_1 a doc:Section ;
    doc:hasSectionTitle "1. Start" ;
    doc:hasSectionPath "1. Start" .
""",
        encoding="utf-8",
    )
    return tmp_path


def test_the_graph_probe_passes_a_graph_that_agrees_with_its_vocabulary(tmp_path):
    kb = _kb_with_graph(tmp_path, "    doc:hasSourceUrl <https://example.org/d1> ;\n")
    probes = {probe["name"]: probe for probe in capability.measure(kb)["probes"]}
    assert probes["graph"]["value"] == 1.0
    assert probes["graph"]["sections"] == 1
    assert "every doc: term declared" in probes["graph"]["detail"]


def test_the_graph_probe_catches_a_url_written_as_a_string(tmp_path):
    """The defect this probe was written for: a declared object property holding
    a literal, which is how `xsd:anyURI` was declared over IRI objects."""
    kb = _kb_with_graph(tmp_path, '    doc:hasSourceUrl "https://example.org/d1" ;\n')
    probes = {probe["name"]: probe for probe in capability.measure(kb)["probes"]}
    assert probes["graph"]["value"] == 0.0
    assert "wrong kind: hasSourceUrl" in probes["graph"]["detail"]
