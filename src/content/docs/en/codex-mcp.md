---
title: MCP with Codex
description: Configure OntoMCP for Codex-based local workflows
sidebar:
  order: 12
---

## Install

Install the runtime first:

```bash
npx ontoskills install mcp
```

This installs:

```text
~/.ontoskills/bin/ontomcp
```

## Fast Bootstrap

The recommended setup is:

```bash
npx ontoskills install mcp --codex
```

Manual equivalent:

```bash
codex mcp add ontomcp -- ~/.ontoskills/bin/ontomcp
```

Codex global setup uses the same local `stdio` command as other clients:

```text
~/.ontoskills/bin/ontomcp
```

## Integration Model

Codex-based workflows use the same MCP contract as other local clients:

- launch `ontomcp` as a local `stdio` subprocess
- point it at the managed ontology home in `~/.ontoskills/ontologies`
- let the client call the five public tools

The stable executable to register is:

```text
~/.ontoskills/bin/ontomcp
```

## Recommended Runtime Command

```bash
~/.ontoskills/bin/ontomcp --ontology-root ~/.ontoskills/ontologies
```

If your Codex client supports environment-based configuration, the equivalent setting is:

```bash
ONTOMCP_ONTOLOGY_ROOT=~/.ontoskills/ontologies
```

## Tools Exposed

- `search_skills`
- `get_skill_context`
- `evaluate_execution_plan`
- `query_epistemic_rules`
- `search_intents`

## Notes

- The MCP server reads compiled `.ttl` ontologies, not raw `SKILL.md`
- If you want custom skills, install the compiler too:

```bash
npx ontoskills install core
```

- Then compile or import source skills — they are auto-enabled on install for MCP access
- `--codex` automates Codex global setup only; for repository-local Codex MCP config, `ontoskills` currently prints manual steps instead of forcing a non-standard config file

## Practical Rule

Treat Codex integration as a standard local `stdio` MCP registration whose command points at:

```text
~/.ontoskills/bin/ontomcp
```

The exact UI or config file shape may vary across Codex builds, but the server command and ontology root remain the same.

