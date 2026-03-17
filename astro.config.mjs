import { defineConfig } from 'astro/config';
import tailwind from '@astrojs/tailwind';
import starlight from '@astrojs/starlight';

export default defineConfig({
  integrations: [
    starlight({
      title: 'OntoClaw',
      description: 'Graph-aware AI validation framework',
      disable404Route: true,
      sidebar: [
        { label: 'Overview', slug: 'overview' },
        { label: 'Getting Started', slug: 'getting-started' },
      ],
    }),
    tailwind(),
  ],
  output: 'static',
  site: 'https://ontoclaw.marea.software',
});
