import { defineConfig } from 'astro/config';
import tailwind from '@astrojs/tailwind';
import starlight from '@astrojs/starlight';

export default defineConfig({
  integrations: [
    starlight({
      title: 'OntoClaw',
      description: 'Neuro-symbolic skill compiler for the Agentic Web',
      disable404Route: true,
      customCss: ['./src/styles/starlight.css'],
      sidebar: [
        { label: 'Overview', slug: 'overview' },
        { label: 'Getting Started', slug: 'getting-started' },
        { label: 'Roadmap', slug: 'roadmap' },
      ],
    }),
    tailwind(),
  ],
  output: 'static',
  site: 'https://ontoclaw.marea.software',
});
