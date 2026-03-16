"""
RDF Ontology Loader Module.

Handles OWL 2 RDF/Turtle serialization, intelligent merging,
and atomic writes for the skill ontology.
"""

import hashlib
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

import owlrl
import rdflib
from rdflib import Graph, Namespace, RDF, RDFS, OWL, Literal, URIRef
from rdflib.namespace import DCTERMS, SKOS, PROV

from schemas import ExtractedSkill, Requirement, ExecutionPayload
from exceptions import OntologyLoadError

logger = logging.getLogger(__name__)

# Namespace for our ontology
AG = Namespace("http://agentic.web/ontology#")


def create_ontology_graph() -> Graph:
    """
    Create a new ontology graph with OWL 2 declarations.

    Returns:
        Graph with ontology header, classes, and property definitions
    """
    g = Graph()

    # Bind namespaces
    g.bind("ag", AG)
    g.bind("owl", OWL)
    g.bind("rdf", RDF)
    g.bind("rdfs", RDFS)
    g.bind("dcterms", DCTERMS)
    g.bind("skos", SKOS)
    g.bind("prov", PROV)

    # Ontology header
    ontology_uri = URIRef("http://agentic.web/ontology")
    g.add((ontology_uri, RDF.type, OWL.Ontology))
    g.add((ontology_uri, DCTERMS.title, Literal("Agentic Skills Ontology")))
    g.add((ontology_uri, DCTERMS.description, Literal(
        "Knowledge graph of agent skills extracted from markdown"
    )))

    # Classes
    g.add((AG.Skill, RDF.type, OWL.Class))
    g.add((AG.Tool, RDF.type, OWL.Class))
    g.add((AG.Tool, RDFS.subClassOf, AG.Skill))
    g.add((AG.Concept, RDF.type, OWL.Class))
    g.add((AG.Concept, RDFS.subClassOf, AG.Skill))
    g.add((AG.Work, RDF.type, OWL.Class))
    g.add((AG.Work, RDFS.subClassOf, AG.Skill))

    # Object Properties with OWL characteristics
    # dependsOn - asymmetric (if A depends on B, B cannot depend on A)
    g.add((AG.dependsOn, RDF.type, OWL.ObjectProperty))
    g.add((AG.dependsOn, RDF.type, OWL.AsymmetricProperty))
    g.add((AG.dependsOn, RDFS.domain, AG.Skill))
    g.add((AG.dependsOn, RDFS.range, AG.Skill))
    g.add((AG.dependsOn, OWL.inverseOf, AG.enables))

    # enables - inverse of dependsOn
    g.add((AG.enables, RDF.type, OWL.ObjectProperty))
    g.add((AG.enables, RDFS.domain, AG.Skill))
    g.add((AG.enables, RDFS.range, AG.Skill))

    # extends - transitive (if A extends B and B extends C, A extends C)
    g.add((AG.extends, RDF.type, OWL.ObjectProperty))
    g.add((AG.extends, RDF.type, OWL.TransitiveProperty))
    g.add((AG.extends, RDFS.domain, AG.Skill))
    g.add((AG.extends, RDFS.range, AG.Skill))
    g.add((AG.extends, OWL.inverseOf, AG.isExtendedBy))

    # isExtendedBy - inverse of extends
    g.add((AG.isExtendedBy, RDF.type, OWL.ObjectProperty))
    g.add((AG.isExtendedBy, RDFS.domain, AG.Skill))
    g.add((AG.isExtendedBy, RDFS.range, AG.Skill))

    # contradicts - symmetric (if A contradicts B, B contradicts A)
    g.add((AG.contradicts, RDF.type, OWL.ObjectProperty))
    g.add((AG.contradicts, RDF.type, OWL.SymmetricProperty))
    g.add((AG.contradicts, RDFS.domain, AG.Skill))
    g.add((AG.contradicts, RDFS.range, AG.Skill))

    # implements
    g.add((AG.implements, RDF.type, OWL.ObjectProperty))
    g.add((AG.implements, RDFS.domain, AG.Skill))
    g.add((AG.implements, RDFS.range, AG.Skill))
    g.add((AG.implements, OWL.inverseOf, AG.isImplementedBy))

    # isImplementedBy - inverse of implements
    g.add((AG.isImplementedBy, RDF.type, OWL.ObjectProperty))
    g.add((AG.isImplementedBy, RDFS.domain, AG.Skill))
    g.add((AG.isImplementedBy, RDFS.range, AG.Skill))

    # exemplifies
    g.add((AG.exemplifies, RDF.type, OWL.ObjectProperty))
    g.add((AG.exemplifies, RDFS.domain, AG.Skill))
    g.add((AG.exemplifies, RDFS.range, AG.Skill))
    g.add((AG.exemplifies, OWL.inverseOf, AG.isExemplifiedBy))

    # isExemplifiedBy - inverse of exemplifies
    g.add((AG.isExemplifiedBy, RDF.type, OWL.ObjectProperty))
    g.add((AG.isExemplifiedBy, RDFS.domain, AG.Skill))
    g.add((AG.isExemplifiedBy, RDFS.range, AG.Skill))

    # Datatype Properties
    g.add((AG.contentHash, RDF.type, OWL.DatatypeProperty))
    g.add((AG.nature, RDF.type, OWL.DatatypeProperty))
    g.add((AG.differentia, RDF.type, OWL.DatatypeProperty))
    g.add((AG.resolvesIntent, RDF.type, OWL.DatatypeProperty))
    g.add((AG.hasConstraint, RDF.type, OWL.DatatypeProperty))
    g.add((AG.executor, RDF.type, OWL.DatatypeProperty))
    g.add((AG.code, RDF.type, OWL.DatatypeProperty))
    g.add((AG.timeout, RDF.type, OWL.DatatypeProperty))
    g.add((AG.requirementValue, RDF.type, OWL.DatatypeProperty))
    g.add((AG.isOptional, RDF.type, OWL.DatatypeProperty))

    # Object Properties for relations
    g.add((AG.hasRequirement, RDF.type, OWL.ObjectProperty))
    g.add((AG.hasPayload, RDF.type, OWL.ObjectProperty))

    return g


