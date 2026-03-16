<p align="center">
  <img src="assets/logo.png" alt="OntoClaw Logo">
</p>

<h1 align="center">OntoClaw</h1>

<p align="center">
  <strong>The first neuro-symbolic skill compiler for the Agentic Web.</strong>
</p>

<p align="center">
  <a href="#components">Components</a> •
  <a href="#installation">Installation</a> •
  <a href="#usage">Usage</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/OWL%202-RDF%2FTurtle-green" alt="OWL 2 RDF/Turtle">
  <img src="https://img.shields.io/badge/license-MIT-orange" alt="MIT License">
</p>

---

## Components

| Component | Language | Status | Description |
|-----------|----------|--------|-------------|
| [compiler/](compiler/) | Python | ✅ Ready | Skill compiler to OWL 2 ontology |
| [mcp/](mcp/) | Rust | 🚧 Coming soon | Fast MCP server for ontology queries |
| skills/ | Markdown | ✅ Ready | Input skill definitions |
| semantic-skills/ | Turtle | Generated | Compiled ontology output |

## Architecture

```
skills/               semantic-skills/
├── office/           ├── ontoclaw-core.ttl
│   └── public/       ├── index.ttl
│       ├── docx/     └── office/public/
│       ├── pdf/          └── */skill.ttl
│       ├── pptx/
│       └── xlsx/
       │
       └────────► compiler/ (Python) ────────►
```

## Installation

```bash
# Clone monorepo
git clone https://github.com/marea-software/ontoclaw.git
cd ontoclaw

# Install compiler
cd compiler
pip install -e ".[dev]"
```

## Usage

```bash
# Compile skills
ontoclaw compile

# Query ontology
ontoclaw query "SELECT ?s WHERE { ?s a oc:Skill }"

# List skills
ontoclaw list-skills
```

See [compiler/README.md](compiler/README.md) for full documentation.

## License

MIT
