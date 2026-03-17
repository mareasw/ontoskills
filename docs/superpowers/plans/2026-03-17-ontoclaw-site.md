# OntoClaw Site Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a hybrid marketing landing page + documentation site for OntoClaw using Astro 5 + Starlight + Tailwind CSS with dark/neon tech-scientific styling.

**Architecture:** Static site generation with zero JS by default. Landing page uses custom components with Tailwind styling. Documentation uses Starlight with custom theme. View Transitions for SPA-like navigation. Assets copied from existing ontoclaw project.

**Tech Stack:** Astro 5, @astrojs/starlight, @astrojs/tailwind, MDX, CSS-only interactivity

---

## File Structure Map

```
ontoclaw-site/
├── package.json                    # Dependencies: astro, starlight, tailwind
├── astro.config.mjs                # Astro + Starlight + Tailwind config
├── tsconfig.json                   # TypeScript config
├── tailwind.config.mjs             # Custom color palette + fonts
│
├── public/
│   ├── ontoclaw-logo.png           # COPY from ../ontoclaw/assets/
│   ├── ontoclaw-banner.png         # COPY from ../ontoclaw/assets/
│   └── og-image.png                # CREATE (placeholder for now)
│
├── src/
│   ├── pages/
│   │   └── index.astro             # Landing page
│   │
│   ├── components/
│   │   ├── landing/
│   │   │   ├── Header.astro        # Sticky nav with CSS mobile menu
│   │   │   ├── Hero.astro          # Banner + headline + CTAs
│   │   │   ├── ProblemSolution.astro
│   │   │   ├── Features.astro      # 3x2 grid
│   │   │   ├── HowItWorks.astro    # 5-step horizontal flow
│   │   │   ├── Architecture.astro  # Mermaid diagram
│   │   │   ├── GettingStarted.astro
│   │   │   ├── CTA.astro
│   │   │   └── Footer.astro
│   │   └── ui/
│   │       ├── Button.astro        # primary/secondary/ghost variants
│   │       └── Card.astro          # Feature cards
│   │
│   ├── layouts/
│   │   └── LandingLayout.astro     # Base HTML + ViewTransitions
│   │
│   ├── styles/
│   │   ├── global.css              # CSS variables + base styles
│   │   └── starlight-theme.css     # Starlight color overrides
│   │
│   └── content/
│       ├── config.ts               # Starlight docs schema
│       └── docs/
│           ├── getting-started.mdx
│           ├── cli-reference.mdx
│           ├── concepts.mdx
│           ├── architecture.mdx
│           └── security.mdx
│
└── .vscode/
    └── extensions.json             # Recommended extensions
```

---

## Task 1: Project Initialization

**Files:**
- Create: `package.json`
- Create: `astro.config.mjs`
- Create: `tsconfig.json`

- [ ] **Step 1: Create package.json with dependencies**

```json
{
  "name": "ontoclaw-site",
  "type": "module",
  "version": "0.0.1",
  "scripts": {
    "dev": "astro dev",
    "start": "astro dev",
    "build": "astro build",
    "preview": "astro preview",
    "astro": "astro"
  },
  "dependencies": {
    "astro": "^5.0.0",
    "@astrojs/starlight": "^0.30.0",
    "@astrojs/tailwind": "^6.0.0",
    "tailwindcss": "^3.4.0",
    "remark-mermaid": "^2.0.0",
    "@fontsource-variable/inter": "^5.0.0",
    "@fontsource-variable/jetbrains-mono": "^5.0.0"
  }
}
```

- [ ] **Step 2: Install dependencies**

Run: `npm install`
Expected: Dependencies installed successfully

- [ ] **Step 3: Create astro.config.mjs**

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

- [ ] **Step 4: Create tsconfig.json**

```json
{
  "extends": "astro/tsconfigs/strict",
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {
      "@/*": ["src/*"]
    }
  }
}
```

- [ ] **Step 5: Update .gitignore for Astro**

```gitignore
# Astro
dist/
.astro/

# Dependencies
node_modules/

# Environment
.env
.env.*
!.env.example

# IDE
.vscode/
.idea/

# OS
.DS_Store
Thumbs.db

# Build
*.tsbuildinfo
```

- [ ] **Step 6: Commit initialization**

```bash
git add package.json package-lock.json astro.config.mjs tsconfig.json .gitignore
git commit -m "feat: initialize Astro 5 + Starlight + Tailwind project"
```

---

## Task 2: Tailwind Configuration

**Files:**
- Create: `tailwind.config.mjs`

- [ ] **Step 1: Create tailwind.config.mjs with design system**

```js
/** @type {import('tailwindcss').Config} */
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
      backgroundImage: {
        'gradient-text': 'linear-gradient(135deg, #6dc9ee, #9763e1)',
        'gradient-logo': 'linear-gradient(135deg, #92eff4, #abf9cc)',
      },
    },
  },
  plugins: [],
};
```

- [ ] **Step 2: Commit Tailwind config**

```bash
git add tailwind.config.mjs
git commit -m "feat: add Tailwind config with OntoClaw design system"
```

---

## Task 3: Global Styles

**Files:**
- Create: `src/styles/global.css`
- Create: `src/styles/starlight-theme.css`

- [ ] **Step 1: Create src/styles directory**

Run: `mkdir -p src/styles`

