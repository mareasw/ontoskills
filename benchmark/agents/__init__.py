"""Benchmark agents: base class, traditional (no-tools), and OntoSkills (MCP)."""

from .base import AgentResult, BaseAgent
from .traditional import TraditionalAgent

__all__ = ["AgentResult", "BaseAgent", "TraditionalAgent"]
