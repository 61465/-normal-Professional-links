import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In production on GitHub Pages we are served under /professional-links/.
// Locally and on Cloudflare/Vercel we serve from /.
const base = process.env.VITE_BASE || '/'

export default defineConfig({
  base,
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8001',
        changeOrigin: true,
      },
    },
  },
})
