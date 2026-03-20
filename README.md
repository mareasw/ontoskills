<p align="center">
  <img src="assets/ontoskills-banner.png" alt="OntoSkills" width="100%">
</p>

<h1 align="center">OntoSkills</h1>

<p align="center">
  Neuro-symbolic skill platform for deterministic AI agents.
</p>

OntoSkills turns `SKILL.md` sources into queryable OWL 2 ontologies, ships a local MCP runtime, and publishes compiled skills through a built-in official registry.

## Quick Start

```bash
npx ontoskills install mcp
npx ontoskills install core
npx ontoskills search hello
npx ontoskills install marea.greeting/hello
npx ontoskills enable marea.greeting/hello
```

## What Ships

| Component | Purpose |
|-----------|---------|
| `ontoskills` | User-facing CLI for installs, updates, registry management, and source imports |
| `ontocore` | Skill compiler for `SKILL.md` sources |
| `ontomcp` | Local MCP server for semantic skill discovery and planning |
| `OntoSkillRegistry` | Official compiled skill registry, built in by default |

## Docs

- [Overview](docs/overview.md)
- [Getting Started](docs/getting-started.md)
- [Architecture](docs/architecture.md)
- [Knowledge Extraction](docs/knowledge-extraction.md)
- [Registry](docs/registry.md)
- [Roadmap](docs/roadmap.md)

## Repository Layout

```text
core/        compiler
mcp/         MCP runtime
docs/        long-form documentation
registry/    official registry blueprint
site/        public site
skills/      source skills
ontoskills/  compiled ontology artifacts
```

## Registry Model

- The official registry is built into `ontoskills`.
- `registry add-source` is for third-party registries only.
- Raw source repos are cloned into `~/.ontoskills/skills/vendor/` and compiled into `~/.ontoskills/ontoskills/vendor/`.
- See [Registry](docs/registry.md) for install, update, remove, and uninstall workflows.

## Related Links

- [Ontology Registry repo](https://github.com/mareasoftware/OntoSkillRegistry)
- [Project site](https://ontoskills.marea.software)
