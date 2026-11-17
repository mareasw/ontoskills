"""What a claim ranker could reach, and what the lexicon alone reaches.

A coverage number on its own says a system is behind, not why. Two measurements
separate the two possible causes, and neither of them needs a model:

* **The ceiling.** If a question's gold facts could be carried by ten claims at
  all, then a ranker that chose them perfectly would score this much. The ceiling
  is computed exactly — every fact against every verified claim, over the same
  quote the read path would return — and with a greedy choice of ten, which is an
  upper bound no real ranker reaches. It answers "is the loss in what we return,
  or in what we choose?".
* **The lexical span.** The best a BM25-only ranker does over a field choice:
  quote alone, statement plus quote, quote counted twice. If the ceiling is far
  above this span, better ranking needs something the lexicon does not have.

Both are measured with the published scorer (`benchmark.retrieval.metrics`), on
the same quotes `ontocore ask` returns, so the numbers are comparable with the
pilot's row by construction. The claims are filtered exactly as the read path
filters them: the verifier's `ok` only.

    python3 -m benchmark.layer.oracle --selection /tmp/layer/corpus/selection.json \\
        --kb /tmp/layer/kb --json /tmp/layer/runs/oracle.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from scipy import sparse

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.retrieval.metrics import tokens  # noqa: E402

# The retrieval tokenizer is not the scorer's: a ranker may tokenize as it likes,
# but the number it is judged by must stay the published one. Decimals are kept
# whole ("4.5" is one token, not "4" and "5").
WORD = re.compile(r"[a-z0-9]+(?:\.[0-9]+)?")
K1 = 0.9
B = 0.4
K = 10
POOL = 100


def words(text: str) -> list[str]:
    return WORD.findall((text or "").lower())


def first_quote(claim: dict) -> str:
    return ((claim.get("evidence") or [{}])[0].get("quote") or "")


def all_quotes(claim: dict) -> str:
    return " ".join(item.get("quote") or "" for item in claim.get("evidence") or [])


TEXTS = {
    "quote": first_quote,
    "quotes": all_quotes,
    "statement+quote": lambda claim: (claim.get("statement") or "") + " " + first_quote(claim),
    "statement, quote x2": lambda claim: (
        (claim.get("statement") or "") + " " + first_quote(claim) + " " + first_quote(claim)
    ),
}


def verified_claims(kb_dir: Path) -> list[dict]:
    """The claims the read path may cite: verifier `ok`, one evidence item at least."""
    verdicts = {}
    for line in (kb_dir / "verifier.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            verdicts[row["claim_id"]] = row["verdict"]
    claims = []
    for line in (kb_dir / "claims.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        claim = json.loads(line)
        if claim.get("evidence") and verdicts.get(claim["claim_id"], "ok") == "ok":
            claims.append(claim)
    return claims


def build(claims, text_of) -> tuple[sparse.csr_matrix, dict[str, int]]:
    vocab: dict[str, int] = {}
    rows, columns, data = [], [], []
    for index, claim in enumerate(claims):
        for token, count in Counter(words(text_of(claim))).items():
            rows.append(index)
            columns.append(vocab.setdefault(token, len(vocab)))
            data.append(min(count, 32))
    matrix = sparse.csr_matrix(
        (np.array(data, dtype=np.int32), (rows, columns)),
        shape=(len(claims), len(vocab)),
    )
    return matrix, vocab


def fact_vectors(facts, vocab):
    vectors = []
    for fact in facts:
        counts = Counter(tokens(fact))
        pairs = [(vocab[t], min(n, 32)) for t, n in counts.items() if t in vocab]
        columns = np.array([c for c, _ in pairs], dtype=np.int32)
        wanted = np.array([n for _, n in pairs], dtype=np.int32)
        vectors.append((columns, wanted, sum(counts.values())))
    return vectors


def coverage_of(total, hits) -> float:
    """The share of a fact's tokens the chosen claims carry."""
    return float(hits) / total if total else 0.0


