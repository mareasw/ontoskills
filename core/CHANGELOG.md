# Changelog

All notable changes to the OntoSkills Core Python package will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- **Sub-skills compilation** — Auxiliary `.md` files (e.g., `planning.md`, `review.md`) are now compiled as sub-skills with Qualified IDs
  - Qualified ID format: `{package_id}/{skill_id}/{sub_skill_id}` (e.g., `obra/superpowers/brainstorming/planning`)
  - Deterministic `oc:extends` injection — compiler automatically sets parent inheritance
  - Independent hash caching — sub-skill hashes based on file content only, not parent
  - `OrphanSubSkillsError` — raises error when auxiliary `.md` files exist without parent `SKILL.md`
  - `resolve_package_id()` — walks directory tree to find `package.json` or `ontoskills.toml`
  - `generate_qualified_skill_id()` and `generate_sub_skill_id()` for hierarchical ID generation
  - `compute_sub_skill_hash()` for independent hash computation
  - `build_sub_skill_context_prompt()` for LLM context augmentation

- **Semantic intent discovery** — Optional embeddings module for semantic skill search
  - `compiler.embeddings` module with intent extraction from ontology
  - `export-embeddings` CLI command to generate ONNX-compatible embeddings
  - Intent extraction from `resolvesIntent` predicates in TTL files
  - Optional dependencies: `pip install ontoskills[embeddings]`

### Fixed

- Knowledge node filtering with JSON parsing and warnings for malformed data
- SHACL validation for KnowledgeNode shapes

## [0.7.3] - 2026-03-19

### Fixed

- Added `license` and `classifiers` metadata to `pyproject.toml` to fix missing Python and License badges on PyPI.
- Copied `LICENSE` file into the package directory.

## [0.7.2] - 2026-03-19

### Fixed

- Fixed missing PyPI project description by declaring `readme = "README.md"` in `pyproject.toml`.

## [0.7.1] - 2026-03-19

### Added

- Added dedicated comprehensive `README.md` for the PyPI package.

## [0.7.0] - 2026-03-19

### Added

#### Core Infrastructure

- **schemas.py** — Pydantic models for structured skill extraction
  - `Requirement` model with types: EnvVar, Tool, Hardware, API, Knowledge
  - `ExecutionPayload` model for code execution (executor, code, timeout)
  - `ExtractedSkill` model with Knowledge Architecture fields (nature, genus, differentia)
  - `StateTransition` model for state machine definitions

- **exceptions.py** — Custom exception hierarchy with exit codes
  - `SkillETLError` (base, exit_code=1)
  - `SecurityError` (exit_code=3)
  - `ExtractionError` (exit_code=4)
  - `OntologyLoadError` (exit_code=5)
  - `SPARQLError` (exit_code=6)
  - `SkillNotFoundError` (exit_code=7)
  - `OntologyValidationError` (exit_code=8)

#### Extraction Pipeline

- **extractor.py** — Deterministic ID and hash generation
  - `generate_skill_id()` — Slugifies directory names to kebab-case (max 64 chars)
  - `compute_skill_hash()` — SHA-256 hash of all skill files (sorted, recursive)

- **transformer.py** — LLM tool-use extraction
  - Tool definitions: `list_files`, `read_file`, `extract_skill`
  - Tool-use loop with max 20 iterations, 120s timeout
  - Knowledge Architecture system prompt
  - Path traversal protection in file reading
  - State transition extraction instructions

#### Security Pipeline

- **security.py** — Defense-in-depth security checks
  - Stage 1: Regex pattern matching for prompt injection, command injection, data exfiltration, path traversal, credential exposure
  - Stage 2: LLM-as-judge with Haiku for nuanced review
  - Unicode normalization (NFC, zero-width removal)
  - Fail-closed error handling

#### Ontology Loader

- **core_ontology.py** — Namespace management and core TBox ontology creation
- **serialization.py** — Pydantic-to-RDF serialization with SHACL gatekeeper
- **storage.py** — File I/O, intelligent merging, orphan cleanup

- Full OWL 2 property characteristics:
  - `ag:dependsOn` — AsymmetricProperty with inverse `ag:enables`
  - `ag:extends` — TransitiveProperty with inverse `ag:isExtendedBy`
  - `ag:contradicts` — SymmetricProperty
  - `ag:implements` / `ag:exemplifies` with inverses

- Skill serialization to RDF triples
- Intelligent merge strategy: skip unchanged (hash match), update modified, add new
- Atomic writes with backup/restore pattern
- `--reason` flag for OWL reasoning with owlrl
- Predefined states: SystemAuthenticated, PermissionDenied, etc.

#### SHACL Validation

- **validator.py** — Constitutional validation layer
  - `ValidationResult` NamedTuple with `conforms`, `results_text`, `results_graph`
  - `load_shacl_shapes()` — Loads constitutional shapes from `specs/ontoskills.shacl.ttl`
  - `load_core_ontology()` — Loads TBox for `sh:class` validation
  - `validate_skill_graph()` — Validates RDF graph against SHACL shapes with RDFS inference
  - `validate_and_raise()` — Raises `OntologyValidationError` on failure

- **specs/ontoskills.shacl.ttl** — Constitutional SHACL shapes
  - `oc:SkillShape` — Base constraints (resolvesIntent, generatedBy required)
  - `oc:ExecutableSkillShape` — Constraints for skills with payloads
  - `oc:DeclarativeSkillShape` — Constraints for knowledge-only skills
  - `oc:ExecutionPayloadShape` — Payload constraints

#### SPARQL Engine

- **sparql.py** — Query execution against ontology
  - SELECT query support
  - Mutation prevention (no INSERT/DELETE)
  - Multiple output formats: `table`, `json`, `turtle`

#### CLI Interface

- **cli.py** — Complete Click-based CLI
  - Commands: `init-core`, `compile`, `query`, `list-skills`, `security-audit`
  - Options: `-i/--input`, `-o/--output`, `--dry-run`, `--skip-security`, `--reason/--no-reason`, `-y/--yes`, `-v/--verbose`, `-q/--quiet`
  - `--force` flag to bypass hash-based caching

### Dependencies

- `anthropic>=0.39.0` — Claude API for extraction
- `click>=8.1.0` — CLI framework
- `pydantic>=2.0.0` — Data validation
- `rdflib>=7.0.0` — RDF graph handling
- `rich>=13.0.0` — Terminal formatting
- `owlrl>=1.0.0` — OWL reasoning
- `pyshacl>=0.25.0` — SHACL validation

### Testing

- 156 tests with comprehensive coverage
- Tests for schemas, exceptions, extraction, transformation, security, serialization, storage, SPARQL, CLI, and validation
