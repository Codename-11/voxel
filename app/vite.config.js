import { defineConfig } from 'vite'
import path from 'path'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    // Trigger HMR when shared YAML files change
    {
      name: 'watch-shared-yaml',
      configureServer(server) {
        const sharedDir = path.resolve(__dirname, '../shared')
        server.watcher.add(sharedDir)
        server.watcher.on('change', (file) => {
          if (file.endsWith('.yaml') && file.includes('shared')) {
            // Invalidate any module that imported the YAML via ?raw
            const mods = server.moduleGraph.getModulesByFile(file)
            if (mods) {
              mods.forEach((mod) => server.moduleGraph.invalidateModule(mod))
            }
            server.ws.send({ type: 'full-reload' })
          }
        })
      },
    },
  ],
  // Allow importing from ../shared (outside the project root)
  server: {
    watch: {
      // Ensure Vite's file watcher covers the shared directory
      ignored: ['!**/shared/**'],
    },
  },
})
