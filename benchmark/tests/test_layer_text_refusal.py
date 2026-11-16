"""A prose refusal is a heuristic, so its hardest cases are the tests.

Every prose system is classified by this one function. If it over-matches, a
system that answered looks like it abstained; if it under-matches, an abstention
counts as a wrong answer. Both errors would show up in the pilot's table as
someone's quality, which is why the near-misses are pinned here.
"""

from __future__ import annotations

import pytest

from benchmark.layer.text_refusal import looks_like_refusal

REFUSALS = [
    "I don't know.",
    "I do not know the answer to that question.",
    "The provided documents do not contain information about that.",
    "There is not enough information in the context to answer this.",
    "The maximum upload size is not stated in the documents.",
    "No relevant information was found.",
    "This question is unanswerable from the given corpus.",
    "",
]

ANSWERS = [
    "The default per-file upload size limit is 10 MiB.",
    "The limit is not 10 MiB but 50 MiB.",
    "The supplier shall notify the buyer within 48 hours of a breach.",
    "Yes. The document says the retry budget is three attempts.",
]


@pytest.mark.parametrize("text", REFUSALS)
def test_a_declination_is_recognised(text):
    assert looks_like_refusal(text) is True


@pytest.mark.parametrize("text", ANSWERS)
def test_an_answer_is_not_mistaken_for_a_declination(text):
    assert looks_like_refusal(text) is False


def test_negation_inside_an_answer_is_not_a_refusal():
    """`not 10 MiB` is a correction, not a refusal, and the pattern is narrow for it."""
    assert looks_like_refusal("The file size limit is not 10 MiB.") is False


def test_the_phrasings_the_two_frameworks_actually_use():
    """GraphRAG and LightRAG decline in prose, not in a field."""
    assert looks_like_refusal("I'm sorry, but I could not find any information about that.")
    assert looks_like_refusal("The provided documents don't have enough information to say.")
    assert looks_like_refusal("The context does not mention the retention period.")


def test_a_sentence_about_what_something_could_not_do_is_an_answer():
    """`could not` alone is not a refusal; the verb after it decides."""
    assert not looks_like_refusal("The cache could not provide the value within 200 ms.")
    assert not looks_like_refusal("The upload limit is not 10 MiB; it is 25 MiB.")
