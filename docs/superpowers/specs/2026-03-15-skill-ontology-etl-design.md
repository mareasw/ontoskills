# Skill Ontology ETL - Design Specification

**Date**: 2026-03-15
**Status**: Draft
**Author**: Claude + Marcello

---

## Overview

Skill Ontology ETL is a CLI tool that compiles unstructured Markdown agent skills into a W3C-standard RDF/Turtle ontology. The tool enables "Semantic Routing" by allowing small LLMs to query SPARQL instead of reading long markdown files, avoiding context rot and hallucinations.

## Goals

1. **Eliminate context rot**: Transform prose skills into deterministic, queryable knowledge graphs
2. **Enable semantic routing**: Allow agents to find skills via SPARQL queries
3. **Ensure data integrity**: Deterministic IDs, intelligent merging, atomic writes
4. **Security first**: Defense-in-depth against prompt injection and malicious content

## Non-Goals

- OpenAI support (Anthropic-only for tool-use capabilities)
- Real-time skill execution (compilation only)
- GUI interface (CLI only)

---

## Architecture

### High-Level Flow

```
skills/                    ontology/
├── skill-a/               └── skills.ttl
│   ├── SKILL.md    ───────────────▲
│   └── references/                │
│       └── guide.md               │
├── skill-b/               ┌───────┴───────┐
│   └── SKILL.md    ──────►│     ETL       │
└── ...                    │   Pipeline    │
                           └───────┬───────┘
                                   │
                    ┌──────────────┼──────────────┐
                    ▼              ▼              ▼
               EXTRACTOR     TRANSFORMER      LOADER
               (scan/hash)   (LLM+tools)    (RDF+merge)
```

### Components

| Component | File | Responsibility |
|-----------|------|----------------|
| **Entry Point** | `compiler.py` | Bootstrap CLI |
| **CLI** | `cli.py` | Click commands: compile, query, list-skills, security-audit |
| **Extractor** | `extractor.py` | Scan `SKILL.md` files, compute SHA-256 hashes |
| **Transformer** | `transformer.py` | Tool-use loop with Claude, structured extraction |
| **Security** | `security.py` | Regex patterns + LLM-as-judge (defense in depth) |
| **Loader** | `loader.py` | RDF/Turtle serialization, intelligent merge, atomic writes |
| **Schemas** | `schemas.py` | Pydantic models for extraction |

---

## Data Models

### ExtractedSkill (Pydantic)

```python
class Requirement(BaseModel):
    type: Literal["EnvVar", "Tool", "Hardware", "API", "Knowledge"]
    value: str
    optional: bool = False

class ExecutionPayload(BaseModel):
    executor: Literal["shell", "python", "node", "claude_tool"]
    code: str
    timeout: int | None = None

class ExtractedSkill(BaseModel):
    # Identity
    id: str                          # Deterministic slug
    hash: str                        # SHA-256 of all files

    # Substance (Knowledge Architecture)
    nature: str                      # Essential nature
    genus: str                       # Broader category
    differentia: str                 # What distinguishes it

    # Relations (first-class citizens)
    intents: list[str]               # User intents resolved
    requirements: list[Requirement]  # Prerequisites
    depends_on: list[str] = []       # Other skills needed
    extends: list[str] = []          # Skills built upon
    contradicts: list[str] = []      # Opposing concepts

    # Constraints & Execution
    constraints: list[str]           # Critical rules
    execution_payload: ExecutionPayload | None

    # Provenance
    provenance: str | None           # Source file path
```

---

## LLM Extraction Strategy

### Tool-Use Architecture (Anthropic-only)

Instead of concatenating all files into one prompt, the tool uses Claude's native tool-use:

```
┌──────────────────────────────────────────────────────────────┐
│                        Claude LLM                             │
│  ┌─────────────┐    ┌─────────────┐    ┌────────────────┐   │
│  │ list_files  │───▶│ read_file   │───▶│ extract_skill  │   │
│  │ (discover)  │    │ (as needed) │    │ (final output) │   │
│  └─────────────┘    └─────────────┘    └────────────────┘   │
└──────────────────────────────────────────────────────────────┘
         │                   │                      │
         ▼                   ▼                      ▼
    [file list]        [file content]       [Pydantic object]
```

**Tools available to LLM**:
1. `list_files` - Discover files in skill directory
2. `read_file` - Read specific files (SKILL.md, references, code)
3. `extract_skill` - Submit final structured extraction

