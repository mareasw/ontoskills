# OntoSkills Site

<img src="public/ontoskills-banner.png" alt="OntoSkills - MCP Server for AI Agents" width="100%">

> **MCP server for deterministic AI agents with ontoskills** — Official website and documentation

## Overview

This repository contains the source code for the OntoSkills website, a hybrid marketing landing page and documentation site built with modern web technologies.

**OntoSkills** is an MCP server that exposes **ontoskills** — structured, queryable knowledge graphs that let AI agents reason deterministically. Instead of reading skill files, the LLM queries the graph and gets precise answers.

- **Phase 1:** OntoCore transforms SKILL.md → RDF/Turtle
- **Phase 2:** OntoSkills compiled skill library
- **Phase 3:** OntoMCP Rust server with 12 semantic tools
- **Phase 4:** OntoStore for centralized ontoskill repository
- **Phase 5:** OntoClaw autonomous agent (planned)

🔗 **Main Project:** [github.com/mareasoftware/ontoskills](https://github.com/mareasoftware/ontoskills)

---

## Features

- **Custom Landing Page** — Dark/neon tech-scientific aesthetic with custom styling
- **Documentation** — Powered by Starlight (Astro's documentation framework)
- **Zero JS by Default** — Static site generation for maximum performance
- **View Transitions** — Smooth SPA-like navigation experience
- **Full-text Search** — Built-in Pagefind search for documentation
- **Responsive Design** — Mobile-first approach with CSS-only interactions

## Tech Stack

| Technology | Purpose |
|------------|---------|
| [Astro 5](https://astro.build/) | Static site generator |
| [Starlight](https://starlight.astro.build/) | Documentation framework |
| [Tailwind CSS](https://tailwindcss.com/) | Utility-first styling |
| [Inter](https://fonts.google.com/specimen/Inter) | Primary typeface |
| [JetBrains Mono](https://www.jetbrains.com/lp/mono/) | Monospace/code font |
| [Pagefind](https://pagefind.app/) | Static search |

## Project Structure

```
ontoskills-site/
├── public/                 # Static assets
│   ├── ontoskills-logo.png
│   ├── ontoskills-banner.png
│   └── og-image.png
├── src/
│   ├── components/         # UI components
│   │   └── landing/        # Landing page sections
│   ├── content/            # Documentation content
│   │   └── docs/           # Markdown/MDX docs
│   ├── layouts/            # Page layouts
│   ├── pages/              # Route pages
│   └── styles/             # Global styles
├── astro.config.mjs        # Astro configuration
├── tailwind.config.mjs     # Tailwind configuration
└── package.json
```

## Getting Started

### Prerequisites

- Node.js 18+
- npm or pnpm

### Installation

```bash
# Clone the repository
git clone https://github.com/mareasoftware/ontoskills-site.git
cd ontoskills-site

# Install dependencies
npm install

# Start development server
npm run dev
```

### Commands

| Command | Description |
|---------|-------------|
| `npm run dev` | Start development server at `localhost:4321` |
| `npm run build` | Build production site to `./dist/` |
| `npm run preview` | Preview production build locally |

## Design System

### Color Palette

| Color | Hex | Usage |
|-------|-----|-------|
| Background Primary | `#0d0d14` | Main background |
| Background Secondary | `#1a1a2e` | Cards, sections |
| Background Tertiary | `#16213e` | Accent backgrounds |
| Text Primary | `#f0f0f5` | Main text |
| Text Muted | `#8b8ba3` | Secondary text |
| Accent Cyan | `#6dc9ee` | Primary accent |
| Accent Purple | `#9763e1` | Secondary accent |
| Accent Mint | `#abf9cc` | Success/highlights |
| Accent Aqua | `#92eff4` | Tertiary accent |

## Documentation

The documentation is located in `src/content/docs/` and follows Starlight's conventions:

- `overview.md` — Introduction to ontoskills and MCP architecture
- `getting-started.md` — Setup and usage guide
- `roadmap.md` — Development phases and future direction

To add new documentation pages, create Markdown files in `src/content/docs/` and update the sidebar configuration in `astro.config.mjs`.

## Deployment

The site is configured for static deployment. Build output is in `./dist/`.

**Recommended platforms:**
- [Vercel](https://vercel.com/)
- [Netlify](https://www.netlify.com/)
- [Cloudflare Pages](https://pages.cloudflare.com/)
- [GitHub Pages](https://pages.github.com/)

## Related

- **OntoSkills Project:** [github.com/mareasoftware/ontoskills](https://github.com/mareasoftware/ontoskills)
- **Marea Software:** [marea.software](https://marea.software)

## License

© 2026 Marea Software. All rights reserved.
