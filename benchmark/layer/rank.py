"""E0 of `RANKER.md`: how deep the gold facts sit in a lexical ranking.

The oracle says ten claims can carry 91,16 % of the facts. That number is a
property of the knowledge base. The question this module answers is different:
*if the ten claims were chosen perfectly among the lexical top N, what would we
get?* The curve over N separates the two repairs a ranker can need — a better
candidate generator, or a better selection over the candidates it already has —
and it costs nothing, because it reads the artifact the pilot already paid for.

The ranker used to build the pool is declared here, not tuned: BM25 over
statement and the first quote, k1 0.9, b 0.4, the variant `oracle.py` scores at
69,25 %. A different pool-builder would move the curve, so the name and the
parameters travel with the numbers.

The score of a pool is the greedy ten over that pool, measured with the
published scorer on the quotes the read path returns. At N = 10 the pool *is*
what the ranker returns, so the curve starts at the ranker's own coverage and
rises to the oracle's ceiling at N = all — a shape whose two endpoints are
already known, which is what makes a wrong implementation visible.

    python3 -m benchmark.layer.rank --selection /tmp/layer/corpus/selection.json \\
        --kb /tmp/layer/kb --answers /tmp/layer/runs/ontoskills.answers.jsonl \\
        --split /tmp/layer/runs/split.json --half dev --json /tmp/layer/runs/e0-dev.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from scipy import sparse

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.layer import oracle  # noqa: E402
from benchmark.retrieval.metrics import answer_fact_coverage  # noqa: E402

DEPTHS = (10, 20, 50, 100, 500)
K = 10


def read_split(path: Path, half: str) -> set[str] | None:
    """The question ids of one half, or None when the split is not applied."""
    if half == "all":
        return None
    record = json.loads(path.read_text(encoding="utf-8"))
    if half not in record:
        raise SystemExit(f"{path} has no {half!r} half")
    return set(record[half])


def published_coverage(answers: Path, items_by_qid: dict[str, dict]) -> float:
    """The pilot's own row on this subset: the quotes it returned, as it returned them."""
    scores = []
    for line in answers.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        item = items_by_qid.get(row["qid"])
        if item is None or not item.get("gold_facts"):
            continue
        scores.append(answer_fact_coverage(item["gold_facts"], row.get("evidence") or []))
    return sum(scores) / len(scores) if scores else 0.0


def pool_ceiling(matrix: sparse.csr_matrix, vectors, pool, budget: int = K) -> tuple[float, float]:
    """(best choice of ten in this pool, share of facts whose best claim is in it)."""
    if len(pool) == 0:
        return 0.0, 0.0
    pool_ids = np.asarray(pool, dtype=np.int64)
    chosen, reachable = [], []
    for columns, wanted, total in vectors:
        if columns.size == 0:
            chosen.append(0.0)
            reachable.append(0.0)
            continue
        hits = np.zeros(matrix.shape[0], dtype=np.float64)
        for column, count in zip(columns, wanted):
            hits += np.minimum(count, matrix[:, column].toarray().ravel())
        # A tie for best is not a miss: any claim that reaches the best value
        # inside the pool is enough for the pool to contain the carrier.
        best = hits.max()
        reachable.append(1.0 if best > 0 and hits[pool_ids].max() == best else 0.0)

        local = matrix[pool_ids][:, columns].toarray()
        covered = np.zeros(columns.size, dtype=np.float64)
        for _ in range(budget):
            gains = np.minimum(local, np.maximum(wanted - covered, 0.0)).sum(axis=1)
            best = int(gains.argmax())
            if gains[best] <= 0:
                break
            covered = np.minimum(wanted, covered + local[best])
            local[best] = 0
        chosen.append(float(covered.sum()) / total if total else 0.0)
    return sum(chosen) / len(chosen), sum(reachable) / len(reachable)


def measure(
    selection: Path,
    kb_dir: Path,
    answers: Path,
    split_path: Path | None = None,
    half: str = "all",
    depths=DEPTHS,
) -> dict:
    claims = oracle.verified_claims(kb_dir)
    items = json.loads(selection.read_text(encoding="utf-8"))["items"]
    wanted = read_split(split_path, half) if split_path else None
    items = [item for item in items if wanted is None or item["qid"] in wanted]
    questions = [item for item in items if item.get("gold_facts")]

    matrix, vocab = oracle.build(claims, oracle.TEXTS["statement+quote"])
    by_qid = {item["qid"]: item for item in items}

    report: dict = {
        "questions": len(questions),
        "claims": len(claims),
        "half": half,
        "pool_builder": "bm25 statement+quote, k1=0.9 b=0.4",
        "baseline": round(published_coverage(answers, by_qid), 6),
        "curve": {},
    }

    for depth in list(depths) + [len(claims)]:
        scores, reach = [], []
        for item in questions:
            pool = oracle.bm25(matrix, vocab, item["text"], k=depth)
            vectors = oracle.fact_vectors(item["gold_facts"], vocab)
            covered, in_pool = pool_ceiling(matrix, vectors, pool)
            scores.append(covered)
            reach.append(in_pool)
        report["curve"]["all" if depth == len(claims) else str(depth)] = {
            "ceiling": round(sum(scores) / len(scores), 6),
            "best_claim_in_pool": round(sum(reach) / len(reach), 6),
        }
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--kb", type=Path, required=True)
    parser.add_argument("--answers", type=Path, required=True)
    parser.add_argument("--split", type=Path, default=None)
    parser.add_argument("--half", default="all", choices=("all", "dev", "test"))
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)
    if args.half != "all" and args.split is None:
        parser.error("--half dev/test needs --split")

    report = measure(args.selection, args.kb, args.answers, args.split, args.half)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"questions {report['questions']}, claims {report['claims']}, half {report['half']}")
    print(f"published baseline {report['baseline'] * 100:6.2f} %")
    for depth, row in report["curve"].items():
        print(
            f"top {depth:>4s}  ceiling {row['ceiling'] * 100:6.2f} %  "
            f"best claim in pool {row['best_claim_in_pool'] * 100:6.2f} %"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
