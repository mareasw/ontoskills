"""A resumed build must not publish the cheap half of its bill.

The manifest keeps the calls this run made apart from the calls it replayed from
cache. A table that printed only the first would show a two-hour build as costing
three cents, which is the kind of number that makes a comparison look better than
it is.
"""

from __future__ import annotations

import json

from benchmark.layer import build_record


def _manifest(**overrides) -> dict:
    base = {
        "name": "kb",
        "model": "deepseek-v4.1-flash",
        "documents": 279,
        "claims": 9000,
        "elapsed_s": 7200.0,
        "tokens": {"input": 1_000_000, "output": 4_000_000},
        "cost_usd": 2.5,
        "replayed_tokens": {"input": 500_000, "output": 1_000_000},
        "replayed_cost_usd": 0.7,
    }
    base.update(overrides)
    return base


def test_the_total_is_fresh_plus_replayed(tmp_path):
    row = build_record.record(_manifest(), tmp_path)
    assert row["prompt_tokens"] == 1_500_000
    assert row["completion_tokens"] == 5_000_000
    assert row["usd"] == 3.2
    assert row["fresh"]["usd"] == 2.5
    assert row["replayed"]["usd"] == 0.7


def test_a_manifest_without_replay_reads_as_it_is(tmp_path):
    row = build_record.record(
        _manifest(replayed_tokens=None, replayed_cost_usd=0.0), tmp_path
    )
    assert row["prompt_tokens"] == 1_000_000
    assert row["usd"] == 2.5


def test_the_artifact_excludes_the_cache(tmp_path):
    (tmp_path / "claims.jsonl").write_text("x" * 50, encoding="utf-8")
    (tmp_path / "cache").mkdir()
    (tmp_path / "cache" / "blob.json").write_text("y" * 950, encoding="utf-8")
    row = build_record.record(_manifest(), tmp_path)
    assert row["artifact_bytes"] == 50
    assert row["excluded"] == ["cache"]


def test_a_wall_clock_can_cover_more_than_the_final_attempt(tmp_path, capsys):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(_manifest()), encoding="utf-8")
    out = tmp_path / "build.json"
    assert (
        build_record.main(
            [
                "--manifest",
                str(manifest),
                "--root",
                str(tmp_path),
                "--out",
                str(out),
                "--wall-clock",
                "9000",
            ]
        )
        == 0
    )
    row = json.loads(out.read_text(encoding="utf-8"))
    assert row["wall_clock_s"] == 9000.0
    assert "all attempts" in row["wall_clock_note"]


def test_a_frameworks_log_gives_the_wall_clock_when_it_has_no_manifest(tmp_path):
    """GraphRAG writes no build manifest; its log still spans the run."""
    log = tmp_path / "indexing-engine.log"
    log.write_text(
        "\n".join(
            [
                "no timestamp here",
                "2026-11-16 18:34:28.1200 - INFO - workflow started",
                "2026-11-16 18:35:05.5000 - INFO - working",
                "2026-11-16 20:59:26.9000 - INFO - workflow complete",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    assert build_record.log_wall_clock(log) == 8698


def test_a_log_without_timestamps_gives_no_number(tmp_path):
    log = tmp_path / "empty.log"
    log.write_text("nothing\n", encoding="utf-8")
    assert build_record.log_wall_clock(log) is None


def test_a_record_can_be_written_from_a_log_alone(tmp_path, capsys):
    (tmp_path / "output").mkdir()
    (tmp_path / "output" / "entities.parquet").write_text("x" * 40, encoding="utf-8")
    (tmp_path / "cache").mkdir()
    (tmp_path / "cache" / "a.json").write_text("y" * 960, encoding="utf-8")
    log = tmp_path / "run.log"
    log.write_text(
        "2026-11-16 18:34:28 - INFO - start\n2026-11-16 18:44:28 - INFO - stop\n",
        encoding="utf-8",
    )
    out = tmp_path / "build.json"
    assert (
        build_record.main(
            [
                "--root",
                str(tmp_path),
                "--name",
                "graphrag",
                "--log",
                str(log),
                "--exclude",
                "cache",
                "logs",
                "input",
                "run.log",
                "--out",
                str(out),
            ]
        )
        == 0
    )
    row = json.loads(out.read_text(encoding="utf-8"))
    assert row["label"] == "graphrag"
    assert row["wall_clock_s"] == 600
    assert row["artifact_bytes"] == 40
    assert row["excluded_not_found"] == ["logs", "input"]
