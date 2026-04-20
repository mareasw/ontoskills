# DocGraph v2: Skeleton & Hydration Architecture

**Date:** 2026-04-20
**Status:** Approved
**Depends on:** DocGraph v1 (current PR branch `feat/ontocore-content-extraction`)

## Problem

DocGraph v1 extracts structural content into a section tree using a flat parser. Coverage against 30 real skills (14 superpowers + 16 Anthropic) averages **54.7%** (char-level) / **57.6%** (line-level). The Anthropic skills average **42.1%**.

Gap breakdown across 30 skills:

| Gap Category | % of All Gaps | Root Cause |
|-------------|---------------|------------|
| Nested content inside list items | 30.3% | Parser extracts only first `inline` token per list item, ignores child blocks |
| Other text not captured | 40.3% | Various: bold standalone lines, short paragraphs, mixed content sections |
| Headings not counted in coverage | 13.5% | Section titles extracted but not counted in coverage metric |
| Bold inline lines | 6.1% | Lines like `**If tests fail:**` treated as paragraph but coverage doesn't match |
| Frontmatter YAML | 4.7% | `mdit-py-plugins` produces `front_matter` token but parser ignores it |
| HTML tags | 3.7% | `<HARD-GATE>`, `<test command>` etc. not extracted |

## Goal

≥95% line-level coverage across all 30 benchmark skills. Every non-blank line of a SKILL.md must be represented as a typed RDF node in the section tree. Zero content loss.

## Architecture: Skeleton & Hydration (Pointer-Based)

### Core Principle

Separate **content extraction** (deterministic, byte-perfect) from **structure building** (LLM-assisted, ID-only). The LLM never touches content — it only arranges block IDs into a tree.

### Phase 1a — Python Flat Extraction (deterministic, byte-perfect)

The `markdown-it-py` token stream is walked to extract ALL content into a flat list. Every block gets a unique `block_id`. Content is preserved byte-perfect via map slicing or `token.content`.

**New block types extracted:**

- `FlatBlock` wrapping every extracted element with `block_id`, `line_start`, `line_end`
- `FrontmatterBlock` — from `front_matter` token (YAML parsed into `properties: dict[str, str]`)
- `HTMLBlock` — from `html_block` token (raw HTML content)
- `HeadingBlock` — heading text + level (becomes Section in tree)

**Existing block types** (code_block, table, flowchart, template, paragraph, bullet_list, ordered_procedure, blockquote) extracted identically to v1, wrapped in FlatBlock.

**New extraction capabilities:**

- `_extract_frontmatter()` — captures `front_matter` token at start of token stream
- `_extract_html()` — captures `html_block` tokens
- `_extract_heading()` — captures heading text and level as a FlatBlock (currently headings are consumed by section grouping, not extracted as blocks)

**Key change in list extraction:** `_extract_bullet_list()` and `_extract_ordered_procedure()` now extract ALL tokens inside each list item — not just the first `inline`. If a list item contains nested code blocks, nested lists, or paragraphs, those are extracted as separate FlatBlocks with their own `block_id`s, but tagged with `parent_block_id` pointing to the list item.

Output: `list[FlatBlock]` where each block has full content, line range, and optional parent reference.

### Phase 1b — LLM Skeleton Building (ID-only, zero content)

The LLM receives a compact representation of all extracted blocks:

```
Extracted blocks from markdown:
- blk_0 (heading, level 1): "# DOCX creation..."
- blk_1 (paragraph): "A .docx file is a ZIP..."
- blk_2 (code_block, bash): 2 lines
- blk_3 (bullet_list): 4 items
- blk_4 (code_block, python): inside bullet item 2
- blk_5 (html_block): "<HARD-GATE>"
- blk_6 (frontmatter): "name: docx"
...
```

The LLM returns a JSON skeleton — only block IDs arranged in a tree:

