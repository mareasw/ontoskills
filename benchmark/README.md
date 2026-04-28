# OntoSkills Benchmarks

Benchmark suite comparing **OntoSkills** (MCP-powered skill queries) vs **Traditional** (stuffing skill docs into the prompt) across three standard agent benchmarks.

## Benchmarks

### GAIA

General AI Assistant benchmark. Agents answer questions that may include file attachments.

- **Dataset**: `gaia-benchmark/GAIA` (HuggingFace)
- **Levels**: `2023_level1`, `2023_level2`, `2023_level3`
- **Metric**: Exact-match accuracy against gold answers
- **Tools injected**: `read_file` (for file attachments)

### SWE-bench

Software engineering benchmark. Agents produce unified-diff patches to resolve GitHub issues.

- **Dataset**: `princeton-nlp/SWE-bench_Verified` (HuggingFace)
- **Metric**: Resolve rate (requires external `swebench.harness` evaluation)
- **Tools injected**: `file_read`, `file_edit` (operate on checked-out repos)
- **Output**: `predictions.json` compatible with the SWE-bench harness

### Tau2-Bench

Tool-use benchmark in simulated customer-service environments.

- **Domains**: airline, retail, banking
- **Metric**: String-match accuracy + pass^k metric
- **Tools injected**: Domain-specific tools from the tau2-bench dataset

## Quick Start

```bash
# Run all benchmarks with both agents (default)
python run.py

# Run a specific benchmark
python run.py --benchmark gaia --mode both

# Only the OntoSkills agent
python run.py --benchmark swebench --mode ontoskills --ttl-dir /path/to/ttls

# Only the traditional agent (needs ANTHROPIC_API_KEY)
python run.py --benchmark gaia --mode traditional --skills-dir /path/to/skills

# Limit tasks for a quick test
python run.py --benchmark gaia --mode both --max-tasks 5
```

## CLI Options

| Flag | Default | Description |
|------|---------|-------------|
| `--benchmark` | `all` | `gaia`, `swebench`, `tau2bench`, or `all` |
| `--mode` | `both` | `traditional`, `ontoskills`, or `both` |
| `--skills-dir` | `benchmark/skills/` | SKILL.md files for traditional agent |
| `--ttl-dir` | `~/.ontoskills/packages` | TTL ontology packages for OntoSkills agent |
| `--ontomcp-bin` | `~/.ontoskills/bin/ontomcp` | Path to ontomcp binary |
| `--model` | First Anthropic model | Anthropic model ID |
| `--max-tasks` | all | Limit tasks per benchmark |
| `--output-dir` | `benchmark/results/` | Where to write results |
| `-v` | off | Verbose logging |

## Structure

```
benchmark/
├── run.py                    # Main CLI orchestrator
├── config.py                 # Model pricing, benchmark definitions
├── agents/
│   ├── base.py               # Abstract BaseAgent (run-loop, API helper)
│   ├── traditional.py        # Stuff-all-skills-into-prompt agent
│   └── ontoskills.py         # MCP-powered agent (4 tools)
├── wrappers/
│   ├── gaia.py               # GAIA benchmark wrapper
│   ├── swebench.py           # SWE-bench benchmark wrapper
│   └── tau2bench.py          # Tau2-Bench benchmark wrapper
├── mcp_client/
│   └── client.py             # JSON-RPC 2.0 client for ontomcp binary
├── reporting/
│   ├── metrics.py            # Metric aggregation and comparison logic
│   └── comparison.py         # Markdown report generator
├── ontomcp-bench/            # Rust SPARQL microbenchmark (legacy)
├── content_coverage.py       # SKILL.md RDF coverage analysis
└── results/                  # Output (gitignored)
    ├── gaia/
    │   ├── traditional/
    │   └── ontoskills/
    ├── swebench/
    ├── tau2bench/
    └── comparison.md
```

## What Gets Measured

For each benchmark and agent mode, the following metrics are collected:

- **Quality**: Accuracy / resolve rate / pass rate per benchmark
- **Tokens**: Input, output, and total tokens per task
- **Latency**: Wall-clock time per task (ms)
- **Cost**: Projected cost across 7 models using `config.MODEL_PRICING`
- **Tool calls**: Number of tool invocations per task
- **Turns**: Number of agent-LLM turns per task
- **Context overflow**: Whether the prompt exceeded the model's context window

When both modes are run, a comparison report is generated at `results/comparison.md` with:

1. **Quality** -- accuracy delta per benchmark
2. **Efficiency** -- tokens, latency, turns comparison
3. **Cost** -- per-model cost projections
4. **Aggregate** -- weighted averages, overall improvement
5. **Workflow** -- tool usage patterns

## Prerequisites

- Python 3.10+ with `anthropic`, `datasets` packages
- `ANTHROPIC_API_KEY` env var (required for both agents)
- `ontomcp` binary (for OntoSkills agent) at `~/.ontoskills/bin/ontomcp`
- TTL ontology packages at `~/.ontoskills/packages/`
- Optional: `tau2-bench` package for Tau2-Bench

## Content Coverage Benchmark

Separate tool that measures how much of each SKILL.md is captured as typed RDF content blocks.

```bash
python benchmark/content_coverage.py --verbose
```

Target: 95%+ line-level coverage across real skills.
