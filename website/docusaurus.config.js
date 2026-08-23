// @ts-check
// `@type` JSDoc annotations allow editor autocompletion and type checking
// (when paired with `@ts-check`).
// There are various equivalent ways to declare your Docusaurus config.
// See: https://docusaurus.io/docs/api/docusaurus-config

import {themes as prismThemes} from 'prism-react-renderer';

// This runs in Node.js - Don't use client-side code here (browser APIs, JSX...)

/** @type {import('@docusaurus/types').Config} */
const config = {
  title: 'TaskSAT',
  tagline: 'A DSL and SMT-based verifier for task scheduling with temporal and resource constraints',
  favicon: 'img/favicon.ico',

  // Future flags, see https://docusaurus.io/docs/api/docusaurus-config#future
  future: {
    v4: true, // Improve compatibility with the upcoming Docusaurus v4
  },

  // Set the production url of your site here
  url: 'https://nasa-jpl.github.io',
  // Set the /<baseUrl>/ pathname under which your site is served
  // For GitHub pages deployment, it is often '/<projectName>/'
  baseUrl: '/tasksat/',

  // GitHub pages deployment config.
  organizationName: 'nasa-jpl', // GitHub org/user name.
  projectName: 'tasksat', // Repo name.
  trailingSlash: false,

  onBrokenLinks: 'throw',

  // Treat .md files as CommonMark (not MDX) so existing docs with angle-bracket
  // placeholders like <name> and brace snippets don't get parsed as JSX.
  markdown: {
    format: 'detect',
    hooks: {
      onBrokenMarkdownLinks: 'warn',
    },
  },

  // Even if you don't use internationalization, you can use this field to set
  // useful metadata like html lang. For example, if your site is Chinese, you
  // may want to replace "en" with "zh-Hans".
  i18n: {
    defaultLocale: 'en',
    locales: ['en'],
  },

  presets: [
    [
      'classic',
      /** @type {import('@docusaurus/preset-classic').Options} */
      ({
        docs: {
          sidebarPath: './sidebars.js',
          routeBasePath: 'docs',
          editUrl:
            'https://github.com/nasa-jpl/tasksat/tree/main/website/',
        },
        blog: false,
        theme: {
          customCss: './src/css/custom.css',
        },
      }),
    ],
  ],

  themeConfig:
    /** @type {import('@docusaurus/preset-classic').ThemeConfig} */
    ({
      // Replace with your project's social card
      image: 'img/docusaurus-social-card.jpg',
      colorMode: {
        respectPrefersColorScheme: true,
      },
      tableOfContents: {
        minHeadingLevel: 2,
        maxHeadingLevel: 4,
      },
      navbar: {
        title: 'TaskSAT',
        logo: {
          alt: 'TaskSAT Logo',
          src: 'img/logo.svg',
        },
        items: [
          {
            type: 'docSidebar',
            sidebarId: 'docsSidebar',
            position: 'left',
            label: 'Docs',
          },
          {
            // Sphinx API reference, generated into static/api/ by `npm run gen:api`.
            // `pathname://` emits a plain link instead of a client-side route, so
            // Docusaurus serves the static file and skips broken-link checking.
            to: 'pathname:///tasksat/api/',
            label: 'API',
            position: 'left',
            // Without this Docusaurus treats the pathname:// link as external
            // and opens a new tab; same-tab keeps the Back button working.
            target: '_self',
          },
          {
            href: 'https://github.com/nasa-jpl/tasksat',
            label: 'GitHub',
            position: 'right',
          },
        ],
      },
      footer: {
        style: 'dark',
        links: [
          {
            title: 'Docs',
            items: [
              {
                label: 'Getting Started',
                to: '/docs/getting-started',
              },
              {
                label: 'Tutorial',
                to: '/docs/tutorial',
              },
              {
                label: 'Manual',
                to: '/docs/manual',
              },
            ],
          },
          {
            title: 'More',
            items: [
              {
                label: 'GitHub',
                href: 'https://github.com/nasa-jpl/tasksat',
              },
              {
                label: 'MEXEC',
                href: 'https://ai.jpl.nasa.gov/public/projects/mexec/',
              },
            ],
          },
        ],
        copyright: `Copyright © ${new Date().getFullYear()} California Institute of Technology. Built with Docusaurus.`,
      },
      prism: {
        theme: prismThemes.github,
        darkTheme: prismThemes.dracula,
        additionalLanguages: ['ebnf'],
      },
    }),
};

export default config;
