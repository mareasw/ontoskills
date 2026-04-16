from compiler.extractor import (
    generate_skill_id,
    generate_qualified_skill_id,
    compute_skill_hash,
    generate_sub_skill_id,
    compute_sub_skill_hash,
    normalize_package_id,
    resolve_package_id,
    _is_author_dir,
)


def test_normalize_package_id():
    # Already normalized
    assert normalize_package_id("obra/superpowers") == "obra/superpowers"
    assert normalize_package_id("local") == "local"

    # NPM scoped package
    assert normalize_package_id("@scope/package-name") == "scope/package-name"

    # Uppercase
    assert normalize_package_id("MyCompany/MyPackage") == "mycompany/mypackage"

    # Dots and special chars
    assert normalize_package_id("my.company/my.package") == "my-company/my-package"
    assert normalize_package_id("my_company/my_package") == "my-company/my-package"

    # Spaces
    assert normalize_package_id("My Company/My Package") == "my-company/my-package"

    # Multiple slashes (nested packages)
    assert normalize_package_id("owner/repo/pkg") == "owner/repo/pkg"

    # Mixed issues
    assert normalize_package_id("@MyScope/My.Package") == "myscope/my-package"

    # Empty segments fall back to local
    assert normalize_package_id("///") == "local"
    assert normalize_package_id("") == "local"


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
    assert generate_qualified_skill_id("owner/repo/pkg", "skill") == "owner/repo/pkg/skill"


def test_generate_sub_skill_id():
    # Basic case
    assert generate_sub_skill_id("obra/superpowers", "brainstorming", "planning.md") == "obra/superpowers/brainstorming/planning"

    # Filename with special chars
    assert generate_sub_skill_id("obra/superpowers", "brainstorming", "my-planning.md") == "obra/superpowers/brainstorming/my-planning"

    # Nested package
    assert generate_sub_skill_id("owner/repo", "skill", "sub.md") == "owner/repo/skill/sub"


def test_resolve_package_id_with_manifest(tmp_path):
    from compiler.extractor import resolve_package_id

    # Create skill directory with package.json
    skill_dir = tmp_path / "skills" / "brainstorming"
    skill_dir.mkdir(parents=True)

    package_json = tmp_path / "skills" / "package.json"
    package_json.write_text('{"name": "obra/superpowers", "version": "1.0.0"}')

    result = resolve_package_id(skill_dir)
    assert result == "obra/superpowers"


def test_resolve_package_id_fallback_local(tmp_path):
    from compiler.extractor import resolve_package_id

    # No manifest, should return "local"
    skill_dir = tmp_path / "skills" / "some-skill"
    skill_dir.mkdir(parents=True)

    result = resolve_package_id(skill_dir)
    assert result == "local"


def test_resolve_package_id_with_toml_manifest(tmp_path):
    from compiler.extractor import resolve_package_id

    # Create skill directory with ontoskills.toml in parent
    skill_dir = tmp_path / "skills" / "brainstorming"
    skill_dir.mkdir(parents=True)

    toml_file = tmp_path / "skills" / "ontoskills.toml"
    toml_file.write_text('name = "obra/superpowers"\nversion = "1.0.0"')

    result = resolve_package_id(skill_dir)
    assert result == "obra/superpowers"


def test_compute_sub_skill_hash(tmp_path):
    md_file = tmp_path / "planning.md"
    md_file.write_text("# Planning Sub-Skill\n\nContent here")

    hash_val = compute_sub_skill_hash(md_file)
    assert isinstance(hash_val, str)
    assert len(hash_val) == 64


def test_compute_sub_skill_hash_independence(tmp_path):
    """Hash is independent of parent - only file content matters."""
    md_file = tmp_path / "test.md"
    md_file.write_text("same content")

    hash1 = compute_sub_skill_hash(md_file)

    # Same content, same hash
    md_file2 = tmp_path / "test2.md"
    md_file2.write_text("same content")
    hash2 = compute_sub_skill_hash(md_file2)

    assert hash1 == hash2


# =============================================================================
# Tests for resolve_package_id with input_path
# =============================================================================


def test_is_author_dir_depth1(tmp_path):
    """Author dir: direct child is a skill (depth 1)."""
    # obra/tdd/SKILL.md  →  obra is an author dir
    (tmp_path / "tdd" / "SKILL.md").parent.mkdir(parents=True)
    (tmp_path / "tdd" / "SKILL.md").write_text("# TDD")
    assert _is_author_dir(tmp_path) is True


def test_is_author_dir_nested_no_depth1(tmp_path):
    """Author dir: no child has SKILL.md, but grandchildren do."""
    # obra/superpowers/tdd/SKILL.md  (no obra/superpowers/SKILL.md)
    (tmp_path / "superpowers" / "tdd" / "SKILL.md").parent.mkdir(parents=True)
    (tmp_path / "superpowers" / "tdd" / "SKILL.md").write_text("# TDD")
    # No depth-1 SKILL.md, and name is not a known root → defaults to True
    assert _is_author_dir(tmp_path) is True


