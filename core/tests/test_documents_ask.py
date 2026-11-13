"""Tests for the deterministic answerer and its tension report."""

from __future__ import annotations

from compiler.documents.ask import Citation, Corpus, ask, durations, find_tensions, topic_of


def _claim(doc_id, claim_id, statement, quote, page=1, section=None, url=""):
    return {
        "claim_id": claim_id,
        "doc_id": doc_id,
        "statement": statement,
        "modality": "obligation",
        "evidence": [
            {
                "quote": quote,
                "locator": {
                    "kind": "pdf",
                    "page": page,
                    "section_path": section or [],
                    "url": url,
                },
                "role": "supports",
            }
        ],
        "context": {"source": f"Document {doc_id}"},
    }


CLAIMS = [
    _claim(
        "MT_SCH20",
        "MT_SCH20-0001",
        "The Supplier shall notify the Buyer within 48 hours of a personal data breach.",
        "The Supplier shall notify the Buyer within 48 hours of a personal data breach.",
        page=4,
        section=["Notification"],
    ),
    _claim(
        "GDPR",
        "GDPR-0001",
        "The controller shall notify the supervisory authority within 72 hours of a personal data breach.",
        "The controller shall notify the supervisory authority within 72 hours of a personal data breach.",
        page=46,
        section=["Article 33"],
    ),
    _claim(
        "TNA_CONTRACTS",
        "TNA_CONTRACTS-0001",
        "Contractual records shall be retained for six years after the end of the contract.",
        "Contractual records shall be retained for six years after the end of the contract.",
        page=5,
    ),
    _claim(
        "NCSC_CLOUD",
        "NCSC_CLOUD-0001",
        "Consumer data in transit should be protected against tampering and eavesdropping.",
        "Consumer data in transit should be protected against tampering and eavesdropping.",
        page=1,
    ),
]

DOCS = [{"doc_id": claim["doc_id"], "title": f"Document {claim['doc_id']}"} for claim in CLAIMS]


def test_search_ranks_the_claim_that_answers():
    corpus = Corpus(CLAIMS, DOCS)
    results = corpus.search("How quickly must a personal data breach be notified?")
    assert results
    assert results[0].claim_id in {"MT_SCH20-0001", "GDPR-0001"}


def test_answer_cites_more_than_one_document():
    result = ask("How quickly must a personal data breach be notified?", Corpus(CLAIMS, DOCS))
    assert len(result.documents) >= 2


def test_citation_carries_page_section_and_url():
    result = ask("breach notification", Corpus(CLAIMS, DOCS), limit=2)
    citation = next(c for c in result.citations if c.doc_id == "GDPR")
    assert citation.page == 46
    assert citation.section_path == ["Article 33"]


def test_tension_between_48_and_72_hours():
    result = ask("How quickly must a personal data breach be notified?", Corpus(CLAIMS, DOCS))
    assert result.tensions
    tension = result.tensions[0]
    assert tension.topic == "breach_notification"
    values = {value for value, _ in tension.values}
    assert "48 hours" in values
    assert "72 hours" in values


def _citation(claim) -> Citation:
    locator = claim["evidence"][0]["locator"]
    return Citation(
        claim_id=claim["claim_id"],
        doc_id=claim["doc_id"],
        title=claim["doc_id"],
        statement=claim["statement"],
        quote=claim["evidence"][0]["quote"],
        page=locator.get("page"),
        section_path=locator.get("section_path") or [],
        url=locator.get("url", ""),
    )


def test_same_document_does_not_create_a_tension():
    first = _claim("DOC", "DOC-0001", "Notify within 48 hours of a breach.", "Notify within 48 hours of a breach.")
    second = _claim("DOC", "DOC-0002", "Notify within 72 hours of a breach.", "Notify within 72 hours of a breach.")
    assert find_tensions([_citation(first), _citation(second)]) == []


def test_durations_parse_number_and_unit():
    assert durations("within 48 hours") == [("48 hours", 48)]
    assert durations("within 3 working days") == [("3 working days", 72)]


def test_durations_parse_word_numbers():
    """Retention periods are written in words ("six years"), not digits."""
    assert durations("six years after the end of the contract") == [("six years", 52560)]
    assert durations("retain for two years") == [("two years", 17520)]


def test_topic_of_refuses_ambiguous_text():
    assert topic_of("notify a breach within 48 hours") == "breach_notification"
    assert topic_of("retain records of a breach") is None
    assert topic_of("the weather") is None


def test_topic_of_ignores_trailing_punctuation():
    assert topic_of("The Supplier shall notify the Buyer of a breach.") == "breach_notification"
    assert topic_of("Records shall be deleted after the retention period.") == "retention"


def test_empty_question_returns_nothing():
    result = ask("", Corpus(CLAIMS, DOCS))
    assert result.citations == []
    assert result.documents == []
