"""Text normalisation shared by the document pipeline.

The verifier, the segmenter and the graph builder must agree on one definition
of "verbatim". It is the definition DocBench already uses: curly quotes and
dashes folded to ASCII, all whitespace collapsed to one space. A quote that is a
substring under this normalisation is the quote the source prints.
"""

from __future__ import annotations

import re

# Grammatical words. Kept here, next to ``tokens``, so the verifier and the
# deterministic answerer cannot drift on what counts as a content word.
STOPWORDS = frozenset(
    """
    a an the and or but if then than that this these those it its it's is are
    was were be been being do does did done have has had having shall must may
    can could would should will not no nor so such as at by for from in into of
    on onto over under with within without to up down out off again further
    once here there when where why how all any both each few more most other
    some only own same too very just also about above after before below
    between during through during against among within upon per via i we you
    he she they them their our your his her its who whom whose which what
    """.split()
)


def norm(text: str) -> str:
    """Fold punctuation and collapse whitespace, the DocBench convention."""
    text = str(text or "")
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def tokens(text: str) -> list[str]:
    """Lower-case alphanumeric tokens; one-letter tokens are noise."""
    return [t for t in re.findall(r"[a-z0-9]+", str(text or "").lower()) if len(t) > 1]


def statement_tokens(text: str) -> list[str]:
    """Content tokens: no grammatical words, no one-letter noise."""
    return [t for t in tokens(text) if t not in STOPWORDS]


def same_word(left: str, right: str) -> bool:
    """Share a stem of at least four characters, allowing two trailing letters.

    ``date``/``dated`` and ``party``/``parties`` match; ``claim``/``clause`` do
    not. This is inflection tolerance, not paraphrase.
    """
    if left == right:
        return True
    shortest = min(len(left), len(right))
    if shortest < 4:
        return False
    prefix = 0
    for a, b in zip(left, right):
        if a != b:
            break
        prefix += 1
    return prefix >= 4 and prefix >= shortest - 2


def attested(token: str, pool: list[str]) -> bool:
    return any(same_word(token, candidate) for candidate in pool)


MODAL_CLASSES = {
    "prohibition": ("must not", "may not", "cannot", "can not", "shall not", "prohibited"),
    "obligation": ("must", "shall", "is required", "are required", "required to"),
    "permission": ("may", "is permitted", "are permitted", "authorized"),
}


def modal_classes(text: str) -> set[str]:
    """The modality classes the text states, by phrase (prohibition first).

    Shared by the deduplicator (never merge opposite modalities) and the
    verifier (report a statement that says permission where evidence says
    obligation). Prohibition is tested first because "must not" also contains
    "must".
    """
    said = " " + " ".join(tokens(text)) + " "
    found: set[str] = set()
    for name, phrases in MODAL_CLASSES.items():
        if any(f" {phrase} " in said for phrase in phrases):
            found.add(name)
    if "prohibition" in found:
        found.discard("obligation")
    return found


def page_of_offset(text: str, offset: int) -> int:
    """1-based page number for a character offset in a form-feed text."""
    return text.count("\f", 0, max(0, offset)) + 1


def split_sentences(text: str, limit: int = 700) -> list[str]:
    """Split a block into sentence windows of at most roughly ``limit`` chars."""
    parts = re.split(r"(?<=[.;:])\s+", text)
    out: list[str] = []
    current = ""
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if current and len(current) + 1 + len(part) > limit:
            out.append(current)
            current = part
        else:
            current = f"{current} {part}".strip()
    if current:
        out.append(current)
    return out
