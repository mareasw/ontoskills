"""The budget cut is the contract between our side and the floor.

`score.py` cuts the floor at the first item that does not fit, keeping the first
item whole. If these tests fail, every equal-budget number in the pilot is
measuring two different things.
"""

from __future__ import annotations

from benchmark.layer.budget import prefix_cut


def test_stops_at_the_first_unit_that_does_not_fit():
    """Packing a later, smaller unit around an oversize one is not the floor's cut."""
    assert prefix_cut(["aaaa", "bbbbbbbb", "c"], 8) == ["aaaa"]


def test_the_first_unit_is_kept_whole_whatever_its_size():
    assert prefix_cut(["x" * 40, "y"], 10) == ["x" * 40]


def test_empty_units_do_not_spend_the_budget():
    assert prefix_cut(["", "abc", "", "de"], 5) == ["abc", "de"]


def test_an_exact_fit_is_kept():
    assert prefix_cut(["abc", "de"], 5) == ["abc", "de"]


def test_no_budget_is_everything():
    assert prefix_cut(["abc", "de"], None) == ["abc", "de"]


def test_the_result_never_exceeds_the_budget():
    units = ["a" * 3, "b" * 7, "c" * 2, "d" * 9]
    for budget in range(1, 25):
        kept = prefix_cut(units, budget)
        if kept and len(kept) > 1:
            assert sum(map(len, kept)) <= budget
