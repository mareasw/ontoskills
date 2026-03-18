---
title: What is OntoClaw?
description: Neuro-symbolic skill core for the Agentic Web
---

**OntoClaw** is a complete neuro-symbolic platform for building deterministic, enterprise-grade AI agents. It transforms natural language skill definitions into **validated OWL 2 ontologies** — queryable knowledge graphs that enable deterministic reasoning.

## Why OntoClaw?

### The Determinism Problem

LLMs read skills probabilistically. Same query, different results. Long skill files are expensive for large models and confusing for small ones.

- **Non-deterministic reading** — LLMs interpret text differently each time
- **Token waste** — Large models burn tokens parsing long documentation
- **Small model limits** — Complex skills are unreadable by edge models

### The Ontological Solution

OntoClaw transforms skills into formal ontologies with **Description Logics (OWL 2)**:

- **Deterministic queries** — SPARQL returns exact answers, every time
- **Entailment reasoning** — Infer dependencies, conflicts, capabilities
- **Democratized intelligence** — Small models query what large models read

### Performance Comparison

| Operation | Reading Files | Ontology Query |
|-----------|---------------|----------------|
| Find skill by intent | O(n) text scan | O(1) indexed lookup |
| Check dependencies | Parse each file | Follow `dependsOn` edges |
| Detect conflicts | Compare all pairs | Single SPARQL query |

For 100 skills: **~500KB text scan → ~1KB query**

## How It Works

<img src="/architecture.webp" alt="OntoCore Architecture" style="max-height: 500px; width: auto; max-width: 100%; display: block; margin: 0 auto;" />

## Key Capabilities

| Capability | Description |
|------------|-------------|
| **LLM Extraction** | Claude extracts structured knowledge from SKILL.md files |
| **Knowledge Architecture** | Follows the "A is a B that C" definition pattern (genus + differentia) |
| **OWL 2 Serialization** | Outputs valid OWL 2 ontologies in RDF/Turtle format |
| **SHACL Validation** | Constitutional gatekeeper ensures logical validity before write |
| **State Machines** | Skills can define preconditions, postconditions, and failure handlers |
| **Security Pipeline** | Defense-in-depth: regex patterns + LLM review for malicious content |

## Components

| Component | Language | Status | Description |
|-----------|----------|--------|-------------|
| **OntoCore** | Python | ✅ Ready | Skill core to OWL 2 ontology |
| **OntoSkills** | Turtle | Generated | Compiled ontology output |
| **OntoMCP** | Rust | ✅ Ready | MCP server with 12 semantic tools |
| **OntoStore** | TBD | 🚧 Planned | Versioned skill registry |
| **OntoClaw** | Python/Rust | 📋 Planned | Enterprise AI agent |
| **skills/** | Markdown | ✅ Ready | Input skill definitions |
| **specs/** | Turtle | ✅ Ready | SHACL shapes constitution |

## Get Started

[Get Started](/getting-started/) with OntoClaw in minutes.

## Links

- [GitHub Repository](https://github.com/mareasoftware/ontoclaw)
- [Roadmap](/roadmap/)
