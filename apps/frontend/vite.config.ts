import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  envDir: '../..',
  server: {
    port: 5173,
    host: true,
  },
  build: {
    // Base64-inlining a woff2 into the render-blocking stylesheet makes it
    // ~33% bigger (base64 of already-compressed data does not gzip) and
    // defeats unicode-range lazy loading. Always emit fonts as files.
    assetsInlineLimit: 0,
    rollupOptions: {
      output: {
        // Only vendors are split by hand. Route chunks come from the
        // React.lazy() boundaries in App.tsx: naming them here as well would
        // force them back into the entry's static graph, which makes Vite
        // emit a modulepreload + a render-blocking <link> for the dashboard
        // on the landing page — exactly what the lazy boundary exists to stop.
        manualChunks(id) {
          if (id.includes('node_modules/react') || id.includes('node_modules/react-dom')) {
            return 'vendor-react';
          }
          if (id.includes('node_modules/lucide-react')) {
            return 'vendor-icons';
          }
        },
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './tests/setup.ts',
    css: false,
  },
});
