"""Generate chart-ready JSON from benchmark results.

Produces structured JSON that can be consumed by Chart.js, D3, or any
charting library for the OntoSkills website.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def generate_chart_data(
    benchmark: str,
    mode: str,
    results: list[dict],
    score: dict | None = None,
    model: str = "",
) -> dict:
    """Generate chart-ready JSON from benchmark results.

    Parameters
    ----------
    benchmark:
        Benchmark identifier (e.g. "skillsbench").
    mode:
        Agent mode (e.g. "claudecode", "claudecode-mcp", "traditional", "ontoskills").
    results:
        List of per-task result dicts.
    score:
        Optional score dict from the wrapper's score() method.
    model:
        Model ID used.

    Returns
    -------
    dict
        Chart-ready JSON structure.
    """
    now = datetime.now(timezone.utc).isoformat()

    per_task = []
    for r in results:
        m = r.get("metrics", {}) or {}
        per_task.append({
            "task_id": r.get("task_id", ""),
            "reward": r.get("reward", 0),
            "passed": r.get("passed", False),
            "input_tokens": m.get("input_tokens", 0),
            "output_tokens": m.get("output_tokens", 0),
            "latency_ms": m.get("latency_ms", 0) or m.get("total_latency_ms", 0),
            "tool_calls": m.get("tool_calls", 0),
            "cost_usd": m.get("cost_usd", 0),
            "num_turns": m.get("num_turns", 0) or m.get("turns", 0),
        })

    valid_rewards = [r["reward"] for r in per_task]
    valid_tokens = [(r["input_tokens"], r["output_tokens"]) for r in per_task if r["input_tokens"] > 0]

    summary = {
        "pass_rate": score.get("pass_rate", 0) if score else 0,
        "avg_reward": score.get("avg_reward", 0) if score else 0,
        "tasks_passed": score.get("tasks_passed", 0) if score else 0,
        "tasks_partial": score.get("tasks_partial", 0) if score else 0,
        "tasks_failed": score.get("tasks_failed", 0) if score else 0,
        "total_tasks": score.get("total_tasks", len(results)) if score else len(results),
        "avg_input_tokens": sum(t[0] for t in valid_tokens) / len(valid_tokens) if valid_tokens else 0,
        "avg_output_tokens": sum(t[1] for t in valid_tokens) / len(valid_tokens) if valid_tokens else 0,
        "total_cost_usd": sum(r["cost_usd"] for r in per_task),
    }

    return {
        "benchmark": benchmark,
        "mode": mode,
        "model": model,
        "date": now,
        "per_task": per_task,
        "summary": summary,
    }


def generate_comparison_chart_data(
    traditional_chart: dict,
    ontoskills_chart: dict,
) -> dict:
    """Generate head-to-head comparison chart data.

    Takes two chart_data dicts (one per mode) and produces comparison metrics.
    """
    t_summary = traditional_chart.get("summary", {})
    o_summary = ontoskills_chart.get("summary", {})

    per_task_comparison = []
    t_tasks = {r["task_id"]: r for r in traditional_chart.get("per_task", [])}
    o_tasks = {r["task_id"]: r for r in ontoskills_chart.get("per_task", [])}

    all_ids = sorted(set(t_tasks.keys()) | set(o_tasks.keys()))
    for tid in all_ids:
        t = t_tasks.get(tid, {})
        o = o_tasks.get(tid, {})
        per_task_comparison.append({
            "task_id": tid,
            "traditional_reward": t.get("reward", 0),
            "ontoskills_reward": o.get("reward", 0),
            "traditional_passed": t.get("passed", False),
            "ontoskills_passed": o.get("passed", False),
        })

    return {
        "benchmark": traditional_chart.get("benchmark", ""),
        "model": traditional_chart.get("model", ""),
        "date": traditional_chart.get("date", ""),
        "traditional": t_summary,
        "ontoskills": o_summary,
        "delta": {
            "pass_rate": (o_summary.get("pass_rate", 0) - t_summary.get("pass_rate", 0)),
            "avg_reward": (o_summary.get("avg_reward", 0) - t_summary.get("avg_reward", 0)),
            "token_efficiency_pct": (
                ((t_summary.get("avg_input_tokens", 0) - o_summary.get("avg_input_tokens", 0))
                 / t_summary.get("avg_input_tokens", 1) * 100)
                if t_summary.get("avg_input_tokens", 0) > 0 else None
            ),
        },
        "per_task": per_task_comparison,
    }


def save_chart_data(chart_data: dict, output_path: str) -> None:
    """Save chart data JSON to file."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(chart_data, indent=2, ensure_ascii=False), encoding="utf-8")
