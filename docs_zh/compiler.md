---
title: 编译器
description: 安装和使用 OntoCore 处理自定义源技能
---

`ontocore` 是可选的编译器，将 `SKILL.md` 源文件转换为已验证的本体模块。

大多数用户不需要它来使用商店技能。当你想在本地编写或导入自定义技能时安装它。

## 安装

```bash
ontoskills install core
```

这将在以下位置添加托管的编译器运行时：

```text
~/.ontoskills/core/
```

## 初始化核心本体

```bash
ontoskills init-core
```

## 编译技能

编译本地树：

```bash
ontoskills compile
```

编译单个技能或子树：

```bash
ontoskills compile office
ontoskills compile my-custom-skill
```

## 查询本地图

```bash
ontoskills query "SELECT ?s WHERE { ?s a oc:Skill }"
```

## 检查质量

```bash
ontoskills list-skills
ontoskills security-audit
```
