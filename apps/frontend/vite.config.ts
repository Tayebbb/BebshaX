import { configDefaults, defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  envDir: process.env.BEBSHAX_FRONTEND_VERIFY === '1' ? path.resolve(__dirname, '.tmp/verification-env') : '../..',
  server: {
    port: 5173,
    host: '127.0.0.1',
    strictPort: true,
  },
  preview: {
    host: '127.0.0.1',
    strictPort: true,
  },
  build: {
    // Base64-inlining a woff2 into the render-blocking stylesheet makes it
    // ~33% bigger (base64 of already-compressed data does not gzip) and
    // defeats unicode-range lazy loading. Always emit fonts as files.
    assetsInlineLimit: 0,
    rolldownOptions: {
      output: {
        // Only React is split by hand. Route chunks come from the
        // React.lazy() boundaries in App.tsx: naming them here as well would
        // force them back into the entry's static graph, which makes Vite
        // emit a modulepreload + a render-blocking <link> for the dashboard
        // on the landing page — exactly what the lazy boundary exists to stop.
        // Icons stay with the route that renders them: one shared icon chunk
        // was preloaded on the landing page for every dashboard route's icons.
        codeSplitting: {
          groups: [{
            name(id: string): string | null {
              if (id.includes('node_modules/react') || id.includes('node_modules/react-dom')) {
                return 'vendor-react';
              }
              return null;
            },
          }],
        },
      },
    },
  },
  test: {
    exclude: [...configDefaults.exclude, '**/.tsupgrader/**'],
    globals: true,
    environment: 'jsdom',
    setupFiles: './tests/setup.ts',
    css: false,
  },
});
