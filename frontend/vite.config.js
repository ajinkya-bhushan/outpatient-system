import { defineConfig } from 'vite';

const port = Number(process.env.PORT || 10100);

export default defineConfig({
  server: {
    host: '0.0.0.0',
    port,
    strictPort: true,
    allowedHosts: true,
  },
  preview: {
    host: '0.0.0.0',
    port,
    strictPort: true,
    allowedHosts: true,
  },
});
