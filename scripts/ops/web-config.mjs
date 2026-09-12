import { spawnSync } from 'node:child_process';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../../', import.meta.url));

export function publicOrigin(value) {
  if (typeof value !== 'string' || /[\s\\*'"<>;]/.test(value)) throw new Error('Invalid public HTTPS URL');
  const parsed = new URL(value);
  if (parsed.protocol !== 'https:' || parsed.username || parsed.password || parsed.search || parsed.hash || parsed.port) {
    throw new Error('Public targets require credential-free HTTPS on port 443');
  }
  if (!parsed.hostname.includes('.') || /^(localhost|127\.|0\.|10\.|192\.168\.|169\.254\.|172\.(1[6-9]|2\d|3[01])\.)/.test(parsed.hostname)
      || /^[\d.]+$/.test(parsed.hostname) || parsed.hostname.includes(':') || parsed.hostname.endsWith('.localhost')) {
    throw new Error('Public targets cannot be loopback, private addresses, or unqualified hosts');
  }
  return parsed.origin;
}

export function contentSecurityPolicy(neonAuthUrl = '') {
  const origin = neonAuthUrl ? ` ${publicOrigin(neonAuthUrl)}` : '';
  const avatars = neonAuthUrl ? ' https://lh3.googleusercontent.com' : '';
  return `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self' data:${avatars}; connect-src 'self'${origin}; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'${origin}`;
}

export function vercelConfig(apiOrigin, neonAuthUrl = '') {
  const origin = publicOrigin(apiOrigin);
  if (new URL(apiOrigin).pathname !== '/') throw new Error('API origin must not contain a path');
  return {
    framework: 'vite',
    installCommand: 'npm ci --workspaces --include-workspace-root',
    buildCommand: 'node scripts/ops/web-config.mjs build-vercel deploy/vercel.generated.json',
    outputDirectory: 'apps/frontend/dist',
    headers: [{ source: '/(.*)', headers: [
      { key: 'Content-Security-Policy', value: contentSecurityPolicy(neonAuthUrl) },
      { key: 'X-Content-Type-Options', value: 'nosniff' },
      { key: 'X-Frame-Options', value: 'DENY' },
      { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
      { key: 'Permissions-Policy', value: 'camera=(), microphone=(), geolocation=(), payment=(), usb=()' },
    ] }],
    rewrites: [
      { source: '/api/:path*', destination: `${origin}/api/:path*` },
      { source: '/((?!api(?:/|$)).*)', destination: '/index.html' },
    ],
  };
}

export function validateVercel(config, neonAuthUrl = '') {
  const route = config.rewrites?.find((entry) => entry.source === '/api/:path*');
  if (!route?.destination.endsWith('/api/:path*')) throw new Error('Hosted API routing is not configured');
  publicOrigin(route.destination.slice(0, -'/api/:path*'.length));
  const csp = config.headers?.flatMap((entry) => entry.headers).find((header) => header.key === 'Content-Security-Policy');
  if (csp?.value !== contentSecurityPolicy(neonAuthUrl)) throw new Error('Build-time Neon configuration and CSP differ');
}

function main() {
  const [operation, argument, output] = process.argv.slice(2);
  const neonAuthUrl = process.env.VITE_NEON_AUTH_URL ?? '';
  if (operation === 'nginx') {
    if (!argument || !output) throw new Error('nginx requires template and output paths');
    const template = readFileSync(argument, 'utf8');
    if (!template.includes('__BEBSHAX_CSP__')) throw new Error('Missing CSP template slot');
    writeFileSync(output, template.replaceAll('__BEBSHAX_CSP__', contentSecurityPolicy(neonAuthUrl)));
  } else if (operation === 'vercel') {
    const config = vercelConfig(argument, neonAuthUrl);
    mkdirSync(path.join(root, 'deploy'), { recursive: true });
    writeFileSync(path.join(root, 'deploy/vercel.generated.json'), `${JSON.stringify(config, null, 2)}\n`);
    process.stdout.write('Generated deploy/vercel.generated.json with an exact-origin policy. No deployment performed.\n');
  } else if (operation === 'build-vercel') {
    const config = JSON.parse(readFileSync(path.resolve(root, argument ?? 'vercel.json'), 'utf8'));
    validateVercel(config, neonAuthUrl);
    const npm = process.platform === 'win32' ? 'npm.cmd' : 'npm';
    const result = spawnSync(npm, ['run', 'build', '--workspace', 'apps/frontend'], {
      cwd: root, stdio: 'inherit', shell: process.platform === 'win32', env: { ...process.env, VITE_API_BASE: '/api' },
    });
    process.exitCode = result.status ?? 1;
  } else {
    throw new Error('Use nginx TEMPLATE OUTPUT, vercel PUBLIC_API_ORIGIN, or build-vercel CONFIG');
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try { main(); } catch (error) {
    process.stderr.write(`Web configuration failed: ${error.message}\n`);
    process.exitCode = 1;
  }
}