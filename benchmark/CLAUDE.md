# OntoSkills Benchmark

## Prerequisites

### Environment variables
- `ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN` — required for both agents
- `ANTHROPIC_BASE_URL` — set to `https://api.z.ai/api/anthropic` (proxy)
- Model ID: `glm-5.1` (via proxy, NOT a standard Claude model)

### Python dependencies
```
datasets    — HuggingFace dataset loading (installed)
anthropic   — API client (installed)
rdflib      — TTL parsing for content coverage (installed)
```

### NOT available
- `gaia-benchmark/GAIA` — gated dataset on HuggingFace. Requires `huggingface-cli login` first. NOT authenticated currently.

### Binary prerequisites
- `ontomcp` at `~/.ontoskills/bin/ontomcp` — Rust MCP server, rebuild from `mcp/` if outdated
- Compiled TTLs at `~/.ontoskills/packages/` — 840 files (408 skills + sub-skills), 11 author packages

## Architecture

```
benchmark/
├── run.py                  # Main orchestrator (CLI entry point)
├── content_coverage.py     # Parser coverage + knowledge yield (no API calls)
├── config.py               # Model pricing, benchmark definitions
├── agents/
│   ├── base.py             # BaseAgent with Anthropic API, run-loop, retry
│   ├── traditional.py      # Skill registry + read_skill tool (like Claude Code)
│   └── ontoskills.py       # 4 MCP tools (search, get_skill_context, etc.)
├── wrappers/
│   ├── gaia.py             # GAIA: Q&A with file attachments
│   ├── skillsbench.py      # SkillsBench: Docker-based deterministic eval (podman + pytest)
│   └── swebench.py         # SWE-bench: repo checkout + diff patch generation
├── reporting/
│   ├── metrics.py          # compute_comparison()
│   └── comparison.py       # generate_comparison_report()
├── mcp_client/
│   └── client.py           # JSON-RPC MCP client for ontomcp subprocess
├── data/                   # Downloaded datasets (currently empty)
└── results/                # Benchmark output (JSON + comparison.md)
```

## Running benchmarks

### Content coverage (instant, no API)
```bash
ANTHROPIC_API_KEY="$ANTHROPIC_AUTH_TOKEN" \
python benchmark/content_coverage.py --verbose --ttl-dir ~/.ontoskills/packages --json benchmark/results/content_coverage.json
```

### SWE-bench (requires API)
```bash
ANTHROPIC_API_KEY="$ANTHROPIC_AUTH_TOKEN" \
python benchmark/run.py --benchmark swebench --mode both --max-tasks 25 --model glm-5.1 \
  --skills-dir .agents/skills --output-dir benchmark/results -v
```

### GAIA (requires HF auth — currently broken)
```bash
huggingface-cli login  # must do this first
python benchmark/run.py --benchmark gaia --mode both --model glm-5.1 ...
```

### SkillsBench (Docker-based deterministic evaluation)
```bash
# Prerequisites: clone the SkillsBench repo and have podman/docker available
git clone --depth 1 https://github.com/benchflow-ai/skillsbench /tmp/skillsbench_full

ANTHROPIC_API_KEY="$ANTHROPIC_AUTH_TOKEN" \
python benchmark/run.py --benchmark skillsbench --mode both --max-tasks 10 --model glm-5.1 \
  --skills-dir .agents/skills --output-dir benchmark/results \
  --skillsbench-repo /tmp/skillsbench_full -v
```

SkillsBench uses deterministic Docker evaluation:
1. Agent generates a Python solution script
2. Script is executed inside the task's Docker container (via podman)
3. Task's pytest test suite verifies the output files
4. Fractional scoring from CTRF report (passed/total tests) with binary reward.txt fallback

5 tasks are skipped due to exotic base images (bugswarm, suricata, oss-fuzz, erlang).

#### Agent design for SkillsBench

**Traditional agent**: SKILL.md content included directly in the user prompt (raw markdown).
No tools — the agent sees all skill documentation in one shot and generates code.

**OntoSkills agent**: Skills loaded via MCP prefetch from compiled TTLs. The user prompt
contains only the task instruction + Dockerfile metadata (89% smaller). Skill knowledge
(structured nodes with types, severity, context) is injected into the system prompt via
`get_skill_context`. No tools needed — single-turn code generation.

This tests OntoSkills' core advantage: **structured skill knowledge via MCP vs. raw SKILL.md**.

