"""The pilot slice: deterministic, documented, and ingestible as written.

The comparison is only worth running if every system reads the same bytes. These
tests pin the three properties that make that true: the question selection is a
function of the dataset and nothing else, the document ids survive the trip into
the ingester, and the slice has a digest that changes when a byte changes.
"""

from __future__ import annotations

import hashlib
import json
import re

import pytest

from benchmark.layer.corpus import (
    corpus_digest,
    select_questions,
    slug,
    stratify,
    write_corpus,
)
from benchmark.retrieval.adapters import Question

# Mirrors `compiler.documents.model.DOC_ID`: a letter, then letters, digits or
# underscores. Kept as a literal here so this suite runs without the compiler
# installed; `test_doc_ids_satisfy_the_ingester_rule` checks the real one.
DOC_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def question(
    qid: str,
    kind: str,
    docs: tuple[str, ...] = ("doc-1",),
    facts: tuple[str, ...] = ("a fact",),
    answerable: bool = True,
) -> Question:
    return Question(
        qid=qid,
        text=f"question {qid}",
        gold_docs=docs,
        gold_facts=facts,
        kind=kind,
        answerable=answerable,
    )


# --- naming -----------------------------------------------------------------


def test_slug_is_a_valid_doc_id():
    for raw in ("abc-123", "9lives", "a.b/c", "x y", "", "-"):
        assert DOC_ID.match(slug(raw)), raw


def test_slug_does_not_merge_different_separators():
    # The ingester namespaces claim ids by document, so two ids that collapse
    # into one are two documents sharing a namespace.
    assert slug("a-b") != slug("a_b")
    assert slug("a_b") != slug("a__b")
    assert slug("a-b") == slug("a.b")


def test_slug_is_stable():
    assert slug("doc-42") == slug("doc-42")


# --- selection --------------------------------------------------------------


def test_stratify_is_proportional():
    questions = [question(f"b{i}", "basic") for i in range(75)]
    questions += [question(f"s{i}", "semantic") for i in range(25)]
    assert stratify(questions, 100) == {"basic": 75, "semantic": 25}
    assert stratify(questions, 40) == {"basic": 30, "semantic": 10}


def test_stratify_breaks_the_remainder_the_same_way_every_time():
    questions = [question(f"{kind}{i}", kind) for kind in "abc" for i in range(3)]
    # Nine questions over three kinds, four seats: one each, and the leftover
    # seat goes to the first kind by name rather than to whichever came first.
    assert stratify(questions, 4) == {"a": 2, "b": 1, "c": 1}
    assert stratify(list(reversed(questions)), 4) == stratify(questions, 4)


def test_stratify_never_asks_a_kind_for_more_than_it_has():
    questions = [question(f"b{i}", "basic") for i in range(10)]
    questions.append(question("rare0", "rare"))
    assert stratify(questions, 10) == {"basic": 9, "rare": 1}


def test_stratify_refuses_a_count_beyond_the_dataset():
    questions = [question(f"b{i}", "basic") for i in range(3)]
    with pytest.raises(SystemExit):
        stratify(questions, 4)


def test_selection_keeps_the_types_that_have_no_gold_document():
    # `high_level` names facts but no document; `info_not_found` is the
    # abstention row. Dropping them would drop the two hardest tests.
    questions = [
        question("b1", "basic"),
        question("b2", "basic"),
        question("h1", "high_level", docs=(), facts=("aggregate",)),
        question("n1", "info_not_found", docs=(), facts=(), answerable=False),
    ]
    chosen = select_questions(questions, 4)
    assert [q.qid for q in chosen] == ["b1", "b2", "h1", "n1"]


def test_selection_stays_in_dataset_order_within_a_kind():
    questions = [question(f"b{i}", "basic") for i in range(6)]
    questions.append(question("s0", "semantic"))
    chosen = select_questions(questions, 4)
    basics = [q.qid for q in chosen if q.kind == "basic"]
    assert basics == sorted(basics)


def test_selection_is_a_function_of_the_dataset_alone():
    questions = [question(f"b{i}", "basic") for i in range(30)]
    questions += [question(f"s{i}", "semantic") for i in range(20)]
    questions += [question("n0", "info_not_found", docs=(), facts=(), answerable=False)]
    first = [q.qid for q in select_questions(questions, 20)]
    second = [q.qid for q in select_questions(list(questions), 20)]
    assert first == second
    assert len(first) == 20


# --- the slice on disk ------------------------------------------------------


def test_corpus_digest_tracks_the_bytes():
    documents = {"x": "one", "y": "two"}
    assert corpus_digest(documents) == corpus_digest({"y": "two", "x": "one"})
    assert corpus_digest(documents) != corpus_digest({"x": "one", "y": "two!"})
    assert corpus_digest(documents) != corpus_digest({"x": "one", "z": "two"})


def test_write_corpus_refuses_to_replace_a_directory(tmp_path):
    out = tmp_path / "corpus"
    out.mkdir()
    (out / "stale.txt").write_text("old", encoding="utf-8")
    with pytest.raises(SystemExit):
        write_corpus(out, [question("b1", "basic")], {"doc-1": ("doc-1", "text")})
    selection = write_corpus(
        out, [question("b1", "basic")], {"doc-1": ("doc-1", "text")}, force=True
    )
    assert selection["documents"] == 1
    assert not (out / "stale.txt").exists()


def test_write_corpus_writes_what_the_ingester_reads(tmp_path):
    out = tmp_path / "corpus"
    questions = [question("b1", "basic", docs=("doc-1",), facts=("the fact",))]
    selection = write_corpus(out, questions, {"doc-1": ("doc-1", "the document text")})

    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["licence"] == "MIT"
    assert len(manifest["documents"]) == 1
    entry = manifest["documents"][0]
    assert DOC_ID.match(entry["doc_id"])
    assert (out / entry["path"]).read_text(encoding="utf-8") == "the document text\n"
    assert entry["sha256"] == hashlib.sha256(b"the document text\n").hexdigest()

    assert selection["corpus_digest"]
    assert selection["document_ids"] == {"doc-1": entry["doc_id"]}
    assert selection["items"][0]["gold_docs"] == [entry["doc_id"]]
    assert selection["items"][0]["gold_facts"] == ["the fact"]
    assert selection["question_ids"] == ["b1"]


def test_doc_ids_satisfy_the_ingester_rule(tmp_path):
    """The real rule, when the compiler is importable, not a copy of it."""
    try:
        from compiler.documents.model import DOC_ID as INGESTER_RULE
    except ImportError:  # the benchmark harness runs without the compiler
        pytest.skip("compiler is not importable in this environment")

    out = tmp_path / "corpus"
    questions = [question("b1", "basic", docs=("Weird.Id/9",))]
    write_corpus(out, questions, {"Weird.Id/9": ("Weird.Id/9", "text")})
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    for entry in manifest["documents"]:
        assert INGESTER_RULE.match(entry["doc_id"]), entry["doc_id"]