def serialize_skill(graph: Graph, skill: ExtractedSkill) -> None:
    """
    Serialize a skill to RDF triples in the graph.

    Args:
        graph: RDF graph to add triples to
        skill: ExtractedSkill to serialize
    """
    # Create skill URI from hash
    skill_uri = AG[f"skill_{skill.hash[:16]}"]

    # Basic properties
    graph.add((skill_uri, RDF.type, AG.Skill))
    graph.add((skill_uri, DCTERMS.identifier, Literal(skill.id)))
    graph.add((skill_uri, AG.contentHash, Literal(skill.hash)))
    graph.add((skill_uri, AG.nature, Literal(skill.nature)))
    graph.add((skill_uri, SKOS.broader, Literal(skill.genus)))
    graph.add((skill_uri, AG.differentia, Literal(skill.differentia)))

    # Intents
    for intent in skill.intents:
        graph.add((skill_uri, AG.resolvesIntent, Literal(intent)))

    # Requirements (as blank nodes)
    for req in skill.requirements:
        req_hash = hashlib.sha256(f"{req.type}:{req.value}".encode()).hexdigest()[:8]
        req_uri = AG[f"req_{req_hash}"]

        # Requirement class based on type
        req_class = AG[f"Requirement{req.type}"]
        graph.add((req_uri, RDF.type, req_class))
        graph.add((req_uri, AG.requirementValue, Literal(req.value)))
        graph.add((req_uri, AG.isOptional, Literal(req.optional)))
        graph.add((skill_uri, AG.hasRequirement, req_uri))

    # Relations
    for dep in skill.depends_on:
        graph.add((skill_uri, AG.dependsOn, AG[f"skill_{dep}"]))

    for ext in skill.extends:
        graph.add((skill_uri, AG.extends, AG[f"skill_{ext}"]))

    for cont in skill.contradicts:
        graph.add((skill_uri, AG.contradicts, AG[f"skill_{cont}"]))

    # Constraints
    for constraint in skill.constraints:
        graph.add((skill_uri, AG.hasConstraint, Literal(constraint)))

    # Execution payload
    if skill.execution_payload:
        payload_uri = AG[f"payload_{skill.hash[:16]}"]
        graph.add((payload_uri, AG.executor, Literal(skill.execution_payload.executor)))
        graph.add((payload_uri, AG.code, Literal(skill.execution_payload.code)))
        if skill.execution_payload.timeout:
            graph.add((payload_uri, AG.timeout, Literal(skill.execution_payload.timeout)))
        graph.add((skill_uri, AG.hasPayload, payload_uri))

    # Provenance
    if skill.provenance:
        graph.add((skill_uri, PROV.wasDerivedFrom, Literal(skill.provenance)))


def load_ontology(ontology_path: Path) -> Graph:
    """
    Load an existing ontology from file.

    Args:
        ontology_path: Path to skills.ttl file

    Returns:
        RDF Graph with loaded ontology

    Raises:
        OntologyLoadError: If file cannot be loaded
    """
    if not ontology_path.exists():
        logger.info(f"Creating new ontology at {ontology_path}")
        return create_ontology_graph()

    try:
        graph = Graph()
        graph.parse(ontology_path, format="turtle")
        logger.info(f"Loaded ontology with {len(graph)} triples")
        return graph
    except Exception as e:
        raise OntologyLoadError(f"Failed to load ontology: {e}")


