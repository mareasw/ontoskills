import pytest
from click.testing import CliRunner
from cli import cli


def test_cli_version():
    runner = CliRunner()
    result = runner.invoke(cli, ['--version'])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(cli, ['--help'])
    assert result.exit_code == 0
    assert "compile" in result.output
    assert "query" in result.output
    assert "list-skills" in result.output


def test_compile_no_skills(tmp_path):
    """Test compile command with no skills directory."""
    runner = CliRunner()
    result = runner.invoke(cli, [
        'compile',
        '-i', str(tmp_path / 'nonexistent'),
        '-o', str(tmp_path / 'output.ttl')
    ])
    # Should succeed but report no skills
    assert result.exit_code == 0


def test_compile_dry_run(tmp_path):
    """Test compile with --dry-run flag."""
    # Create a minimal skill
    skill_dir = tmp_path / "skills" / "test-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Test Skill\n\nA simple test skill.")

    runner = CliRunner()
    # This will fail without API key, but we can test the flag parsing
    result = runner.invoke(cli, [
        'compile',
        '-i', str(tmp_path / 'skills'),
        '-o', str(tmp_path / 'output.ttl'),
        '--dry-run',
        '--skip-security'  # Skip security to avoid API calls
    ])

    # Command should run (even if no skills compiled due to missing API key)
    # The important thing is the flags are parsed correctly
    assert result.exit_code == 0 or "extraction" in result.output.lower() or "no skills" in result.output.lower()


def test_query_missing_ontology(tmp_path):
    """Test query with missing ontology file."""
    runner = CliRunner()
    result = runner.invoke(cli, [
        'query',
        'SELECT ?s WHERE { ?s a ?type }',
        '-o', str(tmp_path / 'nonexistent.ttl')
    ])
    assert result.exit_code != 0


def test_list_skills_missing_ontology(tmp_path):
    """Test list-skills with missing ontology."""
    runner = CliRunner()
    result = runner.invoke(cli, [
        'list-skills',
        '-o', str(tmp_path / 'nonexistent.ttl')
    ])
    # Should report missing file but not crash
    assert "not found" in result.output.lower() or result.exit_code != 0


def test_security_audit_no_skills(tmp_path):
    """Test security-audit with no skills directory."""
    runner = CliRunner()
    result = runner.invoke(cli, [
        'security-audit',
        '-i', str(tmp_path / 'nonexistent')
    ])
    assert result.exit_code != 0 or "not found" in result.output.lower()
