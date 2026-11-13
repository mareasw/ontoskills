"""Text normalisation shared by the document pipeline.

The verifier, the segmenter and the graph builder must agree on one definition
of "verbatim". It is the definition DocBench already uses: curly quotes and
dashes folded to ASCII, all whitespace collapsed to one space. A quote that is a
substring under this normalisation is the quote the source prints.
"""

from __future__ import annotations

import re

# Grammatical words. Kept here, next to ``tokens``, so the verifier and the
# deterministic answerer cannot drift on what counts as a content word. The
# Italian list is not a translation of the English one for its own sake: the
# first corpus this pipeline met outside DocBench was Italian, and a content
# word there was being counted against a statement for the crime of being an
# article. Words that are content in one language and grammar in the other
# ("come", "state", "pure", "era") are deliberately left out of the Italian
# list: removing them would weaken the English check.
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
    + """
    a ad al alla alle allo agli ai
    che chi cui ci si ne
    di del della delle dello degli dei dall dalla dalle dallo dagli dai
    da dal
    in nel nella nelle nello negli nei
    su sul sulla sulle sullo sugli sui
    con coi
    per
    tra fra
    e ed o od ma però se
    non né anche ancora già sempre mai più meno molto poco troppo
    il lo la i gli le un uno una
    è sono essere siano sia stato stata stati
    ha hanno avere avuto
    deve devono debbono può possono potrebbe dovrebbe
    questo questa questi queste quello quella quelli quelle
    loro suo sua suoi sue nostro nostra nostri nostre
    ogni qualche alcuni alcune alcuno alcuna
    tutti tutte tutto tutta altro altra altri altre
    stesso stessa stessi stesse proprio propria
    ciascuno ciascuna nessuno nessuna nulla niente qualcosa
    quale quali quanto quanta tanto tanta
    senza contro verso entro oltre durante secondo tramite mediante
    attraverso dopo prima sotto sopra fuori dentro accanto presso
    viene vengono
    dell all nell sull coll
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


# Letters and digits, in any script. The earlier ``[a-z0-9]`` silently dropped
# every accented letter, so an Italian "può" tokenised to "pu" and "qualità" to
# "qualit": the verifier then compared a truncated word on one side with the
# whole word on the other, and a correct claim looked paraphrased.
_WORD = re.compile(r"[^\W_]+", re.UNICODE)


def tokens(text: str) -> list[str]:
    """Lower-case alphanumeric tokens; one-letter tokens are noise."""
    return [t for t in _WORD.findall(str(text or "").lower()) if len(t) > 1]


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
    "prohibition": (
        "must not", "may not", "cannot", "can not", "shall not", "prohibited",
        # Italian: the negative modal, and the adjective/noun a code of ethics
        # uses for a ban ("è vietato", "divieto di"). The accent-free token is
        # not a variant here: tokens() keeps è, and one-letter tokens are noise,
        # so the phrase is matched without it.
        "non deve", "non devono", "non può", "non possono",
        "vietato", "vietata", "vietati", "vietate", "divieto",
    ),
    "obligation": (
        "must", "shall", "is required", "are required", "required to",
        "deve", "devono", "debbono", "tenuto", "tenuti", "tenuta", "tenute",
    ),
    "permission": (
        "may", "is permitted", "are permitted", "authorized",
        "può", "possono", "consentito", "consentita", "consentiti",
        "consentite", "autorizzato", "autorizzata",
    ),
}


def modal_classes(text: str) -> set[str]:
    """The modality classes the text states, by phrase (prohibition first).

    Shared by the deduplicator (never merge opposite modalities) and the
    verifier (report a statement that says permission where evidence says
    obligation). A negation outranks the modal it contains: "must not" also
    contains "must", and "non può" also contains "può", so a prohibition
    discards both the obligation and the permission reading.
    """
    said = " " + " ".join(tokens(text)) + " "
    found: set[str] = set()
    for name, phrases in MODAL_CLASSES.items():
        if any(f" {phrase} " in said for phrase in phrases):
            found.add(name)
    if "prohibition" in found:
        found.discard("obligation")
        found.discard("permission")
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
