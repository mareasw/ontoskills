"""Load bytes, produce paginated plain text.

The segmenter needs one thing from a source: text, with form-feed page breaks.
Every other format is reduced to that shape before segmentation, so the rest of
the pipeline does not branch on file type.

External tools are used deliberately and named in the error, not guessed at:
``pdftotext`` (poppler) for PDF, LibreOffice for DOCX/ODT. HTML is parsed in
process.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from compiler.documents.model import Document, SUPPORTED


class ExtractionError(RuntimeError):
    pass


def _need(tool: str, hint: str) -> str:
    found = shutil.which(tool)
    if not found:
        raise ExtractionError(f"{tool} not found: {hint}")
    return found


def _run(command: list[str], what: str) -> subprocess.CompletedProcess:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()[:400]
        raise ExtractionError(f"{what} failed: {detail}")
    return result


def pdf_text(path: Path, page_range: list[int] | None = None) -> str:
    tool = _need("pdftotext", "install poppler-utils (Debian/Ubuntu) or poppler (macOS)")
    command = [tool]
    start = 1
    if page_range:
        if len(page_range) != 2 or page_range[0] < 1 or page_range[1] < page_range[0]:
            raise ExtractionError(f"invalid page_range {page_range!r}; expected [first, last]")
        start, end = page_range
        command += ["-f", str(start), "-l", str(end)]
    command += [str(path), "-"]
    text = _run(command, f"pdftotext {path.name}").stdout
    if not text.strip():
        raise ExtractionError(
            f"{path.name}: no text layer; the PDF is scanned and needs OCR before ingest"
        )
    # A page range keeps the original page numbers: the gaps are form feeds, so
    # page 547 of the extract is page 547 of the source and a citation stays true.
    if start > 1:
        text = "\f" * (start - 1) + text
    return text


def _docx_txt(path: Path) -> str:
    soffice = _need(
        "soffice",
        "install LibreOffice (headless) to read DOCX/ODT; PDF and text need no converter",
    )
    with tempfile.TemporaryDirectory(prefix="ontoskills-docx-") as tmp:
        _run(
            [soffice, "--headless", "--convert-to", "txt:Text", "--outdir", tmp, str(path)],
            f"LibreOffice conversion of {path.name}",
        )
        target = Path(tmp) / f"{path.stem}.txt"
        if not target.exists():
            raise ExtractionError(f"{path.name}: LibreOffice produced no text file")
        return target.read_text(encoding="utf-8", errors="ignore").lstrip("\ufeff")


def _html_text(path: Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    try:
        from bs4 import BeautifulSoup
    except ImportError:  # pragma: no cover - exercised only without the extra
        return _html_text_stdlib(raw)

    soup = BeautifulSoup(raw, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "nav", "header", "footer", "aside", "form"]):
        tag.decompose()
    root = soup.find("main") or soup.find("article") or soup.body or soup
    # Site chrome that lives inside <main>: feedback widgets, breadcrumbs and
    # "was this page helpful" forms. They are not part of the document and can
    # only produce a junk claim, so they are removed before segmentation.
    chrome = re.compile(
        r"was this (article|page) helpful|article was (not )?helpful|give feedback"
        r"|you have accepted all cookies|reject optional cookies|skip to main content",
        re.IGNORECASE,
    )
    lines: list[str] = []
    for node in root.find_all(string=True):
        text = re.sub(r"\s+", " ", str(node)).strip()
        if text and not chrome.search(text):
            lines.append(text)
    return "\n".join(lines)


def _html_text_stdlib(raw: str) -> str:
    """Small fallback for environments without beautifulsoup4."""
    from html.parser import HTMLParser

    class Text(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.parts: list[str] = []
            self.skip = 0

        def handle_starttag(self, tag: str, attrs) -> None:
            if tag in {"script", "style", "nav", "header", "footer", "aside", "form"}:
                self.skip += 1
            elif tag in {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}:
                self.parts.append("\n")

        def handle_endtag(self, tag: str) -> None:
            if tag in {"script", "style", "nav", "header", "footer", "aside", "form"} and self.skip:
                self.skip -= 1
            elif tag in {"p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}:
                self.parts.append("\n")

        def handle_data(self, data: str) -> None:
            if not self.skip:
                self.parts.append(data)

    parser = Text()
    parser.feed(raw)
    return "\n".join(
        line.strip() for line in "".join(parser.parts).splitlines() if line.strip()
    )


def plain_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def extract(doc: Document) -> str:
    """Return the document's text with form-feed page breaks where known."""
    if doc.kind == "pdf":
        return pdf_text(doc.path, doc.page_range)
    if doc.kind == "docx":
        return _docx_txt(doc.path)
    if doc.kind == "html":
        return _html_text(doc.path)
    if doc.kind in {"text", "markdown"}:
        return plain_text(doc.path)
    kind = SUPPORTED.get(doc.path.suffix.lower(), "text")
    return extract(Document(**{**doc.__dict__, "kind": kind}))


def strip_pages(spans: list[dict], kind: str) -> list[dict]:
    """Remove the meaningless page 1 the segmenter assigns to unpaginated text."""
    if kind in {"pdf"}:
        return spans
    for span in spans:
        span["locator"].pop("page", None)
    return spans


def extract_corpus(docs: list[Document], text_dir: Path) -> dict[str, str]:
    """Extract every document, write ``text/<doc_id>.txt``, return the texts."""
    text_dir.mkdir(parents=True, exist_ok=True)
    texts: dict[str, str] = {}
    for doc in docs:
        text = extract(doc)
        if not text.strip():
            raise ExtractionError(f"{doc.path.name}: extractor returned no text")
        target = text_dir / f"{doc.doc_id}.txt"
        target.write_text(text, encoding="utf-8")
        doc.text_path = target
        texts[doc.doc_id] = text
    return texts
