---
title: Roadmap
description: OntoClaw development phases and future direction
---

> **Note:** We ship fast. This roadmap evolves with the project.

## Phase 1: Compiler ✅

**Status:** Complete

Transform `SKILL.md` files into validated OWL 2 DL ontologies.

- [x] Natural language parsing with Claude
- [x] OWL 2 DL serialization (RDF/Turtle)
- [x] SHACL validation gatekeeper
- [x] Security audit pipeline
- [x] 150+ tests

## Phase 2: MCP Server 🔨

**Status:** In Development

Expose ontologies via the Model Context Protocol.

- [ ] Rust MCP server with stdio transport
- [ ] Oxigraph in-memory graph store
- [ ] SPARQL query interface
- [ ] Runtime ABox updates
- [ ] Claude Desktop integration

## Phase 3: OntoStore 💡

**Status:** Planned

Centralized repository for compiled ontologies.

- [ ] Ontology registry
- [ ] Version management
- [ ] Dependency resolution
- [ ] Community contributions

## Phase 4+: Ecosystem 🔮

**Status:** Exploratory

Broader ecosystem integration.

- [ ] VSCode extension
- [ ] Multi-agent collaboration
- [ ] Shared knowledge graphs
- [ ] Cross-platform skill sharing

---

## Track Progress

Follow development on [GitHub](https://github.com/mareasoftware/ontoclaw).

Have ideas? [Open an issue](https://github.com/mareasoftware/ontoclaw/issues).
