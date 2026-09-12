import { createServer } from 'vite';
import react from '@vitejs/plugin-react';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const frontend = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const server = await createServer({
  root: frontend,
  configFile: false,
  envFile: false,
  envDir: resolve(frontend, '.tmp/mock-env'),
  plugins: [react(), {
    name: 'mock-only-api-boundary',
    configureServer(instance) {
      instance.middlewares.use('/api', (_request, response) => {
        response.statusCode = 503;
        response.setHeader('Content-Type', 'application/json');
        response.end(JSON.stringify({ detail: 'MOCK preview: live API calls are disabled' }));
      });
    },
  }],
  define: {
    'import.meta.env.VITE_MOCK': JSON.stringify('1'),
    'import.meta.env.VITE_NEON_AUTH_URL': JSON.stringify(''),
    'import.meta.env.VITE_API_BASE': JSON.stringify('http://127.0.0.1:5194/api'),
  },
  resolve: { alias: { '@': resolve(frontend, 'src') } },
  server: {
    host: '127.0.0.1', port: 5194, strictPort: true,
    fs: { strict: true, allow: [frontend, resolve(frontend, '../../node_modules')], deny: ['.env', '.env.*', '.npmrc', '.netrc', '*.{crt,pem}', '**/.git/**'] },
  },
});
await server.listen();
process.stdout.write('MOCK ONLY: http://127.0.0.1:5194 - synthetic fixtures, no live API or environment files\n');
const close = async () => { await server.close(); process.exit(0); };
process.once('SIGINT', () => { void close(); });
process.once('SIGTERM', () => { void close(); });