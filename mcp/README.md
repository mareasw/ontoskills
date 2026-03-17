# OntoMCP

Rust-based MCP (Model Context Protocol) server for the OntoClaw ecosystem.

**Status:** 🚧 Planned

## Overview

OntoMCP is the **runtime layer** of OntoClaw. It loads compiled OntoSkills (`.ttl` files) into an in-memory RDF graph and provides blazing-fast SPARQL queries to AI agents via the Model Context Protocol.

```
┌─────────────────────────────────────────────────────────┐
│                      RUNTIME                            │
│                                                         │
│   Agent ◄──────► OntoMCP (Rust) ◄──────► .ttl files    │
│                                                         │
│   SKILL.md files DO NOT EXIST in the agent's context    │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

## Features (Planned)

- **Fast SPARQL queries** against compiled ontologies
- **Skill routing** based on state transitions (`requiresState`, `yieldsState`)
- **Schema exposure** — query TBox before ABox
- **Dependency resolution** via `oc:dependsOn` edges
- **Conflict detection** via `oc:contradicts` lookup
- **Integration with Claude** and other LLM clients via MCP

## Why Rust?

- **Performance**: Sub-millisecond SPARQL queries for real-time agent interaction
- **Memory efficiency**: Compact in-memory graph representation
- **Safety**: Memory-safe by design, critical for production deployments
- **Concurrency**: Parallel query execution without GIL limitations

## Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   MCP Tool   │     │  SPARQL      │     │  RDF Graph   │
│   Interface  │────►│  Engine      │────►│  (In-Memory) │
│              │     │              │     │              │
└──────────────┘     └──────────────┘     └──────────────┘
                                               │
                                               ▼
                                       ┌──────────────┐
                                       │  .ttl files  │
                                       │  (OntoSkills)│
                                       └──────────────┘
```

## Related Components

| Component | Language | Description |
|-----------|----------|-------------|
| **OntoCore** | Python | Design-time compiler |
| **OntoMCP** | Rust | Runtime server (this) |
| **OntoStore** | TBD | Skill registry (planned) |
| **OntoClaw** | Python/Rust | Enterprise AI agent (planned) |

---

*Part of the [OntoClaw ecosystem](../README.md).*
