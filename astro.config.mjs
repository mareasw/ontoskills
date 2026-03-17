import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import tailwind from '@astrojs/tailwind';
import rehypeMermaid from 'rehype-mermaid';

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
    rehypePlugins: [rehypeMermaid],
  },
  output: 'static',
  site: 'https://ontoclaw.marea.software',
});
