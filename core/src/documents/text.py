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


# The words a text cannot borrow from the other language. Only function words
# are here, and only ones that are unambiguous in both directions: "in" is
# Italian as well as English and "it" is an e-mail address, so neither can say
# what a text is written in. Content words are open-class and cannot be listed.
ITALIAN_MARKERS = frozenset(
    """
    il lo la gli le un una del della delle dello degli dei di che sono non per
    con nel nella nelle nello negli nei alla alle agli al allo dall dalla dalle
    dallo dagli dai sul sulla sulle sullo sugli sui tra fra questo questa questi
    queste quello quella come anche più deve devono può possono essere stato
    stata stati state ha hanno loro suo sua suoi sue nostro nostra ogni tutti
    tutte tutto tutta altro altra altri altre stesso stessa senza contro verso
    entro oltre secondo tramite mediante attraverso dopo prima sotto sopra
    fuori dentro presso viene vengono dell all nell sull sia siano avuto
    """.split()
)
ENGLISH_MARKERS = frozenset(
    """
    the of and to is are was were be been being that this these those its with
    for from by at as not shall must may can will would should has have had they
    their them which who whom what there here than then such also any all each
    other same both more most only over under between during or
    """.split()
)
LANGUAGE_NAMES = {"it": "Italian", "en": "English"}


def _marker_count(text: str, table: frozenset[str]) -> int:
    """Marker words printed in lower case.

    Case is part of the signal: "Is." in "Via G. Porzio Is. G7" is the
    abbreviation for *Isola*, while the English verb "is" is printed in lower
    case inside a sentence. An all-capitals line has no markers and decides
    nothing.
    """
    return sum(
        1
        for word in _WORD.findall(str(text or ""))
        if len(word) > 1 and word == word.lower() and word in table
    )


def language_of(text: str) -> str | None:
    """``"it"``, ``"en"`` or ``None`` when the text does not say.

    A margin, not a count: a sentence is English when its English function words
    outnumber the Italian ones, and the other way round. A text with no marker,
    or with both in similar numbers, is undecided and must not be rewritten.
    """
    words = tokens(text)
    if len(words) < 4:
        return None
    italian = _marker_count(text, ITALIAN_MARKERS)
    english = _marker_count(text, ENGLISH_MARKERS)
    if italian >= 2 * english + 1:
        return "it"
    if english >= 2 * italian + 1:
        return "en"
    return None


# A page label, an address or a form field is not prose: "Via G. Porzio Is. G7"
# has an "is" in it and no sentence. The language of a document is the language
# of its opening prose paragraph — the way a reader decides in one glance — and
# the minimum length is what keeps a heading or an address from deciding.
DOCUMENT_MIN_WORDS = 8


def document_language(paragraphs: list[str]) -> str | None:
    """The language of the first paragraph long enough to be prose and decided."""
    for paragraph in paragraphs:
        if len(tokens(paragraph)) < DOCUMENT_MIN_WORDS:
            continue
        language = language_of(paragraph)
        if language:
            return language
    return None


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
