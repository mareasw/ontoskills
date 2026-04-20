"""End-to-end coverage test: verify DocGraph captures ≥80% of markdown content."""
from compiler.content_parser import extract_structural_content


def test_coverage_on_ontomcp_driver_skill():
    """Test against a rich skill markdown with all block types."""
    md = """\
## OVERVIEW

The OntoSkills MCP server exposes a knowledge graph of compiled skills. This document teaches you how to use its 4 tools effectively.

> Clean code always looks like it was written by someone who cares.

## AVAILABLE MCP TOOLS

### 1. search_skills(query: string) -> Vec<SkillSearchResult>

Semantic search across all compiled skills. Returns matching skills with relevance indicators.

**When to use:** When you need to find skills that address a user's intent.

**Best practices:**
- Use natural language queries that describe the GOAL
- If results are sparse, try synonyms or broader terms
- Call this FIRST before any other MCP tool

### 2. get_skill_context(skill_id: string) -> SkillContextResult

Returns full details for a specific skill.

**Response structure:**

```json
{
  "skill_details": {"name": "..."},
  "payload": {"executor": "shell"}
}
```

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /health | Health check |
| POST | /skills | Create a skill |

## WORKFLOW

### Discovery Phase

1. Call `search_skills` with the user's intent
2. For each match, call `get_skill_context(skill_id)`
3. Select the best 1-3 candidates

### Execution Phase

4. Call `get_skill_context(skill_id, include_content=true)`
5. Follow ordered procedures if present

## COMMON MISTAKES TO AVOID

- **Skipping search_skills:** Don't guess skill names. Always search first.
- **Ignoring requiresState:** Executing a skill without its preconditions leads to failures.
- **Overlooking CRITICAL knowledge nodes:** These are hard constraints, not suggestions.

## CONTENT BLOCK TYPES

When include_content=true, responses may contain:
- **CodeExample**: Inline code with language, purpose
- **Table**: Markdown tables with raw source
- **Flowchart**: Graphviz or Mermaid diagrams
- **Template**: Reusable templates with variables
"""
    result = extract_structural_content(md)

    # Count sections
    total_sections = 0
    total_content = 0
    for s in result.sections:
        total_sections += 1
        total_content += len(s.content)
        for sub in s.subsections:
            total_sections += 1
            total_content += len(sub.content)

    # Verify structural elements captured
    assert total_sections >= 6, f"Expected ≥6 sections, got {total_sections}"
    assert total_content >= 10, f"Expected ≥10 content blocks, got {total_content}"

    # Verify specific block types
    all_blocks = []
    for s in result.sections:
        all_blocks.extend(s.content)
        for sub in s.subsections:
            all_blocks.extend(sub.content)

    block_types = [b.block_type for b in all_blocks]
    assert "paragraph" in block_types
    assert "bullet_list" in block_types
    assert "code_block" in block_types
    assert "table" in block_types
    assert "ordered_procedure" in block_types

    # Calculate character coverage
    extracted_chars = 0
    for b in all_blocks:
        if b.block_type == "paragraph":
            extracted_chars += len(b.text_content)
        elif b.block_type == "code_block":
            extracted_chars += len(b.content)
        elif b.block_type == "table":
            extracted_chars += len(b.markdown_source)
        elif b.block_type == "bullet_list":
            extracted_chars += sum(len(i.text) for i in b.items)
        elif b.block_type == "ordered_procedure":
            extracted_chars += sum(len(s.text) for s in b.items)
        elif b.block_type == "blockquote":
            extracted_chars += len(b.content)

    total_chars = len(md.strip())
    coverage = extracted_chars / total_chars * 100
    assert coverage >= 80, f"Coverage {coverage:.1f}% is below 80% threshold"


def test_empty_markdown_coverage():
    md = ""
    result = extract_structural_content(md)
    assert result.sections == []
    assert result.code_blocks == []
