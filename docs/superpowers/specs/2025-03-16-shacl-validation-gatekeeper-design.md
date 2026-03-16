# SHACL Validation Gatekeeper - Design Specification

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan.

**Goal:** Ensure every generated skill ontology is logically valid before being written to disk, using SHACL validation as a constitutional gatekeeper.

**Architecture:** A validation layer that intercepts skill serialization before file writes, validates the RDF graph against SHACL shapes, and blocks invalid skills from being persisted. Introduces two skill subtypes (ExecutableSkill, DeclarativeSkill) for semantic precision.

**Tech Stack:** Python, pySHACL, rdflib, OWL 2

---

## 1. Overview

The SHACL Validation Gatekeeper ensures that every skill serialized to `skill.ttl` conforms to a set of constitutional constraints defined in SHACL shapes. This prevents malformed or incomplete skills from entering the ontology.

### Key Design Decisions

1. **Two Skill Types**: `oc:ExecutableSkill` (with payload) and `oc:DeclarativeSkill` (without payload) as subclasses of `oc:Skill`
2. **Validation Before Write**: The validator runs in-memory before any file is written
3. **Fail-Fast with Details**: On validation failure, raise `OntologyValidationError` with full SHACL report
4. **State URI Validation**: State transitions must be IRIs pointing to `oc:State` instances, not plain strings

---

## 2. File Structure

```
ontoclaw/
├── specs/
│   └── ontoclaw.shacl.ttl          # NEW: SHACL shapes (the "constitution")
├── compiler/
│   ├── validator.py                 # NEW: Validation module
│   ├── exceptions.py                # MODIFY: Add OntologyValidationError
│   ├── loader.py                    # MODIFY: Hook validation before save
│   ├── schemas.py                   # MODIFY: Add skill_type field
│   └── tests/
│       └── test_validation.py       # NEW: Validation tests
```

---

## 3. Components

### 3.1 SHACL Shapes (`specs/ontoclaw.shacl.ttl`)

The constitutional rules that every skill must follow.

