"""Tests for OntoClaw dependency graph exporter."""

from compiler.graph_export import build_graph

BASE = "@prefix oc: <https://ontoclaw.marea.software/ontology#> .\n"

TTL = BASE + """
oc:SkillA a oc:Skill ; oc:resolvesIntent "a" ; oc:dependsOn oc:SkillB .
oc:SkillB a oc:Skill ; oc:resolvesIntent "b" ; oc:extends    oc:SkillC .
oc:SkillC a oc:Skill ; oc:resolvesIntent "c" .
oc:SkillD a oc:Skill ; oc:resolvesIntent "d" ; oc:contradicts oc:SkillA .
"""


def _write(tmp_path, content=TTL):
    f = tmp_path / "skills.ttl"
    f.write_text(content)
    return str(f)


def test_mermaid_contains_all_nodes(tmp_path):
    """All four skills should appear as Mermaid nodes."""
    out = build_graph(_write(tmp_path), fmt="mermaid")
    for skill in ("SkillA", "SkillB", "SkillC", "SkillD"):
        assert skill in out


def test_mermaid_depends_arrow(tmp_path):
    """A dependsOn B should produce a --> arrow."""
    out = build_graph(_write(tmp_path), fmt="mermaid")
    assert "SkillA --> SkillB" in out


def test_mermaid_extends_dashed(tmp_path):
    """B extends C should produce a dashed arrow."""
    out = build_graph(_write(tmp_path), fmt="mermaid")
    assert "SkillB -.->|extends| SkillC" in out


def test_mermaid_contradicts_double(tmp_path):
    """Contradicts should produce a bidirectional x--x edge."""
    out = build_graph(_write(tmp_path), fmt="mermaid")
    assert "x--x" in out


def test_dot_format(tmp_path):
    """DOT output should start with 'digraph'."""
    out = build_graph(_write(tmp_path), fmt="dot")
    assert out.startswith("digraph OntoClaw")
    assert '"SkillA"' in out
    assert "dependsOn" in out


def test_skill_filter_limits_output(tmp_path):
    """--skill filter should include only the target skill and its neighbours."""
    out = build_graph(_write(tmp_path), fmt="mermaid", skill_filter="SkillA")
    assert "SkillA" in out
    assert "SkillB" in out   # direct neighbour via dependsOn
    assert "SkillD" in out   # direct neighbour via contradicts
    assert "SkillC" not in out  # 2 hops away


def test_empty_ontology(tmp_path):
    """An ontology with no relationships should produce a valid but edge-free graph."""
    path = tmp_path / "empty.ttl"
    path.write_text(BASE + "oc:Alone a oc:Skill ; oc:resolvesIntent \"x\" .\n")
    out = build_graph(str(path), fmt="mermaid")
    assert "graph TD" in out
    assert "-->" not in out
