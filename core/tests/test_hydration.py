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


class TestHydration:
    def _make_blocks(self, md):
        from compiler.content_parser import extract_flat_blocks
        return extract_flat_blocks(md)

    def test_hydrate_simple_sections(self):
        from compiler.transformer import hydrate_skeleton
        blocks = self._make_blocks("## Overview\n\nIntro text.\n\n## Details\n\nDetail text.\n")
        index = {b.block_id: b for b in blocks}
        skeleton = DocumentSkeleton(
            sections=[
                {"block_id": blocks[0].block_id, "children": [{"block_id": blocks[1].block_id}]},
                {"block_id": blocks[2].block_id, "children": [{"block_id": blocks[3].block_id}]},
            ],
        )
        sections = hydrate_skeleton(skeleton, index)
        assert len(sections) == 2
        assert sections[0].title == "Overview"
        assert sections[0].level == 2
        assert len(sections[0].content) == 1
        assert sections[0].content[0].block_type == "paragraph"

    def test_hydrate_nested_sections(self):
        from compiler.transformer import hydrate_skeleton
        blocks = self._make_blocks("## Parent\n\nText.\n\n### Child\n\nChild text.\n")
        index = {b.block_id: b for b in blocks}
        parent_id = [b.block_id for b in blocks if b.block_type == "heading" and b.content.level == 2][0]
        child_id = [b.block_id for b in blocks if b.block_type == "heading" and b.content.level == 3][0]
        parent_para = [b.block_id for b in blocks if b.block_type == "paragraph"][0]
        child_para = [b.block_id for b in blocks if b.block_type == "paragraph" and b.content.text_content != "Text."][0]
        skeleton = DocumentSkeleton(
            sections=[{
                "block_id": parent_id,
                "children": [
                    {"block_id": parent_para},
                    {"block_id": child_id, "children": [{"block_id": child_para}]},
                ],
            }],
        )
        sections = hydrate_skeleton(skeleton, index)
        assert len(sections) == 1
        assert len(sections[0].subsections) == 1
        assert sections[0].subsections[0].title == "Child"

    def test_fallback_to_v1_on_empty_skeleton(self):
        from compiler.transformer import hydrate_skeleton
        blocks = self._make_blocks("## Section\n\nText.\n")
        index = {b.block_id: b for b in blocks}
        skeleton = DocumentSkeleton(sections=[])  # Empty skeleton
        sections = hydrate_skeleton(skeleton, index, markdown="## Section\n\nText.\n")
        assert len(sections) == 1  # Falls back to v1 builder
        assert sections[0].title == "Section"

    def test_hydrate_with_html_and_frontmatter(self):
        from compiler.transformer import hydrate_skeleton
        md = "---\nname: test\n---\n\n## Section\n\nText.\n\n<div>HTML</div>\n"
        blocks = self._make_blocks(md)
        index = {b.block_id: b for b in blocks}
        fm_id = [b.block_id for b in blocks if b.block_type == "frontmatter"][0]
        heading_id = [b.block_id for b in blocks if b.block_type == "heading"][0]
        para_id = [b.block_id for b in blocks if b.block_type == "paragraph"][0]
        html_id = [b.block_id for b in blocks if b.block_type == "html_block"][0]
        skeleton = DocumentSkeleton(
            sections=[
                {"block_id": fm_id, "children": []},
                {"block_id": heading_id, "children": [
                    {"block_id": para_id},
                    {"block_id": html_id},
                ]},
            ],
        )
        sections = hydrate_skeleton(skeleton, index)
        assert len(sections) == 2
        assert sections[0].content[0].block_type == "frontmatter"
        assert sections[1].content[1].block_type == "html_block"


class TestSkeletonNeverLosesContent:
    """A skeleton that does not account for every block must be refused.

    Skipping the node instead produced a document that parsed fine and was
    simply missing its preamble — the one failure mode no verifier can see.
    """

    def _blocks(self, md):
        from compiler.content_parser import extract_flat_blocks
        return extract_flat_blocks(md)

    def test_an_invented_block_id_is_refused(self):
        from compiler.transformer import SkeletonIncomplete, hydrate_skeleton

        blocks = self._blocks("Preamble text.\n\n## First Section\n\nSection text.\n")
        index = {b.block_id: b for b in blocks}
        heading = [b.block_id for b in blocks if b.block_type == "heading"][0]
        # What a real model answers: the prompt says a preamble is a "block_id,
        # no heading", and the model writes the literal name instead of an id.
        skeleton = DocumentSkeleton(
            sections=[
                {"block_id": "preamble", "children": []},
                {"block_id": heading, "children": []},
            ],
        )
        with pytest.raises(SkeletonIncomplete) as exc:
            hydrate_skeleton(skeleton, index)
        assert exc.value.block_ids == ["preamble"]

    def test_a_missing_child_id_is_refused(self):
        from compiler.transformer import SkeletonIncomplete, hydrate_skeleton

        blocks = self._blocks("## Overview\n\nIntro text.\n")
        index = {b.block_id: b for b in blocks}
        heading = [b.block_id for b in blocks if b.block_type == "heading"][0]
        skeleton = DocumentSkeleton(
            sections=[{"block_id": heading, "children": [{"block_id": "blk_999"}]}]
        )
        with pytest.raises(SkeletonIncomplete):
            hydrate_skeleton(skeleton, index)

    def test_a_block_the_skeleton_never_mentions_is_refused(self):
        """Omitting a paragraph loses it just as surely as naming a bad id."""
        from compiler.transformer import SkeletonIncomplete, hydrate_skeleton

        blocks = self._blocks("## Overview\n\nIntro text.\n\n## Details\n\nDetail text.\n")
        index = {b.block_id: b for b in blocks}
        headings = [b.block_id for b in blocks if b.block_type == "heading"]
        skeleton = DocumentSkeleton(
            sections=[{"block_id": headings[0], "children": []}]
        )
        with pytest.raises(SkeletonIncomplete):
            hydrate_skeleton(skeleton, index)

    def test_the_parser_keeps_the_preamble_when_the_skeleton_is_incomplete(self, monkeypatch):
        """End to end: a bad skeleton degrades to the deterministic tree."""
        import json
        import types

        import compiler.llm as llm

        md = "Preamble text.\n\n## First Section\n\nSection text.\n"
        blocks = self._blocks(md)
        heading = [b.block_id for b in blocks if b.block_type == "heading"][0]
        skeleton = {
            "sections": [
                {"block_id": "preamble", "children": []},
                {"block_id": heading, "children": []},
            ]
        }
        monkeypatch.setattr(llm, "api_key", lambda: "test-key")
        monkeypatch.setattr(
            llm,
            "chat",
            lambda **kwargs: types.SimpleNamespace(text=json.dumps(skeleton)),
        )

        from compiler.content_parser import extract_structural_content

        result = extract_structural_content(md)
        assert len(result.sections) == 2
        assert result.sections[0].title == ""
        assert "Preamble text" in result.sections[0].content[0].text_content
        assert result.sections[1].title == "First Section"
