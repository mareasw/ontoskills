---
title: MCP 运行时
description: 通用 OntoMCP 运行时指南和安装流程
---

`OntoMCP` 是 OntoSkills 的运行时层。它从托管本地主目录加载已编译的本体，并通过 `stdio` 上的模型上下文协议暴露它们。

标准产品安装是：

```bash
npx ontoskills install mcp
```

这将在以下位置安装运行时二进制文件：

```text
~/.ontoskills/bin/ontomcp
```

## OntoMCP 加载什么

首选运行时源：

- `~/.ontoskills/ontoskills/index.enabled.ttl`

回退：

- `~/.ontoskills/ontoskills/ontoskills-core.ttl`
- `index.ttl`
- `*/ontoskill.ttl`

你可以用以下方式覆盖本体根目录：

```bash
ONTOMCP_ONTOLOGY_ROOT=/path/to/ontoskills
```

或：

```bash
~/.ontoskills/bin/ontomcp --ontology-root /path/to/ontoskills
```

## 工具界面

当前的公共 MCP 工具是：

- `search_skills`
- `get_skill_context`
- `evaluate_execution_plan`
- `query_epistemic_rules`

服务器不执行负载。它返回结构化上下文、规划输出和认识规则。执行仍然是调用客户端或智能体的责任。

## 本地开发

从仓库根目录：

```bash
cargo run --manifest-path mcp/Cargo.toml -- --ontology-root ./ontoskills
```

运行测试：

```bash
cargo test --manifest-path mcp/Cargo.toml
```

## 客户端指南

- [Claude Code](./mcp-claude-code.md)
- [Codex](./mcp-codex.md)