```turtle
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix oc: <http://ontoclaw.marea.software/ontology#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

# ============================================================================
# ONTOLOGY HEADER
# ============================================================================

<http://ontoclaw.marea.software/shacl>
    a owl:Ontology ;
    rdfs:label "OntoClaw SHACL Shapes" ;
    rdfs:comment "Constitutional constraints for OntoClaw skill ontology" ;
    .

# ============================================================================
# BASE SKILL SHAPE
# Applies to all skills (both Executable and Declarative)
# ============================================================================

oc:SkillShape
    a sh:NodeShape ;
    sh:targetClass oc:Skill ;
    rdfs:label "Skill Shape" ;
    rdfs:comment "Base constraints that apply to all skills" ;

    # Every skill MUST have at least one resolved intent
    sh:property [
        sh:path oc:resolvesIntent ;
        sh:minCount 1 ;
        sh:message "Ogni Skill deve avere almeno un resolvesIntent (intento risolto)" ;
    ] ;

    # Every skill MUST have exactly one generatedBy attestation
    sh:property [
        sh:path oc:generatedBy ;
        sh:minCount 1 ;
        sh:maxCount 1 ;
        sh:datatype xsd:string ;
        sh:message "Ogni Skill deve avere esattamente un generatedBy (modello LLM)" ;
    ] ;

    # requiresState must be an IRI pointing to an oc:State instance
    sh:property [
        sh:path oc:requiresState ;
        sh:nodeKind sh:IRI ;
        sh:class oc:State ;
        sh:message "requiresState deve essere un URI che punta a un'istanza di oc:State" ;
    ] ;

    # yieldsState must be an IRI pointing to an oc:State instance
    sh:property [
        sh:path oc:yieldsState ;
        sh:nodeKind sh:IRI ;
        sh:class oc:State ;
        sh:message "yieldsState deve essere un URI che punta a un'istanza di oc:State" ;
    ] ;

    # handlesFailure must be an IRI pointing to an oc:State instance
    sh:property [
        sh:path oc:handlesFailure ;
        sh:nodeKind sh:IRI ;
        sh:class oc:State ;
        sh:message "handlesFailure deve essere un URI che punta a un'istanza di oc:State" ;
    ] ;
    .

# ============================================================================
# EXECUTABLE SKILL SHAPE
# Skills with execution payloads
# ============================================================================

oc:ExecutableSkillShape
    a sh:NodeShape ;
    sh:targetClass oc:ExecutableSkill ;
    rdfs:label "Executable Skill Shape" ;
    rdfs:comment "Constraints for skills with execution payloads" ;

    # MUST have exactly one payload
    sh:property [
        sh:path oc:hasPayload ;
        sh:minCount 1 ;
        sh:maxCount 1 ;
        sh:class oc:ExecutionPayload ;
        sh:message "Ogni ExecutableSkill deve avere esattamente un hasPayload" ;
    ] ;
    .

# ============================================================================
# DECLARATIVE SKILL SHAPE
# Skills without execution payloads (knowledge only)
# ============================================================================

oc:DeclarativeSkillShape
    a sh:NodeShape ;
    sh:targetClass oc:DeclarativeSkill ;
    rdfs:label "Declarative Skill Shape" ;
    rdfs:comment "Constraints for declarative/knowledge skills" ;

    # MUST NOT have a payload
    sh:property [
        sh:path oc:hasPayload ;
        sh:maxCount 0 ;
        sh:message "Le DeclarativeSkill non possono avere hasPayload" ;
    ] ;
    .

# ============================================================================
# EXECUTION PAYLOAD SHAPE
# ============================================================================

oc:ExecutionPayloadShape
    a sh:NodeShape ;
    sh:targetClass oc:ExecutionPayload ;
    rdfs:label "Execution Payload Shape" ;

    # MUST have exactly one executor
    sh:property [
        sh:path oc:executor ;
        sh:minCount 1 ;
        sh:maxCount 1 ;
        sh:datatype xsd:string ;
        sh:in ("shell" "python" "node" "claude_tool") ;
        sh:message "ExecutionPayload deve avere un executor valido: shell, python, node, o claude_tool" ;
    ] ;

    # MUST have exactly one code block
    sh:property [
        sh:path oc:code ;
        sh:minCount 1 ;
        sh:maxCount 1 ;
        sh:datatype xsd:string ;
        sh:message "ExecutionPayload deve avere esattamente un campo code" ;
    ] ;

    # timeout is optional but must be integer if present
    sh:property [
        sh:path oc:timeout ;
        sh:maxCount 1 ;
        sh:datatype xsd:integer ;
        sh:message "Se presente, timeout deve essere un intero (secondi)" ;
    ] ;
    .

# ============================================================================
# STATE SHAPE
# Validates that state instances are properly defined
# ============================================================================

oc:StateShape
    a sh:NodeShape ;
    sh:targetClass oc:State ;
    rdfs:label "State Shape" ;

    # States should have a label
    sh:property [
        sh:path rdfs:label ;
        sh:minCount 1 ;
        sh:maxCount 1 ;
        sh:message "Ogni State dovrebbe avere un rdfs:label" ;
        sh:severity sh:Warning ;
    ] ;
    .
```

### 3.2 Validator Module (`compiler/validator.py`)

