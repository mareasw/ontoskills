---
title: 商店
description: OntoSkills 中的 OntoStore、第三方商店和包生命周期
---

OntoSkills 使用简单的分发模型：

- OntoStore 默认内置
- 第三方商店可以显式添加
- 原始源仓库单独导入并在本地编译

面向用户的 CLI 是 `ontoskills`。

要查看 OntoStore 的实时可搜索视图，请使用专用市场页面：

- [打开实时市场](/explore/)

## 商店类型

### OntoStore

OntoStore 随产品提供。不需要 `store add-source`。

当你想要由 OntoSkills 项目维护的已发布包时使用它：

```bash
npx ontoskills search hello
npx ontoskills install mareasw/greeting/hello
npx ontoskills enable mareasw/greeting/hello
```

### 第三方商店

第三方商店是可选的。当另一个团队或社区维护单独的目录时添加它们：

```bash
ontoskills store add-source acme https://example.com/index.json
ontoskills store list
```

这些源可以被 `ontoskills search` 发现，并且可以像 OntoStore 一样安装，但它们不是内置的。

### 原始源导入

原始源仓库包含 `SKILL.md` 文件，并在本地编译。

```bash
ontoskills import-source https://github.com/nextlevelbuilder/ui-ux-pro-max-skill
```

源导入被克隆到 `~/.ontoskills/skills/vendor/`，编译输出写入 `~/.ontoskills/ontoskills/vendor/`。

## 技能生命周期

### 安装

从商店安装已编译的包：

```bash
ontoskills install mareasw/greeting/hello
```

### 启用和禁用

启用或禁用已安装的技能：

```bash
ontoskills enable mareasw/greeting/hello
ontoskills disable mareasw/greeting/hello
```

已启用的技能是暴露给 OntoMCP 的技能。

### 更新

显式更新已安装的组件：

```bash
ontoskills update mcp
ontoskills update core
ontoskills update mareasw/greeting/hello
```

### 重建索引

重建本地商店状态和已启用索引：

```bash
ontoskills rebuild-index
```

### 移除

移除包或技能：

```bash
ontoskills remove mareasw/greeting/hello
```

### 卸载所有内容

删除整个托管用户主目录：

```bash
ontoskills uninstall --all
```

这将删除整个 `~/.ontoskills/` 树，包括已安装的二进制文件、已编译的本体、锁、缓存和任何托管的编译器安装。

## 本地布局

托管主目录组织如下：

```text
~/.ontoskills/
  bin/
  core/
  ontoskills/
  skills/
  state/
```

- `bin/` 存储托管二进制文件，如 `ontomcp`
- `core/` 存储托管编译器安装（如果存在）
- `ontoskills/` 存储已编译的本体产物
- `skills/` 存储导入的源仓库
- `state/` 存储锁定文件、商店配置和缓存元数据

## 实用规则

- `install mcp` 安装运行时
- `install core` 安装编译器
- `install <qualified-skill-id>` 从商店安装已编译的包
- `import-source <repo-or-path>` 克隆并编译原始源仓库
- `enable` 和 `disable` 控制 OntoMCP 看到什么
- OntoStore 是内置的，所以不应该手动添加