def get_hash_mapping(graph: Graph) -> dict[str, URIRef]:
    """
    Extract hash → URI mapping from existing ontology.

    Args:
        graph: RDF graph to scan

    Returns:
        Dictionary mapping hashes to skill URIs
    """
    mapping = {}
    for skill_uri in graph.subjects(RDF.type, AG.Skill):
        hash_literal = graph.value(skill_uri, AG.contentHash)
        if hash_literal:
            mapping[str(hash_literal)] = skill_uri
    return mapping


def get_id_mapping(graph: Graph) -> dict[str, URIRef]:
    """
    Extract ID → URI mapping from existing ontology.

    Args:
        graph: RDF graph to scan

    Returns:
        Dictionary mapping IDs to skill URIs
    """
    mapping = {}
    for skill_uri in graph.subjects(RDF.type, AG.Skill):
        id_literal = graph.value(skill_uri, DCTERMS.identifier)
        if id_literal:
            mapping[str(id_literal)] = skill_uri
    return mapping


def remove_skill(graph: Graph, skill_uri: URIRef) -> None:
    """
    Remove all triples for a skill from the graph.

    Args:
        graph: RDF graph to modify
        skill_uri: URI of skill to remove
    """
    # Remove all triples where skill is subject
    for predicate in set(graph.predicates(subject=skill_uri)):
        for obj in graph.objects(skill_uri, predicate):
            graph.remove((skill_uri, predicate, obj))

    # Remove requirement blank nodes
    for req_uri in graph.objects(skill_uri, AG.hasRequirement):
        for p, o in list(graph.predicate_objects(req_uri)):
            graph.remove((req_uri, p, o))

    # Remove payload blank node
    payload_uri = graph.value(skill_uri, AG.hasPayload)
    if payload_uri:
        for p, o in list(graph.predicate_objects(payload_uri)):
            graph.remove((payload_uri, p, o))


def merge_skill(ontology_path: Path, skill: ExtractedSkill) -> Graph:
    """
    Intelligently merge a skill into the ontology.

    - If hash exists → skip (unchanged)
    - If same ID but different hash → remove old, add new
    - If new ID → add

    Args:
        ontology_path: Path to ontology file
        skill: Skill to merge

    Returns:
        Updated graph (not saved to disk)
    """
    graph = load_ontology(ontology_path)
    hash_mapping = get_hash_mapping(graph)
    id_mapping = get_id_mapping(graph)

    # Check if unchanged (same hash)
    if skill.hash in hash_mapping:
        logger.info(f"Skill {skill.id} unchanged (hash match), skipping")
        return graph

    # Check if updated (same ID, different hash)
    if skill.id in id_mapping:
        old_uri = id_mapping[skill.id]
        logger.info(f"Skill {skill.id} updated, removing old version")
        remove_skill(graph, old_uri)

    # Add new/updated skill
    logger.info(f"Adding skill {skill.id} to ontology")
    serialize_skill(graph, skill)

    return graph


def save_ontology_atomic(
    ontology_path: Path,
    graph: Graph,
    backup_dir: Optional[Path] = None,
    max_backups: int = 5
) -> None:
    """
    Save ontology with atomic write and backup.

    1. Backup existing file
    2. Write to temp file
    3. Atomic rename
    4. Cleanup old backups

    Args:
        ontology_path: Path to skills.ttl
        graph: RDF graph to save
        backup_dir: Directory for backups (default: ontology_dir/backups/)
        max_backups: Maximum number of backups to keep
    """
    if backup_dir is None:
        backup_dir = ontology_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    # Backup existing file
    if ontology_path.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"skills_{timestamp}.ttl"
        shutil.copy2(ontology_path, backup_path)
        logger.info(f"Created backup: {backup_path}")

    # Write to temp file
    temp_path = ontology_path.with_suffix(".ttl.tmp")
    graph.serialize(temp_path, format="turtle")

    # Atomic rename
    shutil.move(str(temp_path), str(ontology_path))
    logger.info(f"Saved ontology to {ontology_path}")

    # Cleanup old backups
    backups = sorted(backup_dir.glob("skills_*.ttl"))
    while len(backups) > max_backups:
        oldest = backups.pop(0)
        oldest.unlink()
        logger.debug(f"Removed old backup: {oldest}")


def apply_reasoning(graph: Graph) -> Graph:
    """
    Apply OWL 2 RL reasoning to infer new triples.

    Inferences:
    - Inverse: A dependsOn B → B enables A
    - Transitive: A extends B, B extends C → A extends C
    - Symmetric: A contradicts B → B contradicts A

    Args:
        graph: RDF graph to expand

    Returns:
        Same graph with inferred triples added
    """
    logger.info("Applying OWL reasoning...")
    owlrl.DeductiveClosure(owlrl.OWLRL_Semantics).expand(graph)
    logger.info(f"Reasoning complete, graph now has {len(graph)} triples")
    return graph
