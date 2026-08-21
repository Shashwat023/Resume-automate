import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],

  server: {
    host: true,
    port: 5173,

    // Allow Cloudflare Tunnel domains
    allowedHosts: [
      '.trycloudflare.com',
    ],

    /**
     * Dev proxy — forwards /api/* requests to the FastAPI backend.
     * This avoids CORS issues during local development since the browser
     * will hit localhost:5173 for everything.
     *
     * In production, configure your reverse proxy (nginx / Caddy) instead.
     */
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
      },
      '/storage': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
      },
    },
  },
});