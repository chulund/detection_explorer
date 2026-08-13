import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The API runs on 8000; the dev server proxies so the browser sees one origin.
export default defineConfig({
  plugins: [react()],
  // Both servers need the proxy: `server` covers `npm run dev`, `preview` covers
  // `npm run preview`, which serves the production build and is the honest way to check
  // behaviour without HMR in the picture.
  server: {
    port: 5173,
    proxy: { '/api': { target: 'http://localhost:8000', changeOrigin: true } },
  },
  preview: {
    port: 5199,
    proxy: { '/api': { target: 'http://localhost:8000', changeOrigin: true } },
  },
  test: { environment: 'node', include: ['src/**/*.test.js'] },
});
