"""Tests for OntoClaw Skill Drift Detector — differ module."""

import pytest

from compiler.differ import compute_diff

OLD_TTL = """
@prefix oc: <https://ontoclaw.marea.software/ontology#> .
oc:CreatePDF a oc:Skill ;
    oc:resolvesIntent "create_pdf" ;
    oc:requiresState oc:Idle .
"""

NEW_TTL_INTENT_REMOVED = """
@prefix oc: <https://ontoclaw.marea.software/ontology#> .
oc:CreatePDF a oc:Skill ;
    oc:resolvesIntent "generate_pdf" .
"""

NEW_TTL_SKILL_ADDED = (
    OLD_TTL
    + """
oc:NewSkill a oc:Skill ;
    oc:resolvesIntent "new_thing" .
"""
)


def test_removed_intent_is_breaking(tmp_path):
    """Renaming an intent is a breaking change — agents querying the old name get nothing."""
    old_f = tmp_path / 'old.ttl'
    new_f = tmp_path / 'new.ttl'
    old_f.write_text(OLD_TTL)
    new_f.write_text(NEW_TTL_INTENT_REMOVED)

    report = compute_diff(str(old_f), str(new_f))

    assert report.has_breaking
    assert any(c.category == 'intent' for c in report.breaking)


def test_clean_diff_is_clean(tmp_path):
    """Diffing identical files should produce a clean report."""
    f = tmp_path / 'skill.ttl'
    f.write_text(OLD_TTL)

    report = compute_diff(str(f), str(f))

    assert report.is_clean


def test_added_skill_not_breaking(tmp_path):
    """Adding a new skill is additive, not breaking."""
    old_f = tmp_path / 'old.ttl'
    new_f = tmp_path / 'new.ttl'
    old_f.write_text(OLD_TTL)
    new_f.write_text(NEW_TTL_SKILL_ADDED)

    report = compute_diff(str(old_f), str(new_f))

    assert not report.has_breaking
    assert report.added_skills or report.additive


def test_removed_skill_is_breaking(tmp_path):
    """Removing a skill entirely is a breaking change."""
    old_f = tmp_path / 'old.ttl'
    new_f = tmp_path / 'new.ttl'
    old_f.write_text(OLD_TTL)
    new_f.write_text("""
@prefix oc: <https://ontoclaw.marea.software/ontology#> .
""")

    report = compute_diff(str(old_f), str(new_f))

    assert report.has_breaking
    assert report.removed_skills


def test_added_requirement_is_breaking(tmp_path):
    """Adding a new requirement is breaking — existing agents may not satisfy it."""
    old_f = tmp_path / 'old.ttl'
    new_f = tmp_path / 'new.ttl'
    old_f.write_text(OLD_TTL)
    new_f.write_text("""
@prefix oc: <https://ontoclaw.marea.software/ontology#> .
oc:CreatePDF a oc:Skill ;
    oc:resolvesIntent "create_pdf" ;
    oc:requiresState oc:Idle ;
    oc:requires oc:APIKeySet .
""")

    report = compute_diff(str(old_f), str(new_f))

    assert report.has_breaking
    assert any(c.category == 'requirement' for c in report.breaking)
