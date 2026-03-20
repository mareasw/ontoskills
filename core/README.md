<h1 align="center">
  OntoSkills Core
</h1>

<p align="center">
  <strong>The neuro-symbolic compiler for the <a href="https://ontoskills.sh">OntoSkills</a> platform.</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/ontoskills/"><img src="https://img.shields.io/pypi/v/ontoskills.svg?color=blue&style=for-the-badge" alt="PyPI version"></a>
  <img src="https://img.shields.io/pypi/pyversions/ontoskills.svg?style=for-the-badge" alt="Python versions">
  <img src="https://img.shields.io/badge/OWL%202-RDF%2FTurtle-green?style=for-the-badge&logo=w3c" alt="OWL 2">
  <a href="https://github.com/mareasoftware/ontoskills/blob/main/LICENSE"><img src="https://img.shields.io/pypi/l/ontoskills.svg?style=for-the-badge" alt="License"></a>
</p>

---

## What is `ontoskills`?

`ontoskills` is the core Python engine of the **OntoSkills** platform. It acts as a **neuro-symbolic compiler** that transforms unstructured, human-readable AI skills (`SKILL.md`) into strictly validated, queryable **OWL 2 ontologies**.

By combining the natural language understanding of LLMs with the deterministic formal logic of RDF and SHACL validation, `ontoskills` ensures that AI agents operate on exact, verifiable knowledge graphs rather than probabilistic prompts.

### Key Capabilities

- **LLM Knowledge Extraction**: Extracts structured triples (Dependencies, Inputs, Intents, Operations) from markdown files.
- **SHACL Validation**: Ensures the extracted semantic graph strictly adheres to the OntoSkills Core Ontology.
- **OWL 2 Compilation**: Outputs self-contained `.ttl` (Turtle) graphs ready for deterministic SPARQL querying.
- **Local Registry Management**: Handles the installation, enabling, and indexing of distributed skills packages.
- **Security Auditing**: Analyzes the graph for conflicting intents, missing dependencies, or shadowed skills.

---

## Installation

Install the compiler directly from PyPI (requires Python 3.10+):

```bash
pip install ontoskills
```

---

## Quick Start

### 1. Initialize the Environment

Create the necessary folder structure (`.ontoskills/`) in your project:

```bash
ontoskills init-core
```

### 2. Configure the LLM

`ontoskills` needs an LLM to extract relationships. Create a `.env` file or export the keys:

```bash
export OPENAI_API_KEY="sk-..."
```
*(Anthropic is also supported via `ANTHROPIC_API_KEY`)*

### 3. Compile Skills

Assuming you have `SKILL.md` files in a `skills/` directory, run the compiler:

```bash
ontoskills compile
```
This will read the markdown files, extract knowledge, validate it via SHACL, and generate `.ttl` ontology files in the `.ontoskills/` output directory.

### 4. Query the Knowledge Graph

You can perform exact graph queries using SPARQL directly from the CLI:

```bash
ontoskills query "SELECT ?skill WHERE { ?skill oc:resolvesIntent 'create_pdf' }"
```

---

## CLI Reference

The package provides the `ontoskills` command-line tool. Here are the main commands:

### Core Commands
- `ontoskills compile`: Compile local skills to validated OWL 2 ontologies.
- `ontoskills query <sparql_query>`: Execute a SPARQL query against the compiled domain graph.
- `ontoskills security-audit`: Run security checks against the knowledge graph to find issues.
- `ontoskills init-core`: Initialize an empty OntoSkills registry in the current directory.
- `ontoskills list-skills`: List all successfully compiled skills in the domain graph.

### Registry & Packages
- `ontoskills install-package <path>`: Install a `.tar.gz` skill package.
- `ontoskills import-source-repo <url>`: Import skills directly from a remote Git repository.
- `ontoskills install`: Download and install all dependencies declared in the lockfile.
- `ontoskills enable <skill_id>`: Enable an installed skill.
- `ontoskills disable <skill_id>`: Disable an installed skill.
- `ontoskills list-installed`: Show all installed packages and their status.
- `ontoskills rebuild-index`: Rebuild the registry index manually.

Run `ontoskills --help` or `ontoskills <command> --help` for detailed usage.

---

## Documentation & Source

For the full documentation, architecture details, and to contribute to the project, please visit the main repository:

👉 **[mareasoftware/ontoskills GitHub Repository](https://github.com/mareasoftware/ontoskills)**

---

*© 2026 [Marea Software](https://marea.software)*
