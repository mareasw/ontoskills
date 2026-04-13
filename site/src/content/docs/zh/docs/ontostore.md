---
title: OntoStore 界面
description: 从 OntoStore 市场搜索和安装技能
sidebar:
  order: 13
slug: ontostore-guide
---

OntoSkills 市场是已发布、已编译技能的安装界面。

它由 OntoStore 支持，在两个地方展示：

- 主页市场部分
- 专用实时页面 [`/zh/ontostore/`](/zh/ontostore/)

## 快速示例

```bash
ontoskills search xlsx
ontoskills install mareasw/office/xlsx
```

技能安装后默认启用。

## 限定 ID

市场安装使用限定 ID：

```text
<vendor>/<package>/<skill>
```

支持多层级解析：

- `mareasw/greeting/hello` — 供应商/包/技能
- `mareasw/office/xlsx` — 供应商/包/技能
- `mareasw/office/docx` — 供应商/包/技能

你也可以在包级别或供应商级别安装：

```bash
# 安装整个包中的所有技能
ontoskills install mareasw/office

# 安装某供应商的所有包
ontoskills install mareasw
```

## 安装流程

1. 搜索或浏览市场。
2. 复制所选技能的安装命令。
3. 在本地安装技能 — 自动启用。

```bash
ontoskills install mareasw/greeting/hello
```

使用 `--no-embeddings` 跳过嵌入生成：

```bash
ontoskills install mareasw/greeting/hello --no-embeddings
```

如果之前禁用了技能并想重新启用：

```bash
ontoskills enable mareasw/greeting/hello
```

## 官方与第三方

官方市场默认内置。

第三方商店可以单独添加：

```bash
ontoskills store add-source acme https://example.com/index.json
```

这些商店对 `ontoskills search` 可见，但 OntoStore 仍是默认发现路径。

## 实时市场页面

使用交互式页面查看完整的可搜索目录：

- [打开实时市场](/zh/ontostore/)
