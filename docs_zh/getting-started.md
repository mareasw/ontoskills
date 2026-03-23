---
title: 快速开始
description: 安装 OntoSkills、OntoMCP 和 OntoCore
---

OntoSkills 作为产品套件发布，包含三个部分：

- `ontoskills` - 面向用户的 CLI
- `ontomcp` - 本地 MCP 运行时
- `ontocore` - 可选的源技能编译器

OntoStore 默认内置。第三方商店可以显式添加。

## 前置条件

- **Node.js** 18+ 用于 `ontoskills` CLI
- **Git** 用于源导入
- 可选：**Python** 3.10+ 如果你安装 `ontocore`

## 安装

```bash
npx ontoskills install mcp
npx ontoskills install core
```

这将在 `~/.ontoskills/` 下创建一个托管的用户主目录，包含：

- `bin/ontomcp`
- `core/` 用于编译器运行时（如果已安装）
- `ontoskills/` 用于已编译的本体包
- `state/` 用于锁定文件和商店元数据

## 常用命令

```bash
ontoskills init-core
ontoskills compile
ontoskills compile my-skill
ontoskills query "SELECT ?s WHERE { ?s a oc:Skill }"
ontoskills list-skills
ontoskills security-audit
```

如果你只需要运行时和已发布的技能，则不需要编译器命令。

## 商店工作流

### 内置 OntoStore

OntoStore 已经对 `ontoskills` 可用。你可以发现并安装已发布的技能，无需任何额外设置。

```bash
npx ontoskills search hello
npx ontoskills install mareasw/greeting/hello
npx ontoskills enable mareasw/greeting/hello
```

### 第三方商店

```bash
ontoskills store add-source acme https://example.com/index.json
ontoskills store list
```

### 导入源技能

包含 `SKILL.md` 文件的原始仓库可以在本地导入和编译：

```bash
ontoskills import-source https://github.com/nextlevelbuilder/ui-ux-pro-max-skill
```

导入的源技能存储在 `~/.ontoskills/skills/vendor/` 下，编译输出位于 `~/.ontoskills/ontoskills/vendor/`。

## MCP 服务器

OntoMCP 通过模型上下文协议暴露已编译的本体。

```bash
npx ontoskills install mcp
```

当前的公共工具集是：

- `search_skills`
- `get_skill_context`
- `evaluate_execution_plan`
- `query_epistemic_rules`

特定客户端设置指南：

- [通用 MCP 运行时](./mcp.md)
- [Claude Code 指南](./mcp-claude-code.md)
- [Codex 指南](./mcp-codex.md)

## 下一步？

- [CLI](/cli/) — 完整命令界面和产品工作流
- [市场](/marketplace/) — 搜索和安装已发布的技能
- [编译器](/compiler/) — 安装可选编译器
- [技能创作](/authoring/) — 导入和编译源仓库
- [商店](/registry/) — 安装、更新、移除和卸载技能
- [故障排除](/troubleshooting/) — 诊断安装和运行时问题
- [路线图](/roadmap/) — 查看即将推出的内容
- [GitHub](https://github.com/mareasw/ontoskills) — 贡献
