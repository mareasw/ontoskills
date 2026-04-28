"""Shared utilities for benchmark agents."""

from __future__ import annotations

import re


def extract_python_code(response: str) -> str:
    """Extract the largest Python code block from response text.

    Returns empty string when no code block is found.
    """
    blocks = re.findall(r"```(?:python)?\s*\n(.*?)```", response, re.DOTALL)
    if blocks:
        return max(blocks, key=len).strip()
    return ""
