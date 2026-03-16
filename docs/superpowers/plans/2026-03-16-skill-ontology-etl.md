# Skill Ontology ETL Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a CLI tool that compiles markdown agent skills into a queryable OWL 2 RDF/Turtle ontology to enable semantic routing.

**Architecture:** An ETL pipeline (CLI) that scans directories for skills, computes deterministic hashes/IDs, extracts structured knowledge via Claude tool-use, validates against security patterns, and intelligently merges the results into an RDf/Turtle graph via atomic writes.

**Tech Stack:** Python 3.10+, click, pydantic, rdflib, anthropic, pytest

---

### Task 1: Setup and Schemas

**Files:**
- Create: `schemas.py`
- Test: `tests/test_schemas.py`

**Step 1: Write the failing test**

```python
import pytest
from schemas import Requirement, ExecutionPayload, ExtractedSkill

def test_schemas_validation():
    req = Requirement(type="EnvVar", value="API_KEY")
    assert req.optional is False
    
    payload = ExecutionPayload(executor="shell", code="echo 'hello'")
    assert payload.timeout is None

    skill = ExtractedSkill(
        id="test-skill",
        hash="abcdef",
        nature="A test skill",
        genus="Test",
        differentia="that tests",
        intents=["testing"],
        requirements=[req],
        constraints=["must test"],
        execution_payload=payload,
        provenance="/path"
    )
    assert skill.id == "test-skill"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_schemas.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write minimal implementation**

```python
from pydantic import BaseModel
from typing import Literal

class Requirement(BaseModel):
    type: Literal["EnvVar", "Tool", "Hardware", "API", "Knowledge"]
    value: str
    optional: bool = False

class ExecutionPayload(BaseModel):
    executor: Literal["shell", "python", "node", "claude_tool"]
    code: str
    timeout: int | None = None

class ExtractedSkill(BaseModel):
    id: str
    hash: str
    nature: str
    genus: str
    differentia: str
    intents: list[str]
    requirements: list[Requirement]
    depends_on: list[str] = []
    extends: list[str] = []
    contradicts: list[str] = []
    constraints: list[str]
    execution_payload: ExecutionPayload | None
    provenance: str | None
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_schemas.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add schemas.py tests/test_schemas.py
git commit -m "feat: setup pydantic schemas for extracted skills"
```

### Task 2: Error Definitions

**Files:**
- Create: `exceptions.py`
- Test: `tests/test_exceptions.py`

**Step 1: Write the failing test**

```python
import pytest
from exceptions import SkillETLError, SecurityError

def test_exceptions_exit_codes():
    assert SkillETLError.exit_code == 1
    assert SecurityError.exit_code == 3
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_exceptions.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write minimal implementation**

```python
class SkillETLError(Exception):
    exit_code: int = 1

class OntologyLoadError(SkillETLError):
    exit_code = 5

class SecurityError(SkillETLError):
    exit_code = 3

class ExtractionError(SkillETLError):
    exit_code = 4

class SPARQLError(SkillETLError):
    exit_code = 6

class SkillNotFoundError(SkillETLError):
    exit_code = 7
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_exceptions.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add exceptions.py tests/test_exceptions.py
git commit -m "feat: define custom exception classes"
```

### Task 3: Extractor (Hash and ID Generation)

**Files:**
- Create: `extractor.py`
- Test: `tests/test_extractor.py`

**Step 1: Write the failing test**

```python
import pytest
from pathlib import Path
from extractor import generate_skill_id, compute_skill_hash

def test_generate_skill_id():
    assert generate_skill_id("DOCX-Engineering") == "docx-engineering"
    assert generate_skill_id("My_Awesome Skill!!!") == "my-awesome-skill"

def test_compute_skill_hash(tmp_path):
    skill_dir = tmp_path / "skill-a"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("content")
    hash_val = compute_skill_hash(skill_dir)
    assert isinstance(hash_val, str)
    assert len(hash_val) == 64
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_extractor.py -v`
Expected: FAIL with "ImportError"

**Step 3: Write minimal implementation**