**Benefits**:
- No token limits from concatenation
- LLM reads only what's needed
- Preserves file structure context
- Works with arbitrarily large skills

### System Prompt

The system prompt follows the Knowledge Architecture framework:

```text
You are an Ontological Architect. Your task is to analyze agent skills
and extract their essential structure using the Knowledge Architecture framework.

## KNOWLEDGE ARCHITECTURE FRAMEWORK

### Categories of Being
- Tool: Enables action
- Concept: A framework, methodology
- Work: A created artifact generator

### Genus and Differentia
"A is a B that C" - classical definition structure

### Relations as First-Class Citizens
- depends-on: Cannot function without
- extends: Builds upon
- contradicts: In tension with
- implements: Realizes abstraction
- exemplifies: Instance of pattern

### Essential vs Accidental
Essential: Remove it → becomes something else
Accidental: Could be different without changing identity
```

---

## Security Strategy (Defense in Depth)

### Stage 1: Regex Pattern Matching

Fast detection of common attack patterns:

- **Prompt injection**: "ignore previous instructions", "you are now..."
- **Command injection**: `; rm -rf`, `| bash`, command substitution
- **Data exfiltration**: `curl -d`, upload patterns

### Stage 2: LLM-as-Judge

If Stage 1 flags content, a smaller model (Haiku) reviews:

```python
SECURITY_MODEL = os.getenv("SECURITY_MODEL", "claude-3-5-haiku-20241022")
```

**Fail-closed**: Any error → block the content

### Unicode Normalization

Content is normalized before pattern matching to prevent bypass:
- NFC unicode normalization
- Zero-width character removal
- Whitespace normalization

---

## RDF Ontology Mapping

### Namespaces

```turtle
@prefix ag: <http://agentic.web/ontology#> .
@prefix dcterms: <http://purl.org/dc/terms/> .
@prefix skos: <http://www.w3.org/2004/02/skos/> .
@prefix prov: <http://www.w3.org/ns/prov#> .
```

### Predicate Mapping

| Pydantic Field | RDF Predicate | Namespace |
|----------------|---------------|-----------|
| `id` | `dcterms:identifier` | Dublin Core |
| `nature` | `ag:nature` | Custom |
| `genus` | `skos:broader` | SKOS |
| `differentia` | `ag:differentia` | Custom |
| `intents` | `ag:resolvesIntent` | Custom |
| `depends_on` | `dcterms:requires` | Dublin Core |
| `extends` | `dcterms:isVersionOf` | Dublin Core |
| `contradicts` | `ag:contradicts` | Custom |
| `execution_payload` | `ag:hasPayload` | Custom |
| `provenance` | `prov:wasDerivedFrom` | PROV |

### Example Output

```turtle
@prefix ag: <http://agentic.web/ontology#> .
@prefix dcterms: <http://purl.org/dc/terms/> .

ag:skill_abc123def456 a ag:AgenticSkill ;
    dcterms:identifier "docx-engineering" ;
    ag:contentHash "abc123def456..." ;
    ag:nature "Document generation tool that creates DOCX files from templates" ;
    skos:broader "Document Processing Tool" ;
    ag:differentia "that uses python-docx library" ;
    ag:resolvesIntent "create_docx", "extract_tables" ;
    dcterms:requires "python-docx" ;
    ag:hasPayload [
        ag:executor "python" ;
        ag:code "from docx import Document..."
    ] ;
    prov:wasDerivedFrom "/skills/docx-engineering/SKILL.md" .
```

---

## Merge Strategy

### Intelligent Append

1. Load existing ontology, extract `hash → URI` mapping
2. For each new skill:
   - If hash exists → skip (unchanged)
   - If same ID but different hash → remove old, add new
   - If new ID → add
3. Preserve all unmodified triples

### Atomic Writes

```
1. Backup existing skills.ttl → backups/skills_YYYYMMDD_HHMMSS.ttl
2. Write to skills.ttl.tmp
3. Rename skills.ttl.tmp → skills.ttl (atomic)
4. On failure: restore from backup
5. Cleanup: keep only last 5 backups
```

---

## CLI Commands

### `skill-etl compile [SKILL_NAME]`

Compile skills into ontology.

- No argument: Compile all skills in `./skills/`
- With SKILL_NAME: Compile specific skill (shows preview, asks confirmation)

**Options**:
- `-i, --input`: Input directory (default: `./skills/`)
- `-o, --output`: Output file (default: `./ontology/skills.ttl`)
- `--dry-run`: Preview without saving
- `--skip-security`: Skip security checks (not recommended)
- `-y, --yes`: Skip confirmation prompt

