"""The dev/test split a ranker may be tuned on, fixed before any ranker is touched.

A ranker changed until the pilot's coverage rises is a ranker fitted to the two
hundred questions the pilot publishes. The split is therefore deterministic from
the question id alone, written down before the first experiment, and the
experiments may look at the dev half only. The test half is read once, at the end,
and the published row says which half it was measured on.

Deterministic means reproducible from the selection file without a stored list:
the ids are ordered by the SHA-256 of ``salt:qid`` and cut in the middle. A
different salt gives a different split, so the salt is part of the record.

    python3 -m benchmark.layer.splits --selection /tmp/layer/corpus/selection.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

SALT = "ontoskills-ranker-v1"


def order_key(qid: str, salt: str = SALT) -> str:
    return hashlib.sha256(f"{salt}:{qid}".encode("utf-8")).hexdigest()


def split(qids, salt: str = SALT) -> tuple[list[str], list[str]]:
    """(dev, test): half by hash order, both sorted by the same key.

    The cut is on the hash order, not on the selection order: a selection whose
    first hundred questions are the easiest would otherwise put every easy
    question in dev and make the test half unrepresentative.
    """
    ordered = sorted(qids, key=lambda qid: order_key(qid, salt))
    if len(ordered) != len(set(ordered)):
        raise ValueError("duplicate question ids")
    middle = len(ordered) // 2
    return ordered[:middle], ordered[middle:]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--salt", default=SALT)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)

    selection = json.loads(args.selection.read_text(encoding="utf-8"))
    items = selection["items"]
    dev, test = split([item["qid"] for item in items], args.salt)
    kinds = {}
    for name, part in (("dev", set(dev)), ("test", set(test))):
        counts: dict[str, int] = {}
        for item in items:
            if item["qid"] in part:
                counts[item["kind"]] = counts.get(item["kind"], 0) + 1
        kinds[name] = dict(sorted(counts.items()))
    summary = {"salt": args.salt, "questions": len(items), "dev": len(dev), "test": len(test),
               "by_kind": kinds}
    if args.json:
        args.json.write_text(json.dumps({"summary": summary, "dev": dev, "test": test}, indent=1),
                             encoding="utf-8")
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
