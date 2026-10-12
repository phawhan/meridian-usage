import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The browser only ever calls /api; in dev Vite forwards it to FastAPI, so no CORS setup.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': process.env.API_URL ?? 'http://127.0.0.1:8000',
    },
  },
})
