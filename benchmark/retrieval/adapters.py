"""Public benchmarks, normalised into the one shape the harness scores.

Two shapes, one dataclass. A **corpus-level** question is answered from a shared
corpus (SciFact, EnterpriseRAG-Bench, mMARCO): `scope` is empty and the whole
corpus is searched. A **scoped** question may only use a named subset (QASPER's
paragraphs, ContractNLI's clauses of one NDA, RAGBench's sentences of one row):
`scope` lists the ids it may use and the metric only ever sees those. Making the
scope explicit is what stops a scoped benchmark from accidentally measuring
retrieval over a corpus the original task never had.

Everything streams. The suite is tens of gigabytes and the harness needs a
query, its gold, and the documents — nothing else. A field that is missing
raises, because a silently dropped `answer_facts` turns an answer-level metric
into a document-level one and nobody would notice.

    python3 benchmark/retrieval/adapters.py --check
    python3 benchmark/retrieval/adapters.py --check --only scifact
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

CACHE = Path(os.environ.get("ONTOSKILLS_BENCH_CACHE", Path.home() / ".cache" / "ontoskills-bench"))


@dataclass(frozen=True)
class Question:
    """One query, the gold it must reach, and the documents it may use.

    `gold_docs` is a document-level expectation; `gold_facts` is the stronger,
    answer-level one: the atomic statements a correct answer must contain. When a
    dataset carries both, a system is scored on both, never on one silently.
    """

    qid: str
    text: str
    gold_docs: tuple[str, ...] = ()
    gold_facts: tuple[str, ...] = ()
    kind: str = ""
    answerable: bool = True
    scope: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.qid or not self.text:
            raise ValueError("a question needs an id and a text")
        if self.answerable and not (self.gold_docs or self.gold_facts):
            raise ValueError(f"{self.qid}: no gold at all")
        if self.scope and self.gold_docs:
            outside = set(self.gold_docs) - set(self.scope)
            if outside:
                raise ValueError(f"{self.qid}: gold outside its own scope: {sorted(outside)[:3]}")


@dataclass(frozen=True)
class Benchmark:
    """A question set and the corpus it is scored against, both lazy."""

    name: str
    questions: tuple[Question, ...]
    documents: Callable[[], Iterator[tuple[str, str]]]
    citation: str
    licence: str

    def __len__(self) -> int:
        return len(self.questions)


def _stream(*args, **kwargs) -> Iterator[dict]:
    from datasets import load_dataset

    return load_dataset(*args, split=kwargs.pop("split"), streaming=True, **kwargs)


def _parquet_rows(repo: str, filename: str, batch_size: int = 4096) -> Iterator[dict]:
    """The rows of one parquet file, read in batches.

    `datasets` streaming decodes a row at a time from the Hub and costs ~31 ms per
    document on EnterpriseRAG-Bench; reading the same parquet directly costs
    0.07 ms. Over 512k documents that is four hours against forty seconds, which
    is the difference between a baseline and no baseline. The rows are the same
    rows — `--check`'s digest is unchanged by the switch, which is what says so.
    """
    import pyarrow.parquet as pq
    from huggingface_hub import hf_hub_download

    path = hf_hub_download(repo, filename, repo_type="dataset")
    for batch in pq.ParquetFile(path).iter_batches(batch_size=batch_size):
        for row in batch.to_pylist():
            yield row


# --- EnterpriseRAG-Bench ----------------------------------------------------


def enterprise_rag(limit: int | None = None) -> Benchmark:
    """500 questions over 500k+ generated enterprise documents.

    The dataset has no dev split; the protocol partitions it by a fixed seed
    (PREFLIGHT §5.8), so this returns every row and the partition decides.
    """
    questions: list[Question] = []
    for index, row in enumerate(_parquet_rows("onyx-dot-app/EnterpriseRAG-Bench", "data/questions/test.parquet")):
        if limit is not None and index >= limit:
            break
        kind = str(row["question_type"])
        # "info_not_found" is the abstention row: its ``answer_facts`` describe the
        # behaviour a reply must show ("state that this is not answerable"), not
        # content to retrieve. Keeping them as gold would let a system score by
        # echoing the instruction, so they are dropped and the row is unanswerable.
        if kind.lower() == "info_not_found":
            questions.append(Question(qid=str(row["question_id"]), text=str(row["question"]), kind=kind, answerable=False))
            continue
        questions.append(
            Question(
                qid=str(row["question_id"]),
                text=str(row["question"]),
                gold_docs=tuple(str(doc) for doc in (row.get("expected_doc_ids") or ())),
                gold_facts=tuple(str(fact) for fact in (row.get("answer_facts") or ())),
                kind=kind,
            )
        )

    def documents() -> Iterator[tuple[str, str]]:
        for row in _parquet_rows("onyx-dot-app/EnterpriseRAG-Bench", "data/documents/test.parquet"):
            yield str(row["doc_id"]), f"{row.get('title') or ''}\n\n{row.get('content') or ''}".strip()

    return Benchmark(
        name="enterpriserag",
        questions=tuple(questions),
        documents=documents,
        citation="Sun et al. 2026, arXiv:2605.05253",
        licence="MIT",
    )


# --- BEIR datasets ----------------------------------------------------------


def _beir(name: str, label: str, limit: int | None = None) -> Benchmark:
    """Any BEIR-format dataset: corpus, queries, and the judged test queries."""
    qrels: dict[str, set[str]] = {}
    for row in _stream(f"BeIR/{name}-qrels", split="test"):
        qrels.setdefault(str(row["query-id"]), set()).add(str(row["corpus-id"]))

    questions: list[Question] = []
    for row in _stream(f"BeIR/{name}", "queries", split="queries"):
        qid = str(row["_id"])
        gold = tuple(sorted(qrels.get(qid, ())))
        if not gold:
            # The queries config carries train and test together; only the rows
            # the test qrels judge are scored.
            continue
        if limit is not None and len(questions) >= limit:
            break
        questions.append(Question(qid=qid, text=str(row["text"]), gold_docs=gold, kind=label))

    def documents() -> Iterator[tuple[str, str]]:
        for row in _stream(f"BeIR/{name}", "corpus", split="corpus"):
            title = str(row.get("title") or "").strip()
            text = str(row.get("text") or "").strip()
            yield str(row["_id"]), f"{title} {text}".strip()

    return Benchmark(
        name=label,
        questions=tuple(questions),
        documents=documents,
        citation=f"BEIR/{name} (Thakur et al. 2021)",
        licence="CC BY 4.0 (SciFact); see the dataset card",
    )


def scifact(limit: int | None = None) -> Benchmark:
    """Claim → the abstract that supports it. BEIR gives document-level qrels;
    the original release's rationale sentences are a separate, sentence-level run."""
    return _beir("scifact", "scifact", limit)


