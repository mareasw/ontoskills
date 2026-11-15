"""The metric layer: one definition per number, one test per definition.

Nothing here knows about datasets, rankers or the product. A metric takes gold
and a ranking and returns a number; the statistics take per-query numbers and
return an interval. That split is what makes it possible to check the instrument
against a published value and against a ranker that is deliberately wrong.

Conventions, fixed here and repeated in PREFLIGHT §4:

* `k` counts **returned items**, 1-based in the formulas.
* Relevance is **binary** unless the caller passes grades. BEIR's nDCG@10 is
  binary, so the default reproduces it; ours is graded when a dataset has grades.
* Ties in nDCG are impossible: `rank()` breaks every tie by id, so a run is
  reproducible to the bit rather than "reproducible up to shuffling".
* A metric that cannot be computed raises. It never returns 0.0, because a zero
  is a number someone will average.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

import numpy as np

_WORD = re.compile(r"[^\W_]+", re.UNICODE)


def tokens(text: str) -> list[str]:
    """Lower-case alphanumeric tokens longer than one character.

    Deliberately simple and deliberately independent of the compiler's
    tokeniser: the metric compares systems that all run through the same
    function, so its quirks cancel between them, and an accidental change in the
    product's tokeniser cannot move a published number.
    """
    return [token for token in _WORD.findall(str(text or "").lower()) if len(token) > 1]


# --- ranking metrics --------------------------------------------------------


def rank(scores: dict[str, float], top_k: int | None = None) -> tuple[str, ...]:
    """Order ids by descending score, ties broken by id, so a run is exact.

    Without the id tie-break, two systems with identical scores can produce
    different rankings depending on dict insertion order, and the determinism
    claim becomes a claim about Python rather than about the system.
    """
    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    ids = tuple(identifier for identifier, _ in ordered)
    return ids[:top_k] if top_k is not None else ids


def _cut(ranking: Sequence[str], k: int) -> Sequence[str]:
    if k <= 0:
        raise ValueError("k must be positive")
    return ranking[:k]


def recall_at(ranking: Sequence[str], gold: Iterable[str], k: int) -> float:
    """Fraction of the gold ids present in the top k."""
    gold = set(gold)
    if not gold:
        raise ValueError("recall needs a non-empty gold set")
    return len(gold.intersection(_cut(ranking, k))) / len(gold)


def precision_at(ranking: Sequence[str], gold: Iterable[str], k: int) -> float:
    """Fraction of the top k that is gold. Denominator is k, not the list length."""
    gold = set(gold)
    if not gold:
        raise ValueError("precision needs a non-empty gold set")
    return len(gold.intersection(_cut(ranking, k))) / k


def hit_at(ranking: Sequence[str], gold: Iterable[str], k: int) -> float:
    """1 if any gold id is in the top k. Reported, never gated: it hides the
    multi-item questions, which is where a retriever actually fails."""
    gold = set(gold)
    if not gold:
        raise ValueError("hit needs a non-empty gold set")
    return 1.0 if gold.intersection(_cut(ranking, k)) else 0.0


def mrr_at(ranking: Sequence[str], gold: Iterable[str], k: int) -> float:
    """Reciprocal rank of the first gold id in the top k, else 0."""
    gold = set(gold)
    if not gold:
        raise ValueError("mrr needs a non-empty gold set")
    for position, identifier in enumerate(_cut(ranking, k), start=1):
        if identifier in gold:
            return 1.0 / position
    return 0.0


def ndcg_at(ranking: Sequence[str], gold: Iterable[str], k: int) -> float:
    """Binary-relevance nDCG@k, the BEIR convention.

    DCG = sum over returned positions of rel / log2(position + 1), IDCG from the
    ideal ordering of the gold set, truncated at k.
    """
    gold = set(gold)
    if not gold:
        raise ValueError("ndcg needs a non-empty gold set")
    dcg = 0.0
    for position, identifier in enumerate(_cut(ranking, k), start=1):
        if identifier in gold:
            dcg += 1.0 / math.log2(position + 1)
    ideal = sum(1.0 / math.log2(position + 1) for position in range(1, min(len(gold), k) + 1))
    return dcg / ideal


def ndcg_at_graded(ranking: Sequence[str], grades: dict[str, int], k: int) -> float:
    """Graded nDCG@k with gain 2**grade - 1, for datasets that carry grades."""
    if not grades:
        raise ValueError("graded ndcg needs a non-empty grade map")
    dcg = 0.0
    for position, identifier in enumerate(_cut(ranking, k), start=1):
        grade = grades.get(identifier, 0)
        if grade:
            dcg += (2.0**grade - 1.0) / math.log2(position + 1)
    ideal = 0.0
    for position, grade in enumerate(sorted(grades.values(), reverse=True)[:k], start=1):
        if grade:
            ideal += (2.0**grade - 1.0) / math.log2(position + 1)
    return dcg / ideal if ideal else 0.0


# --- evidence-level matching ------------------------------------------------


def span_cover(gold: tuple[int, int], candidate: tuple[int, int]) -> float:
    """How much of the gold range a candidate range covers, in [0, 1].

    Both are `(char_start, char_end)` in the collapsed source of the same
    document. Asymmetric on purpose: the gold is the reference, so a long
    candidate that contains it scores 1 and a short one that sits inside it
    scores its own length over the gold's.
    """
    start, end = gold
    if end <= start:
        raise ValueError("empty gold range")
    overlap = max(0, min(end, candidate[1]) - max(start, candidate[0]))
    return overlap / (end - start)


def evidence_recall_at(
    ranked: Sequence[object],
    gold: Sequence[object],
    k: int,
    match: Callable[[object, object], bool],
) -> float:
    """Fraction of the gold evidence items reached by the top k, one-to-one.

    A single returned item is credited to at most one gold item, which is why
    this is not `1 - prod(1 - hit)` and why it differs from Hit@k on the
    multi-item questions. The assignment is greedy in rank order: deterministic,
    and optimal whenever each returned item can satisfy at most one gold item,
    which is the case for non-overlapping gold spans.

    The denominator is the gold set, so an item nobody could reach counts
    against the system, not against the metric.
    """
    if not gold:
        raise ValueError("evidence recall needs a non-empty gold set")
    taken: set[int] = set()
    credited = 0
    for candidate in _cut(ranked, k):
        for position, expected in enumerate(gold):
            if position in taken:
                continue
            if match(candidate, expected):
                taken.add(position)
                credited += 1
                break
    return credited / len(gold)


# --- answer-level metrics ---------------------------------------------------


def fact_token_recall(fact: str, evidence: str) -> float:
    """Share of the fact's tokens that the evidence contains, multiset-wise.

    No stopword list and no threshold: every token of the fact counts once, a
    token repeated in the fact must be repeated in the evidence to count again,
    and the result is a fraction rather than a yes/no. It answers "how much of
    the answer is present", which is the question the official EnterpriseRAG
    judge answers with a model and $30; ours is the deterministic proxy and is
    labelled as one.
    """
    wanted = tokens(fact)
    if not wanted:
        raise ValueError("a fact with no tokens cannot be scored")
    available: dict[str, int] = {}
    for token in tokens(evidence):
        available[token] = available.get(token, 0) + 1
    hit = 0
    for token in wanted:
        if available.get(token, 0):
            available[token] -= 1
            hit += 1
    return hit / len(wanted)


def answer_fact_coverage(facts: Sequence[str], evidence: str | Sequence[str]) -> float:
    """Mean `fact_token_recall` over the gold facts, against the returned union.

    `evidence` is either one text or the returned items; a sequence is joined, so
    the number is coverage by the *union* of what was returned — the answer the
    product could assemble. `answer_fact_support` is the stricter companion.
    """
    if not facts:
        raise ValueError("answer coverage needs at least one fact")
    text = evidence if isinstance(evidence, str) else "\n".join(evidence)
    return sum(fact_token_recall(fact, text) for fact in facts) / len(facts)


def answer_fact_support(facts: Sequence[str], evidence: Sequence[str]) -> float:
    """Mean over facts of the best single returned item's `fact_token_recall`.

    The question coverage does not answer: does one citation carry this fact on
    its own? A fact reachable only by pooling several claims is real but weaker,
    and a reply built from it is one reading away from wrong.
    """
    if not facts:
        raise ValueError("answer support needs at least one fact")
    items = list(evidence)
    if not items:
        return 0.0
    return sum(max(fact_token_recall(fact, item) for item in items) for fact in facts) / len(facts)


def numeric_congruence(fact: str, evidence: str) -> bool:
    """True when every number in the fact also appears in the evidence.

    Separate from `fact_token_recall` because numbers are not prose: a reply can
    cover the sentence and still get the number wrong, and averaging that away
    is how a wrong answer scores well.
    """
    wanted = [token for token in tokens(fact) if any(character.isdigit() for character in token)]
    present = set(tokens(evidence))
    return all(token in present for token in wanted)


# --- abstention -------------------------------------------------------------


def auc(scores: Sequence[float], labels: Sequence[int]) -> float:
    """Area under the ROC curve of `scores` against binary `labels`.

    Computed from the Mann–Whitney statistic with average ranks for ties, so it
    agrees with sklearn to machine precision without importing it.
    """
    scores = np.asarray(scores, dtype=float)
    labels = np.asarray(labels, dtype=int)
    if scores.shape != labels.shape:
        raise ValueError("scores and labels must have the same length")
    positives = int(labels.sum())
    negatives = len(labels) - positives
    if positives == 0 or negatives == 0:
        raise ValueError("auc needs both classes")
    order = np.argsort(scores, kind="mergesort")
    ranks = np.empty(len(scores), dtype=float)
    sorted_scores = scores[order]
    position = 0
    while position < len(sorted_scores):
        end = position
        while end + 1 < len(sorted_scores) and sorted_scores[end + 1] == sorted_scores[position]:
            end += 1
        average_rank = (position + end) / 2.0 + 1.0
        ranks[order[position : end + 1]] = average_rank
        position = end + 1
    positive_rank_sum = ranks[labels == 1].sum()
    return float((positive_rank_sum - positives * (positives + 1) / 2.0) / (positives * negatives))


def risk_coverage(scores: Sequence[float], labels: Sequence[int]) -> list[tuple[float, float]]:
    """(coverage, accuracy) points of the risk–coverage curve, high score first.

    A system that abstains on its lowest-confidence questions trades coverage for
    accuracy; the curve is the honest picture, and the single number the protocol
    reports is the accuracy at coverage 0.8.
    """
    scores = np.asarray(scores, dtype=float)
    labels = np.asarray(labels, dtype=int)
    if scores.shape != labels.shape:
        raise ValueError("scores and labels must have the same length")
    order = np.lexsort((np.arange(len(scores)), -scores))
    ordered = labels[order]
    curve = []
    correct = 0
    for position, label in enumerate(ordered, start=1):
        correct += int(label)
        curve.append((position / len(ordered), correct / position))
    return curve


def accuracy_at_coverage(scores: Sequence[float], labels: Sequence[int], coverage: float) -> float:
    """Accuracy on the most confident `coverage` fraction of the questions."""
    if not 0 < coverage <= 1:
        raise ValueError("coverage must be in (0, 1]")
    curve = risk_coverage(scores, labels)
    target = max(1, math.ceil(coverage * len(curve)))
    return curve[target - 1][1]


# --- statistics -------------------------------------------------------------


@dataclass(frozen=True)
class Interval:
    """A mean and the percentile bootstrap interval around it."""

    mean: float
    low: float
    high: float
    n: int
    resamples: int
    seed: int

    def as_dict(self) -> dict:
        return {
            "mean": self.mean,
            "ci_low": self.low,
            "ci_high": self.high,
            "n": self.n,
            "resamples": self.resamples,
            "seed": self.seed,
        }


def _means(values: np.ndarray, rng: np.random.Generator, resamples: int, chunk: int = 1000) -> np.ndarray:
    """Bootstrap distribution of the mean, chunked to keep memory bounded."""
    out = np.empty(resamples, dtype=float)
    for start in range(0, resamples, chunk):
        stop = min(start + chunk, resamples)
        indices = rng.integers(0, len(values), size=(stop - start, len(values)))
        out[start:stop] = values[indices].mean(axis=1)
    return out


def bootstrap_ci(
    values: Sequence[float], resamples: int = 10_000, level: float = 0.95, seed: int = 0
) -> Interval:
    """Percentile bootstrap for the mean of per-query values."""
    values = np.asarray(list(values), dtype=float)
    if len(values) == 0:
        raise ValueError("bootstrap needs at least one value")
    if len(values) == 1:
        return Interval(float(values[0]), float(values[0]), float(values[0]), 1, resamples, seed)
    means = _means(values, np.random.default_rng(seed), resamples)
    low, high = np.quantile(means, [(1.0 - level) / 2.0, 1.0 - (1.0 - level) / 2.0])
    return Interval(float(values.mean()), float(low), float(high), len(values), resamples, seed)


@dataclass(frozen=True)
class Comparison:
    """A paired difference between two systems, on the same queries."""

    mean_difference: float
    low: float
    high: float
    p_bootstrap: float
    p_wilcoxon: float
    n: int
    mde: float

    @property
    def excludes_zero(self) -> bool:
        return self.low > 0.0 or self.high < 0.0

    def non_inferior(self, margin: float) -> bool:
        """The lower end of the interval is above −margin, with margin positive."""
        return self.low > -margin

    def as_dict(self) -> dict:
        return {
            "mean_difference": self.mean_difference,
            "ci_low": self.low,
            "ci_high": self.high,
            "p_bootstrap": self.p_bootstrap,
            "p_wilcoxon": self.p_wilcoxon,
            "n": self.n,
            "mde": self.mde,
            "excludes_zero": self.excludes_zero,
        }


def paired_bootstrap(
    left: Sequence[float],
    right: Sequence[float],
    resamples: int = 10_000,
    level: float = 0.95,
    seed: int = 0,
) -> tuple[float, float, float, np.ndarray]:
    """Paired difference left − right: (mean, low, high, bootstrap distribution).

    The same resample indices are applied to both systems, which is what makes
    the interval narrower than two independent intervals would be and therefore
    what makes a small real effect detectable.
    """
    left = np.asarray(list(left), dtype=float)
    right = np.asarray(list(right), dtype=float)
    if left.shape != right.shape:
        raise ValueError("a paired comparison needs the same queries on both sides")
    if len(left) == 0:
        raise ValueError("a paired comparison needs at least one query")
    if len(left) == 1:
        difference = float(left[0] - right[0])
        return difference, difference, difference, np.array([difference])
    rng = np.random.default_rng(seed)
    differences = left - right
    distribution = _means(differences, rng, resamples)
    low, high = np.quantile(distribution, [(1.0 - level) / 2.0, 1.0 - (1.0 - level) / 2.0])
    return float(differences.mean()), float(low), float(high), distribution


def wilcoxon(left: Sequence[float], right: Sequence[float]) -> float:
    """Two-sided Wilcoxon signed-rank p-value; 1.0 when every difference is zero."""
    from scipy.stats import wilcoxon as scipy_wilcoxon

    left = np.asarray(list(left), dtype=float)
    right = np.asarray(list(right), dtype=float)
    if left.shape != right.shape:
        raise ValueError("a paired test needs the same queries on both sides")
    difference = left - right
    if not np.any(difference):
        return 1.0
    return float(scipy_wilcoxon(difference, zero_method="wilcox", alternative="two-sided").pvalue)


def mde(differences: Sequence[float], alpha: float = 0.05, power: float = 0.8) -> float:
    """Minimum detectable effect at this sample size and variance, in metric points.

    Reported next to every non-significant comparison, so "no difference" is a
    statement about power rather than about the system.
    """
    differences = np.asarray(list(differences), dtype=float)
    if len(differences) < 2:
        return float("inf")
    z_alpha = 1.959963984540054  # two-sided 5%
    z_power = 0.8416212335729143  # 80%
    return float((z_alpha + z_power) * differences.std(ddof=1) / math.sqrt(len(differences)))


def compare(
    left: Sequence[float], right: Sequence[float], resamples: int = 10_000, seed: int = 0
) -> Comparison:
    """Everything the protocol asks of one paired comparison, in one object."""
    mean, low, high, distribution = paired_bootstrap(left, right, resamples=resamples, seed=seed)
    below = float(np.mean(distribution <= 0.0))
    above = float(np.mean(distribution >= 0.0))
    p_bootstrap = min(1.0, 2.0 * min(below, above))
    differences = np.asarray(list(left), dtype=float) - np.asarray(list(right), dtype=float)
    return Comparison(
        mean_difference=mean,
        low=low,
        high=high,
        p_bootstrap=p_bootstrap,
        p_wilcoxon=wilcoxon(left, right),
        n=len(differences),
        mde=mde(differences),
    )


def holm(pvalues: dict[str, float]) -> dict[str, float]:
    """Holm–Bonferroni adjusted p-values over a pre-declared family."""
    if not pvalues:
        return {}
    names = sorted(pvalues)
    ordered = sorted(names, key=lambda name: pvalues[name])
    adjusted: dict[str, float] = {}
    running = 0.0
    total = len(ordered)
    for position, name in enumerate(ordered):
        value = min(1.0, (total - position) * pvalues[name])
        running = max(running, value)
        adjusted[name] = running
    return adjusted


# --- determinism ------------------------------------------------------------


def ranking_digest(ranking: Sequence[str]) -> str:
    """SHA-256 of a ranking, for the determinism check in PREFLIGHT §4."""
    return hashlib.sha256("\n".join(str(item) for item in ranking).encode("utf-8")).hexdigest()
