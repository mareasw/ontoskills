"""A static, read-only HTML view of a compiled corpus.

The view is the product's proof: every answer is a claim, every claim carries
the verbatim quote and the locator that produced it, and the source document is
one click away. There is no editing, no accept/reject, no chat: the artifact is
the compiled corpus, and the page only presents it.

The HTML is self-contained — no CDN, no fonts, no framework — so it can be
opened from disk, attached to an email, or served from anywhere. The only
script is the copy-citation button, and every page works without it.
"""

from __future__ import annotations

import html
from typing import Iterable

from compiler.documents.ask import Answer
from compiler.documents.store import KnowledgeBase


def esc(value: object) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


STYLE = """
:root {
  --ink: #14171c; --muted: #5b6472; --line: #dfe3e9; --paper: #fbfaf7;
  --panel: #ffffff; --accent: #1b4d3e; --warn: #8a4b12; --warn-bg: #fdf4e9;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--paper); color: var(--ink);
  font: 16px/1.55 "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif; }
header.masthead { padding: 2.4rem 1.5rem 1.6rem; border-bottom: 1px solid var(--line); }
.wrap { max-width: 60rem; margin: 0 auto; padding: 0 1.5rem; }
h1 { font-size: 1.9rem; line-height: 1.15; margin: 0 0 .4rem; letter-spacing: -.01em; }
h2 { font-size: 1.15rem; margin: 2.6rem 0 .8rem; letter-spacing: .01em; }
h3 { font-size: .95rem; margin: 1.6rem 0 .5rem; }
p.lede { color: var(--muted); margin: 0; max-width: 46rem; }
.stats { display: flex; flex-wrap: wrap; gap: 1.6rem; margin: 1.4rem 0 0; }
.stat b { display: block; font-size: 1.35rem; font-variant-numeric: tabular-nums; }
.stat span { color: var(--muted); font-size: .78rem; text-transform: uppercase; letter-spacing: .08em; }
section { padding: .2rem 0 1rem; }
.claim { background: var(--panel); border: 1px solid var(--line); border-radius: 6px;
  padding: 1rem 1.1rem; margin: .7rem 0; }
.claim .id { font: .74rem/1 ui-monospace, "SFMono-Regular", Menlo, monospace;
  color: var(--muted); letter-spacing: .04em; }
.claim .statement { margin: .35rem 0 .55rem; }
blockquote { margin: .55rem 0; padding: .1rem 0 .1rem .9rem; border-left: 2px solid var(--line);
  color: #2c323c; font-style: italic; }
.locator { font: .78rem/1.5 ui-monospace, "SFMono-Regular", Menlo, monospace; color: var(--muted);
  display: flex; flex-wrap: wrap; gap: .5rem; align-items: center; }
.locator a { color: var(--accent); }
button.copy { font: inherit; font-size: .72rem; padding: .18rem .5rem; border-radius: 4px;
  border: 1px solid var(--line); background: #fff; color: var(--muted); cursor: pointer; }
button.copy:hover { color: var(--accent); border-color: var(--accent); }
.tension { background: var(--warn-bg); border: 1px solid #f0dcc2; border-radius: 6px;
  padding: .8rem 1rem; margin: .8rem 0; }
.tension b { color: var(--warn); }
details.doc { border-top: 1px solid var(--line); padding: .7rem 0; }
details.doc summary { cursor: pointer; }
details.doc summary .meta { color: var(--muted); font-size: .85rem; margin-left: .4rem; }
table.meta { border-collapse: collapse; width: 100%; font-size: .85rem; margin: .6rem 0; }
table.meta td { border-top: 1px solid var(--line); padding: .35rem .5rem .35rem 0; vertical-align: top; }
table.meta td:first-child { color: var(--muted); white-space: nowrap; width: 9rem; }
footer { color: var(--muted); font-size: .8rem; padding: 2.4rem 0 3rem; border-top: 1px solid var(--line); margin-top: 2.4rem; }
@media (print) { button.copy { display: none; } body { background: #fff; } }
"""

SCRIPT = """
document.addEventListener('click', function (event) {
  var button = event.target.closest('button.copy');
  if (!button) return;
  var text = button.getAttribute('data-citation') || '';
  var done = function () { button.textContent = 'copied'; setTimeout(function () {
    button.textContent = 'copy citation'; }, 1400); };
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(done, function () { window.prompt('Citation', text); });
  } else { window.prompt('Citation', text); }
});
"""


def _citation_text(claim_id: str, title: str, page: int | None, section: list[str], url: str) -> str:
    where = [title]
    if page:
        where.append(f"p. {page}")
    if section:
        where.append(" > ".join(section))
    text = f"{' — '.join(where)} [{claim_id}]"
    return f"{text} {url}".strip()


def _claim_block(claim: dict, verdict: str | None, title: str) -> str:
    evidence = claim.get("evidence") or [{}]
    first = evidence[0]
    locator = first.get("locator") or {}
    page = locator.get("page")
    section = locator.get("section_path") or []
    url = locator.get("url") or ""
    citation = _citation_text(claim["claim_id"], title, page, section, url)
    badge = ""
    if verdict and verdict != "ok":
        badge = f' <span class="id">· verifier: {esc(verdict)}</span>'
    parts = [f'<div class="claim" id="c-{esc(claim["claim_id"])}">']
    parts.append(f'<div class="id">{esc(claim["claim_id"])} · {esc(claim["modality"])}{badge}</div>')
    parts.append(f'<div class="statement">{esc(claim["statement"])}</div>')
    parts.append(f'<blockquote>{esc(first.get("quote", ""))}</blockquote>')
    loc = []
    if url:
        loc.append(f'<a href="{esc(url)}" rel="noreferrer">{esc(title)}</a>')
    else:
        loc.append(esc(title))
    if page:
        loc.append(f"p.&nbsp;{esc(page)}")
    if section:
        loc.append(esc(" > ".join(section)))
    loc.append(
        '<button class="copy" data-citation="'
        + esc(citation)
        + '">copy citation</button>'
    )
    parts.append(f'<div class="locator">{" · ".join(loc)}</div>')
    parts.append("</div>")
    return "\n".join(parts)