- [ ] **Step 2: Create global.css with CSS variables and base styles**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    /* Backgrounds */
    --bg-primary: #0d0d14;
    --bg-secondary: #1a1a2e;
    --bg-tertiary: #16213e;

    /* Text */
    --text-primary: #f0f0f5;
    --text-muted: #8b8ba3;

    /* Accents */
    --accent-cyan: #6dc9ee;
    --accent-purple: #9763e1;
    --accent-mint: #abf9cc;
    --accent-aqua: #92eff4;

    /* Gradients */
    --gradient-text: linear-gradient(135deg, #6dc9ee, #9763e1);
    --gradient-logo: linear-gradient(135deg, #92eff4, #abf9cc);

    /* Borders */
    --border: #2a2a3e;
  }

  html {
    scroll-behavior: smooth;
  }

  body {
    @apply bg-bg-primary text-text-primary font-sans antialiased;
  }

  /* Gradient text utility */
  .gradient-text {
    background: var(--gradient-text);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }

  .gradient-logo {
    background: var(--gradient-logo);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }

  /* Focus styles */
  :focus-visible {
    @apply outline-2 outline-accent-cyan outline-offset-2;
  }
}
```

- [ ] **Step 3: Create starlight-theme.css for dark theme**

```css
/* Starlight dark theme overrides */
:root {
  --sl-color-bg: #0d0d14;
  --sl-color-bg-nav: #1a1a2e;
  --sl-color-bg-sidebar: #1a1a2e;
  --sl-color-bg-inline-code: #16213e;
  --sl-color-bg-accent: #1a1a2e;

  --sl-color-text: #f0f0f5;
  --sl-color-text-accent: #6dc9ee;
  --sl-color-text-muted: #8b8ba3;
  --sl-color-text-invert: #0d0d14;

  --sl-color-accent: #6dc9ee;
  --sl-color-accent-low: #9763e1;
  --sl-color-accent-high: #abf9cc;

  --sl-color-border: #2a2a3e;
  --sl-color-border-accent: #6dc9ee;

  --sl-color-hairline: #2a2a3e;

  /* Code blocks */
  --sl-color-code-bg: #16213e;
  --sl-color-code-border: #2a2a3e;
}

/* Expressive code theme override */
.expressive-code pre {
  background: #16213e !important;
  border: 1px solid #2a2a3e;
}
```

- [ ] **Step 4: Commit styles**

```bash
git add src/styles/
git commit -m "feat: add global CSS and Starlight theme"
```

---

## Task 4: Assets

**Files:**
- Copy: `public/ontoclaw-logo.png` (from ../ontoclaw/assets/)
- Copy: `public/ontoclaw-banner.png` (from ../ontoclaw/assets/)
- Create: `public/og-image.png` (placeholder)

- [ ] **Step 1: Create public directory**

Run: `mkdir -p public`

- [ ] **Step 2: Copy logo and banner from ontoclaw assets**

```bash
cp ../ontoclaw/assets/ontoclaw-logo.png public/
cp ../ontoclaw/assets/ontoclaw-banner.png public/
```

- [ ] **Step 3: Create placeholder og-image.png**

For now, copy the banner as og-image (1200x630 ideal, banner works as placeholder):
```bash
cp public/ontoclaw-banner.png public/og-image.png
```

- [ ] **Step 4: Commit assets**

```bash
git add public/
git commit -m "feat: add logo, banner, and og-image assets"
```

---

## Task 4.5: Font Imports

**Files:**
- Update: `src/layouts/LandingLayout.astro` (add font imports in frontmatter)

**Note:** Fonts are installed via npm in Task 1 (`@fontsource-variable/inter`, `@fontsource-variable/jetbrains-mono`).

- [ ] **Step 1: Add font imports to LandingLayout.astro**

In the frontmatter (between the `---` lines), add:

```astro
---
// Font imports from npm packages
import '@fontsource-variable/inter';
import '@fontsource-variable/jetbrains-mono';

import { ViewTransitions } from 'astro:transitions';
import '../styles/global.css';
// ... rest of component
```

- [ ] **Step 2: Commit font configuration**

```bash
git add src/layouts/LandingLayout.astro
git commit -m "feat: add font imports from @fontsource-variable packages"
```

---

## Task 5: Landing Layout

**Files:**
- Create: `src/layouts/LandingLayout.astro`

- [ ] **Step 1: Create layouts directory**

Run: `mkdir -p src/layouts`

- [ ] **Step 2: Create LandingLayout.astro**

```astro
---
import { ViewTransitions } from 'astro:transitions';
import '../styles/global.css';

interface Props {
  title?: string;
  description?: string;
}

const {
  title = 'OntoClaw - Neuro-Symbolic Skill Compiler',
  description = 'The first neuro-symbolic skill compiler for the Agentic Web. Transform natural language skill definitions into validated OWL 2 ontologies.'
} = Astro.props;
---

<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="description" content={description} />
    <link rel="icon" type="image/png" href="/ontoclaw-logo.png" />
    <meta property="og:title" content={title} />
    <meta property="og:description" content={description} />
    <meta property="og:image" content="/og-image.png" />
    <meta property="og:type" content="website" />
    <meta name="twitter:card" content="summary_large_image" />
    <title>{title}</title>
    <ViewTransitions />
  </head>
  <body class="min-h-screen">
    <slot />
  </body>
</html>
```

- [ ] **Step 3: Commit layout**

```bash
git add src/layouts/
git commit -m "feat: add LandingLayout with ViewTransitions and SEO meta"
```

---

## Task 6: UI Components

**Files:**
- Create: `src/components/ui/Button.astro`
- Create: `src/components/ui/Card.astro`

- [ ] **Step 1: Create ui components directory**

Run: `mkdir -p src/components/ui`

- [ ] **Step 2: Create Button.astro**

```astro
---
interface Props {
  variant?: 'primary' | 'secondary' | 'ghost';
  href?: string;
  size?: 'sm' | 'md' | 'lg';
  class?: string;
}

const {
  variant = 'primary',
  href,
  size = 'md',
  class: className = ''
} = Astro.props;