# --- ContractNLI ------------------------------------------------------------


def _contract_nli_zip() -> Path:
    """The original release, with the evidence spans the HF conversions drop."""
    target = CACHE / "contract-nli"
    marker = target / "contract-nli" / "test.json"
    if marker.exists():
        return marker
    target.mkdir(parents=True, exist_ok=True)
    archive = CACHE / "contract-nli.zip"
    if not archive.exists():
        print("downloading contract-nli.zip (65 MB) …", file=sys.stderr)
        urllib.request.urlretrieve("https://stanfordnlp.github.io/contract-nli/resources/contract-nli.zip", archive)
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(target)
    if not marker.exists():
        raise FileNotFoundError(f"contract-nli.zip did not contain {marker}")
    return marker


def contractnli(split: str = "test", limit: int | None = None) -> Benchmark:
    """17 NDA hypotheses × 607 non-disclosure agreements, with evidence spans.

    The task scored here is **within-document clause retrieval**: given the NDA
    and the hypothesis, return the clause that entails or contradicts it. That is
    the shape of the dataset's own annotation (`spans` are indices into the
    document's sentences, and the annotators marked which ones carry the answer).
    Scoring it as corpus-wide retrieval would be wrong: the same hypothesis is
    true of hundreds of NDAs, so no ranking could reach its own ideal.
    """
    payload = json.loads(_contract_nli_zip().with_name(f"{split}.json").read_text(encoding="utf-8"))
    hypotheses = payload["labels"]

    questions: list[Question] = []
    documents: dict[str, str] = {}
    for document in payload["documents"]:
        doc_id = f"cnli-{document['id']}"
        text = document["text"]
        spans = document["spans"]
        clause_ids = []
        for index, (start, end) in enumerate(spans):
            clause_id = f"{doc_id}#{index}"
            clause_ids.append(clause_id)
            documents[clause_id] = text[start:end].strip()
        for hypothesis_id, hypothesis in hypotheses.items():
            if limit is not None and len(questions) >= limit:
                break
            annotation = document["annotation_sets"][0]["annotations"].get(hypothesis_id)
            if not annotation:
                continue
            choice = annotation["choice"]
            evidence = tuple(clause_ids[index] for index in annotation["spans"] if index < len(clause_ids))
            if choice in ("Entailment", "Contradiction") and evidence:
                questions.append(
                    Question(
                        qid=f"{doc_id}-{hypothesis_id}",
                        text=hypothesis["hypothesis"],
                        gold_docs=evidence,
                        kind=choice.lower(),
                        scope=tuple(clause_ids),
                    )
                )
            elif choice == "NotMentioned":
                # An unanswerable pair is only honest when the document is
                # searchable: it is, the scope holds every clause of it.
                questions.append(
                    Question(
                        qid=f"{doc_id}-{hypothesis_id}",
                        text=hypothesis["hypothesis"],
                        kind="not_mentioned",
                        answerable=False,
                        scope=tuple(clause_ids),
                    )
                )

    return Benchmark(
        name="contractnli",
        questions=tuple(questions),
        documents=lambda: iter(documents.items()),
        citation="Koreeda & Manning 2021, arXiv:2110.01799",
        licence="CC BY 4.0",
    )


