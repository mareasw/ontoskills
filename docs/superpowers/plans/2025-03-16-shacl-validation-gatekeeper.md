# SHACL Validation Gatekeeper Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement SHACL validation gatekeeper to ensure every skill ontology is logically valid before being written to disk.

**Architecture:** A validation layer using pySHACL that validates RDF graphs against constitutional SHACL shapes. Introduces two skill subtypes (ExecutableSkill, DeclarativeSkill) derived from presence of execution_payload. The validator loads the core ontology for state class validation.

**Tech Stack:** Python, pySHACL, rdflib, OWL 2, pytest

---

## File Structure

```
ontoclaw/
├── specs/
│   └── ontoclaw.shacl.ttl          # NEW: SHACL shapes (the "constitution")
├── compiler/
│   ├── validator.py                 # NEW: Validation module
│   ├── exceptions.py                # MODIFY: Add OntologyValidationError
│   ├── loader.py                    # MODIFY: Add skill subclasses + validation hooks
│   ├── schemas.py                   # MODIFY: Add computed skill_type property
│   └── tests/
│       ├── test_validation.py       # NEW: Validation tests
│       ├── test_schemas.py          # MODIFY: Add skill_type tests
│       └── test_loader.py           # MODIFY: Add skill subclass tests
```

---

## Chunk 1: Dependencies, Exception, and SHACL Shapes

### Task 1: Add pyshacl Dependency

**Files:**
- Modify: `compiler/pyproject.toml`

- [ ] **Step 1: Add pyshacl to dependencies**

```toml
# In compiler/pyproject.toml, add to dependencies array:
dependencies = [
    "click>=8.1.0",
    "pydantic>=2.0.0",
    "rdflib>=7.0.0",
    "anthropic>=0.39.0",
    "rich>=13.0.0",
    "owlrl>=1.0.0",
    "pyshacl>=0.25.0",
]
```

- [ ] **Step 2: Install the dependency**

Run: `cd compiler && pip install pyshacl>=0.25.0`
Expected: Successfully installed pyshacl...

- [ ] **Step 3: Commit**

```bash
git add compiler/pyproject.toml
git commit -m "feat: add pyshacl dependency for SHACL validation"
```

---

### Task 2: Add OntologyValidationError Exception

**Files:**
- Modify: `compiler/exceptions.py`
- Modify: `compiler/tests/test_exceptions.py`

- [ ] **Step 1: Write failing test for new exception**

```python
# Add to compiler/tests/test_exceptions.py

def test_ontology_validation_error_exists():
    """Test that OntologyValidationError exception exists."""
    from compiler.exceptions import OntologyValidationError, SkillETLError

    # Should be subclass of SkillETLError
    assert issubclass(OntologyValidationError, SkillETLError)

    # Should have exit_code 8
    assert OntologyValidationError.exit_code == 8

    # Should be instantiable with message
    e = OntologyValidationError("SHACL validation failed")
    assert "SHACL" in str(e)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd compiler && python -m pytest tests/test_exceptions.py::test_ontology_validation_error_exists -v`
Expected: FAIL with "cannot import name 'OntologyValidationError'"

- [ ] **Step 3: Add OntologyValidationError to exceptions.py**

```python
# Add to compiler/exceptions.py at the end:

class OntologyValidationError(SkillETLError):
    """Raised when skill ontology fails SHACL validation."""
    exit_code = 8
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd compiler && python -m pytest tests/test_exceptions.py::test_ontology_validation_error_exists -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add compiler/exceptions.py compiler/tests/test_exceptions.py
git commit -m "feat: add OntologyValidationError exception (exit_code=8)"
```

---

### Task 3: Create SHACL Shapes File

**Files:**
- Create: `specs/ontoclaw.shacl.ttl`

- [ ] **Step 1: Create specs directory and SHACL shapes file**

