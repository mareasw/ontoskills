"""The dev/holdout split, fixed before any run and checkable afterwards.

A protocol that picks its split after seeing a result is not a protocol. This
module writes the split to a file, hashes it, and refuses to accept a file that
no longer matches what its own contents imply — so "we never touched the holdout"
is a checkable claim rather than a promise.

**Why not `sha256(qid) % 2`.** That is the obvious rule and it is wrong at these
sizes. EnterpriseRAG-Bench has strata of 20 questions; independent hashing gives
11/9 there about a quarter of the time and 13/7 about 3% of the time, so a
20-question family can be split 65/35 by accident while the file still looks
principled. Ranking *within each stratum* by the hash and then alternating gives
every stratum a difference of at most one, and still makes the assignment
independent of input order, of names, and of anything a person could nudge.

The salt is fixed and written down here. Changing it changes every assignment, so
it is not a knob: it is part of the protocol, and `verify` compares it.

    python3 benchmark/retrieval/partition.py --build
    python3 benchmark/retrieval/partition.py --verify
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

SALT = "ontoskills-retrieval-2026-11-15"
ALGORITHM = "sha256-rank-alternate-v1"
DEV = "dev"
HOLDOUT = "holdout"
PARTITIONS = Path(__file__).resolve().parent / "partitions"


class PartitionError(AssertionError):
    """A partition file and the question set disagree, or the file was edited."""


def _rank(salt: str, qid: str) -> str:
    """The sort key: a hash of the salt and the id, so order is not alphabetical."""
    return hashlib.sha256(f"{salt}\x00{qid}".encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Partition:
    """A question set's assignment, its strata, and the digest that fixes both."""

    dataset: str
    salt: str
    algorithm: str
    assignment: dict[str, str] = field(default_factory=dict)
    strata: dict[str, str] = field(default_factory=dict)

    @property
    def dev(self) -> tuple[str, ...]:
        return tuple(sorted(qid for qid, side in self.assignment.items() if side == DEV))

    @property
    def holdout(self) -> tuple[str, ...]:
        return tuple(sorted(qid for qid, side in self.assignment.items() if side == HOLDOUT))

    def counts(self) -> dict[str, int]:
        return {
            DEV: sum(1 for side in self.assignment.values() if side == DEV),
            HOLDOUT: sum(1 for side in self.assignment.values() if side == HOLDOUT),
        }

    def stratum_counts(self) -> dict[str, dict[str, int]]:
        out: dict[str, dict[str, int]] = {}
        for qid, side in self.assignment.items():
            stratum = self.strata[qid]
            bucket = out.setdefault(stratum, {DEV: 0, HOLDOUT: 0})
            bucket[side] += 1
        return dict(sorted(out.items()))

    def digest(self) -> str:
        """SHA-256 over the protocol and every assignment, sorted by id."""
        lines = [self.algorithm, self.salt, self.dataset]
        for qid in sorted(self.assignment):
            lines.append(f"{qid}\t{self.strata[qid]}\t{self.assignment[qid]}")
        return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()

    def as_json(self) -> dict:
        return {
            "dataset": self.dataset,
            "algorithm": self.algorithm,
            "salt": self.salt,
            "questions": len(self.assignment),
            "counts": self.counts(),
            "strata": self.stratum_counts(),
            "assignment": {qid: self.assignment[qid] for qid in sorted(self.assignment)},
            "strata_of": {qid: self.strata[qid] for qid in sorted(self.strata)},
            "digest": self.digest(),
        }

    def write(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.as_json(), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        return path

    @classmethod
    def read(cls, path: Path) -> "Partition":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        partition = cls(
            dataset=str(payload["dataset"]),
            salt=str(payload["salt"]),
            algorithm=str(payload["algorithm"]),
            assignment={str(qid): str(side) for qid, side in payload["assignment"].items()},
            strata={str(qid): str(stratum) for qid, stratum in payload["strata_of"].items()},
        )
        if partition.digest() != payload.get("digest"):
            raise PartitionError(
                f"{path}: digest {payload.get('digest')} does not describe the file's own assignments"
            )
        return partition


def build(dataset: str, questions, salt: str = SALT, algorithm: str = ALGORITHM) -> Partition:
    """Assign every question to dev or holdout, balanced inside every stratum.

    `questions` is any iterable of objects with `qid` and `kind`; the harness's
    `Question` satisfies it, and so does a two-field stub in the tests.
    """
    if salt != SALT:
        raise PartitionError(f"the salt is fixed by the protocol; {salt!r} is not {SALT!r}")
    if algorithm != ALGORITHM:
        raise PartitionError(f"unknown algorithm {algorithm!r}")
    by_stratum: dict[str, list[str]] = {}
    strata: dict[str, str] = {}
    for question in questions:
        qid = str(question.qid)
        if qid in strata:
            raise PartitionError(f"{dataset}: duplicate question id {qid!r}")
        stratum = str(getattr(question, "kind", "") or "all")
        strata[qid] = stratum
        by_stratum.setdefault(stratum, []).append(qid)
    if not by_stratum:
        raise PartitionError(f"{dataset}: no questions to partition")

    assignment: dict[str, str] = {}
    for stratum in sorted(by_stratum):
        ordered = sorted(by_stratum[stratum], key=lambda qid: _rank(salt, qid))
        for position, qid in enumerate(ordered):
            # Even positions go to dev, so a stratum of odd size leaves the extra
            # question on the development side: the smaller side is the one whose
            # noise matters, and it is the holdout.
            assignment[qid] = DEV if position % 2 == 0 else HOLDOUT
    return Partition(dataset=dataset, salt=salt, algorithm=algorithm, assignment=assignment, strata=strata)


def verify(path: Path, questions) -> Partition:
    """Load a committed partition and prove it still describes this question set.

    Three failures are caught: the file was edited (its digest no longer matches
    its own contents), the question set changed (a question was added or removed,
    or one changed stratum), and the reassignment moved (which follows from the
    other two but is compared explicitly so the error names the real cause).
    None is recoverable, so this raises instead of warning.
    """
    partition = Partition.read(path)
    expected = build(partition.dataset, questions, salt=partition.salt, algorithm=partition.algorithm)
    if expected.strata != partition.strata:
        changed = sorted(
            qid for qid in set(expected.strata) & set(partition.strata) if expected.strata[qid] != partition.strata[qid]
        )
        raise PartitionError(
            f"{path}: {len(changed)} questions changed stratum since the partition was committed"
            + (f"; first: {[(qid, partition.strata[qid], expected.strata[qid]) for qid in changed[:3]]}" if changed else "")
        )
    if expected.assignment != partition.assignment:
        drifted = sorted(set(expected.assignment).symmetric_difference(partition.assignment))
        changed = sorted(
            qid
            for qid in set(expected.assignment) & set(partition.assignment)
            if expected.assignment[qid] != partition.assignment[qid]
        )
        raise PartitionError(
            f"{path}: the question set has changed since the partition was committed "
            f"({len(drifted)} added or removed, {len(changed)} reassigned)"
            + (f"; first: {drifted[:3] or changed[:3]}" if (drifted or changed) else "")
        )
    return partition


# --- CLI ---------------------------------------------------------------------


def _load(name: str):
    from benchmark.retrieval import adapters

    return adapters.ADAPTERS[name]()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--build", action="store_true", help="write the partition files")
    parser.add_argument("--verify", action="store_true", help="check committed files against the datasets")
    parser.add_argument("--only", nargs="*", help="restrict to these datasets")
    parser.add_argument("--out", type=Path, default=PARTITIONS, help="directory for the partition files")
    args = parser.parse_args(argv)
    if not (args.build or args.verify):
        parser.print_help()
        return 0

    from benchmark.retrieval import adapters

    names = args.only or list(adapters.ADAPTERS)
    failures = 0
    for name in names:
        path = args.out / f"{name}.json"
        benchmark = _load(name)
        if args.build:
            partition = build(name, benchmark.questions)
            partition.write(path)
            counts = partition.counts()
            widest = max(
                (abs(bucket[DEV] - bucket[HOLDOUT]) for bucket in partition.stratum_counts().values()),
                default=0,
            )
            print(
                f"{name:14s} {len(partition.assignment):6d} questions  "
                f"dev {counts[DEV]:5d}  holdout {counts[HOLDOUT]:5d}  "
                f"widest stratum imbalance {widest}  {path.name}"
            )
        else:
            try:
                partition = verify(path, benchmark.questions)
            except (PartitionError, FileNotFoundError) as error:
                print(f"{name:14s} FAIL: {error}")
                failures += 1
                continue
            print(f"{name:14s} verified  {len(partition.assignment)} questions  {partition.digest()[:16]}")
    return failures


if __name__ == "__main__":
    sys.exit(main())