const baseStyles = 'inline-flex items-center justify-center font-medium rounded-lg transition-all duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-cyan focus-visible:ring-offset-2 focus-visible:ring-offset-bg-primary';

const variants = {
  primary: 'bg-accent-cyan text-bg-primary hover:bg-accent-cyan/90',
  secondary: 'bg-bg-secondary text-text-primary border border-border hover:border-accent-cyan',
  ghost: 'text-text-muted hover:text-accent-cyan'
};

const sizes = {
  sm: 'px-3 py-1.5 text-sm',
  md: 'px-5 py-2.5 text-base',
  lg: 'px-7 py-3.5 text-lg'
};

const classes = `${baseStyles} ${variants[variant]} ${sizes[size]} ${className}`;

const Element = href ? 'a' : 'button';
---

{href ? (
  <a href={href} class={classes}>
    <slot />
  </a>
) : (
  <button class={classes}>
    <slot />
  </button>
)}
```

- [ ] **Step 3: Create Card.astro**

```astro
---
interface Props {
  title: string;
  description: string;
  icon?: string;
  href?: string;
}

const { title, description, icon, href } = Astro.props;

const baseStyles = 'group p-6 bg-bg-secondary border border-border rounded-xl transition-all duration-200 hover:border-accent-cyan/50 hover:bg-bg-tertiary';
---

{href ? (
  <a href={href} class={baseStyles}>
    {icon && <div class="text-3xl mb-4" set:html={icon} />}
    <h3 class="text-lg font-semibold text-text-primary mb-2 group-hover:text-accent-cyan transition-colors">
      {title}
    </h3>
    <p class="text-text-muted text-sm leading-relaxed">{description}</p>
  </a>
) : (
  <div class={baseStyles}>
    {icon && <div class="text-3xl mb-4" set:html={icon} />}
    <h3 class="text-lg font-semibold text-text-primary mb-2 group-hover:text-accent-cyan transition-colors">
      {title}
    </h3>
    <p class="text-text-muted text-sm leading-relaxed">{description}</p>
  </div>
)}
```

- [ ] **Step 4: Commit UI components**

```bash
git add src/components/ui/
git commit -m "feat: add Button and Card UI components"
```

---

## Task 7: Header Component

**Files:**
- Create: `src/components/landing/Header.astro`

- [ ] **Step 1: Create landing components directory**

Run: `mkdir -p src/components/landing`

- [ ] **Step 2: Create Header.astro with CSS-only mobile menu**

```astro
---
import Button from '../ui/Button.astro';
---

<header class="fixed top-0 left-0 right-0 z-50 bg-bg-primary/80 backdrop-blur-lg border-b border-border">
  <nav class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
    <div class="flex items-center justify-between h-16">
      <!-- Logo -->
      <a href="/" class="flex items-center gap-2">
        <img src="/ontoclaw-logo.png" alt="OntoClaw" class="h-8 w-auto" />
        <span class="font-semibold text-text-primary">OntoClaw</span>
      </a>

      <!-- Desktop Navigation -->
      <div class="hidden md:flex items-center gap-8">
        <a href="#features" class="text-text-muted hover:text-accent-cyan transition-colors">Features</a>
        <a href="#architecture" class="text-text-muted hover:text-accent-cyan transition-colors">Architecture</a>
        <a href="/docs/" class="text-text-muted hover:text-accent-cyan transition-colors">Docs</a>
        <a href="https://github.com/marea-software/ontoclaw" target="_blank" rel="noopener" class="text-text-muted hover:text-accent-cyan transition-colors">GitHub</a>
        <Button href="/docs/getting-started/" size="sm">Get Started</Button>
      </div>

      <!-- Mobile Menu Toggle (CSS-only) -->
      <input type="checkbox" id="menu-toggle" class="hidden peer" />
      <label for="menu-toggle" class="md:hidden cursor-pointer text-text-muted hover:text-accent-cyan">
        <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </label>

      <!-- Mobile Menu -->
      <div class="hidden peer-checked:flex md:hidden absolute top-16 left-0 right-0 bg-bg-secondary border-b border-border flex-col p-4 gap-4">
        <a href="#features" class="text-text-muted hover:text-accent-cyan transition-colors py-2">Features</a>
        <a href="#architecture" class="text-text-muted hover:text-accent-cyan transition-colors py-2">Architecture</a>
        <a href="/docs/" class="text-text-muted hover:text-accent-cyan transition-colors py-2">Docs</a>
        <a href="https://github.com/marea-software/ontoclaw" target="_blank" rel="noopener" class="text-text-muted hover:text-accent-cyan transition-colors py-2">GitHub</a>
        <Button href="/docs/getting-started/" size="sm" class="w-full text-center">Get Started</Button>
      </div>
    </div>
  </nav>
</header>

<!-- Spacer for fixed header -->
<div class="h-16"></div>
```

- [ ] **Step 3: Commit Header**

```bash
git add src/components/landing/Header.astro
git commit -m "feat: add Header with CSS-only mobile menu"
```

---

## Task 8: Hero Component

**Files:**
- Create: `src/components/landing/Hero.astro`

- [ ] **Step 1: Create Hero.astro**

```astro
---
import Button from '../ui/Button.astro';
---

