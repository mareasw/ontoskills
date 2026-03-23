---
title: CLI
description: OntoSkills 产品的终端用户命令界面
---

`ontoskills` 是产品入口点。它在 `~/.ontoskills/` 下安装和管理运行时、编译器、商店技能和本地状态。

## 快速开始

```bash
npx ontoskills install mcp
```

引导步骤后，持久命令是：

```bash
ontoskills
```

## 产品命令

### 安装组件

```bash
ontoskills install mcp
ontoskills install core
```

### 安装商店技能

```bash
ontoskills search hello
ontoskills install mareasw/greeting/hello
ontoskills enable mareasw/greeting/hello
```

### 管理运行时状态

```bash
ontoskills disable mareasw/greeting/hello
ontoskills remove mareasw/greeting/hello
ontoskills rebuild-index
```

### 更新托管组件

```bash
ontoskills update mcp
ontoskills update core
ontoskills update mareasw/office/xlsx
```

### 检查和诊断

```bash
ontoskills store list
ontoskills list-installed
ontoskills doctor
```

## 托管主目录

所有内容位于：

```text
~/.ontoskills/
  bin/
  core/
  ontoskills/
  skills/
  state/
```

## 编译器前端

如果安装了 `ontocore`，`ontoskills` 也会前置最重要的创作命令：

```bash
ontoskills init-core
ontoskills compile
ontoskills compile my-skill
ontoskills query "SELECT ?s WHERE { ?s a oc:Skill }"
ontoskills list-skills
ontoskills security-audit
```

## 卸载

要完全删除托管主目录：

```bash
ontoskills uninstall --all
```
