"""Every metric is checked against a value computed by hand, and a wrong ranker
has to fail. A metric suite that only passes is not an instrument.

The hand computations are written out in the tests so a reader can check them
without running anything.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from benchmark.retrieval import metrics  # noqa: E402


# --- ranking metrics --------------------------------------------------------

GOLD = {"a", "c"}
RANKING = ("b", "a", "c")


def test_ndcg_matches_the_hand_computation():
    # DCG  = 1/log2(3) + 1/log2(4) = 0.63093 + 0.5     = 1.13093
    # IDCG = 1/log2(2) + 1/log2(3) = 1.0     + 0.63093 = 1.63093
    assert metrics.ndcg_at(RANKING, GOLD, 3) == pytest.approx(0.6934264036172708)


def test_ndcg_truncates_the_ideal_at_k():
    # k=2: DCG = 1/log2(3) = 0.63093, IDCG = 1 + 1/log2(3) = 1.63093
    assert metrics.ndcg_at(RANKING, GOLD, 2) == pytest.approx(0.38685280723454163)


def test_ndcg_is_one_for_the_ideal_ranking():
    assert metrics.ndcg_at(("a", "c"), GOLD, 10) == pytest.approx(1.0)


def test_ndcg_is_zero_when_nothing_relevant_is_returned():
    assert metrics.ndcg_at(("x", "y"), GOLD, 10) == 0.0


def test_recall_precision_hit_mrr_are_what_they_say():
    assert metrics.recall_at(RANKING, GOLD, 3) == pytest.approx(1.0)
    assert metrics.recall_at(RANKING, GOLD, 2) == pytest.approx(0.5)
    # precision@2 counts two returned items, one of them gold
    assert metrics.precision_at(RANKING, GOLD, 2) == pytest.approx(0.5)
    assert metrics.hit_at(RANKING, GOLD, 1) == 0.0
    assert metrics.hit_at(RANKING, GOLD, 2) == 1.0
    # first gold is at position 2
    assert metrics.mrr_at(RANKING, GOLD, 10) == pytest.approx(0.5)


def test_a_metric_without_gold_raises_instead_of_returning_zero():
    for function in (metrics.recall_at, metrics.ndcg_at, metrics.mrr_at, metrics.hit_at):
        with pytest.raises(ValueError):
            function(("a",), (), 10)


def test_graded_ndcg_uses_exponential_gains():
    # grades a=2, c=1; ranking b,a,c
    # DCG  = (2^2-1)/log2(3) + (2^1-1)/log2(4) = 3/log2(3) + 0.5
    # IDCG = 3/log2(2) + 1/log2(3)             = 3 + 1/log2(3)
    expected = (3 / math.log2(3) + 0.5) / (3 + 1 / math.log2(3))
    assert metrics.ndcg_at_graded(RANKING, {"a": 2, "c": 1}, 3) == pytest.approx(expected)


def test_rank_breaks_ties_by_id_so_runs_are_reproducible():
    assert metrics.rank({"b": 1.0, "a": 1.0, "c": 0.5}) == ("a", "b", "c")
    assert metrics.rank({"b": 1.0, "a": 1.0, "c": 0.5}, top_k=2) == ("a", "b")


def test_ranking_digest_depends_on_order():
    assert metrics.ranking_digest(("a", "b")) == metrics.ranking_digest(("a", "b"))
    assert metrics.ranking_digest(("a", "b")) != metrics.ranking_digest(("b", "a"))


# --- evidence-level matching ------------------------------------------------


def test_span_cover_is_asymmetric_and_bounded():
    assert metrics.span_cover((100, 200), (150, 250)) == pytest.approx(0.5)
    assert metrics.span_cover((100, 200), (90, 210)) == pytest.approx(1.0)
    assert metrics.span_cover((100, 200), (120, 140)) == pytest.approx(0.2)
    assert metrics.span_cover((100, 200), (200, 300)) == 0.0
    assert metrics.span_cover((100, 200), (0, 100)) == 0.0


def test_evidence_recall_credits_one_gold_item_per_returned_item():
    """A single returned item cannot satisfy two gold items: that is the point."""
    gold = ["g1", "g2"]

    def matches(candidate, expected):
        return candidate == "both" or candidate == expected

    assert metrics.evidence_recall_at(("both",), gold, 1, matches) == pytest.approx(0.5)
    assert metrics.evidence_recall_at(("both", "g2"), gold, 2, matches) == pytest.approx(1.0)
    assert metrics.evidence_recall_at(("g1",), gold, 1, matches) == pytest.approx(0.5)


def test_evidence_recall_counts_misses_against_the_system():
    assert metrics.evidence_recall_at(("x", "y"), ["g1", "g2"], 2, lambda c, e: False) == 0.0
    assert metrics.evidence_recall_at((), ["g1"], 12, lambda c, e: True) == 0.0


# --- answer-level metrics ---------------------------------------------------


def test_fact_token_recall_is_multiset_containment():
    fact = "Limit is 10 MiB per file"
    everything = "the limit is 10 MiB per file and 50 MiB total"
    assert metrics.fact_token_recall(fact, everything) == pytest.approx(1.0)
    # "per" is missing: 5 of 6 tokens
    assert metrics.fact_token_recall(fact, "the limit is 10 MiB for one file") == pytest.approx(5 / 6)
    # a repeated token needs to be repeated
    assert metrics.fact_token_recall("file file", "file") == pytest.approx(0.5)


def test_answer_fact_coverage_is_the_mean_over_facts():
    facts = ["alpha beta", "gamma delta"]
    # first fact fully present, second half present: (1.0 + 0.5) / 2
    assert metrics.answer_fact_coverage(facts, "alpha beta gamma") == pytest.approx(0.75)
    assert metrics.answer_fact_coverage(facts, "alpha beta") == pytest.approx(0.5)


def test_answer_fact_coverage_pools_the_returned_items_and_support_does_not():
    """Pooling is the product's answer; support is one citation on its own."""
    facts = ["alpha beta gamma"]
    items = ["alpha beta", "gamma"]
    assert metrics.answer_fact_coverage(facts, items) == pytest.approx(1.0)
    assert metrics.answer_fact_support(facts, items) == pytest.approx(2 / 3)
    assert metrics.answer_fact_support(facts, ["alpha beta gamma"]) == pytest.approx(1.0)
    assert metrics.answer_fact_support(facts, []) == 0.0