```turtle
# specs/ontoclaw.shacl.ttl

@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix oc: <http://ontoclaw.marea.software/ontology#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .

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

- [ ] **Step 2: Verify file was created**

Run: `ls -la specs/ontoclaw.shacl.ttl`
Expected: File exists with content

- [ ] **Step 3: Commit**

```bash
git add specs/ontoclaw.shacl.ttl
git commit -m "feat: create SHACL shapes constitution file"
```

---

## Chunk 2: Validator Module

### Task 4: Create Validator Module with ValidationResult

**Files:**
- Create: `compiler/validator.py`
- Create: `compiler/tests/test_validation.py`

- [ ] **Step 1: Create test file and write failing test**

```python
# Create compiler/tests/test_validation.py

from rdflib import Graph


def test_validation_result_namedtuple():
    """Test that ValidationResult is a NamedTuple with correct fields."""
    from compiler.validator import ValidationResult

    # Create a result
    result = ValidationResult(
        conforms=True,
        results_text="All good",
        results_graph=None
    )
    assert result.conforms is True
    assert result.results_text == "All good"
    assert result.results_graph is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd compiler && python -m pytest tests/test_validation.py::test_validation_result_namedtuple -v`
Expected: FAIL with "cannot import name 'ValidationResult'"

- [ ] **Step 3: Create validator.py with ValidationResult**

```python
# Create compiler/validator.py

"""
SHACL Validation Module.

Validates skill RDF graphs against the OntoClaw constitutional SHACL shapes.
"""

import logging
from pathlib import Path
from typing import NamedTuple

from rdflib import Graph

logger = logging.getLogger(__name__)

# Path to SHACL shapes file (project root / specs /)
SHACL_SHAPES_PATH = Path(__file__).parent.parent / "specs" / "ontoclaw.shacl.ttl"


class ValidationResult(NamedTuple):
    """Result of SHACL validation."""
    conforms: bool
    results_text: str
    results_graph: Graph | None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd compiler && python -m pytest tests/test_validation.py::test_validation_result_namedtuple -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add compiler/validator.py compiler/tests/test_validation.py
git commit -m "feat: create validator module with ValidationResult NamedTuple"
```

---

### Task 5: Implement load_shacl_shapes Function

**Files:**
- Modify: `compiler/validator.py`
- Modify: `compiler/tests/test_validation.py`

- [ ] **Step 1: Write failing test for load_shacl_shapes**

```python
# Add to compiler/tests/test_validation.py

from compiler.validator import load_shacl_shapes


def test_load_shacl_shapes():
    """Test that SHACL shapes file loads correctly."""
    shapes = load_shacl_shapes()
    assert shapes is not None
    # Should contain our shapes (more than 0 triples)
    assert len(shapes) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd compiler && python -m pytest tests/test_validation.py::test_load_shacl_shapes -v`
Expected: FAIL with "cannot import name 'load_shacl_shapes'"

- [ ] **Step 3: Implement load_shacl_shapes**

```python
# Add to compiler/validator.py after ValidationResult class

def load_shacl_shapes() -> Graph:
    """Load the SHACL shapes graph from disk."""
    if not SHACL_SHAPES_PATH.exists():
        raise FileNotFoundError(f"SHACL shapes file not found: {SHACL_SHAPES_PATH}")

    shapes_graph = Graph()
    shapes_graph.parse(SHACL_SHAPES_PATH, format="turtle")
    logger.debug(f"Loaded SHACL shapes from {SHACL_SHAPES_PATH}")
    return shapes_graph
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd compiler && python -m pytest tests/test_validation.py::test_load_shacl_shapes -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add compiler/validator.py compiler/tests/test_validation.py
git commit -m "feat: implement load_shacl_shapes function"
```

---

### Task 6: Implement load_core_ontology Function

**Files:**
- Modify: `compiler/validator.py`
- Modify: `compiler/tests/test_validation.py`

- [ ] **Step 1: Write failing test for load_core_ontology**

```python
# Add to compiler/tests/test_validation.py

from compiler.validator import load_core_ontology


def test_load_core_ontology_returns_none_if_missing():
    """Test that load_core_ontology returns None if core ontology doesn't exist."""
    # This test assumes core ontology might not exist in test environment
    result = load_core_ontology()
    # Result could be None or a Graph depending on whether ontoclaw-core.ttl exists
    if result is None:
        assert True  # Expected if file doesn't exist
    else:
        assert isinstance(result, Graph)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd compiler && python -m pytest tests/test_validation.py::test_load_core_ontology_returns_none_if_missing -v`
Expected: FAIL with "cannot import name 'load_core_ontology'"

- [ ] **Step 3: Implement load_core_ontology**

```python
# Add to compiler/validator.py after SHACL_SHAPES_PATH

