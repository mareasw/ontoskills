"""The claim vectors E2 reranks with: one text per claim, pinned model, written once.

The read path's pool is a lexical ranking, and E0 says the top 100 already
contains enough for 87,6 % on dev while the product returns 63,6 %. The next
question is whether a scorer that sees paraphrase can choose inside that pool
better than BM25 can. That needs one vector per claim, built once, deterministic,
and read by every later rung.

What is embedded is the claim as the read path returns it: the statement plus the
first quote — the same text the lexical ranker indexes, so the two scores see the
same words. All claims with evidence are embedded, including the verifier's
rejected ones, because the artifact is a property of the knowledge base and not
of one caller's filter; the ranker intersects with the verified set when it
ranks.

    python3 -m benchmark.layer.claim_vectors --kb /tmp/layer/kb \\
        --out /tmp/layer/runs/claim-vectors.npz

The model is `E5_LARGE_V2`, the same pinned revision the pilot serves to
GraphRAG and LightRAG, with the `passage: ` prefix it was trained with. The
`query: ` prefix is applied by the caller, to questions only.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmark.retrieval.dense import E5_LARGE_V2, SentenceEncoder  # noqa: E402


def claim_text(claim: dict) -> str:
    """The statement and the first quote: what the ranker indexes and returns."""
    quote = ((claim.get("evidence") or [{}])[0].get("quote") or "")
    return f"{claim.get('statement') or ''} {quote}".strip()


def build(claims, encoder, batch_size: int = 32) -> dict:
    texts = [claim_text(claim) for claim in claims]
    started = time.time()
    matrix = encoder.encode_passages(texts, batch_size=batch_size)
    seconds = time.time() - started
    if matrix.shape[0] != len(claims):
        raise ValueError(f"{matrix.shape[0]} vectors for {len(claims)} claims")
    return {
        "claim_ids": [claim["claim_id"] for claim in claims],
        "matrix": np.asarray(matrix, dtype=np.float32),
        "spec": encoder.spec.describe(),
        "seconds": seconds,
    }


def write(path: Path, built: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        path,
        claim_ids=np.array(json.dumps(built["claim_ids"])),
        matrix=built["matrix"],
        spec=np.array(built["spec"]),
        seconds=np.array(built["seconds"]),
    )


def read(path: Path) -> tuple[list[str], np.ndarray]:
    payload = np.load(path, allow_pickle=False)
    ids = json.loads(str(payload["claim_ids"]))
    matrix = np.asarray(payload["matrix"], dtype=np.float32)
    if matrix.shape[0] != len(ids):
        raise ValueError(f"{path}: {matrix.shape[0]} vectors for {len(ids)} ids")
    return ids, matrix


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--kb", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--device", default=None, help="cpu or cuda; default lets torch pick")
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args(argv)

    claims = [
        json.loads(line)
        for line in (args.kb / "claims.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    claims = [claim for claim in claims if claim.get("evidence")]
    if not claims:
        raise SystemExit(f"{args.kb}: no claims with evidence")

    encoder = SentenceEncoder(E5_LARGE_V2, device=args.device)
    built = build(claims, encoder, args.batch_size)
    write(args.out, built)
    rate = len(claims) / built["seconds"] if built["seconds"] else 0.0
    print(
        json.dumps(
            {
                "claims": len(claims),
                "dim": int(built["matrix"].shape[1]),
                "seconds": round(built["seconds"], 1),
                "claims_per_second": round(rate, 2),
                "spec": built["spec"],
                "out": str(args.out),
            },
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