def test_numeric_congruence_is_all_or_nothing_on_numbers():
    assert metrics.numeric_congruence("10 MiB per file", "the 10 MiB limit")
    assert not metrics.numeric_congruence("10 MiB per file", "the 12 MiB limit")
    assert metrics.numeric_congruence("no numbers here", "anything")


# --- abstention -------------------------------------------------------------


def test_auc_matches_the_mann_whitney_definition():
    assert metrics.auc([0.9, 0.8, 0.2], [1, 0, 0]) == pytest.approx(1.0)
    assert metrics.auc([0.1, 0.8, 0.2], [1, 0, 0]) == pytest.approx(0.0)
    assert metrics.auc([0.5, 0.5], [1, 0]) == pytest.approx(0.5)
    # one positive beats one of two negatives: 1/2
    assert metrics.auc([0.5, 0.4, 0.6], [1, 0, 0]) == pytest.approx(0.5)


def test_risk_coverage_trades_coverage_for_accuracy():
    scores = [0.9, 0.8, 0.2, 0.1]
    labels = [1, 1, 0, 0]
    curve = metrics.risk_coverage(scores, labels)
    assert curve[-1] == (1.0, 0.5)
    assert curve[0] == (0.25, 1.0)
    assert metrics.accuracy_at_coverage(scores, labels, 0.5) == pytest.approx(1.0)
    assert metrics.accuracy_at_coverage(scores, labels, 1.0) == pytest.approx(0.5)


# --- statistics -------------------------------------------------------------


def test_bootstrap_interval_of_a_constant_is_degenerate():
    interval = metrics.bootstrap_ci([2.0] * 20)
    assert (interval.mean, interval.low, interval.high) == (2.0, 2.0, 2.0)


def test_bootstrap_is_reproducible_from_its_seed():
    values = [0.1 * index for index in range(50)]
    first = metrics.bootstrap_ci(values, seed=7)
    second = metrics.bootstrap_ci(values, seed=7)
    third = metrics.bootstrap_ci(values, seed=8)
    assert first == second
    assert (first.low, first.high) != (third.low, third.high)


