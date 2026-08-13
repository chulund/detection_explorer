import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The API runs on 8000; the dev server proxies so the browser sees one origin.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': { target: 'http://localhost:8000', changeOrigin: true } },
  },
  test: { environment: 'node', include: ['src/**/*.test.js'] },
});
