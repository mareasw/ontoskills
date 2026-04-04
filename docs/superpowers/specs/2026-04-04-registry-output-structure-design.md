# Design: Registry Output Structure & Package ID System

**Date**: 2026-04-04
**Status**: Draft

## Context

The OntoSkills compiler output directory (`ontostore/`) has structural problems:
1. A spurious `skills/` intermediate directory appears in output (e.g., `ontostore/packages/skills/remotion-best-practices/`)
2. No `index.json` registry file exists for the MCP server and npx tool to discover packages
3. `oc:generatedBy` in TTL files is misplaced — should be in the registry metadata
4. Package IDs are derived from config files (package.json/toml) rather than directory structure
5. No concept of "default author" for skills without a vendor

## Design

### 1. Output Structure — Exact Mirror

The output mirrors the input path exactly under `ontostore/packages/`. System files go in `ontostore/system/`.

**Convention**: Always compile at vendor level: `-i .agents/skills/{vendor}/ -o ontostore/packages/`

```
# Compile: -i .agents/skills/obra/ -o ontostore/packages/
ontostore/
├── packages/
│   ├── obra/superpowers/brainstorming/ontoskill.ttl
│   ├── obra/superpowers/tdd/ontoskill.ttl
│   └── obra/superpowers/impeccable/ontoskill.ttl
├── system/
│   ├── index.json            ← NEW: flat registry
│   ├── index.ttl
│   ├── index.enabled.ttl
│   ├── registry.lock.json
│   └── compile-errors.json
```

**Key rule**: `output_path / rel_path` where `rel_path = skill_dir.relative_to(input_path)`. No intermediate `skills/` or other spurious directories.

### 2. Package ID — Path-based Inference

The `package_id` is everything in the path between `-i` and the directory containing `SKILL.md`:

| Input (-i) | Skill dir | package_id |
|------------|-----------|------------|
| `.agents/skills/obra/` | `obra/superpowers/brainstorming/` | `obra/superpowers` |
| `.agents/skills/coinbase/` | `coinbase/agentic-wallet-skills/trade/` | `coinbase/agentic-wallet-skills` |
| `.agents/skills/remotion-dev/` | `remotion-dev/skills/remotion-best-practices/` | `remotion-dev/skills` |
| `.agents/skills/my-skill/` | `my-skill/` (SKILL.md in root of -i) | `{DEFAULT_SKILLS_AUTHOR}` |

**Algorithm**:
1. Compute `rel_path = skill_dir.relative_to(input_path)`
2. `parts = rel_path.parts` — all path segments except the last (which is the skill dir)
3. If `parts` is non-empty → `package_id = "/".join(parts)`
4. If `parts` is empty (SKILL.md at root of -i) → use `DEFAULT_SKILLS_AUTHOR` env var
5. If `DEFAULT_SKILLS_AUTHOR` is not set → warn and fallback to `"local"`

### 3. index.json — Flat Global Registry

A single file `ontostore/system/index.json` listing all discovered packages and skills.

```json
{
  "version": 1,
  "packages": [
    {
      "package_id": "obra/superpowers",
      "trust_tier": "community",
      "source_kind": "ontology",
      "skills": [
        {
          "skill_id": "brainstorming",
          "manifest_url": "./packages/obra/superpowers/brainstorming/ontoskill.ttl",
          "generated_by": "glm-5.1",
          "generated_at": "2026-04-04T16:30:00"
        },
        {
          "skill_id": "tdd",
          "manifest_url": "./packages/obra/superpowers/tdd/ontoskill.ttl",
          "generated_by": "glm-5.1",
          "generated_at": "2026-04-04T16:32:15"
        }
      ]
    },
    {
      "package_id": "coinbase/agentic-wallet-skills",
      "trust_tier": "community",
      "source_kind": "ontology",
      "skills": [
        {
          "skill_id": "trade",
          "manifest_url": "./packages/coinbase/agentic-wallet-skills/trade/ontoskill.ttl",
          "generated_by": "glm-5.1",
          "generated_at": "2026-04-04T16:35:00"
        },
        {
          "skill_id": "x402",
          "manifest_url": "./packages/coinbase/agentic-wallet-skills/x402/ontoskill.ttl",
          "generated_by": "glm-5.1",
          "generated_at": "2026-04-04T16:36:30"
        }
      ]
    }
  ]
}
```

**Key properties**:
- Flat list — no vendor grouping (consumers like npx don't need it)
- `generated_by`, `generated_at`, and `manifest_url` are per-skill (each skill has its own TTL file)
- `manifest_url` is relative to `ontostore/` root
- `trust_tier` defaults to `"community"` (can be upgraded for verified packages)

**Merge/upsert logic**: When updating `index.json` during a compile run:
1. Read existing `system/index.json` (or start fresh if absent)
2. For each compiled skill, find the package by `package_id`
   - If package exists: find skill by `skill_id` and upsert (update `generated_by`, `generated_at`, `manifest_url`)
   - If skill doesn't exist in package: append to `skills` array
   - If package doesn't exist: append new package entry
3. Write back atomically — never duplicate entries

### 4. Environment Variables

| Variable | Purpose | Example |
|----------|---------|---------|
| `DEFAULT_SKILLS_AUTHOR` | Fallback author when skill has no vendor | `mareasw` |

No hardcoded defaults in code. If unset when needed, compiler emits a warning.

### 5. generated_by Migration

Move `oc:generatedBy` from individual TTL files to `index.json` per-skill metadata:
- **Remove** from `serialization.py`: the `if skill.generated_by` block that writes `oc:generatedBy` triple
- **Add** to `compile.py`: track `(skill_id, model_name, timestamp)` for each compiled skill
- **Write** to `system/index.json` at end of compilation

### 6. Files to Modify

| File | Change |
|------|--------|
| `core/src/extractor.py` | Rewrite `resolve_package_id()` to use path-based inference + DEFAULT_SKILLS_AUTHOR |
| `core/src/config.py` | Add `DEFAULT_SKILLS_AUTHOR` constant from env var |
| `core/src/cli/compile.py` | Track per-skill generation metadata; generate index.json at end |
| `core/src/serialization.py` | Remove `oc:generatedBy` triple |
| `core/src/storage.py` | Add `generate_registry_json()` for system/index.json |
| `mcp/src/catalog.rs` | Update `default_manifest` path; read index.json for package discovery |
| `mcp/src/main.rs` | Update `has_ontology_data` to check new paths |

### 7. Verification

1. Compile remotion-dev:
   ```bash
   rm -rf ontostore/ && python -m compiler.cli compile -i .agents/skills/remotion-dev/ -o ontostore/packages/ -f -y
   ```
   - Output should be `ontostore/packages/remotion-dev/skills/remotion-best-practices/ontoskill.ttl` (no spurious `skills/` at wrong level)
   - `system/index.json` should contain package_id `remotion-dev/skills`

2. Compile coinbase:
   ```bash
   python -m compiler.cli compile -i .agents/skills/coinbase/ -o ontostore/packages/ -f -y
   ```
   - Output: `ontostore/packages/coinbase/agentic-wallet-skills/trade/ontoskill.ttl`
   - `system/index.json` should now have 2 packages (remotion + coinbase)

3. Run tests:
   ```bash
   python -m pytest core/tests/ -q --tb=short
   ```

4. Verify MCP reads new index.json path