def test_is_skills_root_multiple_children(tmp_path):
    """Skills root: multiple children each contain skills → root, not author."""
    root = tmp_path / "packages"
    root.mkdir()
    # obra has skills
    (root / "obra" / "tdd" / "SKILL.md").parent.mkdir(parents=True)
    (root / "obra" / "tdd" / "SKILL.md").write_text("# TDD")
    # coinbase also has skills → 2+ children with skills → root
    (root / "coinbase" / "wallet" / "SKILL.md").parent.mkdir(parents=True)
    (root / "coinbase" / "wallet" / "SKILL.md").write_text("# Wallet")
    assert _is_author_dir(root) is False


def test_is_author_dir_single_child_with_skills(tmp_path):
    """Author dir: only one child contains skills → defaults to author."""
    author = tmp_path / "obra"
    author.mkdir()
    (author / "superpowers" / "tdd" / "SKILL.md").parent.mkdir(parents=True)
    (author / "superpowers" / "tdd" / "SKILL.md").write_text("# TDD")
    # Only one child (superpowers) with skills → can't be sure it's a root → defaults to author
    assert _is_author_dir(author) is True


def test_is_author_dir_empty(tmp_path):
    """Empty directory defaults to author dir."""
    assert _is_author_dir(tmp_path) is True


def test_resolve_package_id_author_dir_nested(tmp_path):
    """Author dir (obra/) with nested package superpowers/tdd/."""
    author_dir = tmp_path / "obra"
    skill_dir = author_dir / "superpowers" / "tdd"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# TDD")

    result = resolve_package_id(skill_dir, author_dir)
    assert result == "obra/superpowers"


def test_resolve_package_id_author_dir_flat(tmp_path):
    """Author dir (obra/) with flat skill tdd/."""
    author_dir = tmp_path / "obra"
    skill_dir = author_dir / "tdd"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# TDD")

    result = resolve_package_id(skill_dir, author_dir)
    assert result == "obra"


def test_resolve_package_id_skills_root_nested(tmp_path):
    """Skills root with multiple authors → nested package."""
    root = tmp_path / "packages"
    root.mkdir()
    skill_dir = root / "obra" / "superpowers" / "tdd"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# TDD")
    # Second author needed for multi-child detection
    (root / "coinbase" / "wallet" / "SKILL.md").parent.mkdir(parents=True)
    (root / "coinbase" / "wallet" / "SKILL.md").write_text("# Wallet")

    result = resolve_package_id(skill_dir, root)
    assert result == "obra/superpowers"


def test_resolve_package_id_skills_root_flat(tmp_path):
    """Skills root with multiple authors → flat skill under author."""
    root = tmp_path / "packages"
    root.mkdir()
    skill_dir = root / "obra" / "tdd"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# TDD")
    # Second author needed for multi-child detection
    (root / "coinbase" / "wallet" / "SKILL.md").parent.mkdir(parents=True)
    (root / "coinbase" / "wallet" / "SKILL.md").write_text("# Wallet")

    result = resolve_package_id(skill_dir, root)
    assert result == "obra"


def test_resolve_package_id_skill_equals_input(tmp_path):
    """skill_dir == input_path → DEFAULT_SKILLS_AUTHOR fallback."""
    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Skill")

    import os
    old = os.environ.get("DEFAULT_SKILLS_AUTHOR")
    os.environ["DEFAULT_SKILLS_AUTHOR"] = "custom-author"
    try:
        result = resolve_package_id(skill_dir, skill_dir)
        assert result == "custom-author"
    finally:
        if old is None:
            os.environ.pop("DEFAULT_SKILLS_AUTHOR", None)
        else:
            os.environ["DEFAULT_SKILLS_AUTHOR"] = old


def test_resolve_package_id_skill_equals_input_no_env(tmp_path):
    """skill_dir == input_path with no DEFAULT_SKILLS_AUTHOR → falls back to 'local'."""
    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Skill")

    import os
    old = os.environ.pop("DEFAULT_SKILLS_AUTHOR", None)
    try:
        result = resolve_package_id(skill_dir, skill_dir)
        assert result == "local"
    finally:
        if old is not None:
            os.environ["DEFAULT_SKILLS_AUTHOR"] = old


def test_resolve_package_id_author_dir_single_skill(tmp_path):
    """Author dir with single flat skill → returns author name."""
    author_dir = tmp_path / "obra"
    skill_dir = author_dir / "tdd"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# TDD")

    result = resolve_package_id(skill_dir, author_dir)
    assert result == "obra"
