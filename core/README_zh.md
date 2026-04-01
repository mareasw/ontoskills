<h1 align="center">
  OntoCore
</h1>

<p align="center">
  <strong>通过 OWL 2 本体实现确定性 AI 技能</strong>
</p>

<p align="center">
  <a href="README.md">🇬🇧 English</a> • <b>🇨🇳 中文</b>
</p>

<p align="center">
  <em><a href="https://ontoskills.sh">OntoSkills</a> 平台的神经符号编译器。</em>
</p>

<p align="center">
  将自然语言技能编译为经过验证的、可查询的知识图谱 ——<br>
  替代概率性智能体技能，配合极速 Rust MCP 运行时使用。
</p>

<p align="center">
  <a href="https://pypi.org/project/ontocore/"><img src="https://img.shields.io/pypi/v/ontocore.svg?color=blue&style=for-the-badge" alt="PyPI version"></a>
  <img src="https://img.shields.io/pypi/pyversions/ontocore.svg?style=for-the-badge" alt="Python versions">
  <img src="https://img.shields.io/badge/OWL%202-RDF%2FTurtle-green?style=for-the-badge&logo=w3c" alt="OWL 2">
  <a href="https://github.com/mareasw/ontoskills/blob/main/LICENSE"><img src="https://img.shields.io/pypi/l/ontocore.svg?style=for-the-badge" alt="License"></a>
</p>

---

## OntoCore 是什么？

OntoCore 是 **OntoSkills** 平台核心的 Python 编译器。它是一个**神经符号编译器**，将非结构化的、人类可读的 AI 技能（`SKILL.md`）转换为经过严格验证的、可查询的 **OWL 2 本体**。

通过结合 LLM 的自然语言理解能力与 RDF 和 SHACL 验证的确定性形式逻辑，OntoCore 确保 AI 智能体基于精确的、可验证的知识图谱运行，而非概率性提示。

### 核心能力

- **LLM 知识提取**：从 Markdown 文件中提取结构化三元组（依赖、输入、意图、操作）。
- **SHACL 验证**：确保提取的语义图严格遵循 OntoSkills 核心本体。
- **OWL 2 编译**：输出自包含的 `.ttl`（Turtle）图，可直接进行确定性 SPARQL 查询。
- **本地注册表管理**：处理分布式技能包的安装、启用和索引。
- **安全审计**：分析图谱中的冲突意图、缺失依赖或隐藏技能。

---

## 安装

直接从 PyPI 安装编译器（需要 Python 3.10+）：

```bash
pip install ontocore
```

---

## 快速开始

### 1. 初始化环境

在项目中创建必要的文件夹结构（`.ontoskills/`）：

```bash
ontocore init-core
```

### 2. 配置 LLM

OntoCore 需要 LLM 来提取关系。创建 `.env` 文件或导出密钥：

```bash
export ANTHROPIC_API_KEY="sk-..."
```
*（也支持 OpenAI：`OPENAI_API_KEY`）*

### 3. 编译技能

假设 `skills/` 目录中有 `SKILL.md` 文件，运行编译器：

```bash
ontocore compile
```
这将读取 Markdown 文件、提取知识、通过 SHACL 验证，并在 `.ontoskills/` 输出目录中生成 `.ttl` 本体文件。

### 4. 查询知识图谱

可以直接从 CLI 使用 SPARQL 执行精确的图谱查询：

```bash
ontocore query "SELECT ?skill WHERE { ?skill oc:resolvesIntent 'create_pdf' }"
```

---

## CLI 参考

本包提供 `ontocore` 命令行工具。主要命令：

### 核心命令
- `ontocore compile`：将本地技能编译为验证过的 OWL 2 本体。
- `ontocore query <sparql_query>`：对编译后的域图执行 SPARQL 查询。
- `ontocore security-audit`：对知识图谱运行安全检查以发现问题。
- `ontocore init-core`：在当前目录初始化空的 OntoSkills 注册表。
- `ontocore list-skills`：列出域图中所有成功编译的技能。

### 注册表与包
- `ontocore install-package <path>`：安装 `.tar.gz` 技能包。
- `ontocore import-source-repo <url>`：从远程 Git 仓库直接导入技能。
- `ontocore install`：下载并安装 lockfile 中声明的所有依赖。
- `ontocore enable <skill_id>`：启用已安装的技能。
- `ontocore disable <skill_id>`：禁用已安装的技能。
- `ontocore list-installed`：显示所有已安装包及其状态。
- `ontocore rebuild-index`：手动重建注册表索引。

运行 `ontocore --help` 或 `ontocore <command> --help` 查看详细用法。

---

## 文档与源码

- **[OntoCore 文档](https://ontoskills.sh/zh/docs/ontocore/)** — 架构、编译管道和 SHACL 验证
- **[快速开始](https://ontoskills.sh/zh/docs/getting-started/)** — 完整安装和入门
- **[mareasw/ontoskills](https://github.com/mareasw/ontoskills)** — 源码和贡献

---

*© 2026 [Marea Software](https://marea.software)*