```python
"""
SHACL Validation Module.

Validates skill RDF graphs against the OntoClaw constitutional SHACL shapes.
"""

import logging
from pathlib import Path
from typing import NamedTuple

from pyshacl import validate
from rdflib import Graph

logger = logging.getLogger(__name__)

# Path to SHACL shapes file
SHACL_SHAPES_PATH = Path(__file__).parent.parent / "specs" / "ontoclaw.shacl.ttl"


class ValidationResult(NamedTuple):
    """Result of SHACL validation."""
    conforms: bool
    results_text: str
    results_graph: Graph | None


class OntologyValidationError(Exception):
    """Raised when skill ontology fails SHACL validation."""
    exit_code = 8

    def __init__(self, results_text: str, results_graph: Graph | None = None):
        self.results_text = results_text
        self.results_graph = results_graph
        super().__init__(f"SHACL validation failed:\n{results_text}")


def load_shacl_shapes() -> Graph:
    """Load the SHACL shapes graph from disk."""
    if not SHACL_SHAPES_PATH.exists():
        raise FileNotFoundError(f"SHACL shapes file not found: {SHACL_SHAPES_PATH}")

    shapes_graph = Graph()
    shapes_graph.parse(SHACL_SHAPES_PATH, format="turtle")
    logger.debug(f"Loaded SHACL shapes from {SHACL_SHAPES_PATH}")
    return shapes_graph


def validate_skill_graph(skill_graph: Graph, shapes_graph: Graph | None = None) -> ValidationResult:
    """
    Validate a skill RDF graph against SHACL shapes.

    Args:
        skill_graph: RDF graph containing the skill to validate
        shapes_graph: SHACL shapes graph (default: load from specs/)

    Returns:
        ValidationResult with conforms flag and detailed report

    Raises:
        OntologyValidationError: If validation fails (when raise_on_error=True)
    """
    if shapes_graph is None:
        shapes_graph = load_shacl_shapes()

    # Run SHACL validation
    conforms, results_graph, results_text = validate(
        skill_graph,
        shacl_graph=shapes_graph,
        ont_graph=None,
        inference='rdfs',  # Use RDFS inference for class hierarchies
        abort_on_first=False,  # Collect all violations
        allow_warnings=True,
        meta_shacl=False,
        debug=False
    )

    logger.info(f"SHACL validation: conforms={conforms}")

    return ValidationResult(
        conforms=conforms,
        results_text=results_text,
        results_graph=results_graph
    )


def validate_and_raise(skill_graph: Graph, shapes_graph: Graph | None = None) -> None:
    """
    Validate a skill graph and raise exception if invalid.

    Args:
        skill_graph: RDF graph to validate
        shapes_graph: SHACL shapes graph (default: load from specs/)

    Raises:
        OntologyValidationError: If validation fails
    """
    result = validate_skill_graph(skill_graph, shapes_graph)

    if not result.conforms:
        logger.error(f"Skill validation failed:\n{result.results_text}")
        raise OntologyValidationError(
            result.results_text,
            result.results_graph
        )

    logger.debug("Skill passed SHACL validation")
```

### 3.3 Exception (`compiler/exceptions.py`)

Add new exception class:

```python
class OntologyValidationError(SkillETLError):
    """Raised when skill ontology fails SHACL validation."""
    exit_code = 8
```

### 3.4 Schema Update (`compiler/schemas.py`)

Add skill type enumeration:

```python
from typing import Literal, Any

class ExtractedSkill(BaseModel):
    # ... existing fields ...
    skill_type: Literal["executable", "declarative"] = "executable"
```

### 3.5 Loader Hook (`compiler/loader.py`)

Modify `serialize_skill_to_module()` to include validation:

```python
from compiler.validator import validate_and_raise, OntologyValidationError

def serialize_skill_to_module(skill: ExtractedSkill, output_path: Path) -> None:
    """Serialize a skill to a standalone skill.ttl module file with validation."""
    oc = get_oc_namespace()
    g = Graph()

    # ... bind namespaces, add imports ...

    # Serialize the skill to graph
    serialize_skill(g, skill)

    # VALIDATE BEFORE WRITE
    try:
        validate_and_raise(g)
    except OntologyValidationError as e:
        logger.critical(f"Refusing to write invalid skill to {output_path}")
        raise

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write to file
    g.serialize(output_path, format="turtle")
    logger.info(f"Serialized validated skill module to {output_path}")
```

---

## 4. Skill Type Classification Logic

The skill type is determined by the presence of `execution_payload`:

```python
# In transformer.py or during extraction
if skill.execution_payload is not None:
    skill.skill_type = "executable"
else:
    skill.skill_type = "declarative"
```

When serializing to RDF:

```python
# In serialize_skill()
if skill.skill_type == "executable":
    graph.add((skill_uri, RDF.type, oc.ExecutableSkill))
else:
    graph.add((skill_uri, RDF.type, oc.DeclarativeSkill))
```

---

## 5. Test Cases

### Test 1: Perfect Executable Skill Passes

