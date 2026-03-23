---
title: 技能创作
description: 编写、导入和编译自定义源技能
---

OntoSkills 支持两种使用源技能的方式：

- 编写本地 `SKILL.md`
- 导入包含一个或多个 `SKILL.md` 文件的仓库

## 本地创作

典型流程：

```bash
ontoskills install core
ontoskills init-core
ontoskills compile
```

## 导入源仓库

如果仓库包含原始源技能，在本地导入并编译：

```bash
ontoskills import-source https://github.com/nextlevelbuilder/ui-ux-pro-max-skill
```

导入器：

- 克隆或复制仓库
- 发现 `SKILL.md` 文件
- 在本地编译它们
- 将编译输出写入托管的本体主目录

## 编译后

已编译的技能仍然遵循相同的运行时生命周期：

```bash
ontoskills enable <qualified-id>
ontoskills disable <qualified-id>
```
