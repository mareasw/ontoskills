"""Reporting module: metrics computation and comparison report generation."""

from .comparison import generate_comparison_report, save_report
from .metrics import (
    AgentMetrics,
    AggregateReport,
    BenchmarkComparison,
    compute_agent_metrics,
    compute_comparison,
)

__all__ = [
    "AgentMetrics",
    "AggregateReport",
    "BenchmarkComparison",
    "compute_agent_metrics",
    "compute_comparison",
    "generate_comparison_report",
    "save_report",
]