<section class="relative overflow-hidden">
  <!-- Banner Image Background -->
  <div class="absolute inset-0 z-0">
    <img
      src="/ontoclaw-banner.png"
      alt=""
      class="w-full h-full object-cover opacity-30"
    />
    <div class="absolute inset-0 bg-gradient-to-b from-bg-primary/50 via-bg-primary/80 to-bg-primary"></div>
  </div>

  <!-- Content -->
  <div class="relative z-10 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-24 lg:py-32 text-center">
    <h1 class="text-4xl sm:text-5xl lg:text-6xl font-bold mb-6">
      <span class="gradient-text">The first neuro-symbolic</span>
      <br />
      <span class="text-text-primary">skill compiler</span>
    </h1>

    <p class="text-lg sm:text-xl text-text-muted max-w-2xl mx-auto mb-8">
      Transform natural language skill definitions into
      <span class="text-accent-mint font-medium">validated OWL 2 ontologies</span>.
      Deterministic knowledge retrieval for the Agentic Web.
    </p>

    <div class="flex flex-col sm:flex-row gap-4 justify-center">
      <Button href="/docs/getting-started/" size="lg">
        Get Started
      </Button>
      <Button href="https://github.com/marea-software/ontoclaw" variant="secondary" size="lg">
        View on GitHub
      </Button>
    </div>
  </div>
</section>
```

- [ ] **Step 2: Commit Hero**

```bash
git add src/components/landing/Hero.astro
git commit -m "feat: add Hero section with banner background"
```

---

## Task 9: ProblemSolution Component

**Files:**
- Create: `src/components/landing/ProblemSolution.astro`

- [ ] **Step 1: Create ProblemSolution.astro**

```astro
---

---

<section class="py-20 bg-bg-secondary">
  <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
    <div class="grid md:grid-cols-2 gap-12">
      <!-- Problem -->
      <div class="space-y-6">
        <h2 class="text-3xl font-bold text-text-primary">
          The <span class="text-red-400">Determinism</span> Problem
        </h2>
        <p class="text-text-muted leading-relaxed">
          LLMs are inherently non-deterministic. The same query can yield different results,
          and reasoning about skill relationships requires reading entire documents.
        </p>
        <ul class="space-y-4">
          <li class="flex items-start gap-3">
            <span class="text-red-400 mt-1">✗</span>
            <span class="text-text-muted"><strong class="text-text-primary">Context rot</strong> from loading 50+ SKILL.md files</span>
          </li>
          <li class="flex items-start gap-3">
            <span class="text-red-400 mt-1">✗</span>
            <span class="text-text-muted"><strong class="text-text-primary">Hallucinations</strong> when information is scattered</span>
          </li>
          <li class="flex items-start gap-3">
            <span class="text-red-400 mt-1">✗</span>
            <span class="text-text-muted"><strong class="text-text-primary">No verifiable structure</strong> for skill relationships</span>
          </li>
        </ul>
      </div>

      <!-- Solution -->
      <div class="space-y-6">
        <h2 class="text-3xl font-bold text-text-primary">
          The <span class="gradient-text">Ontological</span> Solution
        </h2>
        <p class="text-text-muted leading-relaxed">
          OntoClaw transforms unstructured skill definitions into formal, queryable
          knowledge graphs using Description Logics.
        </p>
        <ul class="space-y-4">
          <li class="flex items-start gap-3">
            <span class="text-accent-mint mt-1">✓</span>
            <span class="text-text-muted"><strong class="text-text-primary">Decidable reasoning</strong> with OWL 2 DL</span>
          </li>
          <li class="flex items-start gap-3">
            <span class="text-accent-mint mt-1">✓</span>
            <span class="text-text-muted"><strong class="text-text-primary">SPARQL queries</strong> with O(1) indexed lookup</span>
          </li>
          <li class="flex items-start gap-3">
            <span class="text-accent-mint mt-1">✓</span>
            <span class="text-text-muted"><strong class="text-text-primary">Formal semantics</strong> for skill relationships</span>
          </li>
        </ul>
      </div>
    </div>
  </div>
</section>
```

- [ ] **Step 2: Commit ProblemSolution**

```bash
git add src/components/landing/ProblemSolution.astro
git commit -m "feat: add Problem/Solution section"
```

---

## Task 10: Features Component

**Files:**
- Create: `src/components/landing/Features.astro`

- [ ] **Step 1: Create Features.astro**

```astro
---
import Card from '../ui/Card.astro';

const features = [
  {
    title: 'LLM Extraction',
    description: 'Uses Claude to extract structured knowledge from natural language SKILL.md files.',
    icon: '🧠'
  },
  {
    title: 'Knowledge Architecture',
    description: 'Follows the "A is a B that C" definition pattern (genus + differentia).',
    icon: '🏛️'
  },
  {
    title: 'OWL 2 Serialization',
    description: 'Outputs valid OWL 2 ontologies in RDF/Turtle format with formal semantics.',
    icon: '📊'
  },
  {
    title: 'SHACL Validation',
    description: 'Constitutional gatekeeper ensures logical validity before any write operation.',
    icon: '✅'
  },
  {
    title: 'State Machines',
    description: 'Skills define preconditions, postconditions, and failure handlers.',
    icon: '⚙️'
  },
  {
    title: 'Security Pipeline',
    description: 'Defense-in-depth: regex patterns + LLM review for malicious content detection.',
    icon: '🔒'
  }
];
---

<section id="features" class="py-20">
  <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
    <div class="text-center mb-12">
      <h2 class="text-3xl sm:text-4xl font-bold text-text-primary mb-4">
        Key <span class="gradient-text">Capabilities</span>
      </h2>
      <p class="text-text-muted max-w-2xl mx-auto">
        Everything you need to build deterministic, queryable skill ontologies.
      </p>
    </div>

    <div class="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
      {features.map((feature) => (
        <Card
          title={feature.title}
          description={feature.description}
          icon={feature.icon}
        />
      ))}
    </div>
  </div>
</section>
```

- [ ] **Step 2: Commit Features**

```bash
git add src/components/landing/Features.astro
git commit -m "feat: add Features grid section"
```

---

## Task 11: HowItWorks Component

**Files:**
- Create: `src/components/landing/HowItWorks.astro`

- [ ] **Step 1: Create HowItWorks.astro**

```astro
---