# --- QASPER ----------------------------------------------------------------


def _squash(text: str) -> str:
    """Collapse every whitespace run to one space, for comparing quoted text.

    The extractor and the annotator wrap lines at different points, so two
    copies of the same sentence differ only in whitespace; comparing raw strings
    reports a match failure that is not one.
    """
    return " ".join(str(text or "").split())


def _qasper_answers(entry) -> list[dict]:
    """The answer list for one QASPER question, in either of the two shapes.

    The original release stores, per question, a list of annotation objects each
    holding an ``answer`` list. `datasets` converts a list of structs into a
    struct of lists, so the same data arrives as
    ``{"answer": [...], "annotation_id": [...], "worker_id": [...]}``. Both are
    handled here rather than in the caller: a schema guess that silently yields
    no answers turns every question unanswerable, and the count would still look
    plausible.
    """
    if isinstance(entry, dict):
        return list(entry.get("answer") or ())
    return [answer for annotation in entry for answer in (annotation.get("answer") or ())]


def qasper(split: str = "test", limit: int | None = None) -> Benchmark:
    """Question → the units of the paper that answer it, within that paper.

    Three kinds of unit, because QASPER's annotators cite all three and the
    dataset is only honest if they are all retrievable: a paragraph, a section
    heading (a question can be answered by naming the section that covers it),
    and a figure or table caption, which QASPER writes as
    ``"FLOAT SELECTED: <caption>"``.

    Evidence is quoted text, not an id, so it is mapped back by exact string and a
    single miss raises: mapping a silent mismatch to "no evidence" would score a
    correct system as wrong, and the totals would still look plausible.

    Annotations that are answerable but cite nothing (78 of 3,188 in the test
    split) are kept as `no_evidence` and excluded from evidence recall, rather
    than being counted as misses the system could never fix.
    """
    questions: list[Question] = []
    documents: dict[str, str] = {}
    for row in _stream("allenai/qasper", "qasper", split=split):
        paper = f"qasper-{row['id']}"
        full_text = row["full_text"]

        paragraphs: list[tuple[str, str]] = []
        for section_index, section in enumerate(full_text["paragraphs"]):
            for index, paragraph in enumerate(section):
                if paragraph and paragraph.strip():
                    paragraphs.append((f"{paper}#p{section_index}.{index}", paragraph.strip()))
        headings = [
            (f"{paper}#h{index}", heading.strip())
            for index, heading in enumerate(full_text["section_name"])
            if heading and heading.strip()
        ]
        captions = [
            (f"{paper}#f{index}", caption.strip())
            for index, caption in enumerate(row["figures_and_tables"]["caption"])
            if caption and caption.strip()
        ]

        units = paragraphs + headings + captions
        for unit_id, text in units:
            documents[unit_id] = text
        squashed = [(unit_id, _squash(text)) for unit_id, text in units]
        # Paragraphs first, so a string that is both a heading and a paragraph
        # resolves to the paragraph; `setdefault` makes that order explicit
        # rather than a property of dict insertion nobody wrote down.
        lookup: dict[str, str] = {}
        for unit_id, text in squashed:
            lookup.setdefault(text, unit_id)
        unit_ids = tuple(unit_id for unit_id, _ in units)

        def resolve(cited: str) -> set[str]:
            """Ids of the units an evidence string designates.

            Three shapes occur in QASPER and all three are real: the evidence is
            the unit verbatim, the unit minus a newline, or a sentence lifted out
            of a longer paragraph. Comparison is on whitespace-squashed text
            because the extractor wraps paragraphs at different points than the
            annotator did — the only differences in a sample of misses were a
            newline against a space. A miss raises; mapping it to "no evidence"
            would score a correct system as wrong and leave the totals plausible.
            """
            key = _squash(cited)
            if key.startswith("FLOAT SELECTED:"):
                key = _squash(key[len("FLOAT SELECTED:") :])
            if key in lookup:
                return {lookup[key]}
            containing = {unit_id for unit_id, text in squashed if key and key in text}
            if containing:
                return containing
            # The evidence may carry more than the paragraph: take the longest
            # unit it contains, and require real length so a heading cannot be
            # matched by coincidence.
            inside = [(len(text), unit_id) for unit_id, text in squashed if len(text) >= 40 and text in key]
            if inside:
                longest = max(length for length, _ in inside)
                return {unit_id for length, unit_id in inside if length == longest}
            raise ValueError(f"{paper}: evidence matches no unit ({key[:60]!r})")

        for position, question in enumerate(row["qas"]["question"]):
            if limit is not None and len(questions) >= limit:
                break
            evidence: set[str] = set()
            answerable = False
            for answer in _qasper_answers(row["qas"]["answers"][position]):
                if answer.get("unanswerable"):
                    continue
                answerable = True
                for cited in answer.get("evidence") or ():
                    evidence.update(resolve(cited))
            qid = str(row["qas"]["question_id"][position])
            if answerable and evidence:
                questions.append(
                    Question(qid=qid, text=str(question), gold_docs=tuple(sorted(evidence)), kind="evidence", scope=unit_ids)
                )
            else:
                questions.append(
                    Question(
                        qid=qid,
                        text=str(question),
                        kind="no_evidence" if answerable else "unanswerable",
                        answerable=False,
                        scope=unit_ids,
                    )
                )

    return Benchmark(
        name="qasper",
        questions=tuple(questions),
        documents=lambda: iter(documents.items()),
        citation="Dasigi et al. 2021, arXiv:2105.03011",
        licence="CC BY 4.0",
    )


