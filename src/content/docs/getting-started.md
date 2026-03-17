---
title: Getting Started
description: Install and use OntoClaw to compile skills into ontologies
---

OntoClaw is currently in **Phase 2** development. The compiler is ready, MCP server is in progress.

## Prerequisites

- **Python** 3.10+
- **pip** or **uv** package manager

## Installation

```bash
# Clone the repository
git clone https://github.com/mareasoftware/ontoclaw.git
cd ontoclaw

# Install compiler
cd compiler
pip install -e ".[dev]"
```

## CLI Commands

```bash
# Initialize core ontology with predefined states
ontoclaw init-core

# Compile all skills to ontology
ontoclaw compile

# Compile specific skill
ontoclaw compile my-skill

# Query ontology with SPARQL
ontoclaw query "SELECT ?s WHERE { ?s a oc:Skill }"

# List all skills
ontoclaw list-skills

# Run security audit
ontoclaw security-audit
```

## Command Options

| Option | Description |
|--------|-------------|
| `-i, --input` | Input directory (default: `./skills/`) |
| `-o, --output` | Output file (default: `./ontoskills/skills.ttl`) |
| `--dry-run` | Preview without saving |
| `--skip-security` | Skip security checks (not recommended) |
| `-f, --force` | Force recompilation (bypass hash-based cache) |
| `--reason/--no-reason` | Apply OWL reasoning |
| `-v, --verbose` | Debug logging |

## MCP Server (Phase 2)

The MCP server will expose ontologies via the Model Context Protocol:

```bash
# Coming soon
ontoclaw-mcp --ontologies ./ontoskills/
```

### Claude Desktop Integration

Once available, add to your Claude Desktop config:

```json
{
  "mcpServers": {
    "ontoclaw": {
      "command": "ontoclaw-mcp",
      "args": ["--ontologies", "/path/to/ontoskills"]
    }
  }
}
```

## What's Next?

- [Roadmap](/roadmap/) — See what's coming
- [GitHub](https://github.com/mareasoftware/ontoclaw) — Contribute