const steps = [
  { label: 'Input', icon: '📥', description: 'SKILL.md' },
  { label: 'Extraction', icon: '🔄', description: 'Claude API' },
  { label: 'Security', icon: '🔒', description: 'Audit' },
  { label: 'Validation', icon: '✅', description: 'SHACL' },
  { label: 'Output', icon: '📤', description: '.ttl file' }
];
---

<section class="py-20 bg-bg-secondary">
  <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
    <div class="text-center mb-12">
      <h2 class="text-3xl sm:text-4xl font-bold text-text-primary mb-4">
        How It <span class="gradient-text">Works</span>
      </h2>
    </div>

    <div class="flex flex-col md:flex-row items-center justify-center gap-4 md:gap-0">
      {steps.map((step, index) => (
        <div class="flex items-center">
          <div class="flex flex-col items-center text-center px-6">
            <div class="text-4xl mb-3">{step.icon}</div>
            <div class="font-semibold text-text-primary mb-1">{step.label}</div>
            <div class="text-sm text-text-muted">{step.description}</div>
          </div>
          {index < steps.length - 1 && (
            <div class="hidden md:block text-accent-cyan text-2xl">→</div>
          )}
          {index < steps.length - 1 && (
            <div class="md:hidden text-accent-cyan text-2xl">↓</div>
          )}
        </div>
      ))}
    </div>
  </div>
</section>
```

- [ ] **Step 2: Commit HowItWorks**

```bash
git add src/components/landing/HowItWorks.astro
git commit -m "feat: add How It Works horizontal flow"
```

---

## Task 12: Architecture Component

**Files:**
- Create: `src/components/landing/Architecture.astro`

- [ ] **Step 1: Create Architecture.astro with Mermaid diagram**

```astro
---

const mermaidCode = `
flowchart TB
    subgraph Input["📥 Input"]
        SKILL[SKILL.md<br/>Natural Language]
    end

    subgraph Extraction["🔄 Extraction"]
        CLAUDE[Claude API<br/>LLM Extraction]
        PYDANTIC[Extracted Skill<br/>Pydantic Model]
    end

    subgraph Security["🔒 Security"]
        AUDIT[Security Audit<br/>Regex + LLM Review]
    end

    subgraph Serialization["📦 Serialization"]
        RDF[RDF Graph<br/>OWL 2 Triples]
    end

    subgraph Validation["✅ Validation"]
        SHACL[SHACL Validator<br/>Gatekeeper]
    end

    subgraph Output["📤 Output"]
        PASS["PASS<br/>Write .ttl"]
        FAIL["FAIL<br/>Block & Error"]
    end

    SKILL --> CLAUDE
    CLAUDE --> PYDANTIC
    PYDANTIC --> AUDIT
    AUDIT --> RDF
    RDF --> SHACL
    SHACL --> PASS
    SHACL --> FAIL
`;
---

<section id="architecture" class="py-20">
  <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
    <div class="text-center mb-12">
      <h2 class="text-3xl sm:text-4xl font-bold text-text-primary mb-4">
        <span class="gradient-text">Architecture</span>
      </h2>
      <p class="text-text-muted max-w-2xl mx-auto">
        The OntoClaw pipeline: from natural language to validated ontology.
      </p>
    </div>

    <div class="bg-bg-secondary border border-border rounded-xl p-6 overflow-x-auto">
      <pre class="mermaid text-sm">{mermaidCode}</pre>
    </div>
  </div>
</section>
```

- [ ] **Step 2: Commit Architecture**

```bash
git add src/components/landing/Architecture.astro
git commit -m "feat: add Architecture section with Mermaid diagram"
```

---

## Task 13: GettingStarted Component

**Files:**
- Create: `src/components/landing/GettingStarted.astro`

- [ ] **Step 1: Create GettingStarted.astro**

```astro
---

const steps = [
  {
    number: '1',
    title: 'Install',
    code: 'git clone https://github.com/marea-software/ontoclaw.git\ncd ontoclaw/compiler\npip install -e ".[dev]"'
  },
  {
    number: '2',
    title: 'Initialize',
    code: 'ontoclaw init-core'
  },
  {
    number: '3',
    title: 'Compile',
    code: 'ontoclaw compile'
  }
];
---

<section class="py-20 bg-bg-secondary">
  <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
    <div class="text-center mb-12">
      <h2 class="text-3xl sm:text-4xl font-bold text-text-primary mb-4">
        Getting <span class="gradient-text">Started</span>
      </h2>
      <p class="text-text-muted max-w-2xl mx-auto">
        Three commands to transform your skills into ontologies.
      </p>
    </div>

    <div class="grid md:grid-cols-3 gap-8">
      {steps.map((step) => (
        <div class="space-y-4">
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-full bg-accent-cyan/20 text-accent-cyan font-bold flex items-center justify-center">
              {step.number}
            </div>
            <h3 class="text-xl font-semibold text-text-primary">{step.title}</h3>
          </div>
          <div class="bg-bg-tertiary border border-border rounded-lg p-4 font-mono text-sm text-text-muted overflow-x-auto">
            <pre class="whitespace-pre-wrap">{step.code}</pre>
          </div>
        </div>
      ))}
    </div>
  </div>
</section>
```

- [ ] **Step 2: Commit GettingStarted**

```bash
git add src/components/landing/GettingStarted.astro
git commit -m "feat: add Getting Started section with code blocks"
```

---

## Task 14: CTA Component

**Files:**
- Create: `src/components/landing/CTA.astro`

- [ ] **Step 1: Create CTA.astro**

```astro
---
import Button from '../ui/Button.astro';
---

