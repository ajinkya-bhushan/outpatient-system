import { defineConfig } from 'vite';

const port = Number(process.env.PORT || 10100);
const apiTarget = process.env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:10200';

export default defineConfig({
  server: {
    host: '0.0.0.0',
    port,
    strictPort: true,
    allowedHosts: true,
    proxy: {
      '/api': { target: apiTarget, changeOrigin: true },
    },
  },
  preview: {
    host: '0.0.0.0',
    port,
    strictPort: true,
    allowedHosts: true,
    proxy: {
      '/api': { target: apiTarget, changeOrigin: true },
    },
  },
});
