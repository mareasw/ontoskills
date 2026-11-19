"""The one definition of "the same volume", shared by every budget curve.

`score.py::returned_text` cuts the floor at the first item that does not fit and
keeps the first one whole whatever its size. A pilot that cuts its own side
differently is not comparing at the same budget: skipping an oversize unit and
packing smaller ones after it silently buys text the floor is not allowed to
buy, and the difference lands in the coverage column as if it were quality.

So there is exactly one function, it mirrors `returned_text` line by line, and
`test_layer_budget.py` pins the three properties that matter: the first unit is
never truncated, the cut happens at the first unit that does not fit, and the
result never exceeds the budget unless the first unit alone does.
"""

from __future__ import annotations

from collections.abc import Sequence


def prefix_cut(units: Sequence[str], budget: int | None) -> list[str]:
    """The longest prefix of ``units`` that fits ``budget``, first unit whole."""
    kept: list[str] = []
    used = 0
    for text in units:
        if not text:
            continue
        if budget is not None and kept and used + len(text) > budget:
            break
        kept.append(text)
        used += len(text)
    return kept
