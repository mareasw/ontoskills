#!/usr/bin/env python3
"""Extract benchmark results from state files into a unified dataset.

Usage:
    python benchmark/reporting/extract.py [--results-dir benchmark/results] [--output-dir benchmark/results/data]

Scans benchmark/results/skillsbench/<case>/benchmark_state.json for each case
and produces a unified JSON with per-task, per-case, per-attempt details.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
DEFAULT_OUTPUT_DIR = DEFAULT_RESULTS_DIR / "data"


def _find_cases(results_dir: Path) -> list[tuple[str, Path]]:
    cases = []
    skillsbench_dir = results_dir / "skillsbench"
    if not skillsbench_dir.is_dir():
        logger.warning("No skillsbench results directory at %s", skillsbench_dir)
        return cases
    for entry in sorted(skillsbench_dir.iterdir()):
        state_file = entry / "benchmark_state.json"
        if state_file.exists():
            cases.append((entry.name, state_file))
    return cases


def _extract_attempts(state: dict, task_id: str) -> list[dict]:
    task_data = state.get("tasks", {}).get(task_id, {})
    return task_data.get("attempts", [])


def _case_metadata(case_label: str) -> dict:
    parts = case_label.split("+")
    mode = parts[0]
    hints = len(parts) > 1 and parts[1] == "hints"
    return {"mode": mode, "hints": hints, "label": case_label}


def _compute_case_summary(tasks: dict[str, list[dict]]) -> dict:
    passed = sum(1 for t in tasks.values() if t.get("best_reward", 0) >= 1.0)
    total = len(tasks)
    rewards = [t.get("best_reward", 0.0) for t in tasks.values()]
    avg_reward = sum(rewards) / total if total else 0.0
    return {
        "tasks_passed": passed,
        "total_tasks": total,
        "pass_rate": passed / total if total else 0.0,
        "avg_reward": avg_reward,
    }


def extract_all(
    results_dir: str | Path = DEFAULT_RESULTS_DIR,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
) -> dict:
    results_path = Path(results_dir)
    output_path = Path(output_dir)

    cases = _find_cases(results_path)
    if not cases:
        logger.error("No benchmark state files found in %s/skillsbench/", results_path)
        return {}

    all_tasks: dict[str, dict] = {}
    engines: set[str] = set()
    case_summaries: dict[str, dict] = {}

    for label, state_file in cases:
        with open(state_file) as f:
            state = json.load(f)

        meta = _case_metadata(label)
        engine = state.get("engine", "unknown")
        model = state.get("model", "unknown")
        engines.add(engine)

        for task_id, task_data in state.get("tasks", {}).items():
            if task_id not in all_tasks:
                all_tasks[task_id] = {
                    "task_id": task_id,
                    "cases": {},
                    "best_reward": 0.0,
                }

            attempts = task_data.get("attempts", [])
            processed = []
            for att in attempts:
                processed.append({
                    "attempt": att.get("attempt", 0),
                    "reward": att.get("reward", 0.0),
                    "error": att.get("error"),
                    "n_tool_calls": att.get("n_tool_calls", 0),
                    "tool_calls": att.get("tool_calls", {}),
                    "duration_sec": att.get("duration_sec", 0.0),
                    "counted": att.get("counted", True),
                })

            best = task_data.get("best_reward", 0.0)
            case_key = f"{label}"
            case_info = {
                "engine": engine,
                "model": model,
                "mode": meta["mode"],
                "hints": meta["hints"],
                "best_reward": best,
                "passed": best >= 1.0,
                "attempts": processed,
                "attempts_completed": sum(1 for a in attempts if a.get("counted", True)),
            }
            all_tasks[task_id]["cases"][case_key] = case_info
            if best > all_tasks[task_id]["best_reward"]:
                all_tasks[task_id]["best_reward"] = best

        case_summaries[label] = _compute_case_summary(
            {tid: td for tid, td in state.get("tasks", {}).items()}
        )

    # Global summary per engine
    engine_summaries: dict[str, dict] = {}
    for eng in engines:
        eng_tasks = {}
        for tid, td in all_tasks.items():
            for ck, ci in td["cases"].items():
                if ci["engine"] == eng:
                    if tid not in eng_tasks or ci["best_reward"] > eng_tasks[tid].get("best_reward", 0):
                        eng_tasks[tid] = {"best_reward": ci["best_reward"]}
        eng_sum = _compute_case_summary(eng_tasks)
        engine_summaries[eng] = eng_sum

    dataset = {
        "benchmark": "skillsbench",
        "cases": {label: cs for label, cs in case_summaries.items()},
        "engines": engine_summaries,
        "tasks": all_tasks,
    }

    output_path.mkdir(parents=True, exist_ok=True)
    (output_path / "tasks.json").write_text(
        json.dumps(dataset, indent=2, default=str, ensure_ascii=False),
        encoding="utf-8",
    )
    (output_path / "summary.json").write_text(
        json.dumps({
            "cases": case_summaries,
            "engines": engine_summaries,
        }, indent=2, default=str, ensure_ascii=False),
        encoding="utf-8",
    )

    logger.info("Extracted %d tasks from %d cases → %s", len(all_tasks), len(cases), output_path)
    return dataset


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Extract benchmark results into unified dataset")
    parser.add_argument("--results-dir", default=str(DEFAULT_RESULTS_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    extract_all(results_dir=args.results_dir, output_dir=args.output_dir)
