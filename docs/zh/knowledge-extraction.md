---
title: 知识提取
description: OntoSkills 如何从技能中提取结构化知识
---

## 从 SKILL.md 到本体

技能不仅仅是代码 — 它是**结构化知识**。OntoCore 提取这些知识并将其编译为可查询的本体。

---

## 提取什么

每个技能都编译有：

| 元素 | 属性 | 描述 |
|------|------|------|
| **身份** | `oc:nature`、`oc:genus`、`oc:differentia` | "A 是一个做了 C 的 B" 定义 |
| **意图** | `oc:resolvesIntent` | 此技能解决的用户意图 |
| **需求** | `oc:hasRequirement` | 依赖项（EnvVar、Tool、Hardware、API、Knowledge）|
| **知识节点** | `oc:impartsKnowledge` | 认知知识（每个技能 8-12 个）|
| **状态转换** | `oc:requiresState`、`oc:yieldsState`、`oc:handlesFailure` | 前置条件、结果、错误处理 |
| **执行负载** | `oc:hasPayload` | 可选的要执行的代码 |
| **溯源** | `oc:generatedBy` | 证明（哪个 LLM 编译的）|

---

## 知识节点

知识提取的核心。每个技能传授 8-12 个**知识节点** — 结构化的认知规则。

### 10 种知识节点类型

| 类型 | 描述 | 示例 |
|------|------|------|
| **Heuristic** | 经验法则 | "对于 >100MB 的文件，优先使用流式传输" |
| **AntiPattern** | 要避免的模式 | "不要将整个文件读入内存" |
| **PreFlightCheck** | 执行前验证 | "下载前检查磁盘空间" |
| **RecoveryTactic** | 如何从失败中恢复 | "使用指数退避重试" |
| **OptimizationHint** | 性能指导 | "缓存已编译的正则表达式模式" |
| **ContextualConstraint** | 适用条件 | "仅在 Unix 系统上工作" |
| **ImplementationDetail** | 技术细节 | "使用 libcurl 进行 HTTP" |
| **ExternalDependency** | 所需工具/库 | "需要 Python 3.10+" |
| **FailureMode** | 如何失败 | "在慢速网络上超时" |
| **SuccessMetric** | 如何衡量成功 | "处理在 <5s 内完成" |

### 节点结构

每个知识节点都有：

- `directiveContent` — 实际的规则或见解
- `appliesToContext` — 何时适用
- `hasRationale` — 为什么存在此规则
- `severityLevel` — 重要性（critical、warning、info）

---

## 模块化本体架构

### 单个技能作为模块

每个已编译的技能是一个**自包含的 `.ttl` 文件**：

```
ontoskills/
├── ontoskills-core.ttl      # 核心 TBox（共享）
├── index.ttl                # 带 owl:imports 的清单
├── pdf/
│   └── ontoskill.ttl        # PDF 技能模块
├── markdown/
│   └── ontoskill.ttl        # Markdown 技能模块
└── email/
    └── ontoskill.ttl        # Email 技能模块
```

### 可插拔知识

- **添加**技能 → 放入 `.ttl` 文件
- **移除**技能 → 删除 `.ttl` 文件
- **更新**技能 → 替换 `.ttl` 文件

全局本体通过**添加**而非修改来增长。

---

## 查询知识

### 按意图查找技能

```sparql
SELECT ?skill WHERE {
  ?skill oc:resolvesIntent "create_pdf"
}
```

### 获取技能的知识节点

```sparql
SELECT ?node ?content WHERE {
  ?skill oc:impartsKnowledge ?node .
  ?node oc:directiveContent ?content .
}
```