**Flow for single skill**:
1. Security check (regex → LLM if flagged)
2. LLM extraction via tool-use
3. Display detailed preview
4. Ask: "Add this skill to the ontology?"
5. If yes: merge and save

### `skill-etl query "<sparql>"`

Execute SPARQL query against ontology.

**Options**:
- `-o, --ontology`: Ontology file (default: `./ontology/skills.ttl`)
- `-f, --format`: Output format (table/json/turtle)

**Example**:
```bash
skill-etl query "SELECT ?s ?n WHERE { ?s ag:nature ?n }" -f json
```

### `skill-etl list-skills`

List all skills in the ontology.

### `skill-etl security-audit`

Re-validate all skills in ontology against current security patterns.

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | Yes | - | Anthropic API key |
| `ANTHROPIC_BASE_URL` | No | - | Custom API endpoint |
| `ANTHROPIC_MODEL` | No | `claude-sonnet-4-6-20250514` | Extraction model |
| `SECURITY_MODEL` | No | `claude-3-5-haiku-20241022` | Security review model |

---

## File Structure

```
skill-ontology-etl/
├── compiler.py           # Entry point
├── cli.py                # Click CLI commands
├── extractor.py          # Skill scanning & hashing
├── transformer.py        # LLM tool-use extraction
├── security.py           # Security pipeline
├── loader.py             # RDF serialization & merge
├── schemas.py            # Pydantic models
├── requirements.txt      # Dependencies
├── pyproject.toml        # Package config
├── README.md
├── LICENSE               # MIT
├── CLAUDE.md
├── .gitignore
├── skills/               # Input skills
│   └── (skill directories with SKILL.md)
├── ontology/             # Output
│   ├── skills.ttl
│   └── backups/
└── tests/                # 100% coverage
    ├── conftest.py
    ├── test_extractor.py
    ├── test_security.py
    ├── test_loader.py
    ├── test_schemas.py
    ├── test_transformer.py
    ├── test_cli.py
    └── test_integration.py
```

---

## Dependencies

```
anthropic>=0.39.0
click>=8.1.0
pydantic>=2.0.0
rdflib>=7.0.0
rich>=13.0.0
```

**Dev dependencies**:
```
pytest>=8.0.0
pytest-cov>=4.0.0
ruff>=0.1.0
mypy>=1.0.0
```

---

## Testing Strategy

### Requirements

- **Test-Driven Development**: Write tests before implementation
- **100% Code Coverage**: All modules must have complete coverage
- **Unit Tests**: Each component tested in isolation
- **Integration Tests**: Full pipeline tests (require API key)

### Coverage Targets

| Module | Target |
|--------|--------|
| `schemas.py` | 100% |
| `extractor.py` | 100% |
| `security.py` | 100% |
| `loader.py` | 100% |
| `transformer.py` | 100% |
| `cli.py` | 100% |

### Test Categories

1. **Unit Tests**: Mock external dependencies (LLM, filesystem)
2. **Integration Tests**: Real API calls (marked `@pytest.mark.integration`)
3. **Security Tests**: Pattern matching, bypass attempts

### Run Command

```bash
pytest --cov=. --cov-report=html --cov-fail-under=100
```

---

## Error Handling

### Fail-Closed Principles

| Scenario | Behavior |
|----------|----------|
| Security threat detected | Block skill, report threats |
| LLM extraction fails | Raise error, don't save partial data |
| Ontology parse error | Raise error, suggest restore from backup |
| Write failure | Restore from backup automatically |
| Invalid SPARQL query | Return error, don't modify ontology |

### Error Types

```python
class OntologyLoadError(Exception):
    """Raised when ontology loading/parsing fails."""

class SecurityError(Exception):
    """Raised when security check fails."""
```

---

## Success Criteria

1. ✅ CLI compiles skills to valid RDF/Turtle
2. ✅ SPARQL queries return correct results
3. ✅ Merge preserves unmodified skills
4. ✅ Security blocks malicious content
5. ✅ 100% test coverage
6. ✅ Atomic writes with backup/restore
7. ✅ Tool-use handles arbitrarily large skills

---

## Future Considerations

- [ ] OWL ontology for richer semantics
- [ ] Web UI for ontology browsing
- [ ] Skill versioning and history
- [ ] Multi-language support
- [ ] Custom ontology namespaces per project