<section class="py-20">
  <div class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
    <h2 class="text-3xl sm:text-4xl font-bold text-text-primary mb-4">
      Start building <span class="gradient-text">deterministic</span> skill ontologies
    </h2>
    <p class="text-text-muted mb-8 max-w-2xl mx-auto">
      Transform your skill definitions into validated OWL 2 knowledge graphs.
      Query with precision. Reason with confidence.
    </p>
    <div class="flex flex-col sm:flex-row gap-4 justify-center">
      <Button href="/docs/getting-started/" size="lg">
        Get Started
      </Button>
      <Button href="/docs/concepts/" variant="secondary" size="lg">
        Learn More
      </Button>
    </div>
  </div>
</section>
```

- [ ] **Step 2: Commit CTA**

```bash
git add src/components/landing/CTA.astro
git commit -m "feat: add CTA section"
```

---

## Task 15: Footer Component

**Files:**
- Create: `src/components/landing/Footer.astro`

- [ ] **Step 1: Create Footer.astro**

```astro
---

const links = [
  { label: 'Docs', href: '/docs/' },
  { label: 'GitHub', href: 'https://github.com/marea-software/ontoclaw' },
  { label: 'Marea Software', href: 'https://marea.software' }
];
---

<footer class="border-t border-border py-12">
  <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
    <div class="flex flex-col md:flex-row items-center justify-between gap-6">
      <!-- Logo -->
      <a href="/" class="flex items-center gap-2">
        <img src="/ontoclaw-logo.png" alt="OntoClaw" class="h-6 w-auto" />
        <span class="font-semibold text-text-primary">OntoClaw</span>
      </a>

      <!-- Links -->
      <nav class="flex items-center gap-6">
        {links.map((link) => (
          <a
            href={link.href}
            class="text-text-muted hover:text-accent-cyan transition-colors text-sm"
            {...(link.href.startsWith('http') && { target: '_blank', rel: 'noopener' })}
          >
            {link.label}
          </a>
        ))}
      </nav>

      <!-- Copyright -->
      <div class="text-text-muted text-sm">
        © 2026 Marea Software
      </div>
    </div>
  </div>
</footer>
```

- [ ] **Step 2: Commit Footer**

```bash
git add src/components/landing/Footer.astro
git commit -m "feat: add Footer component"
```

---

## Task 16: Landing Page Assembly

**Files:**
- Create: `src/pages/index.astro`

- [ ] **Step 1: Create pages directory**

Run: `mkdir -p src/pages`

- [ ] **Step 2: Create index.astro**

```astro
---
import LandingLayout from '../layouts/LandingLayout.astro';
import Header from '../components/landing/Header.astro';
import Hero from '../components/landing/Hero.astro';
import ProblemSolution from '../components/landing/ProblemSolution.astro';
import Features from '../components/landing/Features.astro';
import HowItWorks from '../components/landing/HowItWorks.astro';
import Architecture from '../components/landing/Architecture.astro';
import GettingStarted from '../components/landing/GettingStarted.astro';
import CTA from '../components/landing/CTA.astro';
import Footer from '../components/landing/Footer.astro';
---

<LandingLayout>
  <Header />
  <main>
    <Hero />
    <ProblemSolution />
    <Features />
    <HowItWorks />
    <Architecture />
    <GettingStarted />
    <CTA />
  </main>
  <Footer />
</LandingLayout>
```

- [ ] **Step 3: Commit landing page**

```bash
git add src/pages/
git commit -m "feat: assemble landing page with all components"
```

---

## Task 17: Starlight Content Configuration

**Files:**
- Create: `src/content/config.ts`

- [ ] **Step 1: Create content directory**

Run: `mkdir -p src/content/docs`

- [ ] **Step 2: Create config.ts**

```ts
import { defineCollection } from 'astro:content';
import { docsSchema } from '@astrojs/starlight/schema';

export const collections = {
  docs: defineCollection({ schema: docsSchema() }),
};
```

- [ ] **Step 3: Commit content config**

```bash
git add src/content/config.ts
git commit -m "feat: add Starlight content collection config"
```

---

## Task 18: Documentation - Getting Started

**Files:**
- Create: `src/content/docs/getting-started.mdx`

- [ ] **Step 1: Create getting-started.mdx**

````mdx
---
title: Getting Started
description: Get up and running with OntoClaw in minutes.
---

import { Card, CardGrid } from '@astrojs/starlight/components';

## What is OntoClaw?

OntoClaw is a **skill compiler** that transforms natural language skill definitions into **validated semantic knowledge graphs**. It bridges the gap between human-readable documentation and machine-executable ontologies.

## Prerequisites

- Python 3.10 or higher
- An Anthropic API key (for LLM extraction)
- Git

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/marea-software/ontoclaw.git
cd ontoclaw
```

### 2. Install the Compiler

```bash
cd compiler
pip install -e ".[dev]"
```

### 3. Set Up Environment

```bash
export ANTHROPIC_API_KEY=your-api-key-here
```

## Quick Start

### Initialize the Core Ontology

```bash
ontoclaw init-core
```

This creates the core ontology with predefined states in `semantic-skills/ontoclaw-core.ttl`.

### Compile Your Skills

```bash
ontoclaw compile
```

This compiles all skills in the `skills/` directory to OWL 2 ontologies.

### Query the Ontology

```bash
ontoclaw query "SELECT ?s WHERE { ?s a oc:Skill }"
```

## Next Steps

<CardGrid>
  <Card title="CLI Reference" icon="terminal" href="/cli-reference/">
    Explore all available commands and options.
  </Card>
  <Card title="Concepts" icon="lightbulb" href="/concepts/">
    Understand the neuro-symbolic architecture.
  </Card>
  <Card title="Architecture" icon="puzzle" href="/architecture/">
    Learn about the compilation pipeline.
  </Card>
