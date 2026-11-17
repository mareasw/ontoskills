"""Artifact size is a measurement, so it has to be reproducible and honest.

The failure this guards against is a cache being counted as produced knowledge,
which would rank frameworks by how much scratch space they leave behind.
"""

from __future__ import annotations

import json

from benchmark.layer import artifacts


def _write(path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_a_cache_directory_is_not_part_of_the_artifact(tmp_path):
    _write(tmp_path / "entities.parquet", "x" * 100)
    _write(tmp_path / "cache" / "shard.json", "y" * 900)
    assert artifacts.directory_size(tmp_path) == 1000
    assert artifacts.directory_size(tmp_path, ("cache",)) == 100


def test_an_exclusion_that_matches_nothing_is_reported(tmp_path):
    """A typo in an exclusion must not silently change the published size."""
    _write(tmp_path / "a.txt", "x" * 10)
    record = artifacts.describe(tmp_path, ("cache", "logo"))
    assert record["artifact_bytes"] == 10
    assert record["excluded_not_found"] == ["cache", "logo"]


def test_files_are_counted_the_same_way_as_bytes(tmp_path):
    _write(tmp_path / "keep.txt", "x")
    _write(tmp_path / "sub" / "keep2.txt", "x")
    _write(tmp_path / "cache" / "drop.txt", "x")
    record = artifacts.describe(tmp_path, ("cache",))
    assert record["files"] == 2
    assert record["artifact_bytes"] == 2


def test_the_record_is_json_the_report_can_read(tmp_path, capsys):
    _write(tmp_path / "a.txt", "x" * 5)
    assert artifacts.main(["--root", str(tmp_path), "--json"]) == 0
    record = json.loads(capsys.readouterr().out)
    assert record["artifact_bytes"] == 5
    assert record["root"] == str(tmp_path)