```python
import re
import hashlib
from pathlib import Path

def generate_skill_id(directory_name: str) -> str:
    slug = directory_name.lower()
    slug = re.sub(r'[\s_]+', '-', slug)
    slug = re.sub(r'[^a-z0-9-]', '', slug)
    slug = re.sub(r'-+', '-', slug)
    slug = slug.strip('-')
    return slug[:64]

def compute_skill_hash(skill_dir: Path) -> str:
    hasher = hashlib.sha256()
    files = sorted(
        f for f in skill_dir.rglob('*')
        if f.is_file() and not f.name.startswith('.')
    )
    for file_path in files:
        rel_path = file_path.relative_to(skill_dir)
        hasher.update(str(rel_path).encode('utf-8'))
        hasher.update(file_path.read_bytes())
    return hasher.hexdigest()
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_extractor.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add extractor.py tests/test_extractor.py
git commit -m "feat: implement skill id and hash generation"
```

### Task 4: Loader and Ontology Serialization

**Files:**
- Create: `loader.py`
- Test: `tests/test_loader.py`

**Step 1: Write the failing test**

```python
import pytest
from loader import create_ontology_graph
from rdflib import Graph

def test_create_ontology_graph():
    graph = create_ontology_graph()
    assert isinstance(graph, Graph)
    # Check that basic prefixes are bound
    prefixes = dict(graph.namespaces())
    assert "ag" in prefixes
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_loader.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write minimal implementation**

```python
from rdflib import Graph, Namespace, RDF, RDFS, OWL
from rdflib.namespace import DCTERMS, SKOS, PROV

AG = Namespace("http://agentic.web/ontology#")

def create_ontology_graph() -> Graph:
    g = Graph()
    g.bind("ag", AG)
    g.bind("owl", OWL)
    g.bind("dcterms", DCTERMS)
    g.bind("skos", SKOS)
    g.bind("prov", PROV)
    
    ontology_uri = AG[""]
    g.add((ontology_uri, RDF.type, OWL.Ontology))
    g.add((ontology_uri, DCTERMS.title, rdflib.Literal("Agentic Skills Ontology")))
    
    g.add((AG.Skill, RDF.type, OWL.Class))
    g.add((AG.Tool, RDF.type, OWL.Class))
    g.add((AG.Tool, RDFS.subClassOf, AG.Skill))
    
    return g
```
*(Wait, rdflib.Literal needs to be imported, let's fix in code)*

```python
import rdflib
from rdflib import Graph, Namespace, RDF, RDFS, OWL
from rdflib.namespace import DCTERMS, SKOS, PROV

AG = Namespace("http://agentic.web/ontology#")

def create_ontology_graph() -> Graph:
    g = Graph()
    g.bind("ag", AG)
    g.bind("owl", OWL)
    g.bind("dcterms", DCTERMS)
    g.bind("skos", SKOS)
    g.bind("prov", PROV)
    
    ontology_uri = rdflib.URIRef("http://agentic.web/ontology")
    g.add((ontology_uri, RDF.type, OWL.Ontology))
    g.add((ontology_uri, DCTERMS.title, rdflib.Literal("Agentic Skills Ontology")))
    
    g.add((AG.Skill, RDF.type, OWL.Class))
    g.add((AG.Tool, RDF.type, OWL.Class))
    g.add((AG.Tool, RDFS.subClassOf, AG.Skill))
    
    return g
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_loader.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add loader.py tests/test_loader.py
git commit -m "feat: implement initial rdflib loader and graph creation"
```

### Task 5: Basic CLI Setup

**Files:**
- Create: `cli.py`
- Create: `compiler.py` (entry point)
- Test: `tests/test_cli.py`

**Step 1: Write the failing test**

```python
import pytest
from click.testing import CliRunner
from cli import cli

def test_cli_version():
    runner = CliRunner()
    result = runner.invoke(cli, ['--version'])
    assert result.exit_code == 0
    assert "version" in result.output.lower()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write minimal implementation**

`cli.py`:
```python
import click

@click.group()
@click.version_option()
def cli():
    """Skill Ontology ETL CLI"""
    pass

@cli.command()
@click.argument('skill_name', required=False)
def compile(skill_name):
    """Compile skills into ontology."""
    click.echo(f"Compiling {skill_name if skill_name else 'all skills'}")

@cli.command()
@click.argument('query_string')
def query(query_string):
    """Execute SPARQL query."""
    click.echo("Query executed")
```

`compiler.py`:
```python
from cli import cli

if __name__ == '__main__':
    cli()
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add cli.py compiler.py tests/test_cli.py
git commit -m "feat: create basic click cli interface"
```
