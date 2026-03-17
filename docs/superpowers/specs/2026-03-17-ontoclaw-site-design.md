# OntoClaw Site Design Specification

**Date:** 2026-03-17
**Status:** Approved
**Stack:** Astro 5 + Starlight + Tailwind CSS

---

## Overview

OntoClaw requires a hybrid website combining a marketing landing page with integrated documentation. The site targets AI/LLM developers and emphasizes the product's unique position as a neuro-symbolic skill compiler.

### Key Decisions

| Aspect | Decision |
|--------|----------|
| **Type** | Hybrid: Landing page + Docs |
| **Stack** | Astro 5 + Starlight + Tailwind CSS |
| **Deployment** | Vercel (static) |
| **Content** | MDX with Starlight Content Collections |
| **Style** | Dark/neon tech-scientific |
| **Interactivity** | Zero JS by default, View Transitions |

---

## Stack Tecnologico

```
Astro 5 (SSG)
├── @astrojs/starlight (docs framework)
├── @astrojs/tailwind (styling)
├── @astrojs/react (islands, if needed in future)
├── remark-mermaid (diagrams)
└── expressive-code (code blocks, built-in Starlight)
```

### Why Astro + Starlight

1. **Zero JS by default** - HTML statico puro per performance massime
2. **Content Collections con Zod** - Type-safety per frontmatter MDX
3. **Starlight** - Dark mode, sidebar, ricerca locale out-of-the-box
4. **View Transitions** - SPA-like navigation senza framework overhead
5. **React Islands** - Interattività selettiva solo dove serve

---

## Project Structure

```
ontoclaw-site/
├── astro.config.mjs
├── package.json
├── tsconfig.json
├── tailwind.config.mjs
│
├── public/
│   ├── ontoclaw-logo.png        # From ../ontoclaw/assets/
│   ├── ontoclaw-banner.png
│   ├── fonts/
│   │   ├── Inter-*.woff2
│   │   └── JetBrainsMono-*.woff2
│   └── og-image.png
│
├── src/
│   ├── pages/
│   │   └── index.astro          # Landing page
│   │
│   ├── components/
│   │   ├── landing/
│   │   │   ├── Header.astro
│   │   │   ├── Hero.astro
│   │   │   ├── ProblemSolution.astro
│   │   │   ├── Features.astro
│   │   │   ├── HowItWorks.astro
│   │   │   ├── Architecture.astro
│   │   │   ├── GettingStarted.astro
│   │   │   ├── CTA.astro
│   │   │   └── Footer.astro
│   │   └── ui/
│   │       ├── Button.astro
│   │       └── Card.astro
│   │
│   ├── layouts/
│   │   └── LandingLayout.astro
│   │
│   ├── styles/
│   │   ├── global.css
│   │   └── starlight-theme.css
│   │
│   └── content/
│       ├── config.ts
│       └── docs/
│           ├── getting-started.mdx
│           ├── cli-reference.mdx
│           ├── concepts.mdx
│           ├── architecture.mdx
│           └── security.mdx
│
└── .vscode/
    └── extensions.json
```

---

## Design System

### Color Palette

Colors extracted from existing assets (logo and banner).

```css
:root {
  /* Backgrounds */
  --bg-primary: #0d0d14;
  --bg-secondary: #1a1a2e;
  --bg-tertiary: #16213e;

  /* Text */
  --text-primary: #f0f0f5;
  --text-muted: #8b8ba3;

  /* Accents (from banner text gradient) */
  --accent-cyan: #6dc9ee;
  --accent-purple: #9763e1;

  /* Accents (from logo gradient) */
  --accent-mint: #abf9cc;
  --accent-aqua: #92eff4;

  /* Gradients */
  --gradient-text: linear-gradient(135deg, #6dc9ee, #9763e1);
  --gradient-logo: linear-gradient(135deg, #92eff4, #abf9cc);

  /* Borders */
  --border: #2a2a3e;
}
```

### Typography

| Element | Font | Weight | Usage |
|---------|------|--------|-------|
| Headings | Inter | 600-700 | Titles, sections |
| Body | Inter | 400 | Main text |
| Code | JetBrains Mono | 400 | Code blocks, CLI, terminal |
| Labels | Inter | 500, uppercase | Tags, categories |

