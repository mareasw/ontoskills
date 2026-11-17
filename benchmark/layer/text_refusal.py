"""Does a free-text answer decline to answer?

Our own system records a refusal structurally: no citation, no answer. The two
graph frameworks return prose, so their refusal has to be read out of the text,
and the reading is a heuristic. That is stated rather than hidden: the raw answer
is kept in the run file next to the flag, so anyone can audit the classification,
and the same function is applied to every prose system — a pattern that only
matched one system's phrasing would be a thumb on the scale.

The patterns are deliberately few and specific. "It is not stated in the
documents" is a refusal; "the limit is not 10 MiB" is an answer, which is why
`not stated` is matched with its subject and a bare `not` never is.
"""

from __future__ import annotations

import re

PATTERNS = (
    r"\bi (?:do not|don't) know\b",
    r"\b(?:cannot|can ?not|can't|unable to) (?:answer|determine|find|say|tell|confirm)\b",
    r"\bcould not (?:answer|determine)\b",
    r"\bcould not find (?:any |the |an? )?(?:information|relevant|mention|details?)\b",
    r"\bno (?:relevant |specific |such )?information\b",
    r"\bnot (?:enough|sufficient) information\b",
    r"\b(?:do not|don't) have (?:enough|sufficient) information\b",
    r"\b(?:is|are|was|were) not (?:stated|mentioned|specified|provided|included|available)\b",
    r"\bdoes not (?:contain|mention|specify|provide|include|state)\b",
    r"\bthe (?:provided |given )?(?:documents?|context|corpus|passages?)\b[^.]{0,40}\b(?:do not|does not|don't)\b",
    r"\bno (?:mention|reference) of\b",
    r"\bunanswerable\b",
)

_COMPILED = tuple(re.compile(pattern, re.IGNORECASE) for pattern in PATTERNS)

# A model that writes `don’t` with U+2019 has declined exactly as much as one that
# writes `don't`. The 200 GraphRAG answers of the pilot use the curly form, and
# reading them as ASCII only would have counted every one of those refusals as a
# wrong answer instead of as an abstention — a fairness defect in one direction.
_APOSTROPHES = str.maketrans({"\u2019": "'", "\u2018": "'", "\u02bc": "'"})


def looks_like_refusal(text: str) -> bool:
    """True when the text says, in so many words, that it cannot answer."""
    cleaned = (text or "").strip().translate(_APOSTROPHES)
    if not cleaned:
        return True
    return any(pattern.search(cleaned) for pattern in _COMPILED)
