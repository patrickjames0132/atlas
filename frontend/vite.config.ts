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
})