---

## Landing Page

### Structure

```
┌─────────────────────────────────────────────────────────────┐
│  Header (sticky, backdrop-blur)                             │
│  Logo | Features | Architecture | Docs | GitHub | Get Started│
├─────────────────────────────────────────────────────────────┤
│  Hero                                                       │
│  - Banner image (full width)                                │
│  - "The first neuro-symbolic skill compiler"                │
│  - [Get Started] [View on GitHub]                           │
├─────────────────────────────────────────────────────────────┤
│  Problem → Solution                                         │
│  - Context rot, Hallucinations, No structure                │
│  - Deterministic ontologies, SPARQL queries                 │
├─────────────────────────────────────────────────────────────┤
│  Features (3x2 grid)                                        │
│  - LLM Extraction, Knowledge Architecture, OWL 2            │
│  - SHACL Validation, State Machines, Security Pipeline      │
├─────────────────────────────────────────────────────────────┤
│  How It Works (horizontal flow)                             │
│  Input → Extraction → Security → Validation → Output        │
├─────────────────────────────────────────────────────────────┤
│  Architecture (Mermaid diagram)                             │
├─────────────────────────────────────────────────────────────┤
│  Getting Started (3 steps with code)                        │
│  1. Install → 2. Init → 3. Compile                          │
├─────────────────────────────────────────────────────────────┤
│  CTA                                                        │
│  "Start building deterministic skill ontologies today"      │
├─────────────────────────────────────────────────────────────┤
│  Footer                                                     │
│  Logo | Docs | GitHub | Marea Software | © 2026             │
└─────────────────────────────────────────────────────────────┘
```

### Components

| Component | Description |
|-----------|-------------|
| `Header.astro` | Sticky navigation with mobile menu (CSS-only) |
| `Hero.astro` | Banner + headline + CTAs |
| `ProblemSolution.astro` | Two-column problem/solution layout |
| `Features.astro` | 3x2 feature grid with icons |
| `HowItWorks.astro` | Horizontal flow with 5 steps |
| `Architecture.astro` | Mermaid diagram wrapper |
| `GettingStarted.astro` | 3 installation steps with code blocks |
| `CTA.astro` | Final call-to-action |
| `Footer.astro` | Links and copyright |

### UI Components

| Component | Props | Usage |
|-----------|-------|-------|
| `Button.astro` | `variant: 'primary' \| 'secondary' \| 'ghost'`, `href`, `size` | CTAs |
| `Card.astro` | `title`, `description`, `icon?`, `href?` | Features grid |

---

## Documentation (Starlight)

### Pages

| Page | Content |
|------|---------|
| `/docs/getting-started/` | Overview, Prerequisites, Installation, Quick Start |
| `/docs/cli-reference/` | Commands, Options, Exit Codes |
| `/docs/concepts/` | Neuro-Symbolic, Knowledge Architecture, OWL 2 Properties, Skill Types |
| `/docs/architecture/` | Pipeline, Components, Validation Gatekeeper, Project Structure |
| `/docs/security/` | Philosophy, Detection Pipeline, Threat Categories |

### Content Source

Documentation content adapted from existing `README.md` and `PHILOSOPHY.md`, optimized for web readability with:
- Better scannability (shorter paragraphs, more lists)
- Interactive code blocks with copy-to-clipboard
- Mermaid diagrams for architecture visualization
- Proper heading hierarchy for navigation

---

## Configuration

### astro.config.mjs

```js
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import tailwind from '@astrojs/tailwind';
import remarkMermaid from 'remark-mermaid';

export default defineConfig({
  integrations: [
    starlight({
      title: 'OntoClaw',
      logo: { src: '/ontoclaw-logo.png' },
      sidebar: [
        { label: 'Getting Started', link: '/getting-started/' },
        { label: 'CLI Reference', link: '/cli-reference/' },
        { label: 'Concepts', link: '/concepts/' },
        { label: 'Architecture', link: '/architecture/' },
        { label: 'Security', link: '/security/' },
      ],
      customCss: ['/src/styles/starlight-theme.css'],
    }),
    tailwind(),
  ],
  markdown: {
    remarkPlugins: [remarkMermaid],
  },
  output: 'static',
  site: 'https://ontoclaw.marea.software',
});
```

### src/content/config.ts

