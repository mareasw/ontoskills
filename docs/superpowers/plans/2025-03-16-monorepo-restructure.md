# Monorepo Restructure Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize the OntoClaw monorepo to separate Python ETL from future Rust MCP, moving all Python code to `etl/` subdirectory.

**Architecture:** Python src-layout with `etl/src/ontoclaw_etl/` package, tests co-located in `etl/tests/`. Data directories (`skills/`, `semantic-skills/`) remain at root for access from both ETL and MCP.

**Tech Stack:** Python 3.10+, pytest, setuptools

---

## File Structure

| Current Location | New Location | Purpose |
|-----------------|--------------|---------|
| `cli.py` | `etl/src/ontoclaw_etl/cli.py` | CLI commands |
| `compiler.py` | `etl/src/ontoclaw_etl/compiler.py` | Entry point |
| `config.py` | `etl/src/ontoclaw_etl/config.py` | Configuration |
| `exceptions.py` | `etl/src/ontoclaw_etl/exceptions.py` | Error classes |
| `extractor.py` | `etl/src/ontoclaw_etl/extractor.py` | File scanning |
| `loader.py` | `etl/src/ontoclaw_etl/loader.py` | RDF serialization |
| `schemas.py` | `etl/src/ontoclaw_etl/schemas.py` | Pydantic models |
| `security.py` | `etl/src/ontoclaw_etl/security.py` | Security checks |
| `sparql.py` | `etl/src/ontoclaw_etl/sparql.py` | SPARQL queries |
| `transformer.py` | `etl/src/ontoclaw_etl/transformer.py` | LLM extraction |
| `tests/*.py` | `etl/tests/*.py` | All test files |
| `pyproject.toml` | `etl/pyproject.toml` | Package config |
| `README.md` | `etl/README.md` | ETL docs |
| - | `etl/src/ontoclaw_etl/__init__.py` | Package init (new) |
| - | `mcp/README.md` | MCP placeholder (new) |

---

## Chunk 1: Directory Structure and Package Init

### Task 1: Create ETL directory structure

**Files:**
- Create: `etl/src/ontoclaw_etl/__init__.py`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p etl/src/ontoclaw_etl
mkdir -p etl/tests
```

- [ ] **Step 2: Create package __init__.py**

Create `etl/src/ontoclaw_etl/__init__.py`:

```python
"""OntoClaw ETL - Python compiler for skills to OWL 2 ontology."""