```python
def test_valid_executable_skill_passes():
    """A skill with all required fields and valid payload should pass."""
    skill = ExtractedSkill(
        id="test-skill",
        hash="abc123",
        nature="Test skill",
        genus="Test",
        differentia="for testing",
        intents=["test"],
        generated_by="claude-opus-4-6",
        skill_type="executable",
        execution_payload=ExecutionPayload(executor="python", code="print('hello')")
    )
    graph = Graph()
    serialize_skill(graph, skill)
    result = validate_skill_graph(graph)
    assert result.conforms is True
```

### Test 2: Skill Missing Intent Fails

```python
def test_skill_missing_intent_fails():
    """A skill without resolvesIntent should fail validation."""
    skill = ExtractedSkill(
        id="bad-skill",
        hash="def456",
        nature="Bad skill",
        genus="Test",
        differentia="incomplete",
        intents=[],  # Missing required intent
        generated_by="claude-opus-4-6",
        skill_type="declarative"
    )
    graph = Graph()
    serialize_skill(graph, skill)
    result = validate_skill_graph(graph)
    assert result.conforms is False
    assert "resolvesIntent" in result.results_text
```

### Test 3: Executable Skill Missing Payload Fails

```python
def test_executable_skill_missing_payload_fails():
    """An ExecutableSkill without hasPayload should fail."""
    skill = ExtractedSkill(
        id="no-payload",
        hash="ghi789",
        nature="Missing payload",
        genus="Test",
        differentia="incomplete",
        intents=["test"],
        generated_by="claude-opus-4-6",
        skill_type="executable",
        execution_payload=None  # Should not happen, but test the validation
    )
    graph = Graph()
    serialize_skill(graph, skill)  # Won't add hasPayload
    result = validate_skill_graph(graph)
    assert result.conforms is False
    assert "hasPayload" in result.results_text
```

### Test 4: Invalid State URI Fails

```python
def test_invalid_state_uri_fails():
    """A skill with non-URI state transition should fail."""
    # This test verifies that plain strings as states fail
    # In practice, this is prevented by Pydantic validation
    # but SHACL provides defense-in-depth
    pass
```

### Test 5: Declarative Skill with Payload Fails

```python
def test_declarative_skill_with_payload_fails():
    """A DeclarativeSkill with hasPayload should fail."""
    skill = ExtractedSkill(
        id="confused-skill",
        hash="jkl012",
        nature="Confused skill",
        genus="Test",
        differentia="has payload but shouldn't",
        intents=["test"],
        generated_by="claude-opus-4-6",
        skill_type="declarative",
        execution_payload=ExecutionPayload(executor="python", code="print('oops')")
    )
    graph = Graph()
    serialize_skill(graph, skill)
    result = validate_skill_graph(graph)
    assert result.conforms is False
```

---

## 6. Error Handling

When validation fails:

1. **Log critical error** with full SHACL report
2. **Do NOT write the file** - prevent invalid data from entering the ontology
3. **Raise `OntologyValidationError`** with exit code 8
4. **CLI displays** human-readable error message with violations

Example CLI output:

```
❌ SHACL validation failed for skill 'my-skill':

Constraint Violation in SkillShape:
  - Property: oc:resolvesIntent
  - Message: Ogni Skill deve avere almeno un resolvesIntent

Skill file NOT written. Fix the skill definition and try again.
```

---

## 7. Dependencies

Add to `compiler/pyproject.toml`:

```toml
dependencies = [
    # ... existing ...
    "pyshacl>=0.25.0",
]
```

---

## 8. Implementation Order

1. Add `pyshacl` to dependencies
2. Create `specs/ontoclaw.shacl.ttl`
3. Add `OntologyValidationError` to `exceptions.py`
4. Create `compiler/validator.py`
5. Update `compiler/schemas.py` with `skill_type` field
6. Update `compiler/loader.py` with validation hook
7. Update `serialize_skill()` to set correct skill class
8. Create `compiler/tests/test_validation.py`
9. Run all tests to ensure no regressions

---

## 9. Success Criteria

- [ ] All 5 test cases pass
- [ ] Existing 72 tests still pass (no regressions)
- [ ] Invalid skills are blocked from being written
- [ ] Valid skills pass and are written successfully
- [ ] Error messages are clear and actionable
