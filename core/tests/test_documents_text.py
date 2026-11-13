"""Tests for the shared text normalisation and tokenisation."""

from compiler.documents.text import (
    modal_classes,
    norm,
    page_of_offset,
    same_word,
    split_sentences,
    statement_tokens,
    tokens,
)


def test_norm_folds_quotes_dashes_and_whitespace():
    raw = "The Importer\u2019s  \u201cright\u201d\n\tto \u2013 delete\u2014"
    assert norm(raw) == 'The Importer\'s "right" to - delete-'


def test_tokens_drop_one_letter_noise():
    assert tokens("5.1(b) of the Act") == ["of", "the", "act"]


def test_tokens_keep_accented_letters():
    """A dropped accent turned "può" into "pu" and broke the attestation check."""
    assert tokens("Può essere più facile") == ["può", "essere", "più", "facile"]


def test_italian_grammatical_words_are_not_content():
    content = statement_tokens("La direzione deve garantire che i dati siano protetti")
    assert content == ["direzione", "garantire", "dati", "protetti"]


def test_italian_modals_are_classified():
    assert modal_classes("Il fornitore non può cedere i dati") == {"prohibition"}
    assert modal_classes("Il fornitore deve notificare l'incidente") == {"obligation"}
    assert modal_classes("Il fornitore può delegare la funzione") == {"permission"}


def test_a_negated_permission_is_only_a_prohibition():
    assert modal_classes("The Supplier may not transfer the data") == {"prohibition"}


def test_statement_tokens_remove_grammatical_words():
    assert "shall" not in statement_tokens("The Supplier shall notify the Buyer")
    assert "supplier" in statement_tokens("The Supplier shall notify the Buyer")


def test_same_word_is_inflection_not_paraphrase():
    assert same_word("date", "dated")
    assert same_word("party", "parties")
    assert not same_word("claim", "clause")
    assert not same_word("aud", "audit")


def test_split_sentences_keeps_short_text_whole():
    text = "The Supplier must notify. The Buyer may audit."
    assert split_sentences(text, limit=700) == [text]


def test_split_sentences_splits_over_limit():
    text = "One sentence that is long enough to stand alone; " * 6
    windows = split_sentences(text, limit=120)
    assert len(windows) > 1
    assert all(len(window) <= 140 for window in windows)


def test_page_of_offset_counts_form_feeds():
    text = "page one\fpage two\fpage three"
    assert page_of_offset(text, 0) == 1
    assert page_of_offset(text, text.index("two")) == 2
    assert page_of_offset(text, text.index("three")) == 3