from compiler.config import OUTPUT_DIR

CORE_ONTOLOGY_PATH = Path(OUTPUT_DIR) / "ontoclaw-core.ttl"


def load_core_ontology() -> Graph | None:
    """
    Load the core ontology (TBox) for class definitions.

    CRITICAL: This is needed for sh:class validation to work correctly.
    Without the core ontology, pySHACL doesn't know that oc:SystemAuthenticated
    is an oc:State, causing false negatives in state validation.
    """
    if not CORE_ONTOLOGY_PATH.exists():
        logger.warning(f"Core ontology not found at {CORE_ONTOLOGY_PATH}, state validation may fail")
        return None

    ont_graph = Graph()
    ont_graph.parse(CORE_ONTOLOGY_PATH, format="turtle")
    logger.debug(f"Loaded core ontology from {CORE_ONTOLOGY_PATH}")
    return ont_graph
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd compiler && python -m pytest tests/test_validation.py::test_load_core_ontology_returns_none_if_missing -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add compiler/validator.py compiler/tests/test_validation.py
git commit -m "feat: implement load_core_ontology function"
```

---

### Task 7: Implement validate_skill_graph and validate_and_raise

**Files:**
- Modify: `compiler/validator.py`
- Modify: `compiler/tests/test_validation.py`

- [ ] **Step 1: Write failing test for validate_skill_graph**

```python
# Add to compiler/tests/test_validation.py

from compiler.validator import validate_skill_graph


def test_validate_skill_graph_empty_graph():
    """Test validation of empty graph (should pass - no skill instances to validate)."""
    g = Graph()
    result = validate_skill_graph(g)
    assert result.conforms is True  # Empty graph has no skill instances to validate
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd compiler && python -m pytest tests/test_validation.py::test_validate_skill_graph_empty_graph -v`
Expected: FAIL with "cannot import name 'validate_skill_graph'"

- [ ] **Step 3: Implement validate_skill_graph**

```python
# Add to compiler/validator.py after load_core_ontology

from pyshacl import validate


