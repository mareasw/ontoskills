"""The ceiling in E18 is only as strong as the arithmetic that reads the meter.

`spent_usd` is what stops the build, so it is tested directly: a log with a
truncated final line, a failed call and the declared price table must produce the
number the guard compares against. A silent zero here would let a build past the
ceiling the protocol published.
"""

from __future__ import annotations

import json

from benchmark.layer.run_nanographrag import (
    PRICE_IN,
    PRICE_OUT,
    GRAPH_FILES,
    UpstreamUnavailable,
    cache_path,
    clear_stale_graph,
    next_wait,
    retry_hint,
    spent_usd,
)


def write(tmp_path, rows, raw=""):
    path = tmp_path / "meter.jsonl"
    body = "\n".join(json.dumps(row) for row in rows) + raw
    path.write_text(body, encoding="utf-8")
    return path


def test_prices_input_and_output_at_the_declared_table(tmp_path):
    path = write(
        tmp_path,
        [
            {"prompt_tokens": 1_000_000, "completion_tokens": 0},
            {"prompt_tokens": 0, "completion_tokens": 1_000_000},
        ],
    )
    assert abs(spent_usd(path) - (PRICE_IN + PRICE_OUT)) < 1e-9


def test_a_failed_call_still_counts_its_tokens(tmp_path):
    """The gateway charged for what it generated before failing; the guard must see it."""
    path = write(tmp_path, [{"status": 503, "prompt_tokens": 2_000_000, "completion_tokens": 0}])
    assert abs(spent_usd(path) - 2 * PRICE_IN) < 1e-9


def test_a_truncated_last_line_is_dropped_not_trusted(tmp_path):
    path = tmp_path / "meter.jsonl"
    path.write_text(
        json.dumps({"prompt_tokens": 1_000_000, "completion_tokens": 0}) + '\n{"prompt_tok',
        encoding="utf-8",
    )
    assert abs(spent_usd(path) - PRICE_IN) < 1e-9


def test_missing_tokens_are_zero_not_an_exception(tmp_path):
    path = write(tmp_path, [{"status": 200}, {"prompt_tokens": 1_000_000, "completion_tokens": 5}])
    assert abs(spent_usd(path) - (PRICE_IN + 5 * PRICE_OUT / 1_000_000)) < 1e-9


def test_no_log_is_no_spend(tmp_path):
    assert spent_usd(tmp_path / "absent.jsonl") == 0.0


def test_the_cache_is_sharded_by_the_first_two_characters(tmp_path):
    path = cache_path(tmp_path, "abcdef")
    assert path.parent.name == "ab"
    assert path.name == "abcdef.json"


def test_the_gateway_retry_hint_is_obeyed_with_margin():
    message = (
        "Error code: 503 - {'error': {'code': 'rate_limited', "
        "'message': 'upstream rate limited (3x429/60s), retry later', "
        "'retry_after_ms': 30000}}"
    )
    assert retry_hint(message) == 32.0


def test_a_message_without_a_hint_asks_for_nothing():
    assert retry_hint("Error code: 503 - upstream unavailable") == 0.0


def test_an_interrupted_graph_is_moved_aside_not_merged(tmp_path):
    """Nano saves in a `finally`: a dead run leaves nodes and no reports on disk."""
    for name in GRAPH_FILES:
        (tmp_path / name).write_text("{}", encoding="utf-8")
    (tmp_path / "llm-cache").mkdir()

    moved = clear_stale_graph(tmp_path, "20261119-1030")

    assert sorted(moved) == sorted(GRAPH_FILES)
    assert all((tmp_path / "stale-20261119-1030" / name).exists() for name in GRAPH_FILES)
    assert (tmp_path / "llm-cache").exists()
    assert not (tmp_path / "graph_chunk_entity_relation.graphml").exists()


def test_a_finished_graph_is_left_alone(tmp_path):
    (tmp_path / "graph_chunk_entity_relation.graphml").write_text("{}", encoding="utf-8")
    (tmp_path / "build.json").write_text('{"outcome": "ok"}', encoding="utf-8")

    assert clear_stale_graph(tmp_path, "20261119-1030") == []
    assert (tmp_path / "graph_chunk_entity_relation.graphml").exists()


def test_an_empty_working_dir_is_left_alone(tmp_path):
    assert clear_stale_graph(tmp_path, "20261119-1030") == []


QUOTA = (
    "Error code: 503 - {'error': {'code': 'budget_exhausted', "
    "'message': 'quota exhausted (window weekly, resets 2026-11-23)', "
    "'retry_after_ms': 86400000}}"
)


def test_a_daily_hint_raises_instead_of_parking_the_run():
    import pytest

    with pytest.raises(UpstreamUnavailable):
        next_wait(8.0, QUOTA)


def test_an_ordinary_503_backs_off_without_honouring_no_hint():
    assert 8.0 <= next_wait(8.0, "Error code: 503 - upstream unavailable") <= 10.0


def test_a_thirty_second_hint_is_honoured():
    assert 32.0 <= next_wait(8.0, "503 retry_after_ms: 30000") <= 34.0
