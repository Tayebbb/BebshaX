import assert from 'node:assert/strict';
import test from 'node:test';
import { checkManifests, verifyRegistryVersions } from '../ops/npm-graph.mjs';

test('accepts the root graph without relying on any nested lock', () => {
  const root = { workspaces: ['apps/frontend'], dependencies: { rootDependency: '^1' } };
  const frontend = { dependencies: { vite: '^7' } };
  const lock = { lockfileVersion: 3, packages: { '': root, 'apps/frontend': frontend, 'node_modules/vite': { version: '7.3.5' } } };
  assert.equal(checkManifests(root, frontend, lock).vite, '7.3.5');
});

test('rejects a frontend manifest updated without reconciling the root graph', () => {
  const root = { workspaces: ['apps/frontend'] };
  const lock = { lockfileVersion: 3, packages: { '': root, 'apps/frontend': { dependencies: { vite: '^5' } } } };
  assert.throws(() => checkManifests(root, { dependencies: { vite: '^7' } }, lock));
});

test('rejects a missing workspace graph instead of falling back to a nested lock', () => {
  assert.throws(() => checkManifests({ workspaces: ['apps/frontend'] }, {}, { lockfileVersion: 3, packages: { '': {} } }));
});

test('registry verification checks exact version and integrity without credentials or redirect following', async () => {
  const lock = { packages: { 'node_modules/vite': { version: '7.3.5', integrity: 'sha512-synthetic-fixture' } } };
  const calls = [];
  await verifyRegistryVersions({ vite: '7.3.5' }, lock, async (url, options) => {
    calls.push(url);
    assert.equal(options.redirect, 'error');
    assert.deepEqual(options.headers, { Accept: 'application/json' });
    assert.ok(options.signal instanceof AbortSignal);
    return { ok: true, json: async () => ({ name: 'vite', version: '7.3.5', dist: { integrity: 'sha512-synthetic-fixture' } }) };
  });
  assert.deepEqual(calls, ['https://registry.npmjs.org/vite/7.3.5']);
});

test('registry verification rejects missing pins, HTTP errors and mismatched package metadata', async () => {
  const lock = { packages: { 'node_modules/vite': { version: '7.3.5', integrity: 'sha512-synthetic-fixture' } } };
  await assert.rejects(verifyRegistryVersions({ vite: null }, lock, () => assert.fail('Missing pins must not reach the registry')));
  await assert.rejects(verifyRegistryVersions({ vite: '7.3.5' }, lock, async () => ({ ok: false })));
  for (const metadata of [
    { name: 'another-package', version: '7.3.5', dist: { integrity: 'sha512-synthetic-fixture' } },
    { name: 'vite', version: '7.3.6', dist: { integrity: 'sha512-synthetic-fixture' } },
    { name: 'vite', version: '7.3.5', dist: { integrity: 'sha512-different-fixture' } },
  ]) {
    await assert.rejects(verifyRegistryVersions({ vite: '7.3.5' }, lock, async () => ({ ok: true, json: async () => metadata })));
  }
});