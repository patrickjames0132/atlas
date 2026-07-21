/// <reference types="vitest/config" />
/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * Vite + Vitest configuration — the React plugin, the dev-server proxy to the
 * Flask API, and the test runner setup.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// During development the React dev server runs on :5173 and the Flask API on
// :5000. This proxy forwards any /api/* request to Flask so the frontend can
// just call "/api/papers" without worrying about ports or CORS.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:5000',
    },
  },
  // Vitest. The suite lives in test/ (mirroring src/, like the backend's
  // test/ mirrors src/atlas/) and is fully offline. Environment defaults to
  // node; component/hook tests opt into jsdom per file with a
  // `// @vitest-environment jsdom` docblock.
  test: {
    include: ['test/**/*.test.{ts,tsx}'],
  },
})
