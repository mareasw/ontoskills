"""
Static analysis linter for OntoClaw ontologies.

Analyses the compiled ontology (or a set of .ttl files) without calling the
Anthropic API and reports four categories of structural issues:

  - dead_states      : a skill requiresState X but no skill yieldsState X
  - circular_deps    : A dependsOn B dependsOn … dependsOn A
  - duplicate_intents: two different skills resolve the same intent string
  - orphan_skills    : no other skill depends on this skill and it has no
                       required state that another skill yields (isolated leaf)

Each issue is returned as a LintIssue dataclass so callers can format the
output however they like (Rich terminal, JSON, CI log).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from rdflib import Graph, Namespace

OC = Namespace("https://ontoclaw.marea.software/ontology#")

Severity = Literal["error", "warning", "info"]


@dataclass
class LintIssue:
    severity: Severity
    code: str          # e.g. "dead-state", "circular-dep"
    skill_id: str
    message: str
    detail: str = ""


@dataclass
class LintResult:
    issues: list[LintIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[LintIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[LintIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)

    @property
    def is_clean(self) -> bool:
        return not self.issues


def lint_ontology(ttl_path: str | Path) -> LintResult:
    """
    Run all lint checks against a compiled .ttl file.

    Args:
        ttl_path: Path to the ontology file (index.ttl or any skill .ttl).

    Returns:
        LintResult containing all discovered issues.
    """
    g = Graph()
    g.parse(str(ttl_path), format="turtle")

    result = LintResult()
    result.issues += _check_dead_states(g)
    result.issues += _check_circular_deps(g)
    result.issues += _check_duplicate_intents(g)
    result.issues += _check_orphan_skills(g)
    return result


# ─── Private checks ───────────────────────────────────────────────────────────


def _all_skills(g: Graph) -> list[str]:
    """Return local names of all skills that declare at least one intent."""
    return [_local(s) for s in g.subjects(OC.resolvesIntent)]


def _local(uri) -> str:
    return str(uri).split("#")[-1].split("/")[-1]


def _check_dead_states(g: Graph) -> list[LintIssue]:
    """
    Detect states that are required by some skill but never yielded by any skill.

    A dead state makes a skill permanently un-executable: the precondition can
    never be satisfied because no skill produces it.
    """
    required = {str(o) for o in g.objects(predicate=OC.requiresState)}
    yielded  = {str(o) for o in g.objects(predicate=OC.yieldsState)}
    dead     = required - yielded

    issues: list[LintIssue] = []
    for state in dead:
        # Find which skills need this state
        for skill_uri in g.subjects(OC.requiresState, g.store.__class__):
            pass
        affected = [
            _local(s)
            for s in g.subjects(OC.requiresState)
            if str(next(g.objects(s, OC.requiresState), None)) == state
            or state in {str(o) for o in g.objects(s, OC.requiresState)}
        ]
        for skill_id in affected:
            issues.append(LintIssue(
                severity="warning",
                code="dead-state",
                skill_id=skill_id,
                message=f"requiresState '{_local(state)}' is never yielded by any skill",
                detail="This skill may be permanently un-executable in a cold-start scenario.",
            ))
    return issues


def _check_circular_deps(g: Graph) -> list[LintIssue]:
    """
    Detect circular dependency chains via oc:dependsOn.

    Uses DFS with a recursion stack. Reports each skill that is part of a cycle.
    """
    # Build adjacency: skill_id → set of skill_ids it depends on
    adj: dict[str, set[str]] = {}
    for s, o in g.subject_objects(OC.dependsOn):
        sid = _local(s)
        oid = _local(o)
        adj.setdefault(sid, set()).add(oid)

    visited:   set[str] = set()
    rec_stack: set[str] = set()
    cycles:    set[str] = set()

    def dfs(node: str) -> bool:
        visited.add(node)
        rec_stack.add(node)
        for neighbour in adj.get(node, set()):
            if neighbour not in visited:
                if dfs(neighbour):
                    cycles.add(node)
                    return True
            elif neighbour in rec_stack:
                cycles.add(node)
                cycles.add(neighbour)
                return True
        rec_stack.discard(node)
        return False

    for skill in list(adj.keys()):
        if skill not in visited:
            dfs(skill)

    return [
        LintIssue(
            severity="error",
            code="circular-dep",
            skill_id=sid,
            message=f"Circular dependency detected involving '{sid}'",
            detail="Resolve the cycle in oc:dependsOn before deploying.",
        )
        for sid in sorted(cycles)
    ]


def _check_duplicate_intents(g: Graph) -> list[LintIssue]:
    """
    Detect intent strings declared by more than one skill.

    Duplicate intents cause non-deterministic skill selection at runtime:
    the agent cannot know which skill to invoke for a given intent.
    """
    intent_map: dict[str, list[str]] = {}
    for s, o in g.subject_objects(OC.resolvesIntent):
        intent = str(o)
        intent_map.setdefault(intent, []).append(_local(s))

    issues: list[LintIssue] = []
    for intent, skills in intent_map.items():
        if len(skills) > 1:
            for sid in skills:
                issues.append(LintIssue(
                    severity="error",
                    code="duplicate-intent",
                    skill_id=sid,
                    message=f"Intent '{intent}' is also declared by: {', '.join(s for s in skills if s != sid)}",
                    detail="Non-deterministic skill selection at runtime.",
                ))
    return issues


def _check_orphan_skills(g: Graph) -> list[LintIssue]:
    """
    Detect skills that no other skill depends on and that have no required state
    that another skill yields (completely isolated nodes in the skill graph).

    An orphan skill is not necessarily a bug, but it is a common sign of a
    forgotten skill or a skill that was never wired into the workflow.
    """
    all_skill_uris = list(g.subjects(OC.resolvesIntent))
    all_skill_ids  = {_local(s): s for s in all_skill_uris}

    # Skills that are depended upon by at least one other skill
    depended_upon = {_local(o) for _, o in g.subject_objects(OC.dependsOn)}

    issues: list[LintIssue] = []
    for sid in all_skill_ids:
        if sid not in depended_upon:
            # Also check: does any skill yield a state this skill requires?
            skill_uri   = all_skill_ids[sid]
            required    = {str(o) for o in g.objects(skill_uri, OC.requiresState)}
            all_yielded = {str(o) for o in g.objects(predicate=OC.yieldsState)}
            reachable   = bool(required & all_yielded)

            if not reachable and required:
                issues.append(LintIssue(
                    severity="info",
                    code="orphan-skill",
                    skill_id=sid,
                    message=f"'{sid}' has no dependents and its required states are never yielded",
                    detail="Consider adding oc:dependsOn edges or verify this skill is an entry point.",
                ))
    return issues