</CardGrid>
````

- [ ] **Step 2: Commit getting-started docs**

```bash
git add src/content/docs/getting-started.mdx
git commit -m "docs: add Getting Started documentation"
```

---

## Task 19: Documentation - CLI Reference

**Files:**
- Create: `src/content/docs/cli-reference.mdx`

- [ ] **Step 1: Create cli-reference.mdx**

````mdx
---
title: CLI Reference
description: Complete reference for OntoClaw CLI commands.
---

import { Tabs, TabItem } from '@astrojs/starlight/components';

## Commands

### `ontoclaw init-core`

Initialize the core ontology with predefined states.

```bash
ontoclaw init-core
```

Creates:
- `semantic-skills/ontoclaw-core.ttl` - Core ontology with states

### `ontoclaw compile`

Compile skills to OWL 2 ontologies.

<Tabs>
<TabItem label="All Skills" icon="folder">

```bash
ontoclaw compile
```

</TabItem>
<TabItem label="Specific Skill" icon="file">

```bash
ontoclaw compile my-skill
```

</TabItem>
</Tabs>

### `ontoclaw query`

Query the ontology with SPARQL.

```bash
ontoclaw query "SELECT ?skill WHERE { ?skill oc:resolvesIntent 'create_pdf' }"
```

### `ontoclaw list-skills`

List all compiled skills.

```bash
ontoclaw list-skills
```

### `ontoclaw security-audit`

Run security audit on all skills.

```bash
ontoclaw security-audit
```

## Options

| Option | Description |
|--------|-------------|
| `-i, --input` | Input directory (default: `./skills/`) |
| `-o, --output` | Output file (default: `./semantic-skills/skills.ttl`) |
| `--dry-run` | Preview without saving |
| `--skip-security` | Skip security checks (not recommended) |
| `-f, --force` | Force recompilation (bypass cache) |
| `--reason/--no-reason` | Apply OWL reasoning |
| `-y, --yes` | Skip confirmation |
| `-v, --verbose` | Debug logging |
| `-q, --quiet` | Suppress progress |

## Exit Codes

| Code | Exception | Description |
|------|-----------|-------------|
| 0 | - | Success |
| 1 | `SkillETLError` | General ETL error |
| 3 | `SecurityError` | Security threat detected |
| 4 | `ExtractionError` | Skill extraction failed |
| 5 | `OntologyLoadError` | Ontology file not found |
| 6 | `SPARQLError` | Invalid SPARQL query |
| 7 | `SkillNotFoundError` | Skill not found |
| **8** | `OntologyValidationError` | SHACL validation failed |
````

- [ ] **Step 2: Commit CLI reference docs**

```bash
git add src/content/docs/cli-reference.mdx
git commit -m "docs: add CLI Reference documentation"
```

---

## Task 20: Documentation - Concepts

**Files:**
- Create: `src/content/docs/concepts.mdx`

- [ ] **Step 1: Create concepts.mdx**

````mdx
---
title: Concepts
description: Core concepts behind OntoClaw's neuro-symbolic architecture.
---

## Neuro-Symbolic Architecture

OntoClaw is **neuro-symbolic**: it combines neural and symbolic AI paradigms.

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Neural Layer  │     │  Symbolic Layer │     │  Query Layer    │
│                 │     │                 │     │                 │
│  LLM Extraction │ ──► │  OWL 2 Ontology │ ──► │  SPARQL Engine  │
│  (probabilistic)│     │  (deterministic)│     │  (precise)      │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

- **Neural**: Claude extracts structured knowledge from natural language
- **Symbolic**: OWL 2 ontology stores knowledge with formal semantics
- **Query**: SPARQL provides precise, indexed retrieval

## Knowledge Architecture

Skills are extracted following the **Knowledge Architecture** framework:

- **Categories of Being**: Tool, Concept, Work
- **Genus and Differentia**: "A is a B that C" definition structure

### Relations

| Relation | Description |
|----------|-------------|
| `depends-on` | Skill prerequisites |
| `extends` | Skill inheritance |
| `contradicts` | Incompatible skills |
| `implements` | Interface compliance |
| `exemplifies` | Pattern demonstration |

## OWL 2 Properties

| Property | Characteristic | Inverse |
|----------|---------------|---------|
| `oc:dependsOn` | AsymmetricProperty | `oc:enables` |
| `oc:extends` | TransitiveProperty | `oc:isExtendedBy` |
| `oc:contradicts` | SymmetricProperty | - |
| `oc:implements` | - | `oc:isImplementedBy` |

## Skill Types

The classification is **automatic** based on whether the skill has executable code:

- **ExecutableSkill**: Has `hasPayload` (code to execute)
- **DeclarativeSkill**: Knowledge-only, no payload

## Schema-First Querying

1. **First**: Query the TBox (schema) to understand available classes and properties
2. **Then**: Construct precise ABox queries with known predicates

```sparql
# TBox: What properties does Skill have?
SELECT ?property ?range WHERE {
  ?property rdfs:domain oc:Skill .
  ?property rdfs:range ?range .
}
```
````

- [ ] **Step 2: Commit concepts docs**

```bash
git add src/content/docs/concepts.mdx
git commit -m "docs: add Concepts documentation"
```

---

## Task 21: Documentation - Architecture

**Files:**
- Create: `src/content/docs/architecture.mdx`

- [ ] **Step 1: Create architecture.mdx**

````mdx
---
title: Architecture
description: OntoClaw's compilation pipeline and components.
---

## Pipeline Overview