```json
{
  "sections": [
    {
      "block_id": "blk_0",
      "children": [
        {
          "block_id": "blk_1",
          "children": []
        }
      ]
    }
  ],
  "list_items": {
    "blk_3": {
      "items": [
        { "text_block_id": "blk_3_item_0", "children": [] },
        { "text_block_id": "blk_3_item_1", "children": ["blk_4"] }
      ]
    }
  }
}
```

**LLM constraints:**
- Input contains only `block_id`, `block_type`, and a text preview (max 80 chars)
- Output contains only `block_id` references — zero content text
- Typical output: 1-5 KB for a 600-line skill
- LLM acts purely as a structural router

### Phase 1c — Python Hydration (deterministic)

Python receives the skeleton and hydrates it with the real Pydantic objects from Phase 1a:

1. Build `dict[block_id → FlatBlock]` index
2. Walk skeleton recursively
3. For heading nodes: create `Section(title=heading.text, level=heading.level, ...)`
4. For content nodes: extract the Pydantic object from FlatBlock
5. For list items with children: create `BulletItem(text=..., children=[hydrated children])`
6. Derive backward-compatible flat lists from tree walk

**Fallback:** If the LLM skeleton is malformed or missing blocks, Python falls back to the v1 deterministic tree builder (current `_build_section_tree`). This guarantees that even without LLM, extraction produces valid output at v1 coverage levels.

## Pydantic Models (schemas.py)

### New Models

```python
class FlatBlock(BaseModel):
    block_id: str
    block_type: str
    content: ContentBlock
    line_start: int
    line_end: int
    parent_block_id: str | None = None

class HTMLBlock(BaseModel):
    block_type: Literal["html_block"] = "html_block"
    content: str
    content_order: int

class FrontmatterBlock(BaseModel):
    block_type: Literal["frontmatter"] = "frontmatter"
    raw_yaml: str
    properties: dict[str, str] = Field(default_factory=dict)
    content_order: int

class HeadingBlock(BaseModel):
    block_type: Literal["heading"] = "heading"
    text: str
    level: int
    content_order: int
```

### Updated Models

```python
class BulletItem(BaseModel):
    text: str
    order: int
    children: list[ContentBlock] = Field(default_factory=list)  # NEW

class ProcedureStep(BaseModel):
    text: str
    position: int
    children: list[ContentBlock] = Field(default_factory=list)  # NEW
```

### Skeleton Models (LLM output)

```python
class SkeletonNode(BaseModel):
    block_id: str
    children: list["SkeletonNode"] = Field(default_factory=list)

class SkeletonListItem(BaseModel):
    text_block_id: str
    children: list[str] = Field(default_factory=list)  # block_ids

class DocumentSkeleton(BaseModel):
    sections: list[SkeletonNode]
    list_items: dict[str, list[SkeletonListItem]] = Field(default_factory=dict)
```

### Updated Discriminated Union

```python
ContentBlock = Annotated[
    Union[Paragraph, CodeBlock, MarkdownTable, FlowchartBlock,
          TemplateBlock, BulletListBlock, BlockQuoteBlock, OrderedProcedure,
          HTMLBlock, FrontmatterBlock],
    Field(discriminator="block_type")
]
```

## Ontology (core_ontology.py)

### New OWL Classes

```
oc:HTMLBlock
  +-- oc:htmlContent    (xsd:string)

oc:FrontmatterBlock
  +-- oc:rawYaml         (xsd:string)

oc:hasChild  (ObjectProperty, domain: BulletItem/ProcedureStep, range: open)
```

### Updated Properties

```
oc:hasChild  — BulletItem → ContentBlock, ProcedureStep → ContentBlock
oc:htmlContent — DatatypeProperty on HTMLBlock
oc:rawYaml — DatatypeProperty on FrontmatterBlock
```

## Serialization (serialization.py)

### New Serialization

- `HTMLBlock` → BNode with `oc:HTMLBlock` type + `oc:htmlContent`
- `FrontmatterBlock` → BNode with `oc:FrontmatterBlock` type + `oc:rawYaml`
- `BulletItem.children` → recursive serialization via `oc:hasChild`
- `ProcedureStep.children` → recursive serialization via `oc:hasChild`

