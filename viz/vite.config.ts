import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Static SPA. Build emits to `dist/`; host anywhere (GitHub Pages, Vercel, `python -m http.server dist/`).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Relative base so the build runs from any path (file://, /tripwire/, etc.)
  base: './',
  build: {
    target: 'es2022',
    sourcemap: false,
  },
})