```
skills/           →  Extraction  →  Security  →  Serialization  →  semantic-skills/
SKILL.md files       (Claude API)    (Audit)      (RDF/OWL)         .ttl files
```

## Components

| Component | File | Description |
|-----------|------|-------------|
| CLI | `cli.py` | Click-based command interface |
| Extractor | `extractor.py` | ID and hash generation |
| Transformer | `transformer.py` | LLM tool-use extraction |
| Security | `security.py` | Defense-in-depth security |
| Core Ontology | `core_ontology.py` | Namespace and TBox creation |
| Serialization | `serialization.py` | RDF + SHACL gatekeeper |
| Storage | `storage.py` | File I/O, merging, cleanup |
| Validator | `validator.py` | SHACL validation gatekeeper |
| SPARQL | `sparql.py` | Query engine |

## Validation Gatekeeper

Every skill must pass SHACL validation before being written to disk.

| Constraint | Rule |
|------------|------|
| `resolvesIntent` | Required (min 1) |
| `generatedBy` | Required (exactly 1) |
| `requiresState` | Must be IRI of `oc:State` |
| `yieldsState` | Must be IRI of `oc:State` |

## Project Structure

```
ontoclaw/
├── compiler/           # Python skill compiler
│   ├── cli.py         # Click CLI interface
│   ├── schemas.py     # Pydantic models
│   └── tests/         # Test suite (150 tests)
├── specs/
│   └── ontoclaw.shacl.ttl  # SHACL constitution
├── skills/            # Input: SKILL.md definitions
└── semantic-skills/   # Output: compiled .ttl files
    ├── ontoclaw-core.ttl
    ├── index.ttl
    └── */skill.ttl
```

## Dependencies

| Package | Purpose |
|---------|---------|
| `anthropic` | Claude API for extraction |
| `click` | CLI framework |
| `pydantic` | Data validation |
| `rdflib` | RDF graph handling |
| `pyshacl` | SHACL validation |
| `rich` | Terminal formatting |
````

- [ ] **Step 2: Commit architecture docs**

```bash
git add src/content/docs/architecture.mdx
git commit -m "docs: add Architecture documentation"
```

---

## Task 22: Documentation - Security

**Files:**
- Create: `src/content/docs/security.mdx`

- [ ] **Step 1: Create security.mdx**

````mdx
---
title: Security
description: OntoClaw's defense-in-depth security philosophy.
---

## Philosophy

OntoClaw employs **defense-in-depth**: multiple layers of security checks that work together.

```
User Content → Unicode NFC → Regex Patterns → LLM Review → Decision
                Normalize      Check Attacks    Final Check   Pass/Block
```

## Detection Pipeline

### 1. Unicode Normalization

All input is normalized to NFC form to prevent encoding-based attacks.

### 2. Regex Pattern Matching

Fast detection of known attack patterns:

### 3. LLM Review

Final review by Claude for subtle or novel attacks that patterns might miss.

## Threat Categories

| Category | Examples |
|----------|----------|
| **Prompt Injection** | `ignore instructions`, `system:`, `you are now` |
| **Command Injection** | `; rm`, `\| bash`, command substitution |
| **Data Exfiltration** | `curl -d`, `wget --data` |
| **Path Traversal** | `../`, `/etc/passwd` |
| **Credential Exposure** | `api_key=`, `password=` |

## Best Practices

1. **Never skip security** - The `--skip-security` flag exists for development only
2. **Review audit logs** - Check security audit output for warnings
3. **Use dry-run** - Preview extractions before writing to disk

## CLI Commands

```bash
# Run security audit
ontoclaw security-audit

# Compile with verbose security output
ontoclaw compile -v
```

## Exit Codes

Security issues return exit code **3** (`SecurityError`).
````

- [ ] **Step 2: Commit security docs**

```bash
git add src/content/docs/security.mdx
git commit -m "docs: add Security documentation"
```

---

## Task 23: VSCode Configuration

**Files:**
- Create: `.vscode/extensions.json`

- [ ] **Step 1: Create .vscode directory**

Run: `mkdir -p .vscode`

- [ ] **Step 2: Create extensions.json**

```json
{
  "recommendations": [
    "astro-build.astro-vscode",
    "bradlc.vscode-tailwindcss",
    "esbenp.prettier-vscode"
  ]
}
```

- [ ] **Step 3: Commit VSCode config**

```bash
git add .vscode/
git commit -m "chore: add VSCode extension recommendations"
```

---

## Task 24: Build Verification

**Files:**
- Verify: Build succeeds
- Verify: All pages render

- [ ] **Step 1: Run development server**

Run: `npm run dev`
Expected: Server starts at http://localhost:4321

- [ ] **Step 2: Verify landing page loads**

Visit: http://localhost:4321
Expected: Landing page with all components renders correctly

- [ ] **Step 3: Verify docs page loads**

Visit: http://localhost:4321/docs/
Expected: Starlight documentation with sidebar renders

- [ ] **Step 4: Run production build**

Run: `npm run build`
Expected: Build completes without errors

- [ ] **Step 5: Preview production build**

Run: `npm run preview`
Expected: Static site serves correctly

- [ ] **Step 6: Final commit**

```bash
git add -A
git commit -m "feat: complete OntoClaw site implementation"
```

---

## Summary

| Phase | Tasks | Files Created |
|-------|-------|---------------|
| **1. Setup** | 1-4 | package.json, configs, styles, assets |
| **2. UI** | 5-6 | Layout, Button, Card |
| **3. Landing** | 7-16 | Header, Hero, all sections, index.astro |
| **4. Docs** | 17-22 | Starlight config, 5 MDX docs |
| **5. Verify** | 23-24 | VSCode config, build test |

**Total Files:** ~25 files
**Estimated Time:** 2-3 hours for careful execution
