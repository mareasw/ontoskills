import pytest
from pathlib import Path
from compiler.extractor import generate_skill_id, generate_qualified_skill_id, compute_skill_hash, generate_sub_skill_id


def test_generate_skill_id():
    assert generate_skill_id("DOCX-Engineering") == "docx-engineering"
    assert generate_skill_id("My_Awesome Skill!!!") == "my-awesome-skill"


def test_compute_skill_hash(tmp_path):
    skill_dir = tmp_path / "skill-a"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("content")
    hash_val = compute_skill_hash(skill_dir)
    assert isinstance(hash_val, str)
    assert len(hash_val) == 64


def test_generate_qualified_skill_id():
    assert generate_qualified_skill_id("obra/superpowers", "brainstorming") == "obra/superpowers/brainstorming"
    assert generate_qualified_skill_id("local", "my-skill") == "local/my-skill"
    assert generate_qualified_skill_id("vendor/author/pkg", "skill") == "vendor/author/pkg/skill"


def test_generate_sub_skill_id():
    # Basic case
    assert generate_sub_skill_id("obra/superpowers", "brainstorming", "planning.md") == "obra/superpowers/brainstorming/planning"

    # Filename with special chars
    assert generate_sub_skill_id("obra/superpowers", "brainstorming", "my-planning.md") == "obra/superpowers/brainstorming/my-planning"

    # Nested package
    assert generate_sub_skill_id("vendor/author", "skill", "sub.md") == "vendor/author/skill/sub"
