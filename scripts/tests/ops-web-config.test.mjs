import assert from 'node:assert/strict';
import test from 'node:test';
import { contentSecurityPolicy, publicOrigin, validateVercel, vercelConfig } from '../ops/web-config.mjs';

test('disabled federation keeps connection policy same-origin', () => {
  assert.match(contentSecurityPolicy(), /connect-src 'self';/);
  assert.equal(contentSecurityPolicy().includes('googleusercontent'), false);
});

test('configured federation allows exactly the tenant origin, not every Neon host', () => {
  const policy = contentSecurityPolicy('https://tenant.neonauth.example.test/project/auth');
  assert.match(policy, /connect-src 'self' https:\/\/tenant\.neonauth\.example\.test;/);
  assert.equal(policy.includes('*'), false);
});

for (const target of ['http://tenant.example.test', 'https://*.neon.tech', 'https://user:password@example.test',
  'https://127.0.0.1', 'https://localhost', 'https://[::1]', 'https://10.1.2.3', 'https://tenant.example.test/?token=bad',
  'https://tenant.example.test;bad', "https://tenant.example.test/'bad", 'https://tenant.example.test:8443']) {
  test(`rejects unsafe public target ${target.replace('user:password', 'credentials')}`, () => {
    assert.throws(() => publicOrigin(target));
  });
}

test('Vercel proxies API before the SPA fallback using the root workspace install', () => {
  const config = vercelConfig('https://api.example.test', 'https://tenant.example.test/auth');
  assert.equal(config.rewrites[0].destination, 'https://api.example.test/api/:path*');
  assert.equal(config.installCommand, 'npm ci --workspaces --include-workspace-root');
  validateVercel(config, 'https://tenant.example.test/auth');
});

test('Vercel refuses an unconfigured hosted API or a mismatched auth build', () => {
  assert.throws(() => validateVercel({ rewrites: [{ source: '/(.*)', destination: '/index.html' }] }));
  assert.throws(() => validateVercel(vercelConfig('https://api.example.test'), 'https://tenant.example.test/auth'));
});