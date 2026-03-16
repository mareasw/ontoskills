import pytest
from compiler.exceptions import SkillETLError, SecurityError


def test_exceptions_exit_codes():
    assert SkillETLError.exit_code == 1
    assert SecurityError.exit_code == 3
