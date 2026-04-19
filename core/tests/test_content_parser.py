"""Tests for the content_parser module."""
import pytest
from compiler.content_parser import extract_structural_content


class TestCodeBlockExtraction:
    def test_single_python_code_block(self):
        md = "# Title\n\n```python\nprint('hello')\n```\n"
        result = extract_structural_content(md)
        assert len(result.code_blocks) == 1
        assert result.code_blocks[0].language == "python"
        assert "print('hello')" in result.code_blocks[0].content

    def test_multiple_code_blocks(self):
        md = "```python\nx = 1\n```\n\nSome text.\n\n```bash\necho hello\n```\n"
        result = extract_structural_content(md)
        assert len(result.code_blocks) == 2
        assert result.code_blocks[0].language == "python"
        assert result.code_blocks[1].language == "bash"

    def test_no_code_blocks(self):
        md = "# Just a title\n\nSome text."
        result = extract_structural_content(md)
        assert result.code_blocks == []

    def test_code_block_content_preserved_exact(self):
        code = "def foo():\n    return 42\n"
        md = f"```python\n{code}```\n"
        result = extract_structural_content(md)
        assert len(result.code_blocks) == 1
        # content includes the full fenced block (opening + code + closing)
        assert "def foo():" in result.code_blocks[0].content
        assert "return 42" in result.code_blocks[0].content

    def test_empty_language_treated_as_text(self):
        md = "```\nsome text\n```\n"
        result = extract_structural_content(md)
        assert len(result.code_blocks) == 1
        assert result.code_blocks[0].language == ""


class TestTableExtraction:
    def test_single_table(self):
        md = "| Name | Type |\n|------|------|\n| foo  | bar  |\n| baz  | qux  |\n"
        result = extract_structural_content(md)
        assert len(result.tables) == 1
        assert result.tables[0].row_count == 2
        assert "Name" in result.tables[0].markdown_source

    def test_table_raw_markdown_preserved(self):
        md = "| a | b |\n|---|---|\n| 1 | 2 |\n"
        result = extract_structural_content(md)
        assert len(result.tables) == 1
        assert result.tables[0].markdown_source.startswith("| a | b |")

    def test_no_tables(self):
        md = "# Title\n\nJust text."
        result = extract_structural_content(md)
        assert result.tables == []


class TestFlowchartExtraction:
    def test_graphviz_flowchart(self):
        md = "```dot\ndigraph {\n    A -> B -> C\n}\n```\n"
        result = extract_structural_content(md)
        assert len(result.flowcharts) == 1
        assert result.flowcharts[0].chart_type == "graphviz"
        assert "digraph" in result.flowcharts[0].source

    def test_mermaid_flowchart(self):
        md = "```mermaid\ngraph TD\n    A --> B\n```\n"
        result = extract_structural_content(md)
        assert len(result.flowcharts) == 1
        assert result.flowcharts[0].chart_type == "mermaid"

    def test_no_flowcharts(self):
        md = "```python\nprint('hi')\n```\n"
        result = extract_structural_content(md)
        assert result.flowcharts == []


class TestOrderedProcedureExtraction:
    def test_numbered_list(self):
        md = "1. First step\n2. Second step\n3. Third step\n"
        result = extract_structural_content(md)
        assert len(result.procedures) == 1
        assert len(result.procedures[0].items) == 3
        assert result.procedures[0].items[0].position == 1
        assert result.procedures[0].items[0].text == "First step"
        assert result.procedures[0].items[2].position == 3

    def test_no_ordered_lists(self):
        md = "- bullet one\n- bullet two\n"
        result = extract_structural_content(md)
        assert result.procedures == []


class TestTemplateExtraction:
    def test_template_with_variables(self):
        md = "```text\nHello {name}, your order {order_id} is ready.\n```\n"
        result = extract_structural_content(md)
        assert len(result.templates) == 1
        assert "name" in result.templates[0].detected_variables
        assert "order_id" in result.templates[0].detected_variables

    def test_python_fstring_not_template(self):
        """Python code with f-string must be CodeBlock, not Template."""
        md = '```python\nname = "world"\nprint(f"Hello {name}")\n```\n'
        result = extract_structural_content(md)
        assert len(result.templates) == 0
        assert len(result.code_blocks) == 1
        assert result.code_blocks[0].language == "python"

    def test_js_template_literal_not_template(self):
        """JavaScript with template literals must be CodeBlock."""
        md = '```javascript\nconst name = "world";\nconsole.log(`Hello ${name}`);\n```\n'
        result = extract_structural_content(md)
        assert len(result.templates) == 0
        assert len(result.code_blocks) == 1

    def test_empty_fence_with_vars_is_template(self):
        md = "```\nUse {tool} to {action}.\n```\n"
        result = extract_structural_content(md)
        assert len(result.templates) == 1
        assert "tool" in result.templates[0].detected_variables
