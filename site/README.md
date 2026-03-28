# OntoSkills Site

Static site and documentation for [ontoskills.sh](https://ontoskills.sh).

## Pages

| Route | Description |
|-------|-------------|
| `/` | Landing page (Hero, Problem/Solution, Products, Roadmap, CTA) |
| `/how-it-works` | Define → Compile → Query → Execute walkthrough |
| `/ontostore` | Live OntoStore browser — fetches skills from the official store index |
| `/docs/*` | Starlight documentation (EN + ZH) |

## Tech Stack

| Technology | Purpose |
|------------|---------|
| [Astro 5](https://astro.build/) | Static site generator |
| [Starlight](https://starlight.astro.build/) | Documentation framework |
| [Tailwind CSS](https://tailwindcss.com/) | Utility-first styling |
| [Mermaid](https://mermaid.js.org/) | Diagram rendering in docs |

## i18n

Bilingual support via Starlight locales and custom translation dictionaries in `src/i18n/translations.ts`:

- **English** (`en`) — default locale
- **Chinese** (`zh`)

## Project Structure

```
site/
├── public/              # Static assets (images, robots.txt)
├── src/
│   ├── assets/          # Logo and image imports
│   ├── components/
│   │   ├── landing/     # Hero, Header, Footer, CTA, Products, etc.
│   │   ├── store/       # OntoStore browser component
│   │   └── ui/          # Reusable Button, Card, CommandSnippet
│   ├── content/
│   │   └── docs/        # Starlight docs source (en/ + zh/)
│   ├── data/            # Store index URLs
│   ├── i18n/            # Translation dictionaries
│   ├── layouts/         # LandingLayout
│   ├── pages/           # Astro pages (landing, ontostore, i18n routes)
│   └── styles/          # Global CSS, Starlight theme overrides
├── astro.config.mjs     # Astro + Starlight + Tailwind config
└── tailwind.config.mjs  # OntoSkills design system colors and fonts
```

## Commands

```bash
npm install
npm run dev       # Dev server
npm run build     # Production build
npm run preview   # Preview production build
```

## Requirements

- Node.js >= 22

## Deployment

Static output, compatible with Vercel, Netlify, or Cloudflare Pages.

## License

© 2026 [Marea Software](https://marea.software)