__version__ = "0.2.0"
```

- [ ] **Step 3: Verify structure created**

Run: `ls -la etl/src/ontoclaw_etl/`
Expected: `__init__.py` exists

- [ ] **Step 4: Commit**

```bash
git add etl/src/ontoclaw_etl/__init__.py
git commit -m "chore: create etl package structure"
```

---

## Chunk 2: Move Python Source Files

### Task 2: Move all Python source files to etl package

**Files:**
- Move: `cli.py` → `etl/src/ontoclaw_etl/cli.py`
- Move: `compiler.py` → `etl/src/ontoclaw_etl/compiler.py`
- Move: `config.py` → `etl/src/ontoclaw_etl/config.py`
- Move: `exceptions.py` → `etl/src/ontoclaw_etl/exceptions.py`
- Move: `extractor.py` → `etl/src/ontoclaw_etl/extractor.py`
- Move: `loader.py` → `etl/src/ontoclaw_etl/loader.py`
- Move: `schemas.py` → `etl/src/ontoclaw_etl/schemas.py`
- Move: `security.py` → `etl/src/ontoclaw_etl/security.py`
- Move: `sparql.py` → `etl/src/ontoclaw_etl/sparql.py`
- Move: `transformer.py` → `etl/src/ontoclaw_etl/transformer.py`

- [ ] **Step 1: Move all source files**

```bash
mv cli.py etl/src/ontoclaw_etl/
mv compiler.py etl/src/ontoclaw_etl/
mv config.py etl/src/ontoclaw_etl/
mv exceptions.py etl/src/ontoclaw_etl/
mv extractor.py etl/src/ontoclaw_etl/
mv loader.py etl/src/ontoclaw_etl/
mv schemas.py etl/src/ontoclaw_etl/
mv security.py etl/src/ontoclaw_etl/
mv sparql.py etl/src/ontoclaw_etl/
mv transformer.py etl/src/ontoclaw_etl/
```

- [ ] **Step 2: Verify files moved**

Run: `ls etl/src/ontoclaw_etl/*.py | wc -l`
Expected: `11` (10 modules + __init__.py)

- [ ] **Step 3: Verify root is clean**

Run: `ls *.py 2>/dev/null | wc -l`
Expected: `0`

---

## Chunk 3: Move Tests

### Task 3: Move all test files to etl/tests

**Files:**
- Move: `tests/*.py` → `etl/tests/*.py`

- [ ] **Step 1: Move test files**

```bash
mv tests/*.py etl/tests/
rmdir tests
```

- [ ] **Step 2: Verify tests moved**

Run: `ls etl/tests/test_*.py | wc -l`
Expected: `10` (all test files)

- [ ] **Step 3: Create conftest.py if needed**

Create `etl/tests/conftest.py`:

```python
"""Shared pytest fixtures for OntoClaw ETL tests."""
import sys
from pathlib import Path

# Add src to path for imports
src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))
```

---

## Chunk 4: Create etl/pyproject.toml

### Task 4: Create new pyproject.toml for ETL package

**Files:**
- Create: `etl/pyproject.toml`

- [ ] **Step 1: Create etl/pyproject.toml**

```toml
[project]
name = "ontoclaw-etl"
version = "0.2.0"
description = "Python ETL compiler for OntoClaw skills to OWL 2 ontology"
requires-python = ">=3.10"
dependencies = [
    "click>=8.1.0",
    "pydantic>=2.0.0",
    "rdflib>=7.0.0",
    "anthropic>=0.39.0",
    "rich>=13.0.0",
    "owlrl>=1.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-cov>=4.0.0",
    "pytest-timeout>=2.2.0",
    "ruff>=0.1.0",
    "mypy>=1.0.0",
]

[project.scripts]
ontoclaw = "ontoclaw_etl.cli:main"

[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_functions = ["test_*"]
markers = [
    "integration: marks tests as integration tests (deselect with '-m \"not integration\"')",
]
addopts = "-m 'not integration'"

[tool.ruff]
line-length = 100
target-version = "py310"
```

- [ ] **Step 2: Delete old pyproject.toml from root**

```bash
rm pyproject.toml
```

---

## Chunk 5: Update Imports

### Task 5: Update all internal imports to use package namespace

**Files:**
- Modify: `etl/src/ontoclaw_etl/*.py` (all files with imports)

All imports need to change from `from X import` to `from ontoclaw_etl.X import`.

- [ ] **Step 1: Update cli.py imports**

In `etl/src/ontoclaw_etl/cli.py`, replace:
```python
from extractor import generate_skill_id, compute_skill_hash
from transformer import tool_use_loop
from security import security_check, SecurityError
from loader import (
    create_core_ontology,
    serialize_skill_to_module,
    generate_index_manifest,
    get_oc_namespace,
)
from sparql import execute_sparql, format_results
from exceptions import (
    SkillETLError,
    ExtractionError,
    SPARQLError,
    SkillNotFoundError,
)
from config import SKILLS_DIR, OUTPUT_DIR
```

With:
```python
from ontoclaw_etl.extractor import generate_skill_id, compute_skill_hash
from ontoclaw_etl.transformer import tool_use_loop
from ontoclaw_etl.security import security_check, SecurityError
from ontoclaw_etl.loader import (
    create_core_ontology,
    serialize_skill_to_module,
    generate_index_manifest,
    get_oc_namespace,
)
from ontoclaw_etl.sparql import execute_sparql, format_results
from ontoclaw_etl.exceptions import (
    SkillETLError,
    ExtractionError,
    SPARQLError,
    SkillNotFoundError,
)
from ontoclaw_etl.config import SKILLS_DIR, OUTPUT_DIR
```

- [ ] **Step 2: Update transformer.py imports**

In `etl/src/ontoclaw_etl/transformer.py`, replace:
```python
from schemas import ExtractedSkill, Requirement, ExecutionPayload
from exceptions import ExtractionError
from config import ANTHROPIC_MODEL, MAX_ITERATIONS, EXTRACTION_TIMEOUT, CORE_STATES, FAILURE_STATES
```

With:
```python
from ontoclaw_etl.schemas import ExtractedSkill, Requirement, ExecutionPayload
from ontoclaw_etl.exceptions import ExtractionError
from ontoclaw_etl.config import ANTHROPIC_MODEL, MAX_ITERATIONS, EXTRACTION_TIMEOUT, CORE_STATES, FAILURE_STATES
```

- [ ] **Step 3: Update security.py imports**

In `etl/src/ontoclaw_etl/security.py`, replace:
```python
from exceptions import SecurityError
```

With:
```python
from ontoclaw_etl.exceptions import SecurityError
```

- [ ] **Step 4: Update loader.py imports**

In `etl/src/ontoclaw_etl/loader.py`, replace:
```python
from schemas import ExtractedSkill, Requirement, ExecutionPayload
from exceptions import OntologyLoadError
from config import BASE_URI, CORE_STATES, FAILURE_STATES, SKILLS_DIR, OUTPUT_DIR
```

With:
```python
from ontoclaw_etl.schemas import ExtractedSkill, Requirement, ExecutionPayload
from ontoclaw_etl.exceptions import OntologyLoadError
from ontoclaw_etl.config import BASE_URI, CORE_STATES, FAILURE_STATES, SKILLS_DIR, OUTPUT_DIR
```

- [ ] **Step 5: Update sparql.py imports**

In `etl/src/ontoclaw_etl/sparql.py`, replace:
```python
from exceptions import SPARQLError
```

With:
```python
from ontoclaw_etl.exceptions import SPARQLError
```

---

## Chunk 6: Update Test Imports

### Task 6: Update all test file imports

**Files:**
- Modify: `etl/tests/*.py` (all test files)

- [ ] **Step 1: Update test_cli.py imports**

In `etl/tests/test_cli.py`, replace:
```python
from cli import cli
```

With:
```python
from ontoclaw_etl.cli import cli
```

- [ ] **Step 2: Update test_config.py imports**

In `etl/tests/test_config.py`, replace:
```python
import config
```

With:
```python
import ontoclaw_etl.config as config
```

And replace:
```python
import importlib
import config
importlib.reload(config)
```

With:
```python
import importlib
import ontoclaw_etl.config as config
importlib.reload(config)
```

- [ ] **Step 3: Update test_extractor.py imports**

Replace:
```python
from extractor import generate_skill_id, compute_skill_hash
```

With:
```python
from ontoclaw_etl.extractor import generate_skill_id, compute_skill_hash
```

- [ ] **Step 4: Update test_loader.py imports**

Replace:
```python
from loader import ...
```

With:
```python
from ontoclaw_etl.loader import ...
```

- [ ] **Step 5: Update test_schemas.py imports**

Replace:
```python
from schemas import ...
```

With:
```python
from ontoclaw_etl.schemas import ...
```

- [ ] **Step 6: Update test_security.py imports**

Replace:
```python
from security import ...
```

With:
```python
from ontoclaw_etl.security import ...
```

- [ ] **Step 7: Update test_sparql.py imports**

Replace:
```python
from loader import create_core_ontology, get_oc_namespace
from sparql import execute_sparql, format_results
```

With:
```python
from ontoclaw_etl.loader import create_core_ontology, get_oc_namespace
from ontoclaw_etl.sparql import execute_sparql, format_results
```

And replace:
```python
from exceptions import SPARQLError
```

With:
```python
from ontoclaw_etl.exceptions import SPARQLError
```

- [ ] **Step 8: Update test_transformer.py imports**

Replace:
```python
from transformer import ...
from config import ANTHROPIC_MODEL
```

With:
```python
from ontoclaw_etl.transformer import ...
from ontoclaw_etl.config import ANTHROPIC_MODEL
```

- [ ] **Step 9: Update test_exceptions.py imports**

Replace:
```python
from exceptions import ...
```

With:
```python
from ontoclaw_etl.exceptions import ...
```

- [ ] **Step 10: Update test_integration.py imports**

Replace all `from X import` with `from ontoclaw_etl.X import`:
```python
from ontoclaw_etl.extractor import generate_skill_id, compute_skill_hash
from ontoclaw_etl.transformer import tool_use_loop
from ontoclaw_etl.loader import create_core_ontology, serialize_skill_to_module, generate_index_manifest, load_skill_module
from ontoclaw_etl.security import llm_security_review, check_patterns
```

---

## Chunk 7: Create ETL README and MCP Placeholder

### Task 7: Create documentation files

**Files:**
- Create: `etl/README.md`
- Create: `mcp/README.md`
- Modify: `README.md` (root - update for monorepo)

- [ ] **Step 1: Create etl/README.md**

Move current README content to `etl/README.md` (it's ETL-specific):

```bash
cp README.md etl/README.md
```

- [ ] **Step 2: Create mcp/README.md**

```markdown
# OntoClaw MCP Server

Rust-based MCP (Model Context Protocol) server for OntoClaw.

**Status:** Coming soon

This server will provide:
- Fast SPARQL queries against compiled ontologies
- Skill routing based on state transitions
- Integration with Claude and other LLM clients via MCP

Built with Rust for performance.
```

- [ ] **Step 3: Update root README.md for monorepo**

Replace root `README.md` with monorepo overview:

```markdown
<p align="center">
  <img src="assets/logo.png" alt="OntoClaw Logo" width="200">
</p>

<h1 align="center">OntoClaw</h1>

<p align="center">
  <strong>The first neuro-symbolic skill compiler for the Agentic Web.</strong>
</p>

<p align="center">
  <a href="#components">Components</a> •
  <a href="#installation">Installation</a> •
  <a href="#usage">Usage</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/OWL%202-RDF%2FTurtle-green" alt="OWL 2 RDF/Turtle">
  <img src="https://img.shields.io/badge/license-MIT-orange" alt="MIT License">
</p>

---

## Components

| Component | Language | Status | Description |
|-----------|----------|--------|-------------|
| [etl/](etl/) | Python | ✅ Ready | Skill compiler to OWL 2 ontology |
| [mcp/](mcp/) | Rust | 🚧 Coming soon | Fast MCP server for ontology queries |
| skills/ | Markdown | ✅ Ready | Input skill definitions |
| semantic-skills/ | Turtle | Generated | Compiled ontology output |

## Architecture

```
skills/               semantic-skills/
├── office/           ├── ontoclaw-core.ttl
│   └── public/       ├── index.ttl
│       ├── docx/     └── office/public/
│       ├── pdf/          └── */skill.ttl
│       ├── pptx/
│       └── xlsx/
       │
       └────────► etl/ (Python compiler) ────────►