## Parser Changes (content_parser.py)

### New Functions

- `_extract_flat_blocks(tokens, md_lines) → list[FlatBlock]` — main Phase 1a function
- `_extract_frontmatter(token) → FlatBlock | None`
- `_extract_html(token) → FlatBlock | None`
- `_extract_heading(token) → FlatBlock | None`
- Updated `_extract_bullet_list()` — extracts nested blocks inside list items
- Updated `_extract_ordered_procedure()` — extracts nested blocks inside list items

### List Item Nested Extraction

When processing a list item (`list_item_open` to `list_item_close`), the parser now:
1. Captures the first `inline` token as `text`
2. Walks remaining tokens inside the item
3. For each sub-block (fence, table, bullet_list, blockquote, paragraph): extracts as a FlatBlock with `parent_block_id` set to the list item's block_id

## Coverage Metric

### Line-Level Coverage Calculation

```
covered_lines = set of line numbers where:
  - line is inside a FlatBlock's line_start..line_end range
  - OR line contains a section title from a heading block

total_content_lines = count of lines where:
  - line.strip() is not empty
  - line.strip() is not purely "---", "***", or "___" (horizontal rule)

coverage = len(covered_lines) / total_content_lines * 100
```

### Target

≥95% across all 30 benchmark skills.

## SHACL Shapes (ontoskills.shacl.ttl)

New shapes:
- `HTMLBlockShape` — requires `htmlContent`
- `FrontmatterBlockShape` — requires `rawYaml`

## Benchmark Skills

30 skills for coverage testing:

**Superpowers (14):** brainstorming, dispatching-parallel-agents, executing-plans, finishing-a-development-branch, receiving-code-review, requesting-code-review, subagent-driven-development, systematic-debugging, test-driven-development, using-git-worktrees, using-superpowers, verification-before-completion, writing-plans, writing-skills

**Anthropic (16):** algorithmic-art, brand-guidelines, canvas-design, doc-coauthoring, docx, frontend-design, internal-comms, mcp-builder, pdf, pptx, skill-creator, slack-gif-creator, theme-factory, web-artifacts-builder, webapp-testing, xlsx

## Impact on Existing Code

| Component | Change |
|-----------|--------|
| `schemas.py` | New models (FlatBlock, HTMLBlock, FrontmatterBlock, HeadingBlock, SkeletonNode, DocumentSkeleton). Updated BulletItem/ProcedureStep with children. ContentBlock union → 10 types. |
| `content_parser.py` | New `_extract_flat_blocks()` as primary function. Updated list extraction with nested content. New extractors for frontmatter, HTML, heading. |
| `core_ontology.py` | New classes (HTMLBlock, FrontmatterBlock) + properties (htmlContent, rawYaml, hasChild) |
| `serialization.py` | Serialize children of list items recursively. New HTML/Frontmatter serialization. |
| `transformer.py` | New LLM prompt for skeleton building (Phase 1b). Hydration function (Phase 1c). |
| `prompts.py` | New prompt template for skeleton building with ID-only input/output |
| `ontoskills.shacl.ttl` | New SHACL shapes for HTMLBlock, FrontmatterBlock |
| `test_docgraph_coverage.py` | Line-level metric, benchmark against 30 skills, target ≥95% |

## Implementation Phases

| Phase | What | Key Files |
|-------|------|-----------|
| 1 | Pydantic models + discriminated union expansion | schemas.py |
| 2 | Ontology + SHACL for new classes | core_ontology.py, ontoskills.shacl.ttl |
| 3 | Parser: flat extraction with block_ids | content_parser.py |
| 4 | Parser: nested list item extraction | content_parser.py |
| 5 | LLM prompt for skeleton building | transformer.py, prompts.py |
| 6 | Python hydration function | content_parser.py or new hydration.py |
| 7 | Serialization of children + new types | serialization.py |
| 8 | Coverage metric + benchmark test | test_docgraph_coverage.py |
| 9 | End-to-end validation | compile real skills, verify ≥95% |
