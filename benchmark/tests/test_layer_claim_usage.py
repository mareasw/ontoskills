"""E17 attributes money to claims, so the attribution has to be the cut itself.

If `kept_indices` disagreed with `prefix_cut` the tier table would charge the
build to the wrong claims — and it would do so silently, because both would
still return plausible counts. The tests compare the two directly rather than
restating the rule twice.
"""

from __future__ import annotations

from benchmark.layer.budget import prefix_cut
from benchmark.layer.e17_claim_usage import kept_indices


def test_indices_agree_with_the_published_cut():
    units = ["a" * 30, "", "b" * 40, "c" * 5, "", "d" * 90, "e" * 3]
    for budget in range(1, 200):
        kept = prefix_cut(units, budget)
        chosen = [units[index] for index in kept_indices(units, budget)]
        assert chosen == kept, budget


def test_blank_statements_do_not_shift_the_attribution():
    """The cut skips a blank without spending budget; the index must skip it too."""
    units = ["x" * 20, "", "y" * 20]
    assert kept_indices(units, 25) == [0]
    assert kept_indices(units, 40) == [0, 2]


def test_the_first_unit_is_kept_whatever_its_size():
    units = ["z" * 500, "w" * 10]
    assert kept_indices(units, 10) == [0]


def test_no_budget_means_every_non_blank_unit():
    units = ["a", "", "b", "c"]
    assert kept_indices(units, 10**6) == [0, 2, 3]