def ceiling(matrix: sparse.csr_matrix, vectors, budget: int = K) -> tuple[float, float]:
    """(best single claim, greedy ten) for one question, averaged over its facts."""
    single, ten = [], []
    for columns, wanted, total in vectors:
        if columns.size == 0:
            single.append(0.0)
            ten.append(0.0)
            continue
        hits = np.zeros(matrix.shape[0], dtype=np.float64)
        for column, count in zip(columns, wanted):
            hits += np.minimum(count, matrix[:, column].toarray().ravel())
        single.append(coverage_of(total, hits.max()))

        pool = np.argsort(hits)[-POOL:]
        local = matrix[pool][:, columns].toarray()
        covered = np.zeros(columns.size, dtype=np.float64)
        for _ in range(budget):
            gains = np.minimum(local, np.maximum(wanted - covered, 0.0)).sum(axis=1)
            best = int(gains.argmax())
            if gains[best] <= 0:
                break
            covered = np.minimum(wanted, covered + local[best])
            local[best] = 0
        ten.append(coverage_of(total, covered.sum()))
    return sum(single) / len(single), sum(ten) / len(ten)


def bm25(matrix: sparse.csr_matrix, vocab, question: str, k: int = K) -> list[int]:
    """The top k claims for a question, at the declared k1 and b, untuned."""
    query = [token for token in words(question) if token in vocab]
    if not query:
        return []
    lengths = np.asarray(matrix.sum(axis=1)).ravel()
    df = np.asarray((matrix > 0).sum(axis=0)).ravel()
    idf = np.log(1 + (matrix.shape[0] - df + 0.5) / (df + 0.5))
    average = lengths.mean() or 1.0
    norm = K1 * (1 - B + B * lengths / average)
    columns = np.array([vocab[token] for token in query])
    tf = matrix[:, columns].toarray()
    score = ((tf * (K1 + 1)) / (tf + norm[:, None]) * idf[columns]).sum(axis=1)
    return list(np.argsort(-score)[:k])


def measure(selection: Path, kb_dir: Path) -> dict:
    claims = verified_claims(kb_dir)
    items = json.loads(selection.read_text(encoding="utf-8"))["items"]
    questions = [item for item in items if item.get("gold_facts")]
    quotes = [Counter(tokens(first_quote(claim))) for claim in claims]

    report: dict = {"questions": len(questions), "claims": len(claims), "k": K,
                    "k1": K1, "b": B, "ceiling": {}, "lexical": {}}

    for name, text_of in TEXTS.items():
        matrix, vocab = build(claims, text_of)
        single, ten = [], []
        for item in questions:
            vectors = fact_vectors(item["gold_facts"], vocab)
            one, greedy = ceiling(matrix, vectors)
            single.append(one)
            ten.append(greedy)
        report["ceiling"][name] = {
            "best_single_claim": round(sum(single) / len(single), 6),
            "greedy_ten": round(sum(ten) / len(ten), 6),
        }

    # The lexical ranker is measured on the field choices a BM25 can express, and
    # scored on the quote it would return, which is the read path's shape.
    def recall(fact, available):
        wanted = sum(fact.values())
        return sum(min(n, available.get(t, 0)) for t, n in fact.items()) / wanted if wanted else 1.0

    for name, text_of in TEXTS.items():
        matrix, vocab = build(claims, text_of)
        scores = []
        for item in questions:
            facts = [Counter(tokens(f)) for f in item["gold_facts"]]
            available = Counter()
            for index in bm25(matrix, vocab, item["text"]):
                available.update(quotes[index])
            scores.append(sum(recall(f, available) for f in facts) / len(facts))
        report["lexical"][name] = round(sum(scores) / len(scores), 6)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--kb", type=Path, required=True)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)

    report = measure(args.selection, args.kb)
    if args.json:
        args.json.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"questions {report['questions']}, claims {report['claims']}, k={report['k']}")
    for name in TEXTS:
        ceiling_row = report["ceiling"][name]
        print(
            f"{name:20s} ceiling single {ceiling_row['best_single_claim'] * 100:6.2f} %  "
            f"greedy ten {ceiling_row['greedy_ten'] * 100:6.2f} %  "
            f"bm25 {report['lexical'][name] * 100:6.2f} %"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