# --- RAGBench --------------------------------------------------------------


def ragbench(config: str = "emanual", split: str = "test", limit: int | None = None) -> Benchmark:
    """RAGBench: a question, its own documents, and the sentences that support
    the reference answer. Scoped to the row, like the dataset intends.

    The sentence key already carries its document index (`"0a"`, `"2e"`), and the
    relevance list cites those keys verbatim, so the reverse map is the identity
    on the key. Gluing the document index on again silently produced keys like
    `"02e"` that resolve for nothing; a key that does not resolve now raises.
    Nine of the 870 relevance keys in `emanual` carry a trailing full stop
    (`"0b."` for sentence `"0b"`); that one variant is retried, and nothing else
    is, so a real key defect still raises.
    """
    questions: list[Question] = []
    documents: dict[str, str] = {}
    for row_number, row in enumerate(_stream("galileo-ai/ragbench", config, split=split)):
        if limit is not None and len(questions) >= limit:
            break
        row_id = f"ragbench-{config}-{row_number}"
        sentence_ids: list[str] = []
        lookup: dict[str, str] = {}
        for sentences in row["documents_sentences"]:
            for key, sentence in sentences:
                sentence_id = f"{row_id}#{key}"
                sentence_ids.append(sentence_id)
                documents[sentence_id] = str(sentence).strip()
                lookup[str(key)] = sentence_id
        relevant = set()
        for key in row["all_relevant_sentence_keys"] or ():
            resolved = lookup.get(str(key)) or lookup.get(str(key).rstrip("."))
            if resolved is None:
                raise ValueError(f"{row_id}: relevant sentence key {key!r} does not resolve")
            relevant.add(resolved)
        if relevant:
            questions.append(
                Question(
                    qid=f"{row_id}",
                    text=str(row["question"]),
                    gold_docs=tuple(sorted(relevant)),
                    kind="supported",
                    scope=tuple(sentence_ids),
                )
            )
        else:
            questions.append(Question(qid=f"{row_id}", text=str(row["question"]), kind="unsupported", answerable=False, scope=tuple(sentence_ids)))

    return Benchmark(
        name=f"ragbench-{config}",
        questions=tuple(questions),
        documents=lambda: iter(documents.items()),
        citation="Friel et al. 2024, RAGBench",
        licence="see the dataset card",
    )


