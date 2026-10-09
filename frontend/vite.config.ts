import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';
import { cpSync } from 'node:fs';

export default defineConfig(({ command, mode }) => {
  const hosted = mode === 'vercel';
  const outDir = fileURLToPath(new URL(hosted ? '../dist/vercel' : '../src/pbl_docintel/gui/static/react', import.meta.url));
  return {
    root: fileURLToPath(new URL('.', import.meta.url)),
    base: command === 'build' && !hosted ? '/static/react/' : '/',
    plugins: [react(), ...(hosted ? [{
      name: 'santio-pdfjs-assets',
      apply: 'build' as const,
      closeBundle() {
        cpSync(fileURLToPath(new URL('../src/pbl_docintel/gui/static/vendor', import.meta.url)),
          `${outDir}/static/vendor`, { recursive: true });
      },
    }] : [])],
    server: {
      host: '127.0.0.1', port: 5173, strictPort: true,
      proxy: Object.fromEntries(['/api', '/static/vendor'].map(path => [path, {
        target: `http://127.0.0.1:${process.env.SANTIO_API_PORT || 8766}`,
        changeOrigin: false,
      }])),
    },
    build: {
      outDir,
      emptyOutDir: true,
    },
  };
});
