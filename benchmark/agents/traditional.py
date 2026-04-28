"""Traditional agent for the OntoSkills benchmark.

Works like Claude Code: system prompt contains a skill registry (name +
description for every skill).  The model uses the ``read_skill`` tool to
load full skill content on demand.

All 425 skills are available; the model decides which ones to read.
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path

from .base import AgentResult, BaseAgent


# ---------------------------------------------------------------------------
# Frontmatter parsing (lightweight, no yaml dependency)
# ---------------------------------------------------------------------------

_FM_RE = re.compile(
    r"^---\s*\n(?P<body>.*?)\n---",
    re.DOTALL,
)
_FM_NAME_RE = re.compile(r"^name:\s*(.+)$", re.MULTILINE)
_FM_DESC_RE = re.compile(r"^description:\s*(.+)$", re.MULTILINE)


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Extract *name* and *description* from YAML frontmatter."""
    m = _FM_RE.search(text)
    if not m:
        return {}
    body = m.group("body")
    name_m = _FM_NAME_RE.search(body)
    desc_m = _FM_DESC_RE.search(body)
    name = name_m.group(1).strip().strip("\"'") if name_m else ""
    desc = desc_m.group(1).strip().strip("\"'") if desc_m else ""
    return {"name": name, "description": desc}


def _load_skill_registry(
    skills_dir: str,
) -> tuple[str, dict[str, Path]]:
    """Build the skill registry string and lookup table.

    Returns
    -------
    tuple[str, dict[str, Path]]
        (registry_text, skills_by_name) where *registry_text* is the
        formatted list of ``name — description`` entries and
        *skills_by_name* maps skill name to the SKILL.md Path.
    """
    root = Path(skills_dir)
    entries: list[str] = []
    skills_by_name: dict[str, Path] = {}

    if not root.exists():
        return "", skills_by_name

    for skill_file in sorted(root.rglob("SKILL.md")):
        try:
            text = skill_file.read_text(encoding="utf-8")
        except Exception:
            continue
        fm = _parse_frontmatter(text)
        name = fm.get("name", "")
        desc = fm.get("description", "")
        if not name:
            name = skill_file.parent.name
        entries.append(f"- {name}: {desc}" if desc else f"- {name}")
        skills_by_name[name] = skill_file
        # Also index by qualified path for flexible lookup.
        qualified = str(skill_file.relative_to(root).parent).replace(os.sep, "/")
        skills_by_name[qualified] = skill_file

    registry = "\n".join(entries)
    return registry, skills_by_name


# ---------------------------------------------------------------------------
# Tool schema
# ---------------------------------------------------------------------------

_READ_SKILL_TOOL: dict = {
    "name": "read_skill",
    "description": (
        "Read the full content of a skill by name. Use this to load "
        "detailed instructions, procedures, and knowledge for a skill "
        "you identified in the registry."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "skill_name": {
                "type": "string",
                "description": (
                    "Skill name from the registry (e.g. "
                    "'test-driven-development', 'xlsx', "
                    "'obra/superpowers/tdd')"
                ),
            },
        },
        "required": ["skill_name"],
    },
}


# ---------------------------------------------------------------------------
# TraditionalAgent
# ---------------------------------------------------------------------------

class TraditionalAgent(BaseAgent):
    """Agent with a skill registry + on-demand skill reading.

    The system prompt lists all 425 skill names and descriptions (~27K
    tokens).  The model uses the ``read_skill`` tool to load full skill
    content as needed — exactly like Claude Code.
    """

    def __init__(
        self,
        model: str,
        skills_dir: str,
        api_key: str | None = None,
    ) -> None:
        super().__init__(model=model, api_key=api_key)
        self.skills_dir = skills_dir
        self._skill_registry, self._skills_by_name = _load_skill_registry(
            skills_dir,
        )
        self._system_prompt = self._build_system_prompt()

    # ------------------------------------------------------------------
    # System prompt with skill registry
    # ------------------------------------------------------------------

    def _build_system_prompt(self) -> str:
        return (
            "You are an AI agent with access to a library of skills.\n"
            "Below is the full skill registry listing each skill's name "
            "and description.\n"
            "When a task matches a skill, call the `read_skill` tool to "
            "load its full content, then follow the skill's instructions.\n"
            "You may read multiple skills if needed.\n\n"
            "## Skill Registry\n"
            f"{self._skill_registry}\n\n"
            "## Instructions\n"
            "- Identify relevant skills from the registry above.\n"
            "- Use `read_skill` to load their full content.\n"
            "- Follow the loaded skill procedures to complete the task.\n"
            "- Be concise and accurate."
        )

    def get_system_prompt(self) -> str:
        return self._system_prompt

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------

    def get_tools(self) -> list[dict] | None:
        if hasattr(self, "_tools_override"):
            return self._tools_override
        return [_READ_SKILL_TOOL]

    # ------------------------------------------------------------------
    # Skill resolution
    # ------------------------------------------------------------------

    def _resolve_skill(self, query: str) -> str | None:
        """Find and return the full content of a skill by name.

        Tries exact match first, then prefix/substring match.
        Returns None if no skill is found.
        """
        q = query.strip()

        # Exact match on name or qualified path.
        path = self._skills_by_name.get(q)
        if path:
            return path.read_text(encoding="utf-8")

        # Fuzzy: prefix or substring match.
        for name, path in self._skills_by_name.items():
            if name.startswith(q) or q in name:
                return path.read_text(encoding="utf-8")

        return None

    # ------------------------------------------------------------------
    # Multi-turn execution with read_skill tool dispatch
    # ------------------------------------------------------------------

    def run_turn(self, messages: list[dict]) -> tuple[dict, dict]:
        """Call the API, dispatch ``read_skill`` tool calls, return metrics.

        Follows the same pattern as ``OntoSkillsAgent.run_turn()``:
        - Calls the API
        - Builds assistant message from response blocks
        - For each tool_use block, resolves the skill and builds tool_result
        - Appends assistant message + tool_results to *messages*
        """
        start = time.perf_counter()
        response = self._call_api(messages)
        latency_ms = (time.perf_counter() - start) * 1000

        # Build assistant message from response content blocks.
        content_blocks: list[dict] = []
        for block in response.content:
            if block.type == "text":
                content_blocks.append({
                    "type": "text",
                    "text": block.text,
                })
            elif block.type == "tool_use":
                content_blocks.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })

        assistant_msg: dict = {
            "role": "assistant",
            "content": content_blocks,
        }

        # Dispatch read_skill tool calls.
        tool_calls = 0
        tool_result_blocks: list[dict] = []
        for block in content_blocks:
            if block.get("type") != "tool_use":
                continue
            tool_calls += 1
            skill_name = block.get("input", {}).get("skill_name", "")
            content = self._resolve_skill(skill_name)
            if content is None:
                content = f"Skill not found: {skill_name}. Check the registry for exact names."
                is_error = True
            else:
                is_error = False
            tool_result_blocks.append({
                "type": "tool_result",
                "tool_use_id": block["id"],
                "content": content,
                "is_error": is_error,
            })

        # Append assistant message + tool_results to messages.
        if tool_result_blocks:
            messages.append(assistant_msg)
            messages.append({
                "role": "user",
                "content": tool_result_blocks,
            })

        metrics: dict = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "latency_ms": latency_ms,
            "tool_calls": tool_calls,
        }

        return assistant_msg, metrics