# --- mMARCO, Italian -------------------------------------------------------


def _mmarco_file(filename: str) -> Path:
    from huggingface_hub import hf_hub_download

    return Path(hf_hub_download("unicamp-dl/mmarco", filename, repo_type="dataset"))


def mmarco_it(limit: int | None = None, collection: bool = False) -> Benchmark:
    """Italian MS MARCO: translated queries, translated passages, shared qrels.

    A proxy for Italian retrieval, not a native benchmark: the relevance
    judgements are the English ones and the text is machine-translated. It is the
    only public Italian passage-retrieval set, so it is reported as what it is.

    The file names mislead. `*_queries.dev.tsv` holds 101k queries in MS MARCO's
    *train* qid space, and `qrels.dev.tsv` pairs with those (55k judged). The
    standard dev evaluation — the 6,980 queries every mMARCO number is quoted on
    — is the `.small` pair: `italian_queries.dev.small.tsv` and
    `qrels.dev.small.tsv`. Using the non-small files would have measured a
    different, larger, non-comparable set.

    `collection=True` downloads the 3.4 GB passage collection. The query side is
    a few megabytes, so `--check` stays cheap.
    """
    qrels: dict[str, set[str]] = {}
    with _mmarco_file("data/qrels.dev.small.tsv").open(encoding="utf-8") as handle:
        for line in handle:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 4 or parts[3] == "0":
                continue
            qrels.setdefault(parts[0], set()).add(parts[2])

    questions: list[Question] = []
    with _mmarco_file("data/google/queries/dev/italian_queries.dev.small.tsv").open(encoding="utf-8") as handle:
        for line in handle:
            if limit is not None and len(questions) >= limit:
                break
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 2:
                continue
            qid, text = parts[0], parts[1]
            gold = tuple(sorted(qrels.get(qid, ())))
            if not gold:
                continue
            questions.append(Question(qid=qid, text=text, gold_docs=gold, kind="passage"))

    def documents() -> Iterator[tuple[str, str]]:
        path = _mmarco_file("data/google/collections/italian_collection.tsv")
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                parts = line.rstrip("\n").split("\t")
                if len(parts) >= 2:
                    yield parts[0], parts[1]

    return Benchmark(
        name="mmarco-it",
        questions=tuple(questions),
        documents=documents if collection else (lambda: iter(())),
        citation="Bonifacio et al. 2021, mMARCO (arXiv:2108.13897), Table 2",
        licence="MS MARCO terms; see the dataset card",
    )


# --- the instrument check ---------------------------------------------------

