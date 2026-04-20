"""Tests for skeleton building (Phase 1b) and hydration (Phase 1c)."""
import pytest
from compiler.schemas import (
    DocumentSkeleton, FlatBlock, HeadingBlock, Paragraph,
    CodeBlock, Section, HTMLBlock, FrontmatterBlock,
    BulletListBlock, BulletItem, OrderedProcedure, ProcedureStep,
)


class TestSkeletonBuilding:
    def test_build_skeleton_prompt_format(self):
        from compiler.content_parser import extract_flat_blocks
        from compiler.prompts import build_skeleton_prompt
        md = "## Section\n\nParagraph text.\n\n```python\nx=1\n```\n"
        blocks = extract_flat_blocks(md)
        prompt = build_skeleton_prompt(blocks)
        assert "blk_0" in prompt
        assert "heading" in prompt
        assert "paragraph" in prompt
        assert "code_block" in prompt

    def test_skeleton_prompt_max_80_chars_preview(self):
        from compiler.content_parser import extract_flat_blocks
        from compiler.prompts import build_skeleton_prompt
        long_text = "A" * 200
        md = f"## Section\n\n{long_text}\n"
        blocks = extract_flat_blocks(md)
        prompt = build_skeleton_prompt(blocks)
        for line in prompt.split("\n"):
            if "blk_" in line and ":" in line:
                preview = line.split(":", 2)[-1].strip()
                assert len(preview) <= 82  # 80 + quotes