The MCP server uses a SkillsBench-only ontology root (`/tmp/skillsbench_ontology/`) containing
only the 218 SkillsBench TTLs (vs. 626 total). This reduces MCP startup from 10s to 1.8s and
query time from 3.8s to 0.27s per skill.

## Known issues

### SWE-bench wrapper: custom run-loop required
The SWE-bench wrapper patches `agent.run_turn` to intercept file_read/file_edit. It does NOT use `BaseAgent.run()` — it has a custom loop because `BaseAgent.run()` double-appends messages when `run_turn` also appends. See `swebench.py:run_task()` for the custom loop.

### Content coverage: core.ttl must be loaded
The knowledge yield Level 2 SPARQL uses `rdfs:subClassOf*` property paths to resolve leaf types (e.g., `oc:AntiPattern`) to top-level dimensions (e.g., `oc:NormativeRule`). This requires `core.ttl` loaded in the graph. The file is at `ontoskills/core.ttl` in the project root, NOT in `~/.ontoskills/packages/`.

### `trust_remote_code` deprecation
HuggingFace datasets no longer supports `trust_remote_code=True`. The SWE-bench wrapper has been fixed to not pass it. GAIA wrapper still passes it — will get a warning but works.

## Test verification

Run before any changes:
```bash
cd /home/marcello/Documenti/onto/ontoskills/core
python -m pytest tests/ -q
```

Run benchmark tests:
```bash
cd /home/marcello/Documenti/onto/ontoskills
python -m pytest benchmark/tests/ -q
```

Run smoke test after compilation:
```bash
python benchmark/smoketest.py
```

## Prefetch optimization

OntoSkillsAgent supports `prefetch=True` mode:
1. Before the first API call, calls MCP `search` + `get_skill_context`
2. Compacts the verbose MCP JSON into lean markdown-like text
3. Injects into system prompt — model has knowledge from turn 1
4. Removes tool schemas when knowledge is pre-loaded (no tool calls needed)

Result: OntoSkills at **0.86x tokens** vs Traditional (input is 0.40x), with better quality (4.6/5 vs 3.7/5).

## MCP response compaction

All MCP tool responses are compacted in real-time to minimize token usage:

- **search**: 90% reduction — keeps only skill_id, intents, trust_tier
- **get_skill_context**: 79% reduction — formatted as markdown with knowledge nodes sorted by priority
- **evaluate_execution_plan**: 96% reduction — plan steps + warnings only
- **query_epistemic_rules**: 79% reduction — directive content with context and severity

Compaction is applied in `OntoSkillsAgent.run_turn()` via `_compact_tool_result()` which dispatches
to tool-specific compactors (`_compact_search`, `_compact_epistemic_rules`, `_compact_plan`).

Additionally, the ontomcp server (Rust) strips null fields, empty Vecs, URIs, and unavailable
payloads from JSON responses via `#[serde(skip_serializing_if)]` annotations in `catalog.rs`.

## Traditional agent design

The TraditionalAgent works like Claude Code:
- System prompt contains a **skill registry** with all 425 skill names + descriptions (~28K tokens)
- Model has a `read_skill` tool to load full SKILL.md content on demand
- Multi-turn loop: model reads relevant skills then answers
- Both GAIA and SWE-bench wrappers delegate `read_skill` to `agent._resolve_skill()`

## Current benchmark results (2026-04-27, SkillsBench redesign)

### SkillsBench
- 73/82 tasks usable (9 skipped: skills not compiled to TTL due to compiler bug)
- 5 tasks skipped: exotic Docker images (bugswarm, suricata, oss-fuzz, erlang)
- Tasks shuffled with seed=7 before selection
- OntoSkills uses SkillsBench-only ontology root (185 TTLs, 1.4s MCP startup)
- Docker verification: podman + pytest CTRF fractional scoring

_Results pending — first corrected run in progress._

### GAIA
_Results pending — run with compaction enabled._

### SWE-bench
_Results pending — run with compaction enabled._

### Compiler bug (unrelated to benchmark)
11 skills across 9 tasks failed to compile to TTL. Root cause: `ontocore compile`
with `-o` flag resolves `state_dir` incorrectly, creating `/state` instead of
relative path. The 11 missing skills are:
civ6lib, map-optimization-strategy, sqlite-map-parser, pymatgen, lean4-memories,
gemini-video-understanding, senior-data-scientist, gmail-skill, threejs,
data-reconciliation.

