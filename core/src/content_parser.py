"""
Structural Content Parser.

Extracts code blocks, tables, flowcharts, ordered procedures, and templates
from markdown using markdown-it-py for deterministic, lossless parsing.
"""

import re

from compiler.schemas import (
    CodeBlock, ContentExtraction, FlowchartBlock,
    MarkdownTable, OrderedProcedure, ProcedureStep, TemplateBlock,
)


# Languages that are always CodeBlock (never checked for template patterns)
PROGRAMMING_LANGUAGES = frozenset({
    "python", "py", "bash", "sh", "shell", "zsh", "fish",
    "typescript", "ts", "javascript", "js", "jsx", "tsx",
    "go", "rust", "rs", "java", "c", "cpp", "cs", "ruby", "rb",
    "php", "swift", "kotlin", "kt", "scala", "r", "perl",
    "lua", "dart", "elixir", "erlang", "haskell", "hs",
    "sql", "graphql", "yaml", "yml", "json", "xml", "toml",
    "dockerfile", "makefile", "cmake", "nginx", "apache",
})

FLOWCHART_LANGUAGES = frozenset({"dot", "graphviz", "mermaid"})

NEUTRAL_LANGUAGES = frozenset({
    "text", "markdown", "md", "prompt", "jinja", "j2", "jinja2", "template", "",
})

_TEMPLATE_VAR_RE = re.compile(r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}')


def extract_structural_content(markdown: str) -> ContentExtraction:
    """Parse markdown and extract structural content blocks.

    Uses markdown-it-py for tokenization. Content is extracted via
    line-based slicing (map field) to guarantee byte-perfect fidelity.
    """
    from markdown_it import MarkdownIt
    from mdit_py_plugins.front_matter import front_matter_plugin

    md_it = MarkdownIt("commonmark", {"html": True}).enable("table")
    front_matter_plugin(md_it)
    tokens = md_it.parse(markdown)

    md_lines = markdown.splitlines(keepends=True)

    code_blocks: list[CodeBlock] = []
    tables: list[MarkdownTable] = []
    flowcharts: list[FlowchartBlock] = []
    procedures: list[OrderedProcedure] = []
    templates: list[TemplateBlock] = []

    i = 0
    while i < len(tokens):
        token = tokens[i]

        if token.type == "fence" and token.map:
            block = _classify_fence(token, md_lines)
            if isinstance(block, CodeBlock):
                code_blocks.append(block)
            elif isinstance(block, FlowchartBlock):
                flowcharts.append(block)
            elif isinstance(block, TemplateBlock):
                templates.append(block)

        elif token.type == "table_open" and token.map:
            table = _extract_table(token, tokens, i, md_lines)
            if table:
                tables.append(table)

        elif token.type == "ordered_list_open" and token.map:
            proc = _extract_ordered_procedure(token, tokens, i)
            if proc:
                procedures.append(proc)

        i += 1

    return ContentExtraction(
        code_blocks=code_blocks,
        tables=tables,
        flowcharts=flowcharts,
        procedures=procedures,
        templates=templates,
    )


def _slice_lines(md_lines: list[str], start: int, end: int) -> str:
    """Extract lines [start, end) from source, preserving exact formatting."""
    return "".join(md_lines[start:end])


def _classify_fence(token, md_lines: list[str]):
    """Classify a fence token as CodeBlock, FlowchartBlock, or TemplateBlock."""
    lang = (token.info or "").strip().split()[0] if token.info.strip() else ""
    lang_lower = lang.lower()

    if lang_lower in FLOWCHART_LANGUAGES:
        chart_type = "mermaid" if lang_lower == "mermaid" else "graphviz"
        source = _slice_lines(md_lines, token.map[0], token.map[1])
        return FlowchartBlock(source=source, chart_type=chart_type)

    if lang_lower in PROGRAMMING_LANGUAGES:
        content = _slice_lines(md_lines, token.map[0], token.map[1])
        return CodeBlock(
            language=lang_lower,
            content=content,
            source_line_start=token.map[0],
            source_line_end=token.map[1] - 1,
        )

    # Neutral or unknown language — check for template variables
    content = _slice_lines(md_lines, token.map[0], token.map[1])

    if lang_lower in NEUTRAL_LANGUAGES:
        vars_found = _TEMPLATE_VAR_RE.findall(content)
        if vars_found:
            return TemplateBlock(content=content, detected_variables=vars_found)

    return CodeBlock(
        language=lang_lower,
        content=content,
        source_line_start=token.map[0],
        source_line_end=token.map[1] - 1,
    )


def _extract_table(table_open_token, tokens, start_idx, md_lines):
    """Extract a markdown table via map slicing."""
    if not table_open_token.map:
        return None
    start, end = table_open_token.map
    raw_source = _slice_lines(md_lines, start, end)

    # Count data rows (skip header rows — those with th_open children)
    row_count = 0
    for j in range(start_idx, len(tokens)):
        t = tokens[j]
        if t.type == "table_close":
            break
        if t.type == "tr_open":
            # Check if next token is td_open (data) vs th_open (header)
            if j + 1 < len(tokens) and tokens[j + 1].type == "td_open":
                row_count += 1

    # Try to find caption from preceding line
    caption = None
    if start > 0:
        preceding_line = md_lines[start - 1].strip() if start - 1 < len(md_lines) else ""
        if preceding_line and not preceding_line.startswith("|"):
            caption = preceding_line.rstrip(":")

    return MarkdownTable(
        markdown_source=raw_source,
        caption=caption,
        row_count=row_count,
    )


def _extract_ordered_procedure(ol_open_token, tokens, start_idx):
    """Extract ordered list items as an OrderedProcedure."""
    items = []
    current_position = 0
    in_item = False

    for j in range(start_idx, len(tokens)):
        t = tokens[j]
        if t.type == "ordered_list_close":
            break
        if t.type == "list_item_open":
            current_position += 1
            in_item = True
        elif t.type == "list_item_close":
            in_item = False
        elif t.type == "inline" and in_item:
            items.append(ProcedureStep(text=t.content, position=current_position))

    if items:
        return OrderedProcedure(items=items)
    return None