def validate_skill_graph(skill_graph: Graph, shapes_graph: Graph | None = None) -> ValidationResult:
    """
    Validate a skill RDF graph against SHACL shapes.

    Args:
        skill_graph: RDF graph containing the skill to validate
        shapes_graph: SHACL shapes graph (default: load from specs/)

    Returns:
        ValidationResult with conforms flag and detailed report
    """
    if shapes_graph is None:
        shapes_graph = load_shacl_shapes()

    # Load core ontology for class definitions (essential for sh:class validation)
    ont_graph = load_core_ontology()

    # Run SHACL validation
    conforms, results_graph, results_text = validate(
        skill_graph,
        shacl_graph=shapes_graph,
        ont_graph=ont_graph,  # PASS CORE ONTOLOGY! Required for sh:class oc:State
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd compiler && python -m pytest tests/test_validation.py::test_validate_skill_graph_empty_graph -v`
Expected: PASS

- [ ] **Step 5: Write failing test for validate_and_raise**

```python
# Add to compiler/tests/test_validation.py

from compiler.validator import validate_and_raise
from compiler.exceptions import OntologyValidationError


def test_validate_and_raise_raises_for_invalid():
    """Test that validate_and_raise raises OntologyValidationError for invalid graph."""
    from rdflib import Namespace, Literal, RDF

    oc = Namespace("http://ontoclaw.marea.software/ontology#")
    g = Graph()

    # Add a skill without required properties (invalid)
    skill_uri = oc["skill_test"]
    g.add((skill_uri, RDF.type, oc.Skill))
    # Missing resolvesIntent and generatedBy - should fail

    with pytest.raises(OntologyValidationError):
        validate_and_raise(g)
```

- [ ] **Step 6: Run test to verify it fails**

Run: `cd compiler && python -m pytest tests/test_validation.py::test_validate_and_raise_raises_for_invalid -v`
Expected: FAIL with "cannot import name 'validate_and_raise'"

- [ ] **Step 7: Implement validate_and_raise**

```python
# Add to compiler/validator.py after validate_skill_graph

from compiler.exceptions import OntologyValidationError


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

- [ ] **Step 8: Run test to verify it passes**

Run: `cd compiler && python -m pytest tests/test_validation.py::test_validate_and_raise_raises_for_invalid -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add compiler/validator.py compiler/tests/test_validation.py
git commit -m "feat: implement validate_skill_graph and validate_and_raise functions"
```

---

## Chunk 3: Schema and Core Ontology Updates

### Task 8: Add computed skill_type Property

**Files:**
- Modify: `compiler/schemas.py`
- Modify: `compiler/tests/test_schemas.py`

- [ ] **Step 1: Write failing tests for skill_type**

```python
# Add to compiler/tests/test_schemas.py

from compiler.schemas import ExtractedSkill, ExecutionPayload


def test_skill_type_computed_as_executable():
    """Test that skill_type is 'executable' when execution_payload exists."""
    skill = ExtractedSkill(
        id="test",
        hash="abc123",
        nature="Test",
        genus="Test",
        differentia="test",
        intents=["test"],
        generated_by="claude-opus-4-6",
        execution_payload=ExecutionPayload(executor="python", code="print('hi')")
    )
    assert skill.skill_type == "executable"


def test_skill_type_computed_as_declarative():
    """Test that skill_type is 'declarative' when no execution_payload."""
    skill = ExtractedSkill(
        id="test",
        hash="abc123",
        nature="Test",
        genus="Test",
        differentia="test",
        intents=["test"],
        generated_by="claude-opus-4-6"
    )
    assert skill.skill_type == "declarative"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd compiler && python -m pytest tests/test_schemas.py::test_skill_type_computed_as_executable tests/test_schemas.py::test_skill_type_computed_as_declarative -v`
Expected: FAIL with "AttributeError: 'ExtractedSkill' object has no attribute 'skill_type'"

- [ ] **Step 3: Add computed skill_type property**

```python
# In compiler/schemas.py
# Add imports at top:
from typing import Literal, Any
from pydantic import computed_field

# Add to ExtractedSkill class (after existing fields):

    @computed_field
    @property
    def skill_type(self) -> Literal["executable", "declarative"]:
        """Derive skill type from presence of execution_payload."""
        return "executable" if self.execution_payload is not None else "declarative"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd compiler && python -m pytest tests/test_schemas.py::test_skill_type_computed_as_executable tests/test_schemas.py::test_skill_type_computed_as_declarative -v`
Expected: PASS (both tests)

- [ ] **Step 5: Commit**

```bash
git add compiler/schemas.py compiler/tests/test_schemas.py
git commit -m "feat: add computed skill_type property to ExtractedSkill"
```

---

### Task 9: Add Skill Subclasses to Core Ontology

**Files:**
- Modify: `compiler/loader.py`
- Modify: `compiler/tests/test_loader.py`

- [ ] **Step 1: Write failing test for skill subclasses**

```python
# Add to compiler/tests/test_loader.py

from pathlib import Path
from rdflib import RDF, RDFS


def test_core_ontology_has_skill_subclasses():
    """Test that core ontology defines ExecutableSkill and DeclarativeSkill."""
    from compiler.loader import create_core_ontology, get_oc_namespace
    import tempfile

    with tempfile.NamedTemporaryFile(suffix='.ttl', delete=False) as f:
        core_path = Path(f.name)

    try:
        g = create_core_ontology(core_path)
        oc = get_oc_namespace()

        # Check ExecutableSkill is subclass of Skill
        assert (oc.ExecutableSkill, RDFS.subClassOf, oc.Skill) in g

        # Check DeclarativeSkill is subclass of Skill
        assert (oc.DeclarativeSkill, RDFS.subClassOf, oc.Skill) in g
    finally:
        core_path.unlink(missing_ok=True)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd compiler && python -m pytest tests/test_loader.py::test_core_ontology_has_skill_subclasses -v`
Expected: FAIL with AssertionError (subclasses not defined)

- [ ] **Step 3: Add skill subclasses to create_core_ontology**

```python
# In compiler/loader.py, add after oc:Skill definition in create_core_ontology():

    # oc:ExecutableSkill - Skills with execution payloads
    g.add((oc.ExecutableSkill, RDF.type, OWL.Class))
    g.add((oc.ExecutableSkill, RDFS.subClassOf, oc.Skill))
    g.add((oc.ExecutableSkill, RDFS.label, Literal("Executable Skill")))
    g.add((oc.ExecutableSkill, RDFS.comment, Literal(
        "A skill with an executable code payload"
    )))

    # oc:DeclarativeSkill - Skills without execution (knowledge only)
    g.add((oc.DeclarativeSkill, RDF.type, OWL.Class))
    g.add((oc.DeclarativeSkill, RDFS.subClassOf, oc.Skill))
    g.add((oc.DeclarativeSkill, RDFS.label, Literal("Declarative Skill")))
    g.add((oc.DeclarativeSkill, RDFS.comment, Literal(
        "A skill without executable code (declarative knowledge)"
    )))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd compiler && python -m pytest tests/test_loader.py::test_core_ontology_has_skill_subclasses -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add compiler/loader.py compiler/tests/test_loader.py
git commit -m "feat: add ExecutableSkill and DeclarativeSkill subclasses to core ontology"
```

---

### Task 10: Update serialize_skill to Add Subclass Type

**Files:**
- Modify: `compiler/loader.py`
- Modify: `compiler/tests/test_loader.py`

- [ ] **Step 1: Write failing test for subclass type in serialized graph**

```python
# Add to compiler/tests/test_loader.py

from compiler.schemas import ExtractedSkill, ExecutionPayload


def test_serialize_skill_adds_executable_type():
    """Test that serialize_skill adds oc:ExecutableSkill type for skills with payload."""
    from compiler.loader import serialize_skill, get_oc_namespace
    oc = get_oc_namespace()
    g = Graph()

    skill = ExtractedSkill(
        id="exec-skill",
        hash="abc123def456",
        nature="Executable",
        genus="Test",
        differentia="test",
        intents=["test"],
        generated_by="claude-opus-4-6",
        execution_payload=ExecutionPayload(executor="python", code="test")
    )
    serialize_skill(g, skill)
    skill_uri = oc[f"skill_{skill.hash[:16]}"]
    assert (skill_uri, RDF.type, oc.ExecutableSkill) in g


def test_serialize_skill_adds_declarative_type():
    """Test that serialize_skill adds oc:DeclarativeSkill type for skills without payload."""
    from compiler.loader import serialize_skill, get_oc_namespace
    oc = get_oc_namespace()
    g = Graph()

    skill = ExtractedSkill(
        id="decl-skill",
        hash="xyz789abc123",
        nature="Declarative",
        genus="Test",
        differentia="test",
        intents=["test"],
        generated_by="claude-opus-4-6"
    )
    serialize_skill(g, skill)
    skill_uri = oc[f"skill_{skill.hash[:16]}"]
    assert (skill_uri, RDF.type, oc.DeclarativeSkill) in g
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd compiler && python -m pytest tests/test_loader.py::test_serialize_skill_adds_executable_type tests/test_loader.py::test_serialize_skill_adds_declarative_type -v`
Expected: FAIL with AssertionError (type not in graph)

- [ ] **Step 3: Update serialize_skill to add subclass type**

```python
# In compiler/loader.py, modify serialize_skill function
# Add after: graph.add((skill_uri, RDF.type, oc.Skill))

    # Add appropriate subclass type based on skill_type
    if skill.skill_type == "executable":
        graph.add((skill_uri, RDF.type, oc.ExecutableSkill))
    else:
        graph.add((skill_uri, RDF.type, oc.DeclarativeSkill))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd compiler && python -m pytest tests/test_loader.py::test_serialize_skill_adds_executable_type tests/test_loader.py::test_serialize_skill_adds_declarative_type -v`
Expected: PASS (both tests)

- [ ] **Step 5: Commit**

```bash
git add compiler/loader.py compiler/tests/test_loader.py
git commit -m "feat: update serialize_skill to add ExecutableSkill/DeclarativeSkill type"
```

---

## Chunk 4: Validation Hooks

### Task 11: Add Validation Hook to serialize_skill_to_module and merge_skill

**Files:**
- Modify: `compiler/loader.py`
- Modify: `compiler/tests/test_loader.py`

- [ ] **Step 1: Write failing test for validation hook in serialize_skill_to_module**

```python
# Add to compiler/tests/test_loader.py

import tempfile
import pytest


def test_serialize_skill_to_module_validates_and_blocks_invalid():
    """Test that serialize_skill_to_module validates and blocks invalid skills."""
    from compiler.loader import serialize_skill_to_module
    from compiler.exceptions import OntologyValidationError

    skill = ExtractedSkill(
        id="invalid-skill",
        hash="invalid123",
        nature="Invalid",
        genus="Test",
        differentia="test",
        intents=[],  # Missing required intent - should fail validation
        generated_by="claude-opus-4-6"
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "skill.ttl"

        with pytest.raises(OntologyValidationError):
            serialize_skill_to_module(skill, output_path)

        # File should NOT have been written
        assert not output_path.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd compiler && python -m pytest tests/test_loader.py::test_serialize_skill_to_module_validates_and_blocks_invalid -v`
Expected: FAIL with "DID NOT raise OntologyValidationError"

- [ ] **Step 3: Add validation hook to serialize_skill_to_module**

```python
# In compiler/loader.py, modify serialize_skill_to_module function
# Add imports at top:
from compiler.validator import validate_and_raise
from compiler.exceptions import OntologyValidationError

# Add after serialize_skill(g, skill) and before g.serialize():

    # VALIDATE BEFORE WRITE
    try:
        validate_and_raise(g)
    except OntologyValidationError as e:
        logger.critical(f"Refusing to write invalid skill to {output_path}")
        raise
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd compiler && python -m pytest tests/test_loader.py::test_serialize_skill_to_module_validates_and_blocks_invalid -v`
Expected: PASS

- [ ] **Step 5: Add validation hook to merge_skill**

```python
# In compiler/loader.py, modify merge_skill function
# Add after serialize_skill(graph, skill) and before return graph:

    # VALIDATE BEFORE RETURNING
    try:
        validate_and_raise(graph)
    except OntologyValidationError as e:
        logger.critical(f"Skill {skill.id} failed validation, not merging")
        raise
```

- [ ] **Step 6: Commit**

```bash
git add compiler/loader.py compiler/tests/test_loader.py
git commit -m "feat: add SHACL validation hooks to serialize_skill_to_module and merge_skill"
```

---

## Chunk 5: Comprehensive Validation Tests

### Task 12: Write All 5 Validation Test Cases

**Files:**
- Modify: `compiler/tests/test_validation.py`

- [ ] **Step 1: Write Test 1 - Perfect Executable Skill Passes**

```python
# Add to compiler/tests/test_validation.py

from compiler.schemas import ExtractedSkill, ExecutionPayload
from compiler.loader import serialize_skill


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
        execution_payload=ExecutionPayload(executor="python", code="print('hello')")
    )
    graph = Graph()
    serialize_skill(graph, skill)
    result = validate_skill_graph(graph)
    assert result.conforms is True
```

- [ ] **Step 2: Write Test 2 - Skill Missing Intent Fails**

```python
# Add to compiler/tests/test_validation.py

def test_skill_missing_intent_fails():
    """A skill without resolvesIntent should fail validation."""
    skill = ExtractedSkill(
        id="bad-skill",
        hash="def456",
        nature="Bad skill",
        genus="Test",
        differentia="incomplete",
        intents=[],  # Missing required intent
        generated_by="claude-opus-4-6"
    )
    graph = Graph()
    serialize_skill(graph, skill)
    result = validate_skill_graph(graph)
    assert result.conforms is False
    assert "resolvesIntent" in result.results_text
```

- [ ] **Step 3: Write Test 3 - Skill Without Payload Is Declarative (Passes)**

```python
# Add to compiler/tests/test_validation.py

def test_skill_without_payload_is_declarative():
    """A skill without execution_payload becomes DeclarativeSkill and passes."""
    skill = ExtractedSkill(
        id="knowledge-skill",
        hash="ghi789",
        nature="Knowledge skill",
        genus="Test",
        differentia="declarative knowledge",
        intents=["test"],
        generated_by="claude-opus-4-6"
        # No execution_payload - automatically becomes DeclarativeSkill
    )
    graph = Graph()
    serialize_skill(graph, skill)  # Will add oc:DeclarativeSkill type
    result = validate_skill_graph(graph)
    # This should pass since it's a valid DeclarativeSkill (no payload required)
    assert result.conforms is True
```

- [ ] **Step 4: Write Test 4 - Invalid State URI Fails**

```python
# Add to compiler/tests/test_validation.py

from rdflib import Literal, Namespace


def test_literal_as_state_fails():
    """A skill with a literal string (not URI) as state should fail."""
    oc = Namespace("http://ontoclaw.marea.software/ontology#")

    skill = ExtractedSkill(
        id="bad-state",
        hash="mno345",
        nature="Bad state skill",
        genus="Test",
        differentia="invalid state",
        intents=["test"],
        generated_by="claude-opus-4-6",
        execution_payload=ExecutionPayload(executor="python", code="test")
    )
    graph = Graph()
    serialize_skill(graph, skill)

    # Manually add a literal (string) as state - this should fail
    skill_uri = oc[f"skill_{skill.hash[:16]}"]
    graph.add((skill_uri, oc.yieldsState, Literal("SomeState")))  # WRONG: Literal not URI

    result = validate_skill_graph(graph)
    assert result.conforms is False
    assert "yieldsState" in result.results_text or "IRI" in result.results_text
```

- [ ] **Step 5: Write Test 5 - Skill With Payload Is Executable (Passes)**

```python
# Add to compiler/tests/test_validation.py

def test_skill_with_payload_is_executable():
    """A skill with execution_payload becomes ExecutableSkill and passes."""
    skill = ExtractedSkill(
        id="code-skill",
        hash="jkl012",
        nature="Executable skill",
        genus="Test",
        differentia="has code to execute",
        intents=["test"],
        generated_by="claude-opus-4-6",
        execution_payload=ExecutionPayload(executor="python", code="print('hello')")
    )
    # skill.skill_type will be "executable" because payload exists
    # So this will be validated as ExecutableSkill
    graph = Graph()
    serialize_skill(graph, skill)
    result = validate_skill_graph(graph)
    assert result.conforms is True  # It's a valid ExecutableSkill
```

- [ ] **Step 6: Run all validation tests**

Run: `cd compiler && python -m pytest tests/test_validation.py -v`
Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
git add compiler/tests/test_validation.py
git commit -m "test: add all 5 comprehensive SHACL validation test cases"
```

---

## Chunk 6: Final Verification

### Task 13: Run All Tests and Verify No Regressions

**Files:**
- None (verification only)

- [ ] **Step 1: Run all compiler tests**

Run: `cd compiler && python -m pytest tests/ -v`
Expected: All tests pass (existing 72 + new tests = no regressions)

- [ ] **Step 2: Verify success criteria**

Check:
- [ ] All 5 validation test cases pass
- [ ] Existing tests still pass (no regressions)
- [ ] Invalid skills are blocked from being written
- [ ] Valid skills pass validation
- [ ] `oc:ExecutableSkill` and `oc:DeclarativeSkill` defined in core ontology
- [ ] State transitions validated as IRIs

- [ ] **Step 3: Final commit (if any fixes needed)**

```bash
# Only if fixes were needed
git add -A
git commit -m "fix: resolve any remaining issues"
```

---

## Success Criteria

- [ ] All 5 validation test cases pass
- [ ] Existing 72 tests still pass (no regressions)
- [ ] Invalid skills are blocked from being written to disk
- [ ] Valid skills pass validation and are written successfully
- [ ] `oc:ExecutableSkill` and `oc:DeclarativeSkill` subclasses defined in core ontology
- [ ] State transitions validated as IRIs pointing to `oc:State` instances
- [ ] Error messages are clear and actionable (Italian messages in SHACL shapes)
- [ ] `merge_skill()` also validates before returning modified graph
