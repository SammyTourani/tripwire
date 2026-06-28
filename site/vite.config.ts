import { defineConfig } from 'vite'
import { tanstackStart } from '@tanstack/react-start/plugin/vite'
import viteReact from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Deployed as a static, prerendered site on GitHub Pages at
// https://sammytourani.github.io/tripwire/ — hence the subpath base and the
// static prerender of the single landing route.
export default defineConfig({
  base: '/tripwire/',
  server: {
    port: 3000,
  },
  plugins: [
    tailwindcss(),
    tanstackStart({
      prerender: {
        enabled: true,
        crawlLinks: false,
        failOnError: true,
      },
    }),
    // react's vite plugin must come after start's vite plugin
    viteReact(),
  ],
})
