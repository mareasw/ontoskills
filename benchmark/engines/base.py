from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class EngineOutput:
    """Parsed output from a CLI agent run."""
    num_turns: int = 0
    tool_calls: dict[str, int] = field(default_factory=dict)
    tokens: dict[str, Any] = field(default_factory=dict)
    cost: float = 0.0


class AgentEngine:
    """Encapsulates all differences between agent CLIs (claude vs opencode).

    Each engine knows its binary path, model name, environment variables,
    CLI command syntax, JSON output format, and MCP config format.
    """

    def __init__(self) -> None:
        self.name: str = ""
        self.bin_name: str = ""
        self.bin_path: str = ""
        self.model: str = ""
        self.skills_path: str = ""
        self.download_url: str | None = None
        self.mcp_tool_name: str = "mcp__onto__skill"

    @property
    def env_vars(self) -> dict[str, str]:
        return {}

    def build_run_cmd(self, instruction: str) -> str:
        raise NotImplementedError

    def warmup_cmd(self) -> str:
        return f"echo WARMUP_$RANDOM$RANDOM; {self.bin_name} --version 2>/dev/null"

    def parse_output(self, stdout: str) -> EngineOutput:
        raise NotImplementedError

    def mcp_config(self, ontomcp_path: str, ontology_root: str) -> tuple[str, str] | None:
        """Return (filename, content) for MCP config, or None if not supported."""
        return None
