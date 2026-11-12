import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// The browser talks only to the Vite server. It forwards /api to the backend, so the
// session cookie belongs to a single origin and no cross-origin (CORS) setup is needed.
const apiTarget = process.env.WORKLEDGER_API_URL ?? 'http://localhost:8000'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': apiTarget,
    },
  },
  test: {
    environment: 'jsdom',
    testTimeout: 15000,
    // Role queries are CPU heavy. Fewer workers than cores kept timing out tests from
    // starving each other, and it is also faster overall.
    maxWorkers: 2,
    setupFiles: ['./src/test/setup.ts'],
  },
})
