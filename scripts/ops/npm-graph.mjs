import { existsSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { isDeepStrictEqual } from 'node:util';

const root = fileURLToPath(new URL('../../', import.meta.url));
const read = (relative) => JSON.parse(readFileSync(path.join(root, relative), 'utf8'));

export function checkManifests(rootManifest, frontendManifest, lock) {
  if (!Array.isArray(rootManifest.workspaces) || !rootManifest.workspaces.includes('apps/frontend') || lock.lockfileVersion !== 3) {
    throw new Error('The release requires the root npm workspace and lockfile version 3');
  }
  for (const [location, manifest] of [['', rootManifest], ['apps/frontend', frontendManifest]]) {
    const locked = lock.packages?.[location];
    if (!locked) throw new Error('The root lock is missing a declared workspace');
    for (const section of ['dependencies', 'devDependencies', 'optionalDependencies', 'peerDependencies']) {
      if (!isDeepStrictEqual(manifest[section] ?? {}, locked[section] ?? {})) {
        throw new Error(`Root lock and ${location || 'root'} ${section} differ; the frontend owner must reconcile the graph`);
      }
    }
  }
  const versionOf = (name) => lock.packages[`apps/frontend/node_modules/${name}`]?.version ?? lock.packages[`node_modules/${name}`]?.version ?? null;
  const engines = Number((versionOf('vite') ?? '').split('.')[0]) >= 8
    ? ['rolldown', 'lightningcss']
    : ['esbuild', 'rollup'];
  return Object.fromEntries(['vite', 'vitest', '@vitejs/plugin-react', 'typescript', ...engines, 'neonctl']
    .map((name) => [name, versionOf(name)]));
}

export async function verifyRegistryVersions(selected, lock, fetchMetadata = fetch) {
  for (const [name, version] of Object.entries(selected)) {
    const entry = lock.packages[`apps/frontend/node_modules/${name}`] ?? lock.packages[`node_modules/${name}`];
    if (!version || !entry?.integrity) throw new Error(`Missing locked version or integrity for ${name}`);
    const response = await fetchMetadata(`https://registry.npmjs.org/${encodeURIComponent(name)}/${encodeURIComponent(version)}`, {
      redirect: 'error', signal: AbortSignal.timeout(15000), headers: { Accept: 'application/json' },
    });
    if (!response.ok) throw new Error(`Public registry verification failed for ${name}`);
    const metadata = await response.json();
    if (metadata.name !== name || metadata.version !== version || metadata.dist?.integrity !== entry.integrity) {
      throw new Error(`Public registry version or integrity differs from the lock for ${name}`);
    }
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    if (process.argv.slice(2).some((argument) => argument !== '--registry')) throw new Error('Only --registry is supported');
    const registry = process.argv.includes('--registry');
    const lock = read('package-lock.json');
    const selected = checkManifests(read('package.json'), read('apps/frontend/package.json'), lock);
    if (registry) await verifyRegistryVersions(selected, lock);
    process.stdout.write(`${JSON.stringify({
      manifestConsistency: 'PASS', authoritativeLock: 'package-lock.json',
      nestedLockPresent: existsSync(path.join(root, 'apps/frontend/package-lock.json')),
      publicRegistry: registry ? 'PASS: selected versions and integrities match' : 'not requested',
      selected, scope: 'declared graph only; no install, audit, build or tooling-upgrade certification',
    }, null, 2)}\n`);
  } catch (error) {
    process.stderr.write(`npm graph blocked: ${error.message}\n`);
    process.exitCode = 1;
  }
}