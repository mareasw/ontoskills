"""The table that goes in the document must be a function of the artifacts.

Every number the pilot publishes is read from a file that a run wrote, so these
tests pin the three things that could quietly turn a measurement into a claim:
a missing run is an em dash and not a zero, a failed call is counted, and the
per-kind means are pooled by questions rather than averaged by kind.
"""

from __future__ import annotations

import json

from benchmark.layer import report


def test_a_number_is_written_the_way_the_document_writes_it():
    assert report.number(1234567) == "1 234 567"
    assert report.number(0.07351, 4) == "0,0735"
    assert report.percent(0.9407) == "94,1 %"
    assert report.duration(6334) == "1 h 45 min"
    assert report.duration(39) == "39 s"
    assert report.bytes_human(20500) == "20,5 kB"


def test_a_missing_value_is_an_em_dash_and_never_a_zero():
    assert report.number(None) == report.DASH
    assert report.percent(None) == report.DASH
    assert report.duration(None) == report.DASH
    assert report.bytes_human(None) == report.DASH


def test_a_failed_call_appears_in_the_build_row(tmp_path):
    log = tmp_path / "m.jsonl"
    log.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "label": "x",
                        "model": "m",
                        "status": 200,
                        "prompt_tokens": 100,
                        "completion_tokens": 50,
                        "streamed": False,
                    }
                ),
                json.dumps(
                    {
                        "label": "x",
                        "model": "m",
                        "status": 503,
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "streamed": False,
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "b.json").write_text(
        json.dumps({"wall_clock_s": 120, "artifact_bytes": 2048}), encoding="utf-8"
    )
    manifest = {
        "systems": [
            {"name": "x", "modality": "answer", "meter": "m.jsonl", "build": "b.json"}
        ]
    }
    text = report.render(manifest, tmp_path)
    assert "| x | answer | 2 | 1 | 100 | 50 |" in text
    assert "2 min 00 s" in text
    assert "2,0 kB" in text


def test_a_system_that_did_not_run_is_not_a_zero(tmp_path):
    manifest = {
        "systems": [{"name": "graphrag", "modality": "answer", "note": "build failed"}]
    }
    text = report.render(manifest, tmp_path)
    row = [line for line in text.splitlines() if line.startswith("| graphrag |")]
    assert row, text
    assert row[0].count(report.DASH) >= 6
    assert "build failed" in text


def test_the_overall_figure_pools_questions_not_kinds():
    """A kind with 4 questions must not weigh as much as one with 70."""
    score = {
        "by_kind": {
            "basic": {
                "questions": 70,
                "metrics": {"answer_fact_coverage": {"mean": 0.9, "n": 70}},
            },
            "high_level": {
                "questions": 4,
                "metrics": {"answer_fact_coverage": {"mean": 0.1, "n": 4}},
            },
            "info_not_found": {"questions": 8, "metrics": {}},
        }
    }
    pooled, scored = report._overall(score)
    # (0.9*70 + 0.1*4) / 74, not (0.9+0.1)/2 and not a mean that includes the
    # unanswerable kind.
    assert abs(pooled["answer_fact_coverage"] - (0.9 * 70 + 0.1 * 4) / 74) < 1e-12
    assert scored == 74


def test_a_refusal_is_weighted_out_of_the_mean_not_counted_as_a_zero():
    """The count behind a mean is the metric's, not the kind's question count.

    GraphRAG answered 56 of its 70 `basic` questions: weighting that kind's mean
    by 70 would divide fourteen refusals back in as zeros and publish a number
    that is neither the coverage of what it answered nor the coverage with
    refusals counted — the table would show a figure no reading produces.
    """
    score = {
        "by_kind": {
            "basic": {
                "questions": 70,
                "refused": 14,
                "metrics": {"answer_fact_coverage": {"mean": 1.0, "n": 56}},
            },
            "info_not_found": {"questions": 8, "refused": 5, "metrics": {}},
        }
    }
    pooled, scored = report._overall(score)
    assert pooled["answer_fact_coverage"] == 1.0
    assert scored == 56


def test_the_fallback_weight_is_refused_where_the_kind_did_refuse():
    """A score file without counts cannot be pooled when the kind abstained."""
    score = {
        "by_kind": {
            "basic": {
                "questions": 70,
                "refused": 14,
                "metrics": {"answer_fact_coverage": {"mean": 0.8}},
            },
        }
    }
    pooled, scored = report._overall(score)
    assert pooled.get("answer_fact_coverage") is None
    assert scored is None


def test_the_manifest_is_read_relative_to_itself(tmp_path):
    (tmp_path / "score.json").write_text(
        json.dumps(
            {
                "mode": "evidence",
                "k": 10,
                "questions": 2,
                "median_chars": 5071,
                "false_refusal_rate": 0.0,
                "abstention_rate": 0.0,
                "by_kind": {
                    "basic": {
                        "questions": 2,
                        "refused": 0,
                        "metrics": {
                            "answer_fact_coverage": {"mean": 0.5},
                            "answer_fact_support": {"mean": 0.25},
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "systems": [
                    {
                        "name": "ontoskills",
                        "modality": "evidence",
                        "score": "score.json",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "table.md"
    assert report.main(["--manifest", str(tmp_path / "manifest.json"), "--out", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    assert "| ontoskills | 2 | 10 | 5 071 | 50,0 % | 25,0 % |" in text
    assert "By question kind" in text


def test_a_build_that_was_not_metered_still_reports_its_cost(tmp_path):
    """Our own build reads its tokens from the knowledge base manifest."""
    (tmp_path / "b.json").write_text(
        json.dumps(
            {
                "calls": 21,
                "prompt_tokens": 1000,
                "completion_tokens": 2000,
                "usd": 0.0014,
                "wall_clock_s": 90,
                "artifact_bytes": 4096,
            }
        ),
        encoding="utf-8",
    )
    manifest = {
        "systems": [
            {"name": "ontoskills", "modality": "evidence", "build": "b.json"}
        ]
    }
    text = report.render(manifest, tmp_path)
    assert "| ontoskills | evidence | 21 | 0 |" in text
    assert "0,0014" in text


def test_an_offline_system_reports_zero_query_cost_and_its_reply_time(tmp_path):
    """The pitch is "no model at query time": the table has to show it."""
    (tmp_path / "a.jsonl").write_text(
        "\n".join(
            json.dumps({"qid": f"q{n}", "seconds": seconds})
            for n, seconds in enumerate([0.010, 0.050, 0.090])
        )
        + "\n",
        encoding="utf-8",
    )
    manifest = {
        "systems": [
            {
                "name": "ontoskills",
                "modality": "evidence",
                "answers": "a.jsonl",
                "queries_offline": True,
            }
        ]
    }
    text = report.render(manifest, tmp_path)
    assert "## Query" in text
    assert "| ontoskills | 0 | 0 | 0 | 0 | 0,0000 | 50 ms |" in text


def test_a_metered_query_phase_is_reported_with_its_failures(tmp_path):
    (tmp_path / "q.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "label": "graphrag-query",
                        "model": "m",
                        "status": 200,
                        "prompt_tokens": 1000,
                        "completion_tokens": 500,
                        "streamed": False,
                    }
                ),
                json.dumps(
                    {
                        "label": "graphrag-query",
                        "model": "m",
                        "status": 503,
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "streamed": False,
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    manifest = {
        "systems": [
            {"name": "graphrag", "modality": "answer", "query_meter": "q.jsonl"}
        ]
    }
    text = report.render(manifest, tmp_path)
    # 1000 in at 0,15 $/M plus 500 out at 0,60 $/M is 0,00045, which the
    # table prints at four decimals.
    assert "| graphrag | 2 | 1 | 1 000 | 500 | 0,0004 | — |" in text


def test_no_query_section_when_no_system_declares_one(tmp_path):
    manifest = {"systems": [{"name": "x", "modality": "answer"}]}
    assert "## Query" not in report.render(manifest, tmp_path)


def test_the_document_table_is_replaced_between_its_markers(tmp_path):
    """The doc cannot drift from the artifacts: regenerating is one command."""
    doc = tmp_path / "LAYER.md"
    doc.write_text(
        "intro\n\n<!-- PILOT-TABLE -->\n\nold table\n\n<!-- /PILOT-TABLE -->\n\noutro\n",
        encoding="utf-8",
    )
    assert report.splice(doc, "| new | table |") > 0
    text = doc.read_text(encoding="utf-8")
    assert "old table" not in text
    assert "| new | table |" in text
    assert text.startswith("intro")
    assert text.rstrip().endswith("outro")


def test_a_document_without_markers_is_refused(tmp_path):
    doc = tmp_path / "LAYER.md"
    doc.write_text("no markers here\n", encoding="utf-8")
    try:
        report.splice(doc, "x")
    except SystemExit as exc:
        assert "missing" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("a document without markers was spliced")
