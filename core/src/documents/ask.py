"""Deterministic question answering over a compiled corpus.

No model, no network. The answer is a ranked set of claims, each carrying the
document, page, section and URL of the span it was compiled from, plus the
verbatim quote. That is the whole point of the knowledge base: an answer you
can check against the source in one click. Only claims the deterministic
verifier passed are answered; a caller that wants the audit surface asks for
the rest and sees each verdict badge.

Ranking is BM25 over a claim's statement, actor, conditions and the quotes of
its evidence. When the knowledge base carries local embeddings, the cosine
ranking is fused with the lexical one by Reciprocal Rank Fusion — ranks only,
so there is no weight to tune — and a claim the question's words cannot reach
is still reachable. Claims are grouped by document, because the demo's
acceptance criterion is *cross-document*: three questions, each answered from
at least two documents.

Tensions are the deterministic part of "this corpus does not speak with one
voice". A number is attached to a topic by the words around it — a breach
notification deadline, a retention period, an audit window — and two documents
in the result that give the same topic different numbers are reported as a
tension, with both citations. No inference, no precedence: the corpus is shown
disagreeing, and the reader decides.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Iterable

from compiler.documents.text import norm, tokens
from compiler.documents.vector import cosine, fuse

# BM25 parameters. The defaults are the standard ones; the corpus is small
# enough that tuning them would be fitting the demo rather than measuring it.
K1 = 1.5
B = 0.75

FIELD_WEIGHTS = {
    "statement": 3.0,
    "actor": 1.0,
    "conditions": 2.0,
    "quote": 1.0,
    "title": 1.0,
}

UNIT_HOURS = {
    "hour": 1,
    "hours": 1,
    "working hour": 1,
    "working hours": 1,
    "day": 24,
    "days": 24,
    "week": 168,
    "weeks": 168,
    "month": 730,
    "months": 730,
    "year": 8760,
    "years": 8760,
}

WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
}
_NUMBER = r"\d+(?:[.,]\d+)?|" + "|".join(WORD_NUMBERS)
DURATION = re.compile(
    rf"(?<![\w.])({_NUMBER})\s*(working\s+)?(hours?|days?|weeks?|months?|years?)(?![\w])",
    re.IGNORECASE,
)

# A topic is a small, explicit vocabulary. It is not a classifier: it only
# labels the number so two documents can be compared on the same subject.
TOPICS = {
    "breach_notification": (
        "breach",
        "notify",
        "notification",
        "inform",
        "incident",
        "data loss event",
    ),
    "retention": ("retain", "retention", "delete", "deletion", "erasure", "erase", "destroy"),
    "audit": ("audit", "inspection", "inspect", "access to records"),
    "transfer": ("transfer", "transfers", "onward transfer"),
}


@dataclass
class Citation:
    claim_id: str
    doc_id: str
    title: str
    statement: str
    quote: str
    page: int | None
    section_path: list[str]
    url: str
    score: float = 0.0
    verdict: str = "ok"

    def label(self) -> str:
        bits = [self.title or self.doc_id]
        if self.page:
            bits.append(f"p. {self.page}")
        if self.section_path:
            bits.append(" > ".join(self.section_path))
        return ", ".join(bits)


@dataclass
class Tension:
    topic: str
    values: list[tuple[str, str]]  # (duration label, claim_id)
    reason: str


@dataclass
class Answer:
    question: str
    citations: list[Citation] = field(default_factory=list)
    tensions: list[Tension] = field(default_factory=list)

    @property
    def documents(self) -> list[str]:
        seen: list[str] = []
        for citation in self.citations:
            if citation.doc_id not in seen:
                seen.append(citation.doc_id)
        return seen

    def by_document(self) -> dict[str, list[Citation]]:
        groups: dict[str, list[Citation]] = {}
        for citation in self.citations:
            groups.setdefault(citation.doc_id, []).append(citation)
        return groups


def _claim_text(claim: dict) -> dict[str, str]:
    locator = ((claim.get("evidence") or [{}])[0]).get("locator") or {}
    quotes = " ".join((item.get("quote") or "") for item in claim.get("evidence") or [])
    return {
        "statement": claim.get("statement", ""),
        "actor": claim.get("actor", ""),
        "conditions": " ".join(claim.get("conditions") or []),
        "quote": quotes,
        "title": (claim.get("context") or {}).get("source", ""),
        "section": " ".join(str(p) for p in locator.get("section_path") or []),
    }


class Corpus:
    """An in-memory BM25 index over claims."""

    def __init__(
        self,
        claims: list[dict],
        documents: Iterable[dict] = (),
        verdicts: Iterable[dict] = (),
        include_unverified: bool = False,
    ) -> None:
        # The verifier is the only thing that knows whether a claim's evidence
        # supports it, so an answer must not present a claim it did not pass.
        # The filter runs before the index is built, so every index array stays
        # aligned with ``self.claims``; a caller that wants the audit surface
        # asks for it explicitly.
        self.verdicts = {row["claim_id"]: row["verdict"] for row in (verdicts or ())}
        self.include_unverified = include_unverified
        self.claims = [
            claim
            for claim in claims
            if include_unverified
            or not self.verdicts
            or self.verdicts.get(claim["claim_id"], "ok") == "ok"
        ]
        self.documents = {doc["doc_id"]: doc for doc in documents}
        self._by_id = {claim["claim_id"]: claim for claim in self.claims}
        # Set by ``enable_semantic``: the vectors and the model, or nothing.
        self._semantic: tuple[dict[str, list[float]], object] | None = None
        self.fields: list[dict[str, str]] = []
        self.tokens: list[list[str]] = []
        self.lengths: list[int] = []
        self.df: dict[str, int] = {}
        for claim in self.claims:
            text = _claim_text(claim)
            field_tokens = {name: tokens(value) for name, value in text.items()}
            weighted: list[str] = []
            for name, weight in FIELD_WEIGHTS.items():
                repeats = max(1, int(round(weight)))
                for _ in range(repeats):
                    weighted.extend(field_tokens.get(name, []))
            self.fields.append(text)
            self.tokens.append(weighted)
            self.lengths.append(max(1, len(weighted)))
            for term in set(weighted):
                self.df[term] = self.df.get(term, 0) + 1
        self.avg_length = (sum(self.lengths) / len(self.lengths)) if self.lengths else 0.0

    def _idf(self, term: str) -> float:
        total = len(self.claims)
        df = self.df.get(term, 0)
        return math.log(1 + (total - df + 0.5) / (df + 0.5))

    def enable_semantic(self, vectors: dict[str, list[float]], embedder) -> None:
        """Keep the vectors and the model; embedding one question is the only model call."""
        self._semantic = (vectors, embedder)

    def semantic_ranking(self, question: str, depth: int = 200) -> list[str]:
        """Claim ids by cosine to the question, best first.

        The model is called once per question, here; every later step works on
        ranks. ``depth`` bounds the work: beyond it a claim cannot win a fusion
        against a lexical hit anyway, so scoring the whole corpus would only
        cost time.
        """
        if self._semantic is None:
            return []
        vectors, embedder = self._semantic
        asked = embedder.encode_one(question)
        scored = [
            (claim_id, cosine(asked, vector))
            for claim_id, vector in vectors.items()
            if claim_id in self._by_id
        ]
        scored.sort(key=lambda item: (-item[1], item[0]))
        return [claim_id for claim_id, _ in scored[:depth]]

    def search(
        self,
        question: str,
        limit: int = 12,
        semantic_ranking: list[str] | None = None,
    ) -> list[Citation]:
        query = tokens(question)
        if not query or not self.claims:
            return []
        scores: list[float] = []
        for index, document_tokens in enumerate(self.tokens):
            counts: dict[str, int] = {}
            for term in document_tokens:
                counts[term] = counts.get(term, 0) + 1
            score = 0.0
            length = self.lengths[index]
            for term in query:
                frequency = counts.get(term, 0)
                if not frequency:
                    continue
                denominator = frequency + K1 * (1 - B + B * length / (self.avg_length or 1))
                score += self._idf(term) * frequency * (K1 + 1) / denominator
            scores.append(score)

        # Prefer a claim that answers the question to one that merely repeats a
        # word: require at least one content term from the question to appear.
        ranked = sorted(
            (index for index in range(len(scores)) if scores[index] > 0),
            key=lambda index: scores[index],
            reverse=True,
        )

        # Fusion happens before the cut and over the union of both rankings. A
        # claim the lexical pass cannot reach has zero BM25 score and is absent
        # from ``ranked``; if it were merged into a re-sorted ``ranked`` it would
        # never become a candidate, which is the defect this exists to fix.
        lexical = {self.claims[index]["claim_id"]: scores[index] for index in ranked}
        weight: dict[str, float] = {}
        if semantic_ranking:
            fused = fuse([list(lexical), semantic_ranking])
            weight = dict(fused)
            order = {claim_id: position for position, (claim_id, _) in enumerate(fused)}
            ranked = [
                index
                for index in range(len(self.claims))
                if self.claims[index]["claim_id"] in order
            ]
            ranked.sort(key=lambda index: order[self.claims[index]["claim_id"]])

        out: list[Citation] = []
        seen_statements: set[str] = set()
        for index in ranked[: max(limit * 4, limit)]:
            claim = self.claims[index]
            key = norm(claim.get("statement", "")).lower()
            if key in seen_statements:
                continue
            seen_statements.add(key)
            score = weight.get(claim["claim_id"], scores[index])
            out.append(self._citation(claim, score))
            if len(out) >= limit:
                break
        return out

    def _citation(self, claim: dict, score: float) -> Citation:
        evidence = claim.get("evidence") or [{}]
        first = evidence[0]
        locator = first.get("locator") or {}
        document = self.documents.get(claim["doc_id"], {})
        return Citation(
            claim_id=claim["claim_id"],
            doc_id=claim["doc_id"],
            title=document.get("title") or (claim.get("context") or {}).get("source", claim["doc_id"]),
            statement=claim.get("statement", ""),
            quote=first.get("quote", ""),
            page=locator.get("page"),
            section_path=list(locator.get("section_path") or []),
            url=locator.get("url") or document.get("url", ""),
            score=round(score, 4),
            verdict=self.verdicts.get(claim["claim_id"], "ok"),
        )


def durations(text: str) -> list[tuple[str, float]]:
    """``[(label, hours)]`` for every explicit duration in the text."""
    out: list[tuple[str, float]] = []
    for amount, working, unit in DURATION.findall(text or ""):
        if amount.lower() in WORD_NUMBERS:
            number = float(WORD_NUMBERS[amount.lower()])
        else:
            number = float(amount.replace(",", "."))
        key = unit.lower()
        hours = UNIT_HOURS.get(key)
        if hours is None:
            continue
        label = norm(f"{amount} {'working ' if working else ''}{key}")
        out.append((label, number * hours))
    return out


def topic_of(text: str) -> str | None:
    """The one topic the text is about, or ``None`` when it names several/none.

    Ambiguity is not guessed: a claim that mentions both a breach and a
    retention period is left out of the tension report rather than assigned.
    """
    said = " " + " ".join(tokens(text)) + " "
    found = [
        name
        for name, phrases in TOPICS.items()
        if any(f" {phrase} " in said for phrase in phrases)
    ]
    return found[0] if len(found) == 1 else None


def find_tensions(citations: list[Citation]) -> list[Tension]:
    """Durations on the same topic that disagree across two documents."""
    buckets: dict[str, list[tuple[str, float, str, str]]] = {}
    for citation in citations:
        topic = topic_of(" ".join([citation.statement, citation.quote]))
        if topic is None:
            continue
        found = durations(" ".join([citation.statement, citation.quote]))
        # One duration per claim: the first explicit one is the operative one.
        if not found:
            continue
        label, hours = found[0]
        buckets.setdefault(topic, []).append((label, hours, citation.claim_id, citation.doc_id))

    tensions: list[Tension] = []
    for topic, items in sorted(buckets.items()):
        distinct: dict[float, list[tuple[str, str]]] = {}
        for label, hours, claim_id, doc_id in items:
            distinct.setdefault(hours, []).append((label, f"{claim_id} ({doc_id})"))
        if len(distinct) < 2:
            continue
        # Two documents must be involved: a document contradicting itself is a
        # compile defect for the verifier, not a cross-document tension.
        docs = {doc_id for _, _, _, doc_id in items}
        if len(docs) < 2:
            continue
        values: list[tuple[str, str]] = []
        for hours in sorted(distinct):
            labels = distinct[hours]
            values.extend(labels)
        tensions.append(
            Tension(
                topic=topic,
                values=values,
                reason=(
                    f"{len(distinct)} different {topic.replace('_', ' ')} periods across "
                    f"{len(docs)} documents"
                ),
            )
        )
    return tensions


def ask(question: str, corpus: Corpus, limit: int = 12) -> Answer:
    # The model, when one is enabled, runs once per question, here: ``search``
    # only ever sees the resulting ranks.
    semantic = corpus.semantic_ranking(question) if tokens(question) else []
    citations = corpus.search(question, limit=limit, semantic_ranking=semantic)
    return Answer(question=question, citations=citations, tensions=find_tensions(citations))


def render_text(answer: Answer) -> str:
    """Plain-text rendering used by the CLI."""
    lines = [f"Question: {answer.question}", ""]
    groups = answer.by_document()
    for doc_id, citations in groups.items():
        lines.append(f"== {citations[0].title}  [{doc_id}]  ({len(citations)} claim(s))")
        for citation in citations:
            mark = "" if citation.verdict == "ok" else f"[{citation.verdict}] "
            lines.append(f"  {citation.claim_id}  {mark}{citation.statement}")
            where = citation.label()
            lines.append(f"      source: {where}")
            if citation.quote:
                lines.append(f"      quote: \"{citation.quote[:400]}\"")
        lines.append("")
    if answer.tensions:
        lines.append("Tensions in the corpus:")
        for tension in answer.tensions:
            lines.append(f"  {tension.topic}: {tension.reason}")
            for value, claim in tension.values:
                lines.append(f"    - {value}: {claim}")
        lines.append("")
    lines.append(f"Documents answering: {len(groups)} ({', '.join(groups)})")
    return "\n".join(lines)