def _answer_block(
    answer: Answer, claims: list[dict], verdicts: dict[str, str]
) -> str:
    by_id = {claim["claim_id"]: claim for claim in claims}
    parts = [f'<h2>{esc(answer.question)}</h2>']
    groups = answer.by_document()
    parts.append(
        f'<p class="lede">{len(answer.citations)} claim(s) from {len(groups)} '
        f'document(s): {esc(", ".join(groups))}.</p>'
    )
    for tension in answer.tensions:
        rows = "".join(
            f'<div class="locator">{esc(value)} — {esc(claim)}</div>' for value, claim in tension.values
        )
        parts.append(
            f'<div class="tension"><b>{esc(tension.topic.replace("_", " "))}</b> — '
            f'{esc(tension.reason)}{rows}</div>'
        )
    for doc_id, citations in groups.items():
        parts.append(f"<h3>{esc(citations[0].title)} <span class=\"id\">[{esc(doc_id)}]</span></h3>")
        for citation in citations:
            claim = by_id.get(citation.claim_id)
            if claim is not None:
                parts.append(_claim_block(claim, verdicts.get(claim["claim_id"]), citation.title))
    return "\n".join(parts)


def render_view(
    kb: KnowledgeBase,
    answers: Iterable[Answer] = (),
    questions: Iterable[str] = (),
) -> str:
    documents = kb.documents()
    claims = kb.claims()
    verifier = kb.verifier()
    manifest = kb.manifest()
    verdicts = {row["claim_id"]: row["verdict"] for row in verifier}
    titles = {doc["doc_id"]: doc.get("title", doc["doc_id"]) for doc in documents}
    claims_by_doc: dict[str, list[dict]] = {}
    for claim in claims:
        claims_by_doc.setdefault(claim["doc_id"], []).append(claim)

    counts: dict[str, int] = {}
    for row in verifier:
        counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1
    verdict_line = ", ".join(f"{value} {key}" for key, value in sorted(counts.items())) or "not run"

    parts = [
        "<!doctype html>",
        '<html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{esc(manifest.get('name', 'Knowledge base'))}</title>",
        f"<style>{STYLE}</style>",
        "</head><body>",
        '<header class="masthead"><div class="wrap">',
        f"<h1>{esc(manifest.get('name', 'Compiled corpus'))}</h1>",
        f'<p class="lede">{esc(manifest.get("description", "Every claim below carries the verbatim quote and the locator it came from."))}</p>',
        '<div class="stats">',
        f'<div class="stat"><b>{len(documents)}</b><span>documents</span></div>',
        f'<div class="stat"><b>{len(claims)}</b><span>claims</span></div>',
        f'<div class="stat"><b>{len(verifier)}</b><span>verified ({esc(verdict_line)})</span></div>',
        f'<div class="stat"><b>{esc(manifest.get("model", "—"))}</b><span>compile model</span></div>',
        "</div></div></header>",
        '<main class="wrap">',
    ]

    answers = list(answers)
    if answers:
        parts.append('<section id="answers">')
        parts.append("<h2>Questions</h2>")
        for answer in answers:
            parts.append(_answer_block(answer, claims, verdicts))
        parts.append("</section>")
    elif questions:
        parts.append('<section id="answers"><h2>Questions</h2><p class="lede">No answers were computed for this view.</p></section>')

    parts.append('<section id="documents">')
    parts.append("<h2>Corpus</h2>")
    for doc in documents:
        doc_id = doc["doc_id"]
        doc_claims = claims_by_doc.get(doc_id, [])
        meta = " · ".join(
            str(value)
            for value in (doc.get("doc_type"), doc.get("version"), doc.get("jurisdiction"), doc.get("licence"))
            if value
        )
        parts.append('<details class="doc">')
        parts.append(
            f'<summary><b>{esc(doc.get("title", doc_id))}</b> '
            f'<span class="meta">[{esc(doc_id)}] {esc(meta)} · {len(doc_claims)} claim(s)</span></summary>'
        )
        rows = [
            ("Source", f'<a href="{esc(doc.get("url", ""))}" rel="noreferrer">{esc(doc.get("url", ""))}</a>'),
            ("SHA-256", f'<code>{esc(doc.get("sha256", ""))}</code>'),
            ("Licence", esc(doc.get("licence", ""))),
        ]
        if doc.get("page_range"):
            rows.append(("Pages", esc("–".join(str(p) for p in doc["page_range"]))))
        parts.append('<table class="meta">')
        for key, value in rows:
            parts.append(f"<tr><td>{key}</td><td>{value}</td></tr>")
        parts.append("</table>")
        for claim in doc_claims:
            parts.append(_claim_block(claim, verdicts.get(claim["claim_id"]), titles.get(doc_id, doc_id)))
        parts.append("</details>")
    parts.append("</section>")
    parts.append("</main>")

    prompt_hash = manifest.get("prompt_hash", "")
    built = manifest.get("created", "")
    parts.append(
        '<footer class="wrap">Compiled with <code>ontocore ingest</code>. '
        f'Prompt <code>{esc(prompt_hash[:16])}</code>, built {esc(built)}. '
        "Read-only: every statement is a copy of, or a paraphrase over, the quoted span.</footer>"
    )
    parts.append(f"<script>{SCRIPT}</script>")
    parts.append("</body></html>")
    return "\n".join(parts)
