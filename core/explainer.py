"""
Human-readable skill explainer for OntoClaw ontologies.

Reads a compiled skill from its .ttl file (or from the index) and renders
a structured summary card showing every relevant property — intents, states,
dependencies, executor, hash, and provenance.

Usage:
    from compiler.explainer import explain_skill, SkillSummary
    summary = explain_skill(ttl_path, skill_id="create-pdf")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from rdflib import Graph, Namespace, RDF
from rdflib.namespace import DCTERMS

OC = Namespace("https://ontoclaw.marea.software/ontology#")


@dataclass
class SkillSummary:
    skill_id: str
    skill_type: str                    # "ExecutableSkill" | "DeclarativeSkill" | "Skill"
    nature: str
    intents: list[str]                 = field(default_factory=list)
    requires_states: list[str]         = field(default_factory=list)
    yields_states: list[str]           = field(default_factory=list)
    handles_failures: list[str]        = field(default_factory=list)
    depends_on: list[str]              = field(default_factory=list)
    extends: list[str]                 = field(default_factory=list)
    contradicts: list[str]             = field(default_factory=list)
    executor: str | None               = None
    content_hash: str | None           = None
    generated_by: str | None           = None


def explain_skill(ttl_path: str | Path, skill_id: str) -> SkillSummary | None:
    """
    Extract a SkillSummary for the given skill_id from a .ttl file.

    Args:
        ttl_path: Path to the compiled ontology (.ttl).
        skill_id: The local identifier of the skill (e.g. "create-pdf").

    Returns:
        SkillSummary if the skill is found, None otherwise.
    """
    g = Graph()
    g.parse(str(ttl_path), format="turtle")
    return _build_summary(g, skill_id)


def list_skill_ids(ttl_path: str | Path) -> list[str]:
    """Return all skill IDs present in the ontology file."""
    g = Graph()
    g.parse(str(ttl_path), format="turtle")
    ids: list[str] = []
    for s in g.subjects(OC.resolvesIntent):
        id_lit = g.value(s, DCTERMS.identifier)
        if id_lit:
            ids.append(str(id_lit))
        else:
            ids.append(_local(s))
    return sorted(set(ids))


# ─── Private helpers ──────────────────────────────────────────────────────────


def _local(uri) -> str:
    return str(uri).split("#")[-1].split("/")[-1]


def _skill_type(g: Graph, uri) -> str:
    if (uri, RDF.type, OC.ExecutableSkill) in g:
        return "ExecutableSkill"
    if (uri, RDF.type, OC.DeclarativeSkill) in g:
        return "DeclarativeSkill"
    return "Skill"


def _build_summary(g: Graph, skill_id: str) -> SkillSummary | None:
    """Locate the skill URI and populate a SkillSummary from its triples."""
    skill_uri = None

    # Try matching by dcterms:identifier first (most reliable)
    for s in g.subjects(DCTERMS.identifier, None):
        id_lit = g.value(s, DCTERMS.identifier)
        if id_lit and str(id_lit) == skill_id:
            skill_uri = s
            break

    # Fall back to local URI fragment
    if skill_uri is None:
        for s in g.subjects(OC.resolvesIntent):
            if _local(s) == skill_id or _local(s) == skill_id.replace("-", "").replace("_", "").lower():
                skill_uri = s
                break

    if skill_uri is None:
        return None

    nature_lit = g.value(skill_uri, OC.nature)
    nature = str(nature_lit) if nature_lit else ""

    intents         = [str(o) for o in g.objects(skill_uri, OC.resolvesIntent)]
    requires_states = [_local(o) for o in g.objects(skill_uri, OC.requiresState)]
    yields_states   = [_local(o) for o in g.objects(skill_uri, OC.yieldsState)]
    handles_failures= [_local(o) for o in g.objects(skill_uri, OC.handlesFailure)]
    depends_on      = [_local(o) for o in g.objects(skill_uri, OC.dependsOn)]
    extends         = [_local(o) for o in g.objects(skill_uri, OC.extends)]
    contradicts     = [_local(o) for o in g.objects(skill_uri, OC.contradicts)]

    # Executor lives inside oc:ExecutionPayload
    executor = None
    payload_uri = g.value(skill_uri, OC.hasPayload)
    if payload_uri:
        exec_lit = g.value(payload_uri, OC.executor)
        if exec_lit:
            executor = str(exec_lit)

    hash_lit = g.value(skill_uri, OC.contentHash)
    gen_lit  = g.value(skill_uri, OC.generatedBy)

    return SkillSummary(
        skill_id        = skill_id,
        skill_type      = _skill_type(g, skill_uri),
        nature          = nature,
        intents         = sorted(intents),
        requires_states = sorted(requires_states),
        yields_states   = sorted(yields_states),
        handles_failures= sorted(handles_failures),
        depends_on      = sorted(depends_on),
        extends         = sorted(extends),
        contradicts     = sorted(contradicts),
        executor        = executor,
        content_hash    = str(hash_lit)[:8] if hash_lit else None,
        generated_by    = str(gen_lit) if gen_lit else None,
    )