ADAPTERS: dict[str, Callable[..., Benchmark]] = {
    "enterpriserag": enterprise_rag,
    "scifact": scifact,
    "contractnli": contractnli,
    "qasper": qasper,
    "ragbench": ragbench,
    "mmarco-it": mmarco_it,
}


def _digest(questions: tuple[Question, ...]) -> str:
    payload = "\n".join(f"{question.qid}\t{question.text}" for question in questions)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def check(names: list[str] | None = None, documents: int = 300) -> tuple[int, list[dict]]:
    """The Phase-0 instrument test: every adapter reads its gold without loss.

    Returns the number of failures and one record per adapter, so the same run
    can be written to an artifact instead of living only in a terminal scroll.
    """
    failures = 0
    records: list[dict] = []
    for name in names or list(ADAPTERS):
        benchmark = ADAPTERS[name]()
        questions = benchmark.questions
        answerable = [question for question in questions if question.answerable]
        unanswerable = [question for question in questions if not question.answerable]
        gold = sum(len(question.gold_docs) for question in answerable)
        scoped = sum(1 for question in questions if question.scope)
        unfixed: list[str] = []
        notes: list[str] = []
        print(
            f"{name:14s} questions {len(questions):6d}  answerable {len(answerable):6d}"
            f"  unanswerable {len(unanswerable):5d}  gold docs {gold:7d}  scoped {scoped:6d}"
            f"  digest {_digest(questions)}"
        )
        if not questions:
            unfixed.append("no questions reached the adapter")
        else:
            kinds = sorted({question.kind for question in questions})
            print(f"{'':14s} types {kinds}")
            if not answerable:
                unfixed.append("no answerable question")
            if not any(question.gold_facts for question in questions):
                notes.append("no answer-level facts (document-level scoring only)")
            # Documents: read a sample and require every gold id of the first
            # questions to be present in what the loader returns.
            wanted = {doc for question in questions[:50] for doc in question.gold_docs if not question.scope}
            seen: set[str] = set()
            empty = 0
            for position, (doc_id, text) in enumerate(benchmark.documents()):
                if position >= documents:
                    break
                if not text.strip():
                    empty += 1
                seen.add(doc_id)
            if not seen:
                # An adapter may ship only the query side: mMARCO's collection is
                # 3.4 GB and `--check` must stay cheap by default. Saying so is
                # honest; silently passing would not be a check at all.
                notes.append("corpus not loaded by this adapter; only the questions were checked")
            else:
                if empty:
                    unfixed.append(f"{empty} sampled documents have no text")
                missing = wanted - seen
                if missing and len(seen) >= documents:
                    notes.append(f"{len(missing)} gold ids not in the first {documents} documents (corpus is larger)")
                elif missing:
                    unfixed.append(f"gold ids absent from the corpus: {sorted(missing)[:3]}")
        for note in notes:
            print(f"  note: {note}")
        for failure in unfixed:
            print(f"  FAIL: {failure}")
        failures += len(unfixed)
        records.append(
            {
                "dataset": name,
                "questions": len(questions),
                "answerable": len(answerable),
                "unanswerable": len(unanswerable),
                "gold_docs": gold,
                "scoped_questions": scoped,
                "types": sorted({question.kind for question in questions}),
                "unanswerable_types": sorted({question.kind for question in unanswerable}),
                "digest": _digest(questions),
                "notes": notes,
                "failures": unfixed,
                "citation": benchmark.citation,
                "licence": benchmark.licence,
            }
        )
        print()
    return failures, records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="run the instrument check")
    parser.add_argument("--only", nargs="*", help="restrict to these adapters")
    parser.add_argument("--documents", type=int, default=300, help="documents to sample per adapter")
    parser.add_argument("--json", type=Path, help="write the instrument report as an artifact")
    args = parser.parse_args(argv)
    if not args.check:
        parser.print_help()
        return 0
    failures, records = check(args.only, documents=args.documents)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps({"datasets": records, "failures": failures}, indent=1, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {args.json}")
    return failures


if __name__ == "__main__":
    sys.exit(main())
