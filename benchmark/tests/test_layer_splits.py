"""The split is fixed before tuning, and these tests are what "fixed" means."""

from __future__ import annotations

import json

import pytest

from benchmark.layer import splits

QIDS = [f"qst_{number:04d}" for number in range(1, 201)]


def test_the_split_is_reproducible_from_the_ids_alone():
    assert splits.split(QIDS) == splits.split(list(QIDS))


def test_the_two_halves_are_disjoint_and_cover_every_question():
    dev, test = splits.split(QIDS)
    assert not set(dev) & set(test)
    assert sorted(dev + test) == sorted(QIDS)
    assert len(dev) == len(test) == 100


def test_the_split_does_not_follow_the_selection_order():
    # The first hundred ids of the selection would be a different split; the
    # point of hashing is that an ordered selection cannot decide the halves.
    dev, _test = splits.split(QIDS)
    assert dev != QIDS[:100]


def test_a_different_salt_is_a_different_split():
    assert splits.split(QIDS, "one")[0] != splits.split(QIDS, "two")[0]


def test_duplicates_are_refused_rather_than_half_counted():
    with pytest.raises(ValueError, match="duplicate"):
        splits.split(["qst_0001", "qst_0001"])


def test_the_cli_writes_both_halves_and_their_kind_balance(tmp_path, capsys):
    selection = tmp_path / "selection.json"
    selection.write_text(
        json.dumps({"items": [{"qid": qid, "kind": "basic"} for qid in QIDS]}),
        encoding="utf-8",
    )
    out = tmp_path / "split.json"
    assert splits.main(["--selection", str(selection), "--json", str(out)]) == 0
    written = json.loads(out.read_text())
    assert written["summary"]["dev"] == written["summary"]["test"] == 100
    assert len(written["dev"]) == len(written["test"]) == 100
    assert sum(written["summary"]["by_kind"]["dev"].values()) == 100
    assert json.loads(capsys.readouterr().out)["salt"] == splits.SALT
