"""
Dependency graph exporter for OntoClaw ontologies.

Reads the compiled ontology and produces a visual representation of the
skill relationship graph in Mermaid or DOT (Graphviz) format, covering
three relationship types:

  oc:dependsOn   — directed dependency edge  (solid arrow)
  oc:extends     — inheritance edge          (dashed arrow)
  oc:contradicts — mutual-exclusion edge     (dotted, bidirectional)

Usage:
    from compiler.graph_export import build_graph
    mermaid_src = build_graph(ttl_path, fmt="mermaid", skill_filter=None)
"""

from __future__ import annotations

from pathlib import Path

from rdflib import Graph, Namespace

OC = Namespace("https://ontoclaw.marea.software/ontology#")


def build_graph(
    ttl_path: str | Path,
    fmt: str = "mermaid",
    skill_filter: str | None = None,
) -> str:
    """
    Build a dependency graph from a compiled ontology file.

    Args:
        ttl_path:     Path to the .ttl file to analyse.
        fmt:          Output format — 'mermaid' or 'dot'.
        skill_filter: If given, include only this skill and its direct
                      neighbours (1-hop subgraph).

    Returns:
        A string containing the graph source in the requested format.
    """
    g = Graph()
    g.parse(str(ttl_path), format="turtle")

    nodes, edges = _extract_graph(g, skill_filter)

    if fmt == "dot":
        return _render_dot(nodes, edges)
    return _render_mermaid(nodes, edges)


# ─── Extraction ───────────────────────────────────────────────────────────────


def _local(uri) -> str:
    return str(uri).split("#")[-1].split("/")[-1]


def _extract_graph(
    g: Graph, skill_filter: str | None
) -> tuple[set[str], list[tuple[str, str, str]]]:
    """
    Return the set of node IDs and edge list (src, dst, rel_type).

    rel_type is one of: 'depends', 'extends', 'contradicts'.
    """
    edges: list[tuple[str, str, str]] = []

    for s, o in g.subject_objects(OC.dependsOn):
        edges.append((_local(s), _local(o), "depends"))

    for s, o in g.subject_objects(OC.extends):
        edges.append((_local(s), _local(o), "extends"))

    # oc:contradicts is symmetric — avoid duplicate edges
    seen_contradicts: set[frozenset[str]] = set()
    for s, o in g.subject_objects(OC.contradicts):
        pair = frozenset([_local(s), _local(o)])
        if pair not in seen_contradicts:
            seen_contradicts.add(pair)
            edges.append((_local(s), _local(o), "contradicts"))

    # Collect all nodes that have at least one intent (real skills)
    skill_ids = {_local(s) for s in g.subjects(OC.resolvesIntent)}

    # Apply 1-hop filter
    if skill_filter:
        neighbours = {skill_filter}
        for src, dst, _ in edges:
            if src == skill_filter:
                neighbours.add(dst)
            if dst == skill_filter:
                neighbours.add(src)
        edges = [(s, d, r) for s, d, r in edges if s in neighbours and d in neighbours]
        skill_ids &= neighbours

    # Include edge endpoints even if they have no declared intents
    for src, dst, _ in edges:
        skill_ids.add(src)
        skill_ids.add(dst)

    return skill_ids, edges


# ─── Renderers ────────────────────────────────────────────────────────────────


def _render_mermaid(nodes: set[str], edges: list[tuple[str, str, str]]) -> str:
    """Render as a Mermaid flowchart (TD orientation)."""
    lines = ["graph TD"]

    for node in sorted(nodes):
        lines.append(f'  {node}["{node}"]')

    for src, dst, rel in edges:
        if rel == "depends":
            lines.append(f"  {src} --> {dst}")
        elif rel == "extends":
            lines.append(f"  {src} -.->|extends| {dst}")
        elif rel == "contradicts":
            lines.append(f"  {src} x--x {dst}")

    return "\n".join(lines)


def _render_dot(nodes: set[str], edges: list[tuple[str, str, str]]) -> str:
    """Render as a Graphviz DOT digraph."""
    lines = [
        "digraph OntoClaw {",
        "  rankdir=TD;",
        '  node [shape=box, style=filled, fillcolor="#e8f4f8", fontname="Helvetica"];',
    ]

    for node in sorted(nodes):
        lines.append(f'  "{node}";')

    for src, dst, rel in edges:
        if rel == "depends":
            lines.append(f'  "{src}" -> "{dst}" [label="dependsOn"];')
        elif rel == "extends":
            lines.append(f'  "{src}" -> "{dst}" [label="extends", style=dashed];')
        elif rel == "contradicts":
            lines.append(
                f'  "{src}" -> "{dst}" [label="contradicts", style=dotted, dir=both];'
            )

    lines.append("}")
    return "\n".join(lines)