```ts
import { defineCollection } from 'astro:content';
import { docsSchema } from '@astrojs/starlight/schema';

export const collections = {
  docs: defineCollection({ schema: docsSchema() }),
};
```

### tailwind.config.mjs

```js
export default {
  content: ['./src/**/*.{astro,html,js,jsx,md,mdx,svelte,ts,tsx,vue}'],
  theme: {
    extend: {
      colors: {
        'bg-primary': '#0d0d14',
        'bg-secondary': '#1a1a2e',
        'bg-tertiary': '#16213e',
        'text-primary': '#f0f0f5',
        'text-muted': '#8b8ba3',
        'accent-cyan': '#6dc9ee',
        'accent-purple': '#9763e1',
        'accent-mint': '#abf9cc',
        'accent-aqua': '#92eff4',
        'border': '#2a2a3e',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Consolas', 'monospace'],
      },
    },
  },
};
```

---

## Interactivity

### Philosophy: Zero JS by Default

| Feature | Solution | JS Required? |
|---------|----------|--------------|
| Code blocks (copy) | Expressive Code (Starlight built-in) | No |
| Tabs | `<Tabs>` component (Starlight) | No |
| Diagrams | Mermaid (remark plugin, server-rendered) | No |
| Navigation | View Transitions API | Minimal (Astro handles) |
| Smooth scroll | CSS `scroll-behavior: smooth` | No |
| Hover effects | CSS transitions | No |
| Mobile menu | CSS `:checked` hack | No |

### View Transitions

Enabled for SPA-like navigation between landing and docs:

```astro
---
// src/layouts/LandingLayout.astro
import { ViewTransitions } from 'astro:transitions';
---

<html lang="en">
  <head>
    <ViewTransitions />
  </head>
  <body>
    <slot />
  </body>
</html>
```

### React Islands

**None required for Phase 1.** Future consideration:
- Interactive OWL graph visualizer (D3/Cytoscape)
- Live SPARQL query playground

---

## Assets

### Existing (from ../ontoclaw/assets/)

| File | Usage |
|------|-------|
| `ontoclaw-logo.png` | Header, footer, Starlight logo |
| `ontoclaw-banner.png` | Hero section background |

### To Create

| File | Usage |
|------|-------|
| `og-image.png` | Social media preview (1200x630px) |
| Feature icons | SVG icons for Features grid |

---

## Future Expansion (Phase 2+)

| Feature | How to Add |
|---------|------------|
| Pricing page | New section in landing + `/pricing/` route |
| Testimonials | New `Testimonials.astro` component |
| Blog | `@astrojs/mdx` + `blog` content collection |
| Changelog | `changelog` content collection |
| Graph visualizer | React Island with D3/Cytoscape |
| Search | Starlight includes Pagefind by default |

---

## Deployment

### Vercel Configuration

- **Framework Preset:** Astro
- **Build Command:** `npm run build`
- **Output Directory:** `dist`
- **Node.js Version:** 20.x

### Environment

No environment variables required for static build.

---

## Success Criteria

1. **Performance:** Lighthouse score 95+ on all metrics
2. **Accessibility:** WCAG 2.1 AA compliant
3. **SEO:** All pages have proper meta tags and structured data
4. **Mobile:** Fully responsive, mobile-first design
5. **Docs:** All 5 doc pages functional with search, sidebar, TOC
6. **Branding:** Consistent use of gradient colors from assets

---

## File Creation Order

| Priority | File | Description |
|----------|------|-------------|
| 1 | `package.json` | Dependencies |
| 2 | `astro.config.mjs` | Astro + Starlight config |
| 3 | `tailwind.config.mjs` | Tailwind with custom palette |
| 4 | `src/styles/global.css` | CSS variables + base styles |
| 5 | `src/styles/starlight-theme.css` | Starlight color overrides |
| 6 | `src/layouts/LandingLayout.astro` | Base landing layout |
| 7 | `src/components/landing/*.astro` | All landing components |
| 8 | `src/components/ui/*.astro` | Button, Card |
| 9 | `src/pages/index.astro` | Landing page |
| 10 | `src/content/config.ts` | Starlight schema |
| 11 | `src/content/docs/*.mdx` | 5 doc pages |

---

*Design approved: 2026-03-17*
