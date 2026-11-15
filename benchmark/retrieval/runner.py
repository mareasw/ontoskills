"""One dataset, one system, one split: a number, its interval, and its receipts.

The runner is deliberately thin. It does four things and no more: it takes the
questions of one split from the committed partition, asks one retriever for a
ranking, scores the ranking with the metric layer, and writes an artifact that
holds every per-question value so the aggregate can be recomputed and compared
without trusting this file.

The index is always the whole collection; only the *ranking* is scoped. A scoped
question therefore sees IDF statistics from the corpus it lives in, which is how
within-document retrieval is measured everywhere else, and it sees no document
outside its scope — not even as a distractor.

What it refuses to do is as important:

* it will not score a dataset whose partition file is missing or no longer
  matches the question set — `partition.verify` runs first, always;
* it will not drop a question it could not score silently: an unanswerable
  question is listed by id, and a question with gold but no computed metric is an
  error;
* it will not invent a metric: a dataset without `gold_facts` has no
  AnswerFactCoverage, and the artifact says which metrics were *not* computed
  rather than writing a zero.

    python3 benchmark/retrieval/runner.py --dataset scifact --split dev --system bm25
    python3 benchmark/retrieval/runner.py --dataset enterpriserag --split dev \\
        --system bm25 --json benchmark/retrieval/runs/erb-bm25-dev.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.retrieval import adapters, dense, metrics, partition  # noqa: E402
from benchmark.retrieval.baselines import Analysis, BM25  # noqa: E402

PARTITIONS = partition.PARTITIONS
RUNS = Path(__file__).resolve().parent / "runs"

# The retrieval depth per §4: public datasets report at 10 to stay comparable with
# their published numbers; our own corpora use 12, the product's answer size.
K_PUBLIC = 10

# One retriever, described by what it is made of. Adding a system means adding a
# factory, not editing the scoring path.
SYSTEMS: dict[str, Callable[[dict[str, str], Analysis], object]] = {
    "bm25": lambda documents, analysis: BM25(documents, analysis=analysis),
    "dense": lambda documents, analysis: dense.Dense(documents),
    "hybrid": dense.hybrid,
    "hybrid-rerank": dense.hybrid_rerank,
}

ANALYSES: dict[str, Analysis] = {
    "porter-stop": Analysis(stemmer="porter", stopwords=True),
    "porter": Analysis(stemmer="porter", stopwords=False),
    "english-stop": Analysis(stemmer="english", stopwords=True),
    "none": Analysis(stemmer=None, stopwords=True),
    # Italian needs its own stemmer and its own stop list: the English Porter
    # stemmer on Italian text is not a stemmer, it is noise.
    "italian": Analysis(stemmer="italian", stopwords=True, language="italian"),
}

METRIC_ORDER = (
    "ndcg@k",
    "recall@k",
    "mrr@k",
    "hit@k",
    "answer_fact_coverage",
    "answer_fact_support",
    "numeric_congruence",
)


@dataclass(frozen=True)
class Run:
    """Everything one run measured, plus what it measured it on."""

    dataset: str
    split: str
    system: str
    analysis: str
    k: int
    questions: int
    metrics: dict[str, dict] = field(default_factory=dict)
    per_question: tuple[dict, ...] = ()
    unanswerable: tuple[str, ...] = ()
    no_gold_docs: tuple[str, ...] = ()
    missing_metrics: tuple[str, ...] = ()
    digest: str = ""
    partition_digest: str = ""
    seconds: float = 0.0
    config: dict = field(default_factory=dict)

    def as_json(self) -> dict:
        return {
            "dataset": self.dataset,
            "split": self.split,
            "system": self.system,
            "analysis": self.analysis,
            "k": self.k,
            "questions": self.questions,
            "metrics": self.metrics,
            "missing_metrics": list(self.missing_metrics),
            "unanswerable": list(self.unanswerable),
            "no_gold_docs": list(self.no_gold_docs),
            "digest": self.digest,
            "partition_digest": self.partition_digest,
            "seconds": round(self.seconds, 1),
            "config": self.config,
            "per_question": list(self.per_question),
        }


def _aggregate(values: Sequence[float], resamples: int = 10_000, seed: int = 0) -> dict:
    interval = metrics.bootstrap_ci(values, resamples=resamples, seed=seed)
    return {"mean": interval.mean, "ci_low": interval.low, "ci_high": interval.high, "n": interval.n}


def _question_metrics(
    question: adapters.Question,
    ranked: Sequence[str],
    k: int,
    texts: dict[str, str],
) -> dict:
    """Every metric this question supports, and nothing it does not.

    Availability is per question, not per dataset: a question can carry gold
    facts without naming a gold document (10 of EnterpriseRAG-Bench's 480 do), and
    scoring it as a document-retrieval miss would invent a failure the system
    could not avoid. It still scores on the answer-level metrics.
    """
    gold = set(question.gold_docs)
    values: dict[str, float] = {}
    if gold:
        values["ndcg@k"] = metrics.ndcg_at(ranked, gold, k)
        values["recall@k"] = metrics.recall_at(ranked, gold, k)
        values["mrr@k"] = metrics.mrr_at(ranked, gold, k)
        values["hit@k"] = metrics.hit_at(ranked, gold, k)
    if question.gold_facts:
        returned = [texts.get(doc_id, "") for doc_id in ranked[:k]]
        values["answer_fact_coverage"] = metrics.answer_fact_coverage(question.gold_facts, returned)
        values["answer_fact_support"] = metrics.answer_fact_support(question.gold_facts, returned)
        values["numeric_congruence"] = (
            sum(metrics.numeric_congruence(fact, "\n".join(returned)) for fact in question.gold_facts)
            / len(question.gold_facts)
        )
    return values


# Datasets whose loader needs to be told to fetch the corpus. mMARCO's collection
# is 3.4 GB, so it is opt-in everywhere — including `--check`, which must stay
# cheap — but the runner must opt in, or it scores every question against nothing.
ADAPTER_OPTIONS: dict[str, dict] = {
    "mmarco-it": {"collection": True},
}


def run(
    dataset: str,
    split: str = "dev",
    system: str = "bm25",
    analysis: str = "porter-stop",
    k: int | None = None,
    limit: int | None = None,
    partitions: Path = PARTITIONS,
    resamples: int = 10_000,
) -> Run:
    """Score one system on one split of one dataset."""
    if dataset not in adapters.ADAPTERS:
        raise SystemExit(f"unknown dataset {dataset!r}; known: {sorted(adapters.ADAPTERS)}")
    if system not in SYSTEMS:
        raise SystemExit(f"unknown system {system!r}; known: {sorted(SYSTEMS)}")
    if analysis not in ANALYSES:
        raise SystemExit(f"unknown analysis {analysis!r}; known: {sorted(ANALYSES)}")
    if split not in (partition.DEV, partition.HOLDOUT, "all"):
        raise SystemExit(f"unknown split {split!r}")

    started = time.time()
    benchmark = adapters.ADAPTERS[dataset](**ADAPTER_OPTIONS.get(dataset, {}))
    k = k or K_PUBLIC

    path = partitions / f"{dataset}.json"
    if split == "all":
        # Only for the dev-time reference table, and it is labelled as such:
        # scoring the holdout happens once, from a partition, never here.
        chosen = list(benchmark.questions)
        partition_digest = ""
        if path.exists():
            partition_digest = partition.Partition.read(path).digest()
    else:
        try:
            committed = partition.verify(path, benchmark.questions)
        except FileNotFoundError as error:
            # Not a crash but a refusal: without a committed split there is no
            # defensible way to score one half, and guessing is how a holdout
            # stops being a holdout.
            raise SystemExit(
                f"{dataset}: no committed partition at {path}; run `python3 benchmark/retrieval/partition.py --build`"
            ) from error
        except partition.PartitionError as error:
            raise SystemExit(f"{dataset}: {error}") from error
        wanted = set(committed.dev if split == partition.DEV else committed.holdout)
        chosen = [question for question in benchmark.questions if question.qid in wanted]
        partition_digest = committed.digest()
        if len(chosen) != len(wanted):
            raise SystemExit(
                f"{dataset}: {len(wanted) - len(chosen)} questions of the {split} split are missing from the adapter"
            )
    if limit is not None:
        chosen = chosen[:limit]

    documents = dict(benchmark.documents())
    if not documents:
        # An adapter that ships only the query side would otherwise rank against
        # nothing and report zeros as if they were a measurement.
        raise SystemExit(
            f"{dataset}: the adapter returned no documents; a retrieval run needs the corpus"
        )
    index = SYSTEMS[system](documents, ANALYSES[analysis])

    rows: list[dict] = []
    unanswerable: list[str] = []
    rankings: list[str] = []
    for question in chosen:
        if not question.answerable:
            unanswerable.append(question.qid)
            continue
        scope = frozenset(question.scope) if question.scope else None
        if scope is None and hasattr(index, "top_ids"):
            # Same ranking as `rank(scores(...), k)`, without building a dict of
            # every document the query touches: on 8.8M passages that dict is a
            # million entries per query. A test asserts the two paths agree.
            ranked, top_score = index.top_ids(question.text, k)
        else:
            scores = index.scores(question.text)
            if scope is not None:
                scores = {doc_id: score for doc_id, score in scores.items() if doc_id in scope}
            ranked = metrics.rank(scores, top_k=k)
            top_score = scores.get(ranked[0], 0.0) if ranked else 0.0
        values = _question_metrics(question, ranked, k, documents)
        rows.append(
            {
                "qid": question.qid,
                "kind": question.kind,
                "gold": list(question.gold_docs),
                "retrieved": list(ranked),
                "top_score": top_score,
                **{name: round(value, 6) for name, value in values.items()},
            }
        )
        # The digest covers the scored questions only; unanswerable ones have no
        # ranking to be deterministic about and are listed by id instead.
        rankings.append(question.qid + "\t" + " ".join(ranked))
    if not rows:
        raise SystemExit(f"{dataset}/{split}: no answerable question to score")

    # A metric is computed if any question supports it, and it is averaged over the
    # questions that do — the artifact reports each metric's own n, so a subset
    # average can never be mistaken for a whole-set one.
    computed = [name for name in METRIC_ORDER if any(name in row for row in rows)]
    missing = tuple(name for name in METRIC_ORDER if name not in computed)
    aggregates = {
        name: _aggregate([row[name] for row in rows if name in row], resamples=resamples) for name in computed
    }
    no_gold_docs = tuple(question.qid for question in chosen if question.answerable and not question.gold_docs)

    return Run(
        dataset=dataset,
        split=split,
        system=system,
        analysis=analysis,
        k=k,
        questions=len(rows),
        metrics=aggregates,
        per_question=tuple(rows),
        unanswerable=tuple(unanswerable),
        no_gold_docs=no_gold_docs,
        missing_metrics=missing,
        digest=metrics.ranking_digest(rankings),
        partition_digest=partition_digest,
        seconds=time.time() - started,
        config={
            # A system that knows what produced its numbers says so; the lexical
            # baseline's identity is its analysis, a dense one's is its model.
            "retriever": index.describe() if hasattr(index, "describe") else f"{system} ({analysis})",
            "indexed_documents": len(documents),
            "k": k,
            "bootstrap_resamples": resamples,
            "citation": benchmark.citation,
            "licence": benchmark.licence,
            "scoped_questions": sum(1 for question in chosen if question.scope),
        },
    )


def format_run(result: Run) -> str:
    lines = [
        f"{result.dataset} / {result.split} / {result.system} ({result.analysis}) / k={result.k}",
        f"  questions {result.questions}  unanswerable {len(result.unanswerable)}"
        f"  no gold document {len(result.no_gold_docs)}"
        f"  documents {result.config.get('indexed_documents')}  {result.seconds:.1f}s",
    ]
    for name in METRIC_ORDER:
        if name not in result.metrics:
            continue
        value = result.metrics[name]
        lines.append(
            f"  {name:22s} {value['mean']:.4f}  [{value['ci_low']:.4f}, {value['ci_high']:.4f}]  n={value['n']}"
        )
    if result.missing_metrics:
        lines.append(f"  not computed: {', '.join(result.missing_metrics)} (the dataset does not carry them)")
    lines.append(f"  rankings {result.digest[:16]}  partition {result.partition_digest[:16]}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dataset", required=True, help="adapter name")
    parser.add_argument("--split", default=partition.DEV, choices=[partition.DEV, partition.HOLDOUT, "all"])
    parser.add_argument("--system", default="bm25", choices=sorted(SYSTEMS))
    parser.add_argument("--analysis", default="porter-stop", choices=sorted(ANALYSES))
    parser.add_argument("--k", type=int, default=None, help="retrieval depth (default 10, §4)")
    parser.add_argument("--limit", type=int, default=None, help="debug: score only the first N questions")
    parser.add_argument("--resamples", type=int, default=10_000)
    parser.add_argument("--json", type=Path, help="artifact path (default runs/<dataset>-<system>-<split>.json)")
    args = parser.parse_args(argv)

    result = run(
        args.dataset,
        split=args.split,
        system=args.system,
        analysis=args.analysis,
        k=args.k,
        limit=args.limit,
        resamples=args.resamples,
    )
    print(format_run(result))
    target = args.json or RUNS / f"{result.dataset}-{result.system}-{result.split}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result.as_json(), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
