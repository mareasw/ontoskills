---
title: Registry & Packages
description: Package distribution and import for OntoSkills
---

## Overview

OntoSkills supports a simplified registry and import model:

- User-facing product root: `~/.ontoskills/`
- Imported source repositories: `~/.ontoskills/skills/vendor/`
- Compiled imported packages: `~/.ontoskills/ontoskills/vendor/`
- Runtime state: `~/.ontoskills/state/`

## Important Files

| File | Purpose |
|------|---------|
| `~/.ontoskills/state/registry.lock.json` | Installed packages manifest |
| `~/.ontoskills/state/registry.sources.json` | Configured registry sources |
| `~/.ontoskills/ontoskills/index.installed.ttl` | All installed skills |
| `~/.ontoskills/ontoskills/index.enabled.ttl` | Enabled skills (runtime) |

## Package Types

| Type | Description |
|------|-------------|
| **Registry packages** | Compiled `.ttl` modules from GitHub repo |
| **Source repositories** | Raw `SKILL.md` files, compiled locally |

## CLI Commands

```bash
# Search the official registry
ontoskills search hello

# Install a package
ontoskills install marea.greeting/hello

# Enable for runtime
ontoskills enable marea.greeting/hello

# List installed packages
ontoskills list-installed

# Rebuild indexes after manual changes
ontoskills rebuild-index

# Add third-party registry (optional)
ontoskills registry add-source acme https://example.com/index.json
ontoskills registry list
```

## End-User Flow

For most users, the expected flow is:

```bash
ontoskills search hello
ontoskills install marea.greeting/hello
ontoskills enable marea.greeting/hello
```

No manual registry setup is required — the official registry is built-in.

## Official Registry

The official compiled skill registry is at:
- `https://github.com/mareasoftware/ontoskills-registry`

First demo package:
- `marea.greeting/hello`

## Managed Installs

```bash
# Install MCP server
ontoskills install mcp

# Install core compiler
ontoskills install core

# Update components
ontoskills update mcp
ontoskills update core
```

## Import Source Repositories

```bash
# Import and compile a raw source repo
ontoskills import-source https://github.com/user/skill-repo
```

## Identity Model

| Format | Description |
|-------|-------------|
| Canonical | `package_id/skill_id` (e.g., `marea.office/xlsx`) |
| Short ID | Just `xlsx` (resolves via precedence) |

Resolution precedence:
1. `local` > `verified` > `trusted` > `community`
