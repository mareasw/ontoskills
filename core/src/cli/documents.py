"""CLI commands for the document knowledge base: ``ingest``, ``ask``, ``view``.

These are thin: the pipeline lives in ``compiler.documents``; the commands load
credentials, print a cost estimate before spending anything, and write the
corpus directory. ``ask`` never calls a paid API: when the KB carries vectors it
may load the pinned local embedding model, offline, and fuses that ranking with
BM25; ``view`` is pure BM25.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from compiler.documents.ask import Corpus, ask as answer, render_text
from compiler.documents.compile import CompileOptions, compile_document
from compiler.documents.extract import ExtractionError, extract, strip_pages
from compiler.documents.model import load_corpus
from compiler.documents.prompt import PROMPT_HASH
from compiler.documents.segment import chunk, lead_ins, segment
from compiler.documents.sections import Breaks, apply_sections, clean_sections
from compiler.documents.store import KnowledgeBase
from compiler.documents.verify import summarise, verify_all
from compiler.documents.web import render_view

console = Console()

CHARS_PER_TOKEN = 3.8
# Output/input ratio measured on the accepted Phase 1 run (217,937 / 96,164).
OUTPUT_RATIO = 2.27


def load_env() -> None:
    """Load ``.env`` from the working directory or a parent, without overriding."""
    candidates = [Path.cwd() / ".env"]
    candidates += [parent / ".env" for parent in Path.cwd().resolve().parents]
    for path in candidates:
        if not path.exists():
            continue
        for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[len("export "):].strip()
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                os.environ.setdefault(key, value)
        return


def _manifest_path(source: Path, explicit: Path | None) -> Path | None:
    if explicit is not None:
        return explicit
    candidate = source / "manifest.json"
    return candidate if candidate.exists() else None


def _print_estimate(rows: list[dict], price_in: float, price_out: float) -> dict:
    table = Table(title="Estimate (no API calls)")
    table.add_column("doc")
    table.add_column("spans", justify="right")
    table.add_column("chunks", justify="right")
    table.add_column("prompt chars", justify="right")
    table.add_column("~in tok", justify="right")
    table.add_column("~out tok", justify="right")
    # Pages are what the reader of a legal PDF navigates by, and the only unit
    # that can be checked against the source without reading the token count.
    table.add_column("pages", justify="right")
    total_in = 0
    total_pages = 0
    for row in rows:
        table.add_row(
            row["doc_id"],
            str(row["spans"]),
            str(row["chunks"]),
            f"{row['chars']:,}",
            f"{row['tokens']:,}",
            f"{int(row['tokens'] * OUTPUT_RATIO):,}",
            "" if row.get("pages") is None else str(row["pages"]),
        )
        total_in += row["tokens"]
        total_pages += row["pages"] or 0
    console.print(table)
    out_tokens = int(total_in * OUTPUT_RATIO)
    cost = total_in / 1_000_000 * price_in + out_tokens / 1_000_000 * price_out
    console.print(
        f"Total: ~{total_in:,} input tokens, ~{out_tokens:,} output tokens, "
        f"{total_pages} PDF pages → ~${cost:.2f} at ${price_in}/M in, ${price_out}/M out."
    )
    console.print(
        "[dim]Estimate assumes 3.8 chars/token and the Phase 1 output ratio; "
        "the real number is only known after the run.[/dim]"
    )
    return {
        "input_tokens": total_in,
        "output_tokens": out_tokens,
        "pages": total_pages,
        "cost": round(cost, 2),
    }


@click.command("ingest")
@click.argument("source", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("-o", "--out", "out_dir", type=click.Path(path_type=Path), default=Path("kb"),
              help="Knowledge-base directory to write (default: ./kb)")
@click.option("-m", "--manifest", "manifest_file", type=click.Path(exists=True, dir_okay=False, path_type=Path),
              default=None, help="Corpus manifest (default: <source>/manifest.json)")
@click.option("--model", default=None, help="Model id (default: OPENAI_MODEL)")
@click.option("--base-url", default=None, help="OpenAI-compatible base URL (default: OPENAI_BASE_URL)")
@click.option("--estimate", is_flag=True, help="Print the token/cost estimate and stop")
@click.option("--dry-run", is_flag=True, help="Extract and segment, print the plan, write nothing")
@click.option("--chunk-size", default=15, show_default=True, type=int, help="Spans per model call")
@click.option("--overlap", default=2, show_default=True, type=int, help="Span overlap between chunks")
@click.option("--max-tokens", default=10000, show_default=True, type=int, help="Max tokens per reply")
@click.option("--concurrency", default=1, show_default=True, type=int, help="Parallel model calls")
@click.option("--resume", is_flag=True, help="Reuse cached replies for identical chunks")
@click.option("--no-split-truncated", is_flag=True,
              help="Do not halve a chunk whose reply hit --max-tokens; report it instead")
@click.option("--cache-dir", type=click.Path(path_type=Path), default=None,
              help="Chunk cache (default: <out>/cache)")
@click.option("--no-conflicts", is_flag=True, help="Skip the conflict pass")
@click.option("--price-in", default=0.15, show_default=True, type=float, help="USD per million input tokens")
@click.option("--price-out", default=0.60, show_default=True, type=float, help="USD per million output tokens")
@click.option("--question", "questions", multiple=True, help="Demo question to answer in the view (repeatable)")
@click.option("--questions-file", type=click.Path(exists=True, dir_okay=False, path_type=Path), default=None,
              help="One demo question per line")
@click.option("--name", default=None, help="Corpus name shown in the view")
@click.option("--semantic", is_flag=True,
              help="Embed every claim with the local MiniLM model (vectors.jsonl, no network)")
def ingest_cmd(source, out_dir, manifest_file, model, base_url, estimate, dry_run,
               chunk_size, overlap, max_tokens, concurrency, resume, cache_dir,
               no_conflicts, price_in, price_out, questions, questions_file, name,
               semantic, no_split_truncated):
    """Compile a folder of documents into a knowledge base.

    \b
    Example:
        ontocore ingest ./corpus -o ./kb --estimate
        ontocore ingest ./corpus -o ./kb --resume
        ontocore ask "How long does a party have to report a breach?" --kb ./kb
    """
    load_env()
    if questions_file:
        questions = tuple(questions) + tuple(
            line.strip() for line in questions_file.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        )

    model = model or os.environ.get("OPENAI_MODEL", "")
    base_url = base_url or os.environ.get("OPENAI_BASE_URL", "")
    api_key = os.environ.get("OPENAI_API_KEY", "")

    try:
        docs = load_corpus(source, _manifest_path(source, manifest_file))
    except (ValueError, FileNotFoundError) as exc:
        raise click.ClickException(str(exc))

    if any(doc.kind == "docx" and not doc.sha256 for doc in docs):
        console.print("[yellow]warning:[/yellow] manifest entries without SHA-256 cannot be checked")

    try:
        texts = {doc.doc_id: extract(doc) for doc in docs}
    except ExtractionError as exc:
        raise click.ClickException(str(exc))

    spans: dict[str, list[dict]] = {}
    rows: list[dict] = []
    for doc in docs:
        doc_spans = strip_pages(segment(texts[doc.doc_id], doc.segment_meta()), doc.kind)
        spans[doc.doc_id] = doc_spans
        chunks = chunk(doc_spans, chunk_size, overlap)
        chars = sum(len(span["paragraph"]) for span in doc_spans)
        rows.append(
            {
                "doc_id": doc.doc_id,
                "spans": len(doc_spans),
                "chunks": len(chunks),
                "chars": chars,
                "tokens": int(chars / CHARS_PER_TOKEN) + len(chunks) * 40,
                "pages": _page_count(texts[doc.doc_id]) if doc.kind == "pdf" else None,
                "text": texts[doc.doc_id],
                "spans_list": doc_spans,
            }
        )

    if estimate or dry_run:
        _print_estimate(rows, price_in, price_out)
        if dry_run:
            for row in rows:
                console.print(f"  {row['doc_id']}: {row['chunks']} chunk(s), {row['spans']} span(s)")
            console.print("[dim]Dry run: nothing written.[/dim]")
        return

    if not model:
        raise click.ClickException("no model: set OPENAI_MODEL or pass --model")
    if not base_url:
        raise click.ClickException("no base URL: set OPENAI_BASE_URL or pass --base-url")

    options = CompileOptions(
        model=model,
        base_url=base_url,
        api_key=api_key,
        chunk_size=chunk_size,
        overlap=overlap,
        max_tokens=max_tokens,
        conflicts=not no_conflicts,
        concurrency=max(1, concurrency),
        resume=resume,
        split_truncated=not no_split_truncated,
        price_in=price_in,
        price_out=price_out,
        cache_dir=cache_dir or (out_dir / "cache"),
    )

    started = time.time()
    all_claims: list[dict] = []
    all_spans: list[dict] = []
    all_rejected: list[dict] = []
    total_in = total_out = 0
    replayed_in = replayed_out = 0
    total_rejected_numbers = 0
    total_truncated = 0
    total_retried = 0
    total_localised = 0
    languages: dict[str, str] = {}
    failed: list[str] = []
    for doc, row in zip(docs, rows):
        with console.status(f"compiling {doc.doc_id} ({len(row['spans_list'])} spans)") as status:
            def progress(message: str, _status=status) -> None:
                _status.update(f"[yellow]{message}[/yellow]")

            breaks: Breaks = {}
            cleaned = clean_sections(row["spans_list"], row["text"], breaks)
            lead_map = lead_ins(cleaned)
            compiled = compile_document(
                doc, row["text"], row["spans_list"], options, progress, lead_map=lead_map
            )
        # The prompt above showed the model the raw headings, and the cache
        # fingerprint covers the text and the span ids, so the repair happens
        # only now: the reply is cached, the claims are built, and from here on
        # the artifact and the verifier see the section a reader would name.
        apply_sections(compiled.claims, cleaned, breaks, row["text"])
        compiled.spans = cleaned
        if compiled.stats.failed:
            # One unservable chunk must not block the rest of the corpus: the
            # cache keeps every reply that did arrive, so the next --resume
            # retries only what is missing. The run still exits non-zero.
            failed.append(doc.doc_id)
            console.print(
                f"  [red]{doc.doc_id}: {compiled.stats.failed} model call(s) failed; "
                "document skipped, rerun with --resume[/red]"
            )
            if compiled.stats.errors:
                # The reason, not just the count: a missing base URL showed up
                # here as twelve identical failures with nothing to act on.
                console.print(
                    f"    [red]first failure: {compiled.stats.errors[0][:300]}[/red]"
                )
            continue
        all_claims.extend(compiled.claims)
        all_spans.extend(compiled.spans)
        all_rejected.extend(compiled.rejected)
        total_rejected_numbers += compiled.stats.rejected_numbers
        total_truncated += compiled.stats.truncated
        total_retried += compiled.stats.retried
        total_localised += compiled.stats.localised
        if compiled.stats.language:
            languages[doc.doc_id] = compiled.stats.language
        total_in += compiled.stats.input_tokens
        total_out += compiled.stats.output_tokens
        replayed_in += compiled.stats.replayed_input_tokens
        replayed_out += compiled.stats.replayed_output_tokens
        cost = compiled.stats.cost(options)
        replayed = compiled.stats.replayed_cost(options)
        detail = ""
        if compiled.stats.retried:
            detail += f", {compiled.stats.retried} split"
        if compiled.stats.localised:
            detail += (
                f", {compiled.stats.localised} statement(s) rewritten in "
                f"{compiled.stats.language}"
            )
        if compiled.stats.localise_failed:
            detail += f", [red]{compiled.stats.localise_failed} language pass failed[/red]"
        if compiled.stats.truncated:
            detail += f", [red]{compiled.stats.truncated} truncated[/red]"
        if compiled.stats.replayed_input_tokens or compiled.stats.replayed_output_tokens:
            detail += f", ${replayed:.3f} replayed from cache"
        console.print(
            f"  {doc.doc_id}: {len(compiled.claims)} claim(s), "
            f"{compiled.stats.calls} call(s), {compiled.stats.cached} cached, "
            f"{compiled.stats.rejected} rejected, {compiled.stats.merged} merged"
            f"{detail}, ${cost:.3f}"
        )

    rows_verdicts = verify_all(all_claims, all_spans, texts)
    report = summarise(rows_verdicts)
    kb = KnowledgeBase(out_dir)
    kb.save_texts(texts)

    manifest = {
        "name": name or source.resolve().name,
        "description": f"{len(docs)} public documents, compiled into atomic claims with verbatim evidence.",
        "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model": model,
        "base_url": base_url,
        "prompt_hash": PROMPT_HASH,
        "chunk_size": chunk_size,
        "overlap": overlap,
        "documents": len(docs),
        "pages": sum(
            _page_count(texts[doc.doc_id]) for doc in docs if doc.kind == "pdf"
        ),
        "claims": len(all_claims),
        "verifier": report["by_verdict"],
        "truncated_calls": total_truncated,
        "retried_chunks": total_retried,
        # The language each document opens in, and how many statements were
        # rewritten to match it. A document that opens in an undecided paragraph
        # has no entry and nothing is rewritten.
        "languages": languages,
        "localised_statements": total_localised,
        # What this run paid, and what the cached replies cost when they were
        # first generated. A resumed build is not free and not a second bill.
        "cost_usd": round(total_in / 1_000_000 * price_in + total_out / 1_000_000 * price_out, 4),
        "tokens": {"input": total_in, "output": total_out},
        "replayed_cost_usd": round(
            replayed_in / 1_000_000 * price_in + replayed_out / 1_000_000 * price_out, 4
        ),
        "replayed_tokens": {"input": replayed_in, "output": replayed_out},
        "licences": sorted({doc.licence for doc in docs}),
        "elapsed_s": round(time.time() - started, 1),
    }
    rows_docs = []
    for doc in docs:
        payload = doc.to_dict()
        payload["claims"] = sum(1 for claim in all_claims if claim["doc_id"] == doc.doc_id)
        payload["pages"] = _page_count(texts[doc.doc_id])
        rows_docs.append(payload)

    kb.write(
        manifest=manifest,
        documents=rows_docs,
        spans=all_spans,
        claims=all_claims,
        verifier_rows=rows_verdicts,
        rejected_rows=all_rejected,
    )
    if semantic:
        # The vectors are a derived artifact like graph.ttl: same claims, same
        # text, so they are built after the KB is written and never call a model
        # over the network. A missing runtime is a hard error here, because the
        # operator asked for something the build did not produce.
        from compiler.documents.store import write_vectors

        try:
            from compiler.documents.vector import MODEL as EMBED_MODEL, embedder_for

            started_vectors = time.time()
            written = write_vectors(kb, all_claims, embedder_for(kb))
        except (ImportError, OSError, ValueError) as exc:
            raise click.ClickException(
                f"--semantic needs the local embedding runtime: {exc}"
            )
        console.print(
            f"vectors: {written} claim(s), model {EMBED_MODEL}, "
            f"{time.time() - started_vectors:.1f}s"
        )
    # The view is the audit surface: a claim the verifier did not pass is shown
    # with its badge, not hidden, so a reader can see what the gate caught.
    view_corpus = Corpus(
        all_claims, rows_docs, verdicts=rows_verdicts, include_unverified=True
    )
    answers = [answer(question, view_corpus) for question in questions] if questions else []
    kb.write_view(render_view(kb, answers=answers))

    console.print()
    console.print(f"[bold]{len(all_claims)}[/bold] claims in [bold]{len(docs)}[/bold] documents")
    console.print(f"verifier: {json.dumps(report['by_verdict'])}")
    if total_rejected_numbers:
        console.print(
            f"rejected: {total_rejected_numbers} claim(s) whose quantity is not in the "
            "evidence — see rejected.jsonl"
        )
    console.print(
        f"cost: ${manifest['cost_usd']:.3f} ({total_in:,} in / {total_out:,} out), "
        f"{manifest['elapsed_s']}s"
    )
    if replayed_in or replayed_out:
        console.print(
            f"[dim]replayed from cache: ${manifest['replayed_cost_usd']:.3f} "
            f"({replayed_in:,} in / {replayed_out:,} out), already paid[/dim]"
        )
    console.print(f"written: {out_dir} (view: {out_dir / 'view.html'})")
    if total_truncated:
        console.print(
            f"[red]{total_truncated} reply(ies) still hit --max-tokens after splitting: "
            "the claims they would have carried are missing from this build[/red]"
        )
        console.print(
            "  the replies that stopped cleanly are cached; rerun with --resume "
            "--chunk-size <smaller>, or raise --max-tokens"
        )
    if report["failures"]:
        console.print(
            f"[yellow]{len(report['failures'])} claim(s) not ok — see {out_dir / 'verifier.jsonl'}[/yellow]"
        )
        for row in report["failures"][:5]:
            console.print(f"  {row['claim_id']} {row['verdict']}: {'; '.join(row['reasons'])[:160]}")
    problems: list[str] = []
    if failed:
        problems.append(
            f"{', '.join(failed)}: model call(s) failed, knowledge base written without "
            "them; rerun with --resume"
        )
    if total_truncated:
        problems.append(
            f"{total_truncated} reply(ies) truncated: the knowledge base is incomplete; "
            "rerun with --resume --chunk-size <smaller> or raise --max-tokens"
        )
    if problems:
        raise click.ClickException("; ".join(problems))


def _page_count(text: str) -> int:
    return text.count("\f") + 1 if "\f" in text else 1


def _corpus(kb: KnowledgeBase, include_unverified: bool) -> Corpus:
    """The corpus `ask` answers from: verified claims only, unless asked otherwise."""
    verdicts = kb.verifier()
    if not verdicts:
        console.print(
            "[yellow]warning:[/yellow] no verifier.jsonl: unverified claims are shown unfiltered"
        )
    return Corpus(
        kb.claims(), kb.documents(), verdicts=verdicts, include_unverified=include_unverified
    )


def _enable_semantic(corpus: Corpus, kb: KnowledgeBase, asked: bool = False) -> None:
    """Add the embedding ranking when the KB has vectors and the runtime loads.

    Silent when the KB was simply built without ``--semantic``: that is a normal
    KB, not a failure. Anything else — no vectors but the flag was typed, a
    corpus in a language the model was not trained on, no torch, a vectors file
    from another model — is one dim line and BM25, because a missing or
    mismatched model must never turn a deterministic answer into an error.
    """
    vectors = kb.vectors()
    if not vectors:
        if asked:
            console.print("[dim]semantic ranking unavailable (no vectors.jsonl): BM25 only[/dim]")
        return
    languages = set((kb.manifest().get("languages") or {}).values())
    try:
        from compiler.documents.vector import LANGUAGES, MODEL, embedder_for, supports

        # Check the language before loading the model: there is no reason to
        # import torch to decide not to use it.
        if not supports(languages):
            console.print(
                f"[dim]semantic ranking skipped: {MODEL} is trained on "
                f"{', '.join(sorted(LANGUAGES))}, the corpus is "
                f"{', '.join(sorted(languages))}: BM25 only[/dim]"
            )
            return
        corpus.enable_semantic(vectors, embedder_for(kb), languages)
    except Exception as exc:  # sentence-transformers, torch, or a foreign model
        console.print(f"[dim]semantic ranking unavailable ({exc}): BM25 only[/dim]")


@click.command("ask")
@click.argument("question")
@click.option("-k", "--kb", "kb_dir", type=click.Path(exists=True, file_okay=False, path_type=Path),
              default=Path("kb"), show_default=True, help="Knowledge-base directory")
@click.option("-n", "--limit", default=12, show_default=True, type=int, help="Max citations")
@click.option("--json", "as_json", is_flag=True, help="Emit JSON instead of text")
@click.option("--include-unverified", is_flag=True,
              help="Also cite claims the verifier did not pass, marked with their verdict")
@click.option("--semantic/--no-semantic", "semantic", default=None,
              help="Fuse a local embedding ranking with BM25 (default: when the KB has vectors)")
def ask_cmd(question, kb_dir, limit, as_json, include_unverified, semantic):
    """Answer a question from a compiled corpus, with citations."""
    kb = KnowledgeBase(kb_dir)
    claims = kb.claims()
    if not claims:
        raise click.ClickException(f"{kb_dir}: no claims.jsonl; run `ontocore ingest` first")
    corpus = _corpus(kb, include_unverified)
    if semantic is not False:
        _enable_semantic(corpus, kb, asked=semantic is True)
    result = answer(question, corpus, limit=limit)
    if as_json:
        click.echo(json.dumps({
            "question": result.question,
            "documents": result.documents,
            "citations": [citation.__dict__ for citation in result.citations],
            "tensions": [tension.__dict__ for tension in result.tensions],
        }, ensure_ascii=False, indent=1))
        return
    click.echo(render_text(result))
    if len(result.documents) < 2:
        console.print(
            "[yellow]note:[/yellow] this answer cites one document; the demo's exit criterion "
            "is at least two per question."
        )


@click.command("view")
@click.option("-k", "--kb", "kb_dir", type=click.Path(exists=True, file_okay=False, path_type=Path),
              default=Path("kb"), show_default=True, help="Knowledge-base directory")
@click.option("-q", "--question", "questions", multiple=True, help="Question to render (repeatable)")
@click.option("--questions-file", type=click.Path(exists=True, dir_okay=False, path_type=Path), default=None)
@click.option("-o", "--out", type=click.Path(path_type=Path), default=None, help="Output HTML path")
@click.option("-n", "--limit", default=12, show_default=True, type=int, help="Max citations per question")
def view_cmd(kb_dir, questions, questions_file, out, limit):
    """Render (or re-render) the static view of a compiled corpus."""
    kb = KnowledgeBase(kb_dir)
    claims = kb.claims()
    if not claims:
        raise click.ClickException(f"{kb_dir}: no claims.jsonl; run `ontocore ingest` first")
    if questions_file:
        questions = tuple(questions) + tuple(
            line.strip() for line in questions_file.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        )
    corpus = _corpus(kb, include_unverified=True)
    answers = [answer(question, corpus, limit=limit) for question in questions]
    html = render_view(kb, answers=answers)
    target = out or (kb_dir / "view.html")
    target.write_text(html, encoding="utf-8")
    click.echo(f"wrote {target}")
    for result in answers:
        if len(result.documents) < 2:
            console.print(
                f"[yellow]note:[/yellow] '{result.question}' cites {len(result.documents)} document(s)."
            )
