import pytest
from click.testing import CliRunner
from cli import cli


def test_cli_version():
    runner = CliRunner()
    result = runner.invoke(cli, ['--version'])
    assert result.exit_code == 0
    assert "version" in result.output.lower()
