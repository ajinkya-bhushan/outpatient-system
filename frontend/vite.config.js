import { defineConfig } from 'vite';

const port = Number(process.env.PORT || 5173);
const apiTarget = process.env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:18000';

const host = process.env.HOST || '127.0.0.1';

export default defineConfig({
  server: {
    host,
    port,
    strictPort: true,
    allowedHosts: true,
    proxy: {
      '/api': { target: apiTarget, changeOrigin: true },
    },
  },
  preview: {
    host,
    port,
    strictPort: true,
    allowedHosts: true,
    proxy: {
      '/api': { target: apiTarget, changeOrigin: true },
    },
  },
});
