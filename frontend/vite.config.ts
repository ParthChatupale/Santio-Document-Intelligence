import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';

export default defineConfig(({ command }) => ({
  root: fileURLToPath(new URL('.', import.meta.url)),
  base: command === 'build' ? '/static/react/' : '/',
  plugins: [react()],
  server: {
    host: '127.0.0.1', port: 5173, strictPort: true,
    proxy: Object.fromEntries(['/api', '/static/vendor'].map(path => [path, {
      target: `http://127.0.0.1:${process.env.SANTIO_API_PORT || 8766}`,
      changeOrigin: false,
    }])),
  },
  build: {
    outDir: fileURLToPath(new URL('../src/pbl_docintel/gui/static/react', import.meta.url)),
    emptyOutDir: true,
  },
}));
