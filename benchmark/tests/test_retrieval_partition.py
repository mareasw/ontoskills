"""The split is only worth committing if editing it is detectable.

Each test here pins one property the protocol claims: balanced inside a stratum,
independent of input order, fixed by a digest, and impossible to quietly change.
"""

from __future__ import annotations

import json
import random
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from benchmark.retrieval import partition  # noqa: E402


@dataclass(frozen=True)
class Q:
    qid: str
    kind: str = "basic"


def questions(count: int, kind: str = "basic", prefix: str = "q") -> list[Q]:
    return [Q(f"{prefix}{index:04d}", kind) for index in range(count)]


def test_every_question_is_assigned_exactly_once():
    items = questions(37)
    split = partition.build("demo", items)
    assert set(split.assignment) == {item.qid for item in items}
    assert set(split.assignment.values()) == {partition.DEV, partition.HOLDOUT}
    assert len(split.dev) + len(split.holdout) == len(items)


def test_a_stratum_is_never_split_worse_than_one():
    """The reason this is not `sha256(qid) % 2`: twenty questions split 10/10."""
    split = partition.build("demo", questions(20))
    assert split.counts() == {partition.DEV: 10, partition.HOLDOUT: 10}
    for size in range(2, 30):
        counts = partition.build("demo", questions(size)).counts()
        assert abs(counts[partition.DEV] - counts[partition.HOLDOUT]) <= 1


def test_odd_strata_leave_the_extra_question_on_the_development_side():
    split = partition.build("demo", questions(7))
    assert split.counts() == {partition.DEV: 4, partition.HOLDOUT: 3}


def test_the_split_does_not_depend_on_input_order():
    items = questions(50) + questions(30, kind="hard", prefix="h")
    first = partition.build("demo", items)
    shuffled = list(items)
    random.Random(0).shuffle(shuffled)
    second = partition.build("demo", shuffled)
    assert first.assignment == second.assignment
    assert first.digest() == second.digest()


def test_strata_are_balanced_independently():
    items = questions(20, "basic") + questions(20, "hard", prefix="h") + questions(3, "rare", prefix="r")
    split = partition.build("demo", items)
    counts = split.stratum_counts()
    assert counts["basic"] == {partition.DEV: 10, partition.HOLDOUT: 10}
    assert counts["hard"] == {partition.DEV: 10, partition.HOLDOUT: 10}
    assert counts["rare"] == {partition.DEV: 2, partition.HOLDOUT: 1}
    # A question never changes stratum, and the file says which stratum it had.
    assert split.strata["r0000"] == "rare"


def test_the_digest_pins_the_salt_and_the_algorithm():
    split = partition.build("demo", questions(10))
    other_salt = partition.Partition(
        dataset=split.dataset,
        salt="another-salt",
        algorithm=split.algorithm,
        assignment=split.assignment,
        strata=split.strata,
    )
    other_algorithm = partition.Partition(
        dataset=split.dataset,
        salt=split.salt,
        algorithm="something-else",
        assignment=split.assignment,
        strata=split.strata,
    )
    assert split.digest() != other_salt.digest()
    assert split.digest() != other_algorithm.digest()


def test_the_salt_is_fixed_by_the_protocol():
    with pytest.raises(partition.PartitionError):
        partition.build("demo", questions(5), salt="chosen-after-the-fact")


def test_a_round_trip_preserves_the_partition(tmp_path):
    split = partition.build("demo", questions(21))
    path = split.write(tmp_path / "demo.json")
    loaded = partition.Partition.read(path)
    assert loaded.assignment == split.assignment
    assert loaded.strata == split.strata
    assert loaded.digest() == split.digest()


def test_an_edited_file_is_rejected(tmp_path):
    split = partition.build("demo", questions(10))
    path = split.write(tmp_path / "demo.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    victim = next(qid for qid, side in payload["assignment"].items() if side == partition.DEV)
    payload["assignment"][victim] = partition.HOLDOUT
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(partition.PartitionError, match="digest"):
        partition.Partition.read(path)


def test_a_changed_question_set_is_rejected(tmp_path):
    items = questions(10)
    path = partition.build("demo", items).write(tmp_path / "demo.json")
    with pytest.raises(partition.PartitionError, match="changed"):
        partition.verify(path, items[:-1])
    with pytest.raises(partition.PartitionError, match="changed"):
        partition.verify(path, items + [Q("extra")])


def test_a_changed_stratum_is_rejected(tmp_path):
    items = questions(6, "basic")
    path = partition.build("demo", items).write(tmp_path / "demo.json")
    moved = [Q(item.qid, "hard") for item in items]
    with pytest.raises(partition.PartitionError, match="changed"):
        partition.verify(path, moved)


def test_verify_accepts_the_committed_file(tmp_path):
    items = questions(12) + questions(4, "rare", prefix="r")
    path = partition.build("demo", items).write(tmp_path / "demo.json")
    assert partition.verify(path, items).assignment == partition.build("demo", items).assignment


def test_a_missing_file_is_a_file_error_not_a_pass(tmp_path):
    with pytest.raises(FileNotFoundError):
        partition.verify(tmp_path / "absent.json", questions(3))


def test_duplicates_and_empty_sets_are_refused():
    with pytest.raises(partition.PartitionError, match="duplicate"):
        partition.build("demo", questions(4) + questions(1))
    with pytest.raises(partition.PartitionError, match="no questions"):
        partition.build("demo", [])


def test_the_same_question_lands_on_the_same_side_in_a_bigger_stratum_only_by_hash_order():
    """Adding a question may move its neighbours in that stratum, never another
    stratum: a split that leaks across strata would make one family's growth
    rewrite another family's holdout."""
    small = partition.build("demo", questions(10, "basic") + questions(10, "hard", prefix="h"))
    grown = partition.build(
        "demo", questions(10, "basic") + questions(10, "hard", prefix="h") + questions(1, "rare", prefix="r")
    )
    for qid, side in small.assignment.items():
        assert grown.assignment[qid] == side
