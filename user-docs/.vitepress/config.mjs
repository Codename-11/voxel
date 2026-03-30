import { defineConfig } from 'vitepress'

export default defineConfig({
  title: 'Voxel Docs',
  description: 'Documentation for the Voxel AI companion device',
  cleanUrls: true,

  appearance: 'dark',

  head: [
    ['meta', { name: 'theme-color', content: '#00D4D2' }],
    ['link', { rel: 'icon', type: 'image/svg+xml', href: '/logo.svg' }],
  ],

  themeConfig: {
    logo: '/logo.svg',

    nav: [
      { text: 'Guide', link: '/guide/quick-start' },
      { text: 'CLI Reference', link: '/guide/cli-reference' },
    ],

    sidebar: [
      {
        text: 'Getting Started',
        items: [
          { text: 'Quick Start', link: '/guide/quick-start' },
          { text: 'Pi Setup', link: '/guide/pi-setup' },
          { text: 'WiFi Setup', link: '/guide/wifi-setup' },
        ],
      },
      {
        text: 'Configuration',
        items: [
          { text: 'Configuration', link: '/guide/configuration' },
          { text: 'CLI Reference', link: '/guide/cli-reference' },
        ],
      },
      {
        text: 'Development',
        items: [
          { text: 'Dev Workflow', link: '/guide/dev-workflow' },
          { text: 'Display Architecture', link: '/guide/display-architecture' },
        ],
      },
      {
        text: 'Reference',
        items: [
          { text: 'Troubleshooting', link: '/guide/troubleshooting' },
          { text: 'Hardware', link: '/guide/hardware' },
        ],
      },
    ],

    socialLinks: [
      { icon: 'github', link: 'https://github.com/Codename-11/voxel' },
    ],

    outline: {
      level: [2, 3],
    },

    search: {
      provider: 'local',
    },

    footer: {
      message: 'Built by Axiom Labs',
    },
  },

  vite: {
    css: {
      preprocessorOptions: {},
    },
  },
})