def test_a_paired_comparison_of_a_constant_gap_is_unambiguous():
    left = [index / 10 + 1 for index in range(20)]
    right = [index / 10 for index in range(20)]
    comparison = metrics.compare(left, right, resamples=2000)
    assert comparison.mean_difference == pytest.approx(1.0)
    assert (comparison.low, comparison.high) == pytest.approx((1.0, 1.0))
    assert comparison.p_bootstrap == 0.0
    assert comparison.excludes_zero
    assert comparison.non_inferior(0.5)


def test_non_inferiority_is_a_different_question_from_significance():
    # left is worse by 0.5 everywhere, with no variance: significant, and still
    # non-inferior at a margin of 2 points.
    left = [1.0] * 20
    right = [1.5] * 20
    comparison = metrics.compare(left, right, resamples=2000)
    assert comparison.mean_difference == pytest.approx(-0.5)
    assert comparison.excludes_zero
    assert comparison.non_inferior(2.0)
    assert not comparison.non_inferior(0.4)


def test_wilcoxon_agrees_with_the_sign_test_on_a_clean_shift():
    left = [float(index) + 1.0 for index in range(12)]
    right = [float(index) for index in range(12)]
    # all twelve differences positive, no ties: p = 2 * 2^-12
    assert metrics.wilcoxon(left, right) == pytest.approx(2 * 2**-12)


def test_wilcoxon_returns_one_when_nothing_differs():
    assert metrics.wilcoxon([1.0, 2.0], [1.0, 2.0]) == 1.0


def test_holm_adjusts_a_known_family():
    adjusted = metrics.holm({"a": 0.01, "b": 0.02, "c": 0.03, "d": 0.04})
    assert adjusted == pytest.approx({"a": 0.04, "b": 0.06, "c": 0.06, "d": 0.06})


def test_mde_shrinks_with_sample_size():
    small = [1.0, -1.0] * 5
    large = [1.0, -1.0] * 50
    assert metrics.mde(large) < metrics.mde(small)
    assert metrics.mde(large) == pytest.approx(0.28157, abs=1e-4)


# --- a deliberately wrong ranker must fail ----------------------------------


def test_a_wrong_ranker_scores_worse_than_the_right_one():
    """Five queries, three gold documents each. The bad ranker is the exact
    reverse of each correct ranking: no implementation slip can make it win."""
    by_query = {f"q{query}": {f"d{query}-{item}" for item in range(3)} for query in range(5)}

    good: list[float] = []
    bad: list[float] = []
    absent: list[float] = []
    for query, gold in by_query.items():
        relevant = sorted(gold)
        noise = [f"x{query}-{item}" for item in range(7)]
        good.append(metrics.ndcg_at(tuple(relevant + noise), gold, 10))
        bad.append(metrics.ndcg_at(tuple(reversed(relevant + noise)), gold, 10))
        absent.append(metrics.ndcg_at(tuple(noise), gold, 10))

    assert sum(good) / len(good) == pytest.approx(1.0)
    assert sum(bad) / len(bad) < sum(good) / len(good) - 0.1
    assert sum(absent) / len(absent) == 0.0

    comparison = metrics.compare(good, bad, resamples=2000)
    assert comparison.mean_difference > 0
    assert comparison.low > 0, "the right ranker must beat the reversed one with certainty"


def test_ndcg_of_a_reversed_three_item_ranking_is_computable_by_hand():
    # gold a,b,c; reversed c,b,a: DCG = 1/log2(2) + 1/log2(3) + 1/log2(4) == IDCG
    # because every returned item is relevant, only the order of the discounts
    # matters and the ideal is the ascending one, so reversed == ideal here.
    assert metrics.ndcg_at(("c", "b", "a"), {"a", "b", "c"}, 10) == pytest.approx(1.0)
    # with one filler first, the reversal loses the top slot
    assert metrics.ndcg_at(("x", "c", "b", "a"), {"a", "b", "c"}, 10) == pytest.approx(
        (1 / math.log2(3) + 1 / math.log2(4) + 1 / math.log2(5)) / (1 + 1 / math.log2(3) + 1 / math.log2(4))
    )
