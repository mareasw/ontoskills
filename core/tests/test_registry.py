"""Tests for the ontology registry helpers."""

import json
from pathlib import Path

from compiler.core_ontology import create_core_ontology
from compiler.registry import (
    add_registry_source,
    import_source_repository,
    enabled_index_path,
    install_package_from_directory,
    install_source_package_from_directory,
    install_package_from_sources,
    load_registry_lock,
    load_registry_sources,
    rebuild_registry_indexes,
    disable_skills,
    enable_skills,
)


def write_package(package_dir: Path) -> None:
    (package_dir / "skills").mkdir(parents=True, exist_ok=True)
    (package_dir / "skills" / "office.ttl").write_text(
        """
@prefix oc: <http://ontoclaw.marea.software/ontology#> .
@prefix dcterms: <http://purl.org/dc/terms/> .

oc:skill_office a oc:Skill, oc:DeclarativeSkill ;
    dcterms:identifier "office" ;
    oc:nature "Office base" .
""",
        encoding="utf-8",
    )
    (package_dir / "skills" / "xlsx.ttl").write_text(
        """
@prefix oc: <http://ontoclaw.marea.software/ontology#> .
@prefix dcterms: <http://purl.org/dc/terms/> .

oc:skill_xlsx a oc:Skill, oc:ExecutableSkill ;
    dcterms:identifier "xlsx" ;
    oc:nature "Spreadsheet" ;
    oc:extends oc:skill_office .
""",
        encoding="utf-8",
    )
    (package_dir / "package.json").write_text(
        json.dumps(
            {
                "package_id": "marea.office",
                "version": "1.0.0",
                "trust_tier": "verified",
                "source": "https://example.invalid/marea/office",
                "modules": ["skills/office.ttl", "skills/xlsx.ttl"],
                "skills": [
                    {"id": "office", "path": "skills/office.ttl", "default_enabled": False},
                    {"id": "xlsx", "path": "skills/xlsx.ttl", "default_enabled": False},
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def test_install_enable_disable_package_rebuilds_indexes(tmp_path):
    root = tmp_path / "ontoskills"
    create_core_ontology(root / "ontoclaw-core.ttl")

    package_dir = tmp_path / "package"
    write_package(package_dir)

    install_package_from_directory(package_dir, root=root)
    lock = load_registry_lock(root)
    assert "marea.office" in lock.packages
    assert enabled_index_path(root).exists()

    enable_skills("marea.office", ["xlsx"], root=root)
    lock = load_registry_lock(root)
    office_pkg = lock.packages["marea.office"]
    enabled = {skill.skill_id for skill in office_pkg.skills if skill.enabled}
    assert enabled == {"office", "xlsx"}

    disable_skills("marea.office", ["office"], root=root)
    lock = load_registry_lock(root)
    office_pkg = lock.packages["marea.office"]
    enabled = {skill.skill_id for skill in office_pkg.skills if skill.enabled}
    assert enabled == set()

    installed_index, enabled_index = rebuild_registry_indexes(root)
    assert installed_index.exists()
    assert enabled_index.exists()


def test_registry_source_install_from_file_index(tmp_path):
    root = tmp_path / "ontoskills"
    create_core_ontology(root / "ontoclaw-core.ttl")

    package_dir = tmp_path / "package"
    write_package(package_dir)

    index_path = tmp_path / "registry.json"
    manifest_url = (package_dir / "package.json").resolve().as_uri()
    index_path.write_text(
        json.dumps(
            {
                "packages": [
                    {
                        "package_id": "marea.office",
                        "manifest_url": manifest_url,
                        "trust_tier": "verified",
                        "source_kind": "ontology",
                    }
                ]
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    add_registry_source("official", index_path.resolve().as_uri(), root=root, trust_tier="verified")
    sources = load_registry_sources(root)
    assert len(sources.sources) == 1

    install_package_from_sources("marea.office", root=root)
    lock = load_registry_lock(root)
    assert "marea.office" in lock.packages
    assert lock.packages["marea.office"].trust_tier == "verified"


def test_registry_source_install_resolves_relative_manifest_url(tmp_path):
    root = tmp_path / "ontoskills"
    create_core_ontology(root / "ontoclaw-core.ttl")

    registry_dir = tmp_path / "registry"
    package_dir = registry_dir / "packages" / "marea.greeting"
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "hello").mkdir(parents=True, exist_ok=True)
    (package_dir / "hello" / "ontoskill.ttl").write_text(
        """
@prefix oc: <http://ontoclaw.marea.software/ontology#> .
@prefix dcterms: <http://purl.org/dc/terms/> .

oc:skill_hello a oc:Skill, oc:DeclarativeSkill ;
    dcterms:identifier "hello" ;
    oc:nature "Greeting" .
""",
        encoding="utf-8",
    )
    (package_dir / "package.json").write_text(
        json.dumps(
            {
                "package_id": "marea.greeting",
                "version": "0.1.0",
                "trust_tier": "verified",
                "modules": ["hello/ontoskill.ttl"],
                "skills": [
                    {"id": "hello", "path": "hello/ontoskill.ttl", "default_enabled": False},
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (registry_dir / "index.json").write_text(
        json.dumps(
            {
                "packages": [
                    {
                        "package_id": "marea.greeting",
                        "manifest_url": "./packages/marea.greeting/package.json",
                        "trust_tier": "verified",
                        "source_kind": "ontology",
                    }
                ]
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    add_registry_source("official", (registry_dir / "index.json").resolve().as_uri(), root=root, trust_tier="verified")
    package = install_package_from_sources("marea.greeting", root=root)

    assert package.package_id == "marea.greeting"
    assert package.skills[0].skill_id == "hello"


def test_import_source_package_compiles_and_stays_disabled(tmp_path):
    from unittest.mock import patch

    root = tmp_path / "ontoskills"
    create_core_ontology(root / "ontoclaw-core.ttl")

    package_dir = tmp_path / "source-package"
    (package_dir / "src" / "office" / "xlsx").mkdir(parents=True, exist_ok=True)
    (package_dir / "src" / "office" / "SKILL.md").write_text("# Office", encoding="utf-8")
    (package_dir / "src" / "office" / "xlsx" / "SKILL.md").write_text("# Xlsx", encoding="utf-8")
    (package_dir / "package.json").write_text(
        json.dumps(
            {
                "package_id": "community.office",
                "version": "0.1.0",
                "trust_tier": "community",
                "source_root": "src",
                "skills": [
                    {"id": "office", "path": "office/ontoskill.ttl", "default_enabled": False},
                    {"id": "xlsx", "path": "office/xlsx/ontoskill.ttl", "default_enabled": False},
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    def fake_compile(source_root, compiled_root):
        (compiled_root / "office").mkdir(parents=True, exist_ok=True)
        (compiled_root / "office" / "xlsx").mkdir(parents=True, exist_ok=True)
        (compiled_root / "office" / "ontoskill.ttl").write_text(
            """
@prefix oc: <http://ontoclaw.marea.software/ontology#> .
@prefix dcterms: <http://purl.org/dc/terms/> .

oc:skill_office a oc:Skill, oc:DeclarativeSkill ;
    dcterms:identifier "office" ;
    oc:nature "Office" .
""",
            encoding="utf-8",
        )
        (compiled_root / "office" / "xlsx" / "ontoskill.ttl").write_text(
            """
@prefix oc: <http://ontoclaw.marea.software/ontology#> .
@prefix dcterms: <http://purl.org/dc/terms/> .

oc:skill_xlsx a oc:Skill, oc:ExecutableSkill ;
    dcterms:identifier "xlsx" ;
    oc:nature "Xlsx" ;
    oc:extends oc:skill_office .
""",
            encoding="utf-8",
        )

    with patch("compiler.registry.compile_source_tree", side_effect=fake_compile):
        package = install_source_package_from_directory(package_dir, root=root, trust_tier="community")

    assert package.source_kind == "source"
    assert all(not skill.enabled for skill in package.skills)
    lock = load_registry_lock(root)
    assert "community.office" in lock.packages


def test_registry_source_import_from_file_index_for_remote_source_package(tmp_path):
    from unittest.mock import patch

    root = tmp_path / "ontoskills"
    create_core_ontology(root / "ontoclaw-core.ttl")

    package_dir = tmp_path / "remote-source-package"
    (package_dir / "src" / "office" / "xlsx").mkdir(parents=True, exist_ok=True)
    (package_dir / "src" / "office" / "SKILL.md").write_text("# Office", encoding="utf-8")
    (package_dir / "src" / "office" / "xlsx" / "SKILL.md").write_text("# Xlsx", encoding="utf-8")
    (package_dir / "package.json").write_text(
        json.dumps(
            {
                "package_id": "skillssh.office",
                "version": "0.2.0",
                "trust_tier": "community",
                "source_root": "src",
                "source_files": [
                    "src/office/SKILL.md",
                    "src/office/xlsx/SKILL.md",
                ],
                "skills": [
                    {"id": "office", "path": "office/ontoskill.ttl", "default_enabled": False},
                    {"id": "xlsx", "path": "office/xlsx/ontoskill.ttl", "default_enabled": False},
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    registry_index = tmp_path / "registry-source.json"
    registry_index.write_text(
        json.dumps(
            {
                "packages": [
                    {
                        "package_id": "skillssh.office",
                        "manifest_url": (package_dir / "package.json").resolve().as_uri(),
                        "trust_tier": "community",
                        "source_kind": "source",
                    }
                ]
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    def fake_compile(source_root, compiled_root):
        assert (source_root / "office" / "SKILL.md").exists()
        assert (source_root / "office" / "xlsx" / "SKILL.md").exists()
        (compiled_root / "office").mkdir(parents=True, exist_ok=True)
        (compiled_root / "office" / "xlsx").mkdir(parents=True, exist_ok=True)
        (compiled_root / "office" / "ontoskill.ttl").write_text(
            """
@prefix oc: <http://ontoclaw.marea.software/ontology#> .
@prefix dcterms: <http://purl.org/dc/terms/> .

oc:skill_office a oc:Skill, oc:DeclarativeSkill ;
    dcterms:identifier "office" ;
    oc:nature "Office" .
""",
            encoding="utf-8",
        )
        (compiled_root / "office" / "xlsx" / "ontoskill.ttl").write_text(
            """
@prefix oc: <http://ontoclaw.marea.software/ontology#> .
@prefix dcterms: <http://purl.org/dc/terms/> .

oc:skill_xlsx a oc:Skill, oc:ExecutableSkill ;
    dcterms:identifier "xlsx" ;
    oc:nature "Xlsx" ;
    oc:extends oc:skill_office .
""",
            encoding="utf-8",
        )

    add_registry_source("skillssh", registry_index.resolve().as_uri(), root=root, trust_tier="community", source_kind="source")
    with patch("compiler.registry.compile_source_tree", side_effect=fake_compile):
        package = install_package_from_sources("skillssh.office", root=root)

    assert package.source_kind == "source"
    assert package.package_id == "skillssh.office"
    assert all(not skill.enabled for skill in package.skills)


def test_import_source_repository_discovers_skills_and_registers_package(tmp_path):
    from unittest.mock import patch

    root = tmp_path / "ontoskills"
    create_core_ontology(root / "ontoclaw-core.ttl")

    repo_dir = tmp_path / "ui-ux-pro-max-skill"
    (repo_dir / ".claude" / "skills" / "ui-ux-pro-max").mkdir(parents=True, exist_ok=True)
    (repo_dir / ".claude" / "skills" / "ui-ux-pro-max" / "SKILL.md").write_text("# UI UX Pro Max", encoding="utf-8")
    (repo_dir / "src" / "landing-page").mkdir(parents=True, exist_ok=True)
    (repo_dir / "src" / "landing-page" / "SKILL.md").write_text("# Landing Page", encoding="utf-8")

    def fake_compile(source_root, compiled_root):
        (compiled_root / ".claude" / "skills" / "ui-ux-pro-max").mkdir(parents=True, exist_ok=True)
        (compiled_root / "src" / "landing-page").mkdir(parents=True, exist_ok=True)
        (compiled_root / ".claude" / "skills" / "ui-ux-pro-max" / "ontoskill.ttl").write_text(
            """
@prefix oc: <http://ontoclaw.marea.software/ontology#> .
@prefix dcterms: <http://purl.org/dc/terms/> .

oc:skill_ui_ux_pro_max a oc:Skill, oc:DeclarativeSkill ;
    dcterms:identifier "ui-ux-pro-max" ;
    oc:nature "Design system skill" .
""",
            encoding="utf-8",
        )
        (compiled_root / "src" / "landing-page" / "ontoskill.ttl").write_text(
            """
@prefix oc: <http://ontoclaw.marea.software/ontology#> .
@prefix dcterms: <http://purl.org/dc/terms/> .

oc:skill_landing_page a oc:Skill, oc:DeclarativeSkill ;
    dcterms:identifier "landing-page" ;
    oc:nature "Landing page skill" .
""",
            encoding="utf-8",
        )

    with patch("compiler.registry.compile_source_tree", side_effect=fake_compile):
        package = import_source_repository(
            str(repo_dir),
            root=root,
            trust_tier="community",
        )

    assert package.package_id == "source.ui-ux-pro-max-skill"
    assert package.source_kind == "source"
    assert sorted(skill.skill_id for skill in package.skills) == ["landing-page", "ui-ux-pro-max"]
    assert all(not skill.enabled for skill in package.skills)
    lock = load_registry_lock(root)
    assert package.package_id in lock.packages


def test_import_source_repository_rewrites_compiled_payload_script_paths(tmp_path):
    from unittest.mock import patch

    root = tmp_path / "ontoskills"
    create_core_ontology(root / "ontoclaw-core.ttl")

    repo_dir = tmp_path / "ui-ux-pro-max-skill"
    (repo_dir / ".claude" / "skills" / "ui-ux-pro-max").mkdir(parents=True, exist_ok=True)
    (repo_dir / ".claude" / "skills" / "ui-ux-pro-max" / "SKILL.md").write_text("# UI UX Pro Max", encoding="utf-8")

    def fake_compile(source_root, compiled_root):
        (compiled_root / ".claude" / "skills" / "ui-ux-pro-max").mkdir(parents=True, exist_ok=True)
        (compiled_root / "src" / "ui-ux-pro-max" / "scripts").mkdir(parents=True, exist_ok=True)
        (compiled_root / "src" / "ui-ux-pro-max" / "scripts" / "search.py").write_text(
            "print('search')",
            encoding="utf-8",
        )
        (compiled_root / ".claude" / "skills" / "ui-ux-pro-max" / "ontoskill.ttl").write_text(
            """
@prefix oc: <http://ontoclaw.marea.software/ontology#> .
@prefix dcterms: <http://purl.org/dc/terms/> .

oc:skill_ui_ux_pro_max a oc:Skill, oc:DeclarativeSkill ;
    dcterms:identifier "ui-ux-pro-max" ;
    oc:nature "Design system skill" ;
    oc:hasPayload [
        a oc:PythonCode ;
        oc:code "python3 skills/ui-ux-pro-max/scripts/search.py \\"hero section\\""
    ] .
""",
            encoding="utf-8",
        )

    with patch("compiler.registry.compile_source_tree", side_effect=fake_compile):
        package = import_source_repository(
            str(repo_dir),
            root=root,
            trust_tier="community",
        )

    ttl_path = Path(package.install_root) / "compiled" / ".claude" / "skills" / "ui-ux-pro-max" / "ontoskill.ttl"
    payload = ttl_path.read_text(encoding="utf-8")
    expected_script = (Path(package.install_root) / "compiled" / "src" / "ui-ux-pro-max" / "scripts" / "search.py").resolve().as_posix()
    assert expected_script in payload
    assert "skills/ui-ux-pro-max/scripts/search.py" not in payload


def test_import_source_repository_rewrites_relative_and_broken_absolute_script_paths(tmp_path):
    from unittest.mock import patch

    root = tmp_path / "ontoskills"
    create_core_ontology(root / "ontoclaw-core.ttl")

    repo_dir = tmp_path / "design-repo"
    (repo_dir / ".claude" / "skills" / "design-system").mkdir(parents=True, exist_ok=True)
    (repo_dir / ".claude" / "skills" / "design-system" / "SKILL.md").write_text("# Design System", encoding="utf-8")
    (repo_dir / ".claude" / "skills" / "design").mkdir(parents=True, exist_ok=True)
    (repo_dir / ".claude" / "skills" / "design" / "SKILL.md").write_text("# Design", encoding="utf-8")

    def fake_compile(source_root, compiled_root):
        (compiled_root / ".claude" / "skills" / "design-system" / "scripts").mkdir(parents=True, exist_ok=True)
        (compiled_root / ".claude" / "skills" / "design" / "scripts" / "logo").mkdir(parents=True, exist_ok=True)
        (compiled_root / ".claude" / "skills" / "design-system" / "scripts" / "search-slides.py").write_text(
            "print('slides')",
            encoding="utf-8",
        )
        (compiled_root / ".claude" / "skills" / "design" / "scripts" / "logo" / "search.py").write_text(
            "print('logo')",
            encoding="utf-8",
        )
        (compiled_root / ".claude" / "skills" / "design-system" / "ontoskill.ttl").write_text(
            """
@prefix oc: <http://ontoclaw.marea.software/ontology#> .
@prefix dcterms: <http://purl.org/dc/terms/> .

oc:skill_design_system a oc:Skill, oc:ExecutableSkill ;
    dcterms:identifier "design-system" ;
    oc:hasPayload [
        a oc:ExecutionPayload ;
        oc:code "python scripts/search-slides.py \\"investor pitch\\""
    ] .
""",
            encoding="utf-8",
        )
        (compiled_root / ".claude" / "skills" / "design" / "ontoskill.ttl").write_text(
            """
@prefix oc: <http://ontoclaw.marea.software/ontology#> .
@prefix dcterms: <http://purl.org/dc/terms/> .

oc:skill_design a oc:Skill, oc:ExecutableSkill ;
    dcterms:identifier "design" ;
    oc:hasPayload [
        a oc:ExecutionPayload ;
        oc:code "python ~/.claude//Users/test/skill/scripts/logo/search.py"
    ] .
""",
            encoding="utf-8",
        )

    with patch("compiler.registry.compile_source_tree", side_effect=fake_compile):
        package = import_source_repository(
            str(repo_dir),
            root=root,
            trust_tier="community",
        )

    design_system_ttl = Path(package.install_root) / "compiled" / ".claude" / "skills" / "design-system" / "ontoskill.ttl"
    design_payload = design_system_ttl.read_text(encoding="utf-8")
    expected_relative_script = (
        Path(package.install_root) / "compiled" / ".claude" / "skills" / "design-system" / "scripts" / "search-slides.py"
    ).resolve().as_posix()
    assert expected_relative_script in design_payload
    assert "python scripts/search-slides.py" not in design_payload

    design_ttl = Path(package.install_root) / "compiled" / ".claude" / "skills" / "design" / "ontoskill.ttl"
    broken_payload = design_ttl.read_text(encoding="utf-8")
    assert "~/.claude//Users/" not in broken_payload
    assert "python /Users/test/skill/scripts/logo/search.py" in broken_payload
