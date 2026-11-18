"""The ceiling in E18 is only as strong as the arithmetic that reads the meter.

`spent_usd` is what stops the build, so it is tested directly: a log with a
truncated final line, a failed call and the declared price table must produce the
number the guard compares against. A silent zero here would let a build past the
ceiling the protocol published.
"""

from __future__ import annotations

import json

from benchmark.layer.run_nanographrag import PRICE_IN, PRICE_OUT, cache_path, spent_usd


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