```

## Installation

```bash
# Clone monorepo
git clone https://github.com/marea-software/ontoclaw.git
cd ontoclaw

# Install ETL
cd etl
uv venv .venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

## Usage

```bash
# Compile skills
ontoclaw compile

# Query ontology
ontoclaw query "SELECT ?s WHERE { ?s a oc:Skill }"

# List skills
ontoclaw list-skills
```

See [etl/README.md](etl/README.md) for full documentation.

## License

MIT
```

---

## Chunk 8: Verify and Commit

### Task 8: Run tests and commit the restructure

- [ ] **Step 1: Install package in development mode**

```bash
cd etl
pip install -e ".[dev]"
```

- [ ] **Step 2: Run unit tests**

Run: `cd etl && pytest tests/ -v`
Expected: 72 passed, 3 deselected

- [ ] **Step 3: Run integration tests**

Run: `cd etl && pytest -m integration tests/ -v`
Expected: 3 passed (requires ANTHROPIC_API_KEY)

- [ ] **Step 4: Test CLI**

Run: `ontoclaw --version`
Expected: `ontoclaw-etl, version 0.2.0`

Run: `ontoclaw --help`
Expected: Shows help with compile, query, list-skills commands

- [ ] **Step 5: Stage all changes**

```bash
git add -A
```

- [ ] **Step 6: Commit the restructure**

```bash
git commit -m "refactor: reorganize monorepo with etl/ and mcp/ structure

- Move all Python ETL code to etl/src/ontoclaw_etl/
- Move tests to etl/tests/
- Create etl/pyproject.toml with package config
- Update all imports to use ontoclaw_etl namespace
- Create mcp/README.md placeholder for Rust MCP server
- Update root README for monorepo overview

All 72 unit tests pass. Integration tests pass with API key."
```

---

## Success Criteria Checklist

- [ ] All Python files moved to `etl/src/ontoclaw_etl/`
- [ ] All tests moved to `etl/tests/`
- [ ] All 72 unit tests pass
- [ ] Integration tests pass with `pytest -m integration`
- [ ] `ontoclaw compile` works from command line
- [ ] Root directory has <5 non-config files
